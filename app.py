import streamlit as st
import requests
import os
import json
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 디자인 커스텀
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stInfo { font-size: 1.1rem; min-height: 250px; border-radius: 10px; padding: 15px; background-color: #e3f2fd; border-left: 5px solid #2196f3; }
    .stSuccess { font-size: 1.1rem; min-height: 250px; border-radius: 10px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #4caf50; }
    .transcript-box { height: 300px; overflow-y: auto; white-space: pre-wrap; }
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
if 'is_translating' not in st.session_state:
    st.session_state['is_translating'] = False
if 'en_text' not in st.session_state:
    st.session_state['en_text'] = ""
if 'ko_text' not in st.session_state:
    st.session_state['ko_text'] = ""

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
            "api": "SYNO.API.Auth",
            "version": "7",
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "sid" 
        }
        
        try:
            with st.spinner(f"NAS 연결 중..."):
                auth_response = session.post(f"{SYNO_URL}/webapi/auth.cgi", data=login_data, timeout=20, verify=use_ssl_verify)
                auth_res = auth_response.json()
                
                if auth_res.get("success"):
                    st.session_state['sid'] = auth_res["data"]["sid"]
                    
                    list_params = {
                        "api": "SYNO.FileStation.List",
                        "version": "2",
                        "method": "list",
                        "folder_path": "/RLRC/509 자료",
                        "_sid": st.session_state['sid']
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
        st.session_state['en_text'] = ""
        st.session_state['ko_text'] = ""
        st.rerun()

# 5. 실시간 통역 인터페이스
st.subheader(f"📍 진행 중인 강의: {selected_subject}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    en_placeholder = st.empty()
    en_placeholder.info(st.session_state['en_text'] if st.session_state['en_text'] else "강의자의 음성이 인식되면 여기에 표시됨.")

with col2:
    st.markdown("### 🇰🇷 한국어 (Translation)")
    ko_placeholder = st.empty()
    ko_placeholder.success(st.session_state['ko_text'] if st.session_state['ko_text'] else "실시간 번역 결과가 여기에 표시됨.")

# 6. 번역 로직 함수
def translate_text(text):
    if not text.strip() or not llm:
        return ""
    prompt = f"Translate the following lecture transcript into natural Korean. Maintain a formal and academic tone suitable for a university lecture. Text: {text}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content

# 7. 하단 컨트롤 및 시뮬레이션 로직
st.divider()
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.caption(f"접속 상태: ✅ 정상 | 서버: {SYNO_URL}")

with c2:
    if not st.session_state['is_translating']:
        if st.button("▶️ 통역 시작", type="primary", use_container_width=True):
            if not st.session_state.get('sid'):
                st.error("NAS 연결이 먼저 필요함.")
            else:
                st.session_state['is_translating'] = True
                st.rerun()
    else:
        if st.button("⏹ 중지", type="secondary", use_container_width=True):
            st.session_state['is_translating'] = False
            st.rerun()

# 8. 통역 루프 (임시 시뮬레이션 포함)
if st.session_state['is_translating']:
    # 실제 환경에서는 여기서 AssemblyAI WebSocket 연결 및 마이크 입력을 처리함
    # 지금은 구조 확인을 위해 루프 형태만 구성함
    with st.spinner("음성 인식 중..."):
        # 데모용: 실제 구현 시에는 별도의 스레드나 비동기 루프로 대체
        st.write("📢 마이크로부터 데이터를 기다리는 중 (실제 통역 로직 연결 대기)")
        
        # 임시 데이터 업데이트 예시 (동작 확인용)
        # st.session_state['en_text'] += "\nHello, today we will talk about..."
        # st.session_state['ko_text'] += f"\n{translate_text('Hello, today we will talk about...')}"
