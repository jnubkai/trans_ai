import streamlit as st
import requests
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 디자인 커스텀
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stInfo { font-size: 1.1rem; min-height: 250px; border-radius: 10px; }
    .stSuccess { font-size: 1.1rem; min-height: 250px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. Secrets 로드 및 검증
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    
    # 요청하신 주소 반영: speedep.synology.me:7651 (HTTPS)
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

st.title("🎤 RLRC 실시간 강의 통역 시스템")

# 4. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 강의 환경 설정")
    
    # HTTPS 보안 경고 제어 옵션
    use_ssl_verify = st.checkbox("SSL 인증서 검증 활성화", value=False, help="인증서 오류 시 체크 해제.")
    
    if st.button("📁 시놀로지 목록 업데이트", use_container_width=True):
        session = requests.Session()
        # 브라우저인 것처럼 헤더 추가 (차단 방지)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        # 서버 권장 사항 반영: API 버전 7 사용
        # 에러 코드 400 방지를 위해 파라미터 재구성
        login_params = {
            "api": "SYNO.API.Auth",
            "version": "7",
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "cookie"  # 버전 7에서는 cookie 방식 선호됨
        }
        
        try:
            with st.spinner(f"NAS 연결 중 ({SYNO_URL})..."):
                auth_res = session.get(
                    f"{SYNO_URL}/webapi/auth.cgi", 
                    params=login_params, 
                    timeout=15, 
                    verify=use_ssl_verify
                ).json()
                
                if auth_res.get("success"):
                    st.session_state['sid'] = auth_res["data"]["sid"]
                    
                    # 폴더 목록 조회 (버전 2)
                    list_params = {
                        "api": "SYNO.FileStation.List",
                        "version": "2",
                        "method": "list",
                        "folder_path": "/RLRC/509 자료",
                        "_sid": st.session_state['sid']
                    }
                    
                    list_res = session.get(
                        f"{SYNO_URL}/webapi/entry.cgi", 
                        params=list_params, 
                        timeout=15, 
                        verify=use_ssl_verify
                    ).json()
                    
                    if list_res.get("success"):
                        folders = [f['name'] for f in list_res['data']['files'] if f.get('isdir')]
                        st.session_state['folder_list'] = sorted(folders)
                        st.toast(f"{len(folders)}개의 강의 주제 발견", icon="📂")
                    else:
                        st.error(f"목록 로드 실패 (Error Code: {list_res.get('error', {}).get('code')})")
                else:
                    # 상세 에러 코드 출력
                    error_info = auth_res.get("error", {})
                    error_code = error_info.get("code", "Unknown")
                    st.error(f"NAS 로그인 실패 (Error Code: {error_code})")
                    
                    if str(error_code) == "400":
                        st.warning("400 에러 감지: API 버전이나 파라미터 형식이 맞지 않음. 버전 6으로 다시 시도하거나 계정 권한 확인 필요함.")
        except Exception as e:
            st.error(f"접속 불가: {type(e).__name__}")
        finally:
            session.close()

    # 주제 선택 UI
    folders = st.session_state['folder_list'] if st.session_state['folder_list'] else ["목록을 업데이트해 주세요"]
    selected_subject = st.selectbox("🎯 현재 강의 주제", folders)
    
    st.divider()
    if st.button("🧹 기록 모두 삭제", type="secondary", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# 5. 실시간 통역 인터페이스
st.subheader(f"📍 진행 중인 강의: {selected_subject}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    en_area = st.empty()
    en_area.info("강의자의 음성이 인식되면 여기에 영문 텍스트가 표시됨.")

with col2:
    st.markdown("### 🇰🇷 한국어 (Translation)")
    ko_area = st.empty()
    ko_area.success("실시간 번역 결과가 여기에 표시됨.")

# 6. 하단 컨트롤
st.divider()
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.caption(f"접속 주소: {SYNO_URL} | 계정: {SYNO_ID}")
with c2:
    if st.button("▶️ 통역 시작", type="primary", use_container_width=True):
        if not st.session_state.get('sid'):
            st.error("NAS 연결이 먼저 필요함.")
        else:
            st.info("AssemblyAI 스트리밍 연결 시도 중...")
with c3:
    if st.button("⏹ 중지", use_container_width=True):
        st.stop()
