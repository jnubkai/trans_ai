import streamlit as st
import requests
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 2. Secrets 로드
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"].rstrip('/')
    GOOGLE_API_KEY = CRED["GEMINI_KEY"]
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

# 4. 사이드바: 시놀로지 제어 (세션 최적화 적용)
with st.sidebar:
    st.header("강의 설정")
    
    if st.button("목록 업데이트"):
        # 통신 세션 생성 (연결 재사용으로 속도 향상)
        session = requests.Session()
        
        # 1단계: 로그인
        # version을 3으로 고정하고 필요한 파라미터만 최소화하여 전송
        login_params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "cookie"
        }
        
        try:
            with st.spinner("데이터 로드 중..."):
                auth_res = session.get(f"{SYNO_URL}/webapi/auth.cgi", params=login_params, timeout=5).json()
                
                if auth_res.get("success"):
                    sid = auth_res["data"]["sid"]
                    st.session_state['sid'] = sid
                    
                    # 2단계: 폴더 목록 가져오기
                    # target_path 내 공백 등 특수문자 처리를 위해 params 활용
                    list_params = {
                        "api": "SYNO.FileStation.List",
                        "version": "2",
                        "method": "list",
                        "folder_path": "/RLRC/509 자료",
                        "_sid": sid
                    }
                    
                    list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=5).json()
                    
                    if list_res.get("success"):
                        # 'isdir' 필드를 확인하여 폴더만 추출
                        folders = [f['name'] for f in list_res['data']['files'] if f.get('isdir')]
                        st.session_state['folder_list'] = folders
                        st.success(f"{len(folders)}개 주제 로드 완료")
                    else:
                        st.error(f"목록 조회 실패 (코드: {list_res.get('error')})")
                else:
                    st.error(f"로그인 실패 (코드: {auth_res.get('error')})")
        except Exception as e:
            st.error(f"접속 에러: {e}")
        finally:
            session.close()

    folders = st.session_state.get('folder_list', ["업데이트를 눌러주세요"])
    selected_subject = st.selectbox("강의 주제 선택", folders)

# 5. 메인 화면 레이아웃
st.subheader(f"📍 현재 주제: {selected_subject}")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    st.info("실시간 음성 인식 영역")

with col2:
    st.markdown("### 🇰🇷 한국어 (실시간 번역)")
    st.success("실시간 번역 자막 영역")

st.caption("시스템 상태: 정상 가동 중")
