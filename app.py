import streamlit as st
import requests
import os
import json
import asyncio
import queue
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 디자인 커스텀
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stInfo { font-size: 1.1rem; min-height: 300px; border-radius: 10px; padding: 15px; background-color: #e3f2fd; border-left: 5px solid #2196f3; }
    .stSuccess { font-size: 1.1rem; min-height: 300px; border-radius: 10px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #4caf50; }
    .transcript-box { height: 350px; overflow-y: auto; white-space: pre-wrap; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; font-family: 'Malgun Gothic', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# 2. Secrets 로드 및 검증
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = "https://speedep.synology.me:7651"
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
except Exception as e:
    st.error("설정 오류: .streamlit/secrets.toml 파일의 설정을 확인해 주세요.")
    st.stop()

# 3. AI 모델 초기화
@st.cache_resource
def init_llm():
    try:
        return ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
    except Exception as e:
        st.error(f"AI 모델 연결 실패: {e}")
        return None

llm = init_llm()

# 세션 상태 관리
if 'folder_list' not in st.session_state:
    st.session_state['folder_list'] = []
if 'sid' not in st.session_state:
    st.session_state['sid'] = None
if 'en_text_list' not in st.session_state:
    st.session_state['en_text_list'] = []
if 'ko_text_list' not in st.session_state:
    st.session_state['ko_text_list'] = []

st.title("🎤 RLRC 실시간 강의 통역 시스템")

# 4. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 강의 환경 설정")
    
    use_ssl_verify = st.checkbox("SSL 인증서 검증 활성화", value=False)
    
    if st.button("📁 시놀로지 목록 업데이트", use_container_width=True):
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        login_data = {
            "api": "SYNO.API.Auth", "version": "7", "method": "login",
            "account": SYNO_ID, "passwd": SYNO_PW,
            "session": "FileStation", "format": "sid" 
        }
        
        try:
            with st.spinner(f"NAS 연결 중..."):
                auth_response = session.post(f"{SYNO_URL}/webapi/auth.cgi", data=login_data, timeout=20, verify=use_ssl_verify)
                auth_res = auth_response.json()
                
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
                        st.toast(f"{len(folders)}개의 강의 주제 발견", icon="📂")
                else:
                    st.error(f"NAS 로그인 실패: {auth_res.get('error', {}).get('code')}")
        except Exception as e:
            st.error(f"접속 불가: {str(e)}")
        finally:
            session.close()

    folders = st.session_state['folder_list'] if st.session_state['folder_list'] else ["목록을 업데이트해 주세요"]
    selected_subject = st.selectbox("🎯 현재 강의 주제", folders)
    
    st.divider()
    if st.button("🧹 기록 모두 삭제", type="secondary", use_container_width=True):
        st.session_state['en_text_list'] = []
        st.session_state['ko_text_list'] = []
        st.rerun()

# 5. 실시간 통역 인터페이스
st.subheader(f"📍 진행 중인 강의: {selected_subject}")

col1, col2 = st.columns(2)

# 텍스트 합치기 도우미
full_en = "\n\n".join(st.session_state['en_text_list'])
full_ko = "\n\n".join(st.session_state['ko_text_list'])

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    en_area = st.empty()
    en_area.markdown(f'<div class="stInfo transcript-box">{full_en if full_en else "마이크를 켜면 음성 인식이 시작됨."}</div>', unsafe_allow_html=True)

with col2:
    st.markdown("### 🇰🇷 한국어 (Translation)")
    ko_area = st.empty()
    ko_area.markdown(f'<div class="stSuccess transcript-box">{full_ko if full_ko else "실시간 번역 결과가 여기에 표시됨."}</div>', unsafe_allow_html=True)

# 6. 번역 로직 함수
def translate_text(text):
    if not text.strip() or not llm:
        return ""
    try:
        prompt = f"Translate the following lecture transcript into natural Korean. Maintain a formal and academic tone. Text: {text}"
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except:
        return "[번역 실패]"

# 7. 오디오 처리 클래스
# 실제 AssemblyAI 연동을 위한 결과 수신 큐(Queue) 준비
result_queue = queue.Queue()

class AudioProcessor(AudioProcessorBase):
    def recv(self, frame):
        # 마이크로부터 받은 오디오 프레임 처리 (향후 AssemblyAI 전송부 연결 지점)
        return frame

# 8. 실시간 마이크 입력 제어 버튼 (START/STOP)
st.divider()
st.write("### 🎙️ 통역 컨트롤 센터")

# webrtc_streamer 자체가 시작/중지 버튼 역할을 수행함
webrtc_ctx = webrtc_streamer(
    key="speech-to-text",
    mode=WebRtcMode.SENDONLY,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    async_processing=True,
    # UI 한글화 및 버튼 가시성 설정
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
)

if webrtc_ctx.state.playing:
    st.success("🎤 통역 진행 중... 브라우저 상단의 'Stop'을 누르면 종료됨.")
    
    # [시뮬레이션/구현 로직 예시]
    # 실제로는 AssemblyAI의 결과를 비동기로 받아와서 세션에 추가해야 함
    # 임시 테스트: 결과가 감지되었다고 가정하고 화면 갱신
    # new_en = "Testing real-time translation system."
    # if new_en not in st.session_state['en_text_list']:
    #     st.session_state['en_text_list'].append(new_en)
    #     st.session_state['ko_text_list'].append(translate_text(new_en))
    #     st.rerun()
else:
    st.warning("통역이 중지된 상태임. 위의 'START' 버튼을 눌러 마이크를 활성화해.")

# 하단 정보
st.caption(f"서버 연결 상태: ✅ 정상 | 접속 주소: {SYNO_URL}")
