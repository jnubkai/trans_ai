import streamlit as st
import requests

# 페이지 설정 (가로 모드 최적화)
st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 1. Secrets에서 정보 가져오기
try:
    SYNO_ID = st.secrets["credentials"]["SYNO_ID"]
    SYNO_PW = st.secrets["credentials"]["SYNO_PW"]
    SYNO_URL = st.secrets["credentials"]["SYNO_URL"]
except Exception as e:
    st.error("Streamlit Secrets 설정이 누락되었거나 형식이 틀립니다. Settings에서 확인해 주세요.")
    st.stop()

st.title("🎤 실시간 강의 통역 시스템 (연결 테스트)")

# 2. 사이드바: 주제 선택 UI
with st.sidebar:
    st.header("강의 설정")
    subject = st.selectbox("강의 분야를 선택하세요", ["그린수소", "AI 미래", "멤브레인 기술"])
    
    if st.button("시놀로지 연결 테스트"):
        # 시놀로지 로그인 API 시뮬레이션
        test_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
        try:
            res = requests.get(test_url, timeout=5)
            if res.status_code == 200:
                st.success("✅ 시놀로지 연결 성공!")
            else:
                st.error(f"❌ 연결 실패 (응답 코드: {res.status_code})")
        except Exception as e:
            st.error(f"접속 에러 발생: {e}")

# 3. 메인 화면: 레이아웃 고정
st.subheader(f"현재 선택된 주제: {subject}")
col1, col2 = st.columns(2)

with col1:
    st.info("### 🇬🇧 English Area")
    st.write("영어 자막이 고정될 자리임.")

with col2:
    st.success("### 🇰🇷 한국어 영역")
    st.write("한국어 자막이 고정될 자리임.")
