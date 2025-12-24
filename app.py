import streamlit as st
import requests
import os
import json
import asyncio
import queue
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 필수 라이브러리 체크
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
    st.error("Secrets 설정(SYNO_ID, SYNO_PW, GEMINI_KEY, ASSEMBLY_KEY)을 확인해.")
    st.stop()

# 3. AI 모델 초기화 (Gemini)
@st.cache_resource
def init_llm():
    try:
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
    except Exception as e:
        return None

llm = init_llm()

# 4. 세션 상태 초기화
if 'folder_list' not in st.session_state:
    st.session_state['folder_list'] = []
if 'en_text_list' not in st.session_state:
    st.session_state['en_text_list'] = []
if 'ko_text_list' not in st.session_state:
    st.session_state['ko_text_list'] = []

st.title("🎤 AI 실시간 자동 통역 시스템 (Multi-Language)")

# 5. 사이드바 - NAS 연동 및 설정
with st.sidebar:
    st.header("⚙️ NAS & System")
    use_ssl_verify = st.checkbox("SSL 인증서 검증", value=False)
    
    if st.button("📁 NAS 폴더 목록 업데이트", use_container_width=True):
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        login_data = {
            "api": "SYNO.API.Auth", "version": "7", "method": "login",
            "account": SYNO_ID, "passwd": SYNO_PW,
            "session": "FileStation", "format": "sid" 
        }
        try:
            with st.spinner("NAS 접속 중..."):
                auth_res = session.post(f"{SYNO_URL}/webapi/auth.cgi", data=login_data, timeout=20, verify=use_ssl_verify).json()
                if auth_res.get("success"):
                    st.session_state['sid'] = auth_res["data"]["sid"]
                    list_params = {
                        "api": "SYNO.FileStation.List", "version": "2", "method": "list",
                        "folder_path": "/RLRC/509 자료", "_sid": st.session_state['sid']
                    }
                    list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=20, verify=use_ssl_verify).json()
                    if list_res.get("success"):
                        folders = [f['name'] for f in list_res['data']['files'] if f.get('isdir')]
                        st.session_state['folder_list'] = sorted(folders)
                        st.toast("목록 업데이트 완료")
                else:
                    st.error(f"NAS 로그인 실패: {auth_res.get('error', {}).get('code')}")
        except Exception as e:
            st.error(f"접속 오류: {str(e)}")
        finally:
            session.close()

    folders = st.session_state['folder_list'] if st.session_state['folder_list'] else ["목록 없음"]
    selected_subject = st.selectbox("🎯 현재 강의 주제", folders)
    
    if st.button("🧹 기록 초기화", use_container_width=True):
        st.session_state['en_text_list'] = []
        st.session_state['ko_text_list'] = []
        st.rerun()

# 6. 통역 결과 표시 영역
st.subheader(f"📍 진행 주제: {selected_subject}")
col1, col2 = st.columns(2)

full_en = "\n\n".join(st.session_state['en_text_list'])
full_ko = "\n\n".join(st.session_state['ko_text_list'])

with col1:
    st.markdown("### 🇬🇧 English (Global)")
    st.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "Waiting for input..."}</div>', unsafe_allow_html=True)

with col2:
    st.markdown("### 🇰🇷 한국어 (번역)")
    st.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "한국어 번역 결과가 표시됨"}</div>', unsafe_allow_html=True)

# 7. 언어 처리 및 번역 로직 (자동 감지 대응)
def process_voice_input(text):
    """
    입력이 어떤 언어든 감지하여 
    왼쪽에는 영어, 오른쪽에는 한국어로 고정 출력함.
    """
    if not text.strip() or not llm:
        return

    try:
        # 영어로 정제/번역 (왼쪽용)
        en_prompt = f"Convert the following to professional English lecture transcript. If it's already English, correct grammar: {text}"
        en_out = llm.invoke([HumanMessage(content=en_prompt)]).content
        
        # 한국어로 정제/번역 (오른쪽용)
        ko_prompt = f"Translate the following to natural Korean university lecture style. If it's already Korean, refine it: {text}"
        ko_out = llm.invoke([HumanMessage(content=ko_prompt)]).content
        
        st.session_state['en_text_list'].append(en_out)
        st.session_state['ko_text_list'].append(ko_out)
        st.rerun()
    except Exception as e:
        st.error(f"번역 엔진 오류: {e}")

# 8. WebRTC 마이크 제어
class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        return frame

st.divider()
st.write("### 🎙️ 마이크 제어")
webrtc_ctx = webrtc_streamer(
    key="translator-mic",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    async_processing=True,
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

if webrtc_ctx.state.playing:
    st.success("🎤 시스템 가동 중 - 음성을 인식하고 있음")
else:
    st.info("시작 버튼(START)을 눌러 통역을 시작해.")

# 하단 상태 정보
st.caption(f"NAS 연결: {'정상' if st.session_state.get('sid') else '미연결'} | 배포 서버: Streamlit Cloud")
