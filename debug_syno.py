import streamlit as st
import requests
import time
import json
import urllib.parse

st.set_page_config(page_title="시놀로지 접속 디버깅")

st.title("🔍 시놀로지 접속 상세 디버깅 (최종 점검)")

# 1. Secrets 로드 로직
try:
    if "credentials" in st.secrets:
        CRED = st.secrets["credentials"]
        SYNO_ID = CRED.get("SYNO_ID")
        SYNO_PW = CRED.get("SYNO_PW")
        SYNO_URL = CRED.get("SYNO_URL")
    else:
        SYNO_ID = st.secrets.get("SYNO_ID")
        SYNO_PW = st.secrets.get("SYNO_PW")
        SYNO_URL = st.secrets.get("SYNO_URL")
    
    if SYNO_URL:
        SYNO_URL = SYNO_URL.rstrip('/')

    if not all([SYNO_ID, SYNO_PW, SYNO_URL]):
        st.error("🚨 필수 값 누락!")
        st.stop()
        
    st.success(f"✅ 설정 로드 성공: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 접근 중 에러: {e}")
    st.stop()

if st.button("마지막 통신 테스트"):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        # 0단계: API Info (정상 작동 확인용)
        st.subheader("0단계: API 정보")
        info_res = session.get(f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.API.Info&version=1&method=query&query=SYNO.API.Auth").json()
        st.json(info_res)

        # 1단계: 가장 단순한 형태의 로그인 요청
        st.subheader("1단계: 로그인 (최소 파라미터)")
        
        # 400 에러를 유발할 수 있는 session 이름을 기본값(dsm)으로 변경
        # otp_code를 명시적으로 전달 (공백)
        login_params = {
            "api": "SYNO.API.Auth",
            "version": "3", 
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "default", # FileStation 대신 default 시도
            "format": "sid",
            "otp_code": "" 
        }
        
        url = f"{SYNO_URL}/webapi/entry.cgi"
        
        # 이번에는 POST가 아닌 GET으로도 한 번 더 시도 (가장 원시적인 방식)
        st.write("📡 테스트 방식: GET 요청")
        response = session.get(url, params=login_params, timeout=15)
        st.json(response.json())
        
        if not response.json().get("success"):
            st.write("📡 테스트 방식: POST 요청")
            post_response = session.post(url, data=login_params, timeout=15)
            st.json(post_response.json())

    except Exception as e:
        st.error(f"🚨 네트워크 에러: {e}")
    finally:
        session.close()

st.divider()
st.warning("⚠️ 코드로 해결되지 않는 경우, DSM 제어판에서 '사용자 권한'과 'OTP 강제 설정'을 반드시 확인해 보셔야 합니다.")
