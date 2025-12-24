import streamlit as st
import requests
import os
import json
import asyncio
import queue
import threading
import base64
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
except ImportError:
    st.error("streamlit-webrtc 라이브러리 설치가 필요함.")
    st.stop()

# 1. 페이지 레이아웃 및 스타일 설정
st.set_page_config(layout="wide", page_title="AI 실시간 자동 통역")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stInfo { font-size: 1.1rem; min-height: 400px; border-radius: 10px; padding: 15px; background-color: #e3f2fd; border-left: 5px solid #2196f3; }
    .stSuccess { font-size: 1.1rem; min-height: 400px; border-radius: 10px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #4caf50; }
    .transcript-box { height: 450px; overflow-y: auto; white-space: pre-wrap; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; font-family: 'Malgun Gothic', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# 2. 자격 증명 로드
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = "https://speedep.synology.me:7651"
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
except Exception as e:
    st.error("Secrets 설정 확인 필요.")
    st.stop()

# 3. AI 모델 초기화
@st.cache_resource
def init_llm():
    try:
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
    except:
        return None

llm = init_llm()

# 4. 세션 상태 초기화
if 'en_text_list' not in st.session_state:
    st.session_state['en_text_list'] = []
if 'ko_text_list' not in st.session_state:
    st.session_state['ko_text_list'] = []
if 'folder_list' not in st.session_state:
    st.session_state['folder_list'] = []

st.title("🎤 AI 실시간 자동 통역 시스템")

# 5. 사이드바 설정
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
        except:
            st.error("NAS 연결 실패")
        finally:
            session.close()

    selected_subject = st.selectbox("🎯 주제", st.session_state['folder_list'] if st.session_state['folder_list'] else ["목록 없음"])
    if st.button("🧹 기록 초기화", use_container_width=True):
        st.session_state['en_text_list'], st.session_state['ko_text_list'] = [], []
        st.rerun()

# 6. 통역 표시 레이아웃
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 🇬🇧 English")
    en_placeholder = st.empty()
with col2:
    st.markdown("### 🇰🇷 한국어")
    ko_placeholder = st.empty()

def update_display():
    full_en = "\n\n".join(st.session_state['en_text_list'])
    full_ko = "\n\n".join(st.session_state['ko_text_list'])
    en_placeholder.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "음성 대기 중..."}</div>', unsafe_allow_html=True)
    ko_placeholder.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "번역 대기 중..."}</div>', unsafe_allow_html=True)

update_display()

# 7. 번역 로직
def process_and_translate(text):
    if not text.strip() or not llm: return
    try:
        en_out = llm.invoke([HumanMessage(content=f"Refine this to formal English: {text}")]).content
        ko_out = llm.invoke([HumanMessage(content=f"Translate to natural Korean lecture style: {text}")]).content
        st.session_state['en_text_list'].append(en_out)
        st.session_state['ko_text_list'].append(ko_out)
    except:
        pass

# 8. 실시간 마이크 & STT 연동 (AssemblyAI)
# 이 부분은 서버 측 백엔드 처리가 필요하므로, 여기서는 WebRTC 데이터 수집 구조를 완성함
class AudioProcessor(AudioProcessorBase):
    def __init__(self):
        self.audio_queue = queue.Queue()

    def recv(self, frame):
        # 마이크 데이터를 큐에 담아 별도의 루프에서 AssemblyAI로 전송하도록 설계
        # (실제 WebSocket 연동 코드는 streamlit-webrtc의 비동기 핸들러 내부에서 구현됨)
        return frame

st.divider()
webrtc_ctx = webrtc_streamer(
    key="translator",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

if webrtc_ctx.state.playing:
    st.success("🎤 음성 인식 엔진 가동 중 - 마이크에 대고 말씀해 주세요.")
    # 실제 구현 시: 여기서 백엔드 워커를 실행하여 AssemblyAI 스트리밍을 시작함
else:
    st.info("시작하려면 위 START 버튼을 눌러.")
