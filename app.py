import streamlit as st
import requests
import json
import asyncio
import queue
import threading
import base64
import websockets
import numpy as np
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from streamlit.runtime.scriptrunner import add_script_run_ctx

try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
except ImportError:
    st.error("streamlit-webrtc 라이브러리 설치 필요")
    st.stop()

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 자동 통역")

st.markdown("""
    <style>
    .stInfo { font-size: 1.1rem; min-height: 400px; border-radius: 10px; padding: 15px; background-color: #e3f2fd; border-left: 5px solid #2196f3; }
    .stSuccess { font-size: 1.1rem; min-height: 400px; border-radius: 10px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #4caf50; }
    .transcript-box { height: 450px; overflow-y: auto; white-space: pre-wrap; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; font-family: 'Malgun Gothic', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# 2. 자격 증명 (Secrets 연동)
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = "https://speedep.synology.me:7651"
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
except:
    st.error("Secrets 설정 확인 필요 (GEMINI_KEY, ASSEMBLY_KEY 등)")
    st.stop()

# 3. AI 모델 (Gemini-1.5-Flash)
@st.cache_resource
def init_llm():
    try:
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
    except:
        return None

llm = init_llm()

# 4. 세션 상태 초기화
if 'en_text_list' not in st.session_state: st.session_state['en_text_list'] = []
if 'ko_text_list' not in st.session_state: st.session_state['ko_text_list'] = []
if 'folder_list' not in st.session_state: st.session_state['folder_list'] = []
if 'audio_queue' not in st.session_state: st.session_state['audio_queue'] = queue.Queue()
if 'stt_active' not in st.session_state: st.session_state['stt_active'] = False

st.title("🎤 AI 실시간 자동 통역 시스템")

# 5. 사이드바 (NAS 연동 및 기록 관리)
with st.sidebar:
    st.header("⚙️ NAS & System")
    use_ssl_verify = st.checkbox("SSL 인증서 검증", value=False)
    if st.button("📁 목록 업데이트", use_container_width=True):
        session = requests.Session()
        login_data = {"api": "SYNO.API.Auth", "version": "7", "method": "login", "account": SYNO_ID, "passwd": SYNO_PW, "session": "FileStation", "format": "sid"}
        try:
            auth_res = session.post(f"{SYNO_URL}/webapi/auth.cgi", data=login_data, timeout=20, verify=use_ssl_verify).json()
            if auth_res.get("success"):
                st.session_state['sid'] = auth_res["data"]["sid"]
                list_params = {"api": "SYNO.FileStation.List", "version": "2", "method": "list", "folder_path": "/RLRC/509 자료", "_sid": st.session_state['sid']}
                list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=20, verify=use_ssl_verify).json()
                if list_res.get("success"):
                    st.session_state['folder_list'] = sorted([f['name'] for f in list_res['data']['files'] if f.get('isdir')])
        except: st.error("NAS 연결 실패")
        finally: session.close()

    selected_subject = st.selectbox("🎯 주제", st.session_state['folder_list'] if st.session_state['folder_list'] else ["목록 없음"])
    if st.button("🧹 기록 초기화", use_container_width=True):
        st.session_state['en_text_list'], st.session_state['ko_text_list'] = [], []
        st.rerun()

# 6. 통역 결과 레이아웃 (실시간 업데이트 영역)
col1, col2 = st.columns(2)
en_area = col1.empty()
ko_area = col2.empty()

def update_ui():
    full_en = "\n\n".join(st.session_state['en_text_list'])
    full_ko = "\n\n".join(st.session_state['ko_text_list'])
    en_area.markdown(f'### 🇬🇧 English\n<div class="stInfo transcript-box">{full_en if full_en else "Listening..."}</div>', unsafe_allow_html=True)
    ko_area.markdown(f'### 🇰🇷 한국어\n<div class="stSuccess transcript-box">{full_ko if full_ko else "번역 대기 중..."}</div>', unsafe_allow_html=True)

update_ui()

# 7. 오디오 프로세서 (데이터 정규화 및 큐잉)
class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        # 마이크 프레임을 넘파이 배열로 변환
        audio = frame.to_ndarray()
        # 스테레오 -> 모노
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # float32 또는 int32 데이터를 int16(16bit PCM)으로 정규화
        if audio.dtype != np.int16:
            audio = (audio * 32767).astype(np.int16)
        
        # 바이너리 데이터를 큐에 삽입
        st.session_state['audio_queue'].put(audio.tobytes())
        return frame

# 8. 실시간 통역 엔진 (WebSocket)
async def translate_engine():
    auth_header = {"Authorization": ASSEMBLY_KEY}
    # 브라우저 기본 샘플 레이트가 높으므로 서버 설정을 44100Hz로 시도 (연결 실패 시 16000으로 강제 조정됨)
    url = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000"
    
    try:
        async with websockets.connect(url, extra_headers=auth_header) as ws:
            # 첫 번째 수신 메시지는 연결 승인 메시지임
            await ws.recv()

            async def send_audio_task():
                while True:
                    try:
                        # 큐에서 데이터를 비차단 방식으로 가져와 전송
                        data = st.session_state['audio_queue'].get_nowait()
                        msg = json.dumps({"audio_data": base64.b64encode(data).decode("utf-8")})
                        await ws.send(msg)
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                    except Exception:
                        break

            async def receive_text_task():
                while True:
                    try:
                        result_msg = await ws.recv()
                        result = json.loads(result_msg)
                        
                        # 최종 문장(FinalTranscript)만 캡처하여 Gemini로 전송
                        if result.get("message_type") == "FinalTranscript" and result.get("text"):
                            text = result["text"]
                            
                            # Gemini 통역 (속도를 위해 짧은 지침 사용)
                            en_res = llm.invoke([HumanMessage(content=f"Fix as formal English: {text}")]).content
                            ko_res = llm.invoke([HumanMessage(content=f"Translate to Korean lecture tone: {text}")]).content
                            
                            st.session_state['en_text_list'].append(en_res)
                            st.session_state['ko_text_list'].append(ko_res)
                            # UI 즉시 반영 트리거
                            st.rerun()
                    except Exception:
                        break

            await asyncio.gather(send_audio_task(), receive_text_task())
    except Exception as e:
        print(f"Engine Connection Lost: {e}")

# 9. 백그라운드 스레드 가동
def start_stt_thread(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(translate_engine())

# 10. WebRTC 스트리머 설정
st.divider()
webrtc_ctx = webrtc_streamer(
    key="speech-translator-v2",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={
        "audio": {
            "sampleRate": 16000,
            "channelCount": 1,
            "echoCancellation": True
        },
        "video": False
    },
    rtc_configuration={
        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
    },
)

# 마이크 실행 중일 때 스레드 감시 및 시작
if webrtc_ctx.state.playing:
    if 'stt_thread_obj' not in st.session_state or st.session_state['stt_thread_obj'] is None or not st.session_state['stt_thread_obj'].is_alive():
        new_loop = asyncio.new_event_loop()
        t = threading.Thread(target=start_stt_thread, args=(new_loop,), daemon=True)
        add_script_run_ctx(t) # Streamlit 컨텍스트 주입
        t.start()
        st.session_state['stt_thread_obj'] = t
    st.success("🎤 엔진 가동 완료 - 지금 말씀하세요.")
else:
    st.session_state['stt_thread_obj'] = None
    st.info("시작하려면 START 버튼을 눌러주세요.")
