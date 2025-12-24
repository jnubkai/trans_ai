import streamlit as st
import requests
import json
import asyncio
import queue
import threading
import base64
import websockets
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from streamlit.runtime.scriptrunner import add_script_run_ctx

try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
except ImportError:
    st.error("streamlit-webrtc 라이브러리 설치가 필요함.")
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
    st.error("Secrets 설정 확인 필요.")
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

st.title("🎤 AI 실시간 자동 통역 시스템")

# 5. 사이드바 (NAS)
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

# 6. 통역 표시 레이아웃
col1, col2 = st.columns(2)
full_en = "\n\n".join(st.session_state['en_text_list'])
full_ko = "\n\n".join(st.session_state['ko_text_list'])

with col1:
    st.markdown("### 🇬🇧 English")
    st.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "음성 대기 중..."}</div>', unsafe_allow_html=True)
with col2:
    st.markdown("### 🇰🇷 한국어")
    st.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "번역 대기 중..."}</div>', unsafe_allow_html=True)

# 7. 오디오 큐 및 프로세서
if 'audio_queue' not in st.session_state:
    st.session_state['audio_queue'] = queue.Queue()

class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        # 16bit PCM, 16000Hz 가공 데이터 추출
        audio_data = frame.to_ndarray().tobytes()
        st.session_state['audio_queue'].put(audio_data)
        return frame

# 8. 실시간 STT 및 번역 루프
async def start_stt_stream():
    auth_header = {"Authorization": ASSEMBLY_KEY}
    # 멀티링구얼 대신 수동 언어 지정 혹은 자동 감지 옵션 정교화
    url = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000"
    
    try:
        async with websockets.connect(url, extra_headers=auth_header) as ws:
            # 초기화 메시지 수신 대기
            await ws.recv()

            async def send_audio():
                while True:
                    try:
                        # 큐에서 데이터를 가져와 전송
                        data = st.session_state['audio_queue'].get(timeout=0.2)
                        await ws.send(json.dumps({"audio_data": base64.b64encode(data).decode("utf-8")}))
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                    except:
                        break

            async def receive_text():
                while True:
                    try:
                        res = json.loads(await ws.recv())
                        if res.get("message_type") == "FinalTranscript" and res.get("text"):
                            text = res["text"]
                            # 번역 처리
                            en_res = llm.invoke([HumanMessage(content=f"Refine to formal English: {text}")]).content
                            ko_res = llm.invoke([HumanMessage(content=f"Translate to natural Korean: {text}")]).content
                            
                            # 세션 리스트 업데이트
                            st.session_state['en_text_list'].append(en_res)
                            st.session_state['ko_text_list'].append(ko_res)
                            # 강제 리런 (백그라운드에서 실행되므로 트리거 필요)
                            st.rerun()
                    except:
                        break

            await asyncio.gather(send_audio(), receive_text())
    except Exception as e:
        print(f"WS Error: {e}")

# 9. 백그라운드 스레드 제어
def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_stt_stream())

# 10. WebRTC 스트리머
webrtc_ctx = webrtc_streamer(
    key="speech-to-text",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

if webrtc_ctx.state.playing:
    if 'stt_thread' not in st.session_state or st.session_state['stt_thread'] is None:
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=run_loop, args=(loop,), daemon=True)
        # 중요: 스레드에 Streamlit 컨텍스트 주입
        add_script_run_ctx(thread)
        thread.start()
        st.session_state['stt_thread'] = thread
    st.success("🎤 실시간 통역 중")
else:
    st.session_state['stt_thread'] = None
    st.info("START 버튼을 눌러 통역을 시작해.")
