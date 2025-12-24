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
        # 16kHz Mono로 변환된 데이터 추출 (AssemblyAI 권장 규격)
        audio_data = frame.to_ndarray().tobytes()
        audio_queue.put(audio_data)
        return frame

# 8. AssemblyAI WebSocket 및 번역 비동기 처리 함수
async def start_stt_stream():
    auth_header = {"Authorization": ASSEMBLY_KEY}
    url = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000&multilingual=true"
    
    async with websockets.connect(url, extra_headers=auth_header) as ws:
        # 최초 연결 시 대기
        await ws.recv() 

        async def send_audio():
            while True:
                try:
                    data = audio_queue.get(timeout=0.1)
                    msg = json.dumps({"audio_data": base64.b64encode(data).decode("utf-8")})
                    await ws.send(msg)
                except queue.Empty:
                    await asyncio.sleep(0.01)
                except Exception:
                    break

        async def receive_text():
            while True:
                try:
                    result_str = await ws.recv()
                    result = json.loads(result_str)
                    
                    if result.get("message_type") == "FinalTranscript" and result.get("text"):
                        raw_text = result["text"]
                        
                        # Gemini 번역 수행
                        en_out = llm.invoke([HumanMessage(content=f"Fix/Formalize English lecture: {raw_text}")]).content
                        ko_out = llm.invoke([HumanMessage(content=f"Translate to natural Korean lecture: {raw_text}")]).content
                        
                        st.session_state['en_text_list'].append(en_out)
                        st.session_state['ko_text_list'].append(ko_out)
                        # Streamlit의 상태 변경을 알리기 위해 빈 엘리먼트 갱신 시도 (혹은 rerun)
                except Exception:
                    break

        await asyncio.gather(send_audio(), receive_text())

# 9. 백그라운드 스레드 관리
def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_stt_stream())

if 'stt_thread' not in st.session_state:
    st.session_state['stt_thread'] = None

# 10. 마이크 스트리머 실행
st.divider()
webrtc_ctx = webrtc_streamer(
    key="translator",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

# 마이크가 켜졌을 때 스레드가 없으면 생성하여 실행
if webrtc_ctx.state.playing:
    if st.session_state['stt_thread'] is None or not st.session_state['stt_thread'].is_alive():
        new_loop = asyncio.new_event_loop()
        t = threading.Thread(target=run_async_loop, args=(new_loop,), daemon=True)
        t.start()
        st.session_state['stt_thread'] = t
    st.success("🎤 실시간 엔진 작동 중 - 마이크에 대고 말씀해 보세요.")
else:
    st.session_state['stt_thread'] = None
    st.info("시작하려면 위 START 버튼을 눌러.")
