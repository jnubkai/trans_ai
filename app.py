import streamlit as st
import requests
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 2. Secrets에서 설정된 이름 그대로 로드
try:
    # 사용자님이 입력하신 명칭 그대로 매칭
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"].rstrip('/')
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]  # [gemini][api_key]가 아니라 [credentials][GEMINI_KEY]임
    ASSEMBLY_KEY = CRED["ASSEMBLY_KEY"]
except Exception as e:
    st.error(f"Secrets 설정 확인 필요: {e}")
    st.stop()

# 3. AI 모델 초기화
try:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"AI 모델 초기화 실패: {e}")
    st.stop()

st.title("🎤 RLRC 실시간 강의 통역 시스템")

# 4. 사이드바: 시놀로지 제어
with st.sidebar:
    st.header("강의 설정")
    
    if st.button("목록 업데이트"):
        auth_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
        try:
            with st.spinner("연결 중..."):
                res = requests.get(auth_url, timeout=5).json()
                if res.get("success"):
                    sid = res["data"]["sid"]
                    st.session_state['sid'] = sid
                    
                    # 지정된 경로에서 폴더 목록 가져오기
                    target_path = "/RLRC/509 자료"
                    list_url = f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.FileStation.List&version=2&method=list&folder_path={target_path}&_sid={sid}"
                    l_res = requests.get(list_url, timeout=5).json()
                    
                    if l_res.get("success"):
                        folders = [f['name'] for f in l_res['data']['files'] if f['isdir']]
                        st.session_state['folder_list'] = folders
                        st.success(f"{len(folders)}개 주제 로드됨")
                    else:
                        st.error(f"목록 조회 실패 (코드: {l_res.get('error')})")
                else:
                    st.error(f"로그인 거절 (코드: {res.get('error')})")
        except Exception as e:
            st.error(f"접속 에러: {e}")

    folders = st.session_state.get('folder_list', ["업데이트를 눌러주세요"])
    selected_subject = st.selectbox("강의 주제 선택", folders)

# 5. 메인 화면 레이아웃
st.subheader(f"📍 현재 주제: {selected_subject}")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    st.info("Speech Area")

with col2:
    st.markdown("### 🇰🇷 한국어 (실시간 번역)")
    st.success("Subtitle Area")

st.caption("시스템 상태: 정상 가동 중")
