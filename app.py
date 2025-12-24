import streamlit as st
import requests
import base64
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 1. 초기 설정 및 보안 정보 로드
st.set_page_config(layout="wide", page_title="AI 실시간 특강 통역")

try:
    CRED = st.secrets["credentials"]
    GEMINI_KEY = CRED["GEMINI_KEY"]
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
    SYNO_URL = CRED["SYNO_URL"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
except:
    st.error("Secrets 설정 확인이 필요합니다.")
    st.stop()

# 2. 시놀로지 파일 리스트 가져오기 함수
def get_synology_folders():
    # 로그인 및 SID 획득
    auth_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
    sid = requests.get(auth_url).json()['data']['sid']
    
    # rlrc/509 자료/ 하위 폴더 목록 조회
    list_url = f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.FileStation.List&version=2&method=list&folder_path=/rlrc/509 자료/&_sid={sid}"
    folders = requests.get(list_url).json()['data']['files']
    return [f['name'] for f in folders if f['isdir']]

# 3. UI 구성
st.title("🎤 RLRC 실시간 강의 통역 시스템")

with st.sidebar:
    st.header("강의 준비")
    try:
        subjects = get_synology_folders()
        selected_subject = st.selectbox("오늘의 강의 주제를 선택하세요", subjects)
    except:
        st.warning("시놀로지에서 주제 목록을 가져오지 못했습니다.")
        selected_subject = "일반 강의"
    
    st.divider()
    if st.button("강의 시작 (마이크 활성화)"):
        st.session_state.streaming = True
        st.success("시스템이 가동되었습니다. 말씀해 주세요.")

# 4. 메인 자막 화면 (고정 레이아웃)
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English Subtitles")
    en_area = st.empty()
    en_area.info("Waiting for speech...")

with col2:
    st.markdown("### 🇰🇷 한국어 실시간 자막")
    kr_area = st.empty()
    kr_area.success("음성 인식을 대기 중입니다...")

# 5. 번역 로직 (가이드라인)
# 내일 실제 실행 시에는 AssemblyAI의 실시간 스트리밍 SDK와 연동되어 
# 아래 en_area와 kr_area에 결과값이 실시간으로 채워지게 됩니다.
