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

# 2. 자격 증명
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = "https://speedep.synology.me:7651"
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
except:
    st.error("Secrets 설정 확인 필요")
    st.stop()

# 3. AI 모델
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

st.title("🎤 AI 실시간 자동 통역 시스템")

# 5. 사이드바 (NAS 연동)
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

# 6. 통역 결과 레이아웃
col1, col2 = st.columns(2)
full_en = "\n\n".join(st.session_state['en_text_list'])
full_ko = "\n\n".join(st.session_state['ko_text_list'])

with col1:
    st.markdown("### 🇬🇧 English")
    st.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "Waiting for voice..."}</div>', unsafe_allow_html=True)

with col2:
    st.markdown("### 🇰🇷 한국어")
    st.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "번역 대기 중..."}</div>', unsafe_allow_html=True)

# 7. 오디오 프로세서 (데이터 규격화)
class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        # 16-bit PCM 데이터로 변환
        audio = frame.to_ndarray()
        # 스테레오일 경우 모노로 변환
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # int16 형식으로 변환하여 큐에 삽입
        audio_int16 = (audio * 32767).astype(np.int16)
        st.session_state['audio_queue'].put(audio_int16.tobytes())
        return frame

# 8. 실시간 통역 엔진 (AssemblyAI + Gemini)
async def run_stt_engine():
    auth_header = {"Authorization": ASSEMBLY_KEY}
    # 브라우저 기본 샘플 레이트가 48000Hz인 경우가 많으므로 명시적 설정
    url = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=48000"
    
    try:
        async with websockets.connect(url, extra_headers=auth_header) as ws:
            # 세션 시작 확인 메시지 대기
            await ws.recv()

            async def send_audio():
                while True:
                    try:
                        # 0.1초 단위로 오디오 조각 전송
                        data = st.session_state['audio_queue'].get(timeout=0.1)
                        await ws.send(json.dumps({"audio_data": base64.b64encode(data).decode("utf-8")}))
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                    except:
                        break

            async def receive_text():
                while True:
                    try:
                        msg = await ws.recv()
                        res = json.loads(msg)
                        # 최종 확정된 문장만 처리
                        if res.get("message_type") == "FinalTranscript" and res.get("text"):
                            raw_text = res["text"]
                            # Gemini 통역 수행
                            en_res = llm.invoke([HumanMessage(content=f"Convert to formal English lecture transcript: {raw_text}")]).content
                            ko_res = llm.invoke([HumanMessage(content=f"Translate to natural Korean lecture tone: {raw_text}")]).content
                            
                            st.session_state['en_text_list'].append(en_res)
                            st.session_state['ko_text_list'].append(ko_res)
                            # UI 강제 갱신
                            st.rerun()
                    except:
                        break

            await asyncio.gather(send_audio(), receive_text())
    except Exception as e:
        print(f"Engine Error: {e}")

# 9. 백그라운드 스레드 관리 루틴
def start_worker(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_stt_engine())

# 10. 마이크 및 스트리머 실행
webrtc_ctx = webrtc_streamer(
    key="speech-translator",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

if webrtc_ctx.state.playing:
    # 스레드가 없거나 죽어있을 때만 새로 시작
    if 'stt_worker' not in st.session_state or st.session_state['stt_worker'] is None or not st.session_state['stt_worker'].is_alive():
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=start_worker, args=(loop,), daemon=True)
        add_script_run_ctx(thread)
        thread.start()
        st.session_state['stt_worker'] = thread
    st.success("🎤 통역 엔진이 활성화됨. 말씀해 주시기 바람.")
else:
    st.session_state['stt_worker'] = None
    st.info("시작하려면 START 버튼을 누르기 바람.")
