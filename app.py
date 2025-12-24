import streamlit as st
import requests
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_community.document_loaders import PyPDFLoader
import tempfile

# 1. 페이지 설정
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 2. Secrets 설정 로드
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"].rstrip('/')
    GOOGLE_API_KEY = st.secrets["gemini"]["api_key"]
    # AssemblyAI 키 등 추가 필요시 여기에 작성
except Exception as e:
    st.error(f"Secrets 설정 오류: {e}")
    st.stop()

# 3. AI 모델 설정 (Gemini 2.5 Flash)
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY)

st.title("🎤 RLRC 실시간 강의 통역 시스템")

# 4. 사이드바: 시놀로지 연동 및 주제 선택
with st.sidebar:
    st.header("1. 강의 준비")
    
    if st.button("시놀로지 목록 업데이트"):
        auth_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
        try:
            with st.spinner("연결 중..."):
                res = requests.get(auth_url, timeout=5).json()
                if res.get("success"):
                    sid = res["data"]["sid"]
                    st.session_state['sid'] = sid
                    
                    # 폴더 목록 가져오기
                    target_path = "/RLRC/509 자료"
                    list_url = f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.FileStation.List&version=2&method=list&folder_path={target_path}&_sid={sid}"
                    l_res = requests.get(list_url, timeout=5).json()
                    
                    if l_res.get("success"):
                        folders = [f['name'] for f in l_res['data']['files'] if f['isdir']]
                        st.session_state['folder_list'] = folders
                        st.success(f"{len(folders)}개의 주제 확인됨")
                    else:
                        st.error("폴더를 찾을 수 없음")
                else:
                    st.error("로그인 실패")
        except Exception as e:
            st.error(f"접속 에러: {e}")

    folder_list = st.session_state.get('folder_list', ["먼저 업데이트를 누르세요"])
    selected_subject = st.selectbox("오늘의 강의 주제", folder_list)
    
    st.divider()
    st.header("2. 시스템 제어")
    start_btn = st.button("강의 시작 (마이크 ON)")

# 5. 메인 화면: 통역 레이아웃
st.subheader(f"📍 현재 진행 중인 강의: {selected_subject}")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🇬🇧 English (Original)")
    en_placeholder = st.empty()
    en_placeholder.info("Speech will be displayed here...")

with col2:
    st.markdown("### 🇰🇷 한국어 (번역)")
    kr_placeholder = st.empty()
    kr_placeholder.success("실시간 번역 자막이 표시됩니다.")

# 6. PDF 지식 기반 번역 로직 (예시 함수)
def translate_with_context(text, context_data):
    prompt = f"강의 자료 내용: {context_data}\n\n위 내용을 바탕으로 다음 영어를 전문 용어에 맞게 번역해줘: {text}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content

# 안내 메시지
st.caption("시스템 상태: 대기 중 | Gemini 1.5 Flash 연결됨")
