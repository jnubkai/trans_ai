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

try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
except ImportError:
    st.error("streamlit-webrtc 라이브러리 설치가 필요함.")
    st.stop()

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 자동 통역")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
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

# 4. 세션 상태
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
    en_box = st.empty()
    en_box.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "음성 대기 중..."}</div>', unsafe_allow_html=True)
with col2:
    st.markdown("### 🇰🇷 한국어")
    ko_box = st.empty()
    ko_box.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "번역 대기 중..."}</div>', unsafe_allow_html=True)

# 7. 오디오 데이터 전송용 큐
audio_queue = queue.Queue()

class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        # 마이크에서 오디오 원시 데이터(Raw PCM) 추출
        audio_data = frame.to_ndarray().tobytes()
        audio_queue.put(audio_data)
        return frame

# 8. AssemblyAI WebSocket 및 번역 비동기 처리
async def assemblyai_stt_loop():
    auth_header = {"Authorization": ASSEMBLY_KEY}
    # 실시간 다국어 감지 모드로 접속
    url = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000&multilingual=true"
    
    try:
        async with websockets.connect(url, extra_headers=auth_header) as ws:
            async def send_audio():
                while True:
                    data = await asyncio.get_event_loop().run_in_executor(None, audio_queue.get)
                    msg = json.dumps({"audio_data": base64.b64encode(data).decode("utf-8")})
                    await ws.send(msg)
                    await asyncio.sleep(0.01)

            async def receive_text():
                while True:
                    result_str = await ws.recv()
                    result = json.loads(result_str)
                    
                    # 최종 인식 결과(Final Transcript)가 나왔을 때만 처리
                    if result.get("message_type") == "FinalTranscript" and result.get("text"):
                        raw_text = result["text"]
                        
                        # Gemini 번역/정제 수행
                        en_out = llm.invoke([HumanMessage(content=f"Fix and formalize this as English lecture transcript: {raw_text}")]).content
                        ko_out = llm.invoke([HumanMessage(content=f"Translate this to natural Korean lecture tone: {raw_text}")]).content
                        
                        st.session_state['en_text_list'].append(en_out)
                        st.session_state['ko_text_list'].append(ko_out)
                        
                        # UI 갱신 유도
                        st.rerun()

            await asyncio.gather(send_audio(), receive_text())
    except:
        pass

# 9. 마이크 스트리머 실행
st.divider()
webrtc_ctx = webrtc_streamer(
    key="translator",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

# 스트리밍 중일 때 백그라운드에서 STT 루프 실행
if webrtc_ctx.state.playing:
    st.success("🎤 실시간 통역 엔진 가동 중")
    # Streamlit Cloud 환경에서 비동기 루프를 유지하기 위해 스레드 사용 고려 가능
    # 여기서는 간단히 루프 안내만 표시 (실제 배포 시 백엔드 워커 연동 필요)
else:
    st.info("시작하려면 위 START 버튼을 눌러.")
