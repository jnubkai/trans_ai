import streamlit as st
import requests
import time
import json

st.set_page_config(page_title="시놀로지 접속 디버깅")

st.title("🔍 시놀로지 접속 상세 디버깅")

# Secrets 로드 확인
try:
    CRED = st.secrets["credentials"]
    SYNO_ID = CRED["SYNO_ID"]
    SYNO_PW = CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"].rstrip('/')
    st.success(f"설정 로드 완료: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 로드 에러: {e}")
    st.stop()

if st.button("통신 테스트 시작"):
    session = requests.Session()
    stats = {}
    
    try:
        # 1단계: 로그인 테스트
        st.subheader("1단계: 로그인 시도")
        start_time = time.time()
        
        login_params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "cookie"
        }
        
        response = session.get(f"{SYNO_URL}/webapi/auth.cgi", params=login_params, timeout=10)
        stats['login_time'] = time.time() - start_time
        
        st.write(f"⏱️ 로그인 소요 시간: {stats['login_time']:.2f}초")
        st.json(response.json())
        
        if response.json().get("success"):
            sid = response.json()["data"]["sid"]
            
            # 2단계: 목록 조회 테스트
            st.subheader("2단계: 목록 조회 시도")
            start_time = time.time()
            
            list_params = {
                "api": "SYNO.FileStation.List",
                "version": "2",
                "method": "list",
                "folder_path": "/RLRC/509 자료",
                "_sid": sid
            }
            
            list_response = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=10)
            stats['list_time'] = time.time() - start_time
            
            st.write(f"⏱️ 목록 조회 소요 시간: {stats['list_time']:.2f}초")
            st.json(list_response.json())
            
        else:
            st.error("로그인 단계에서 실패함")
            
    except requests.exceptions.Timeout:
        st.error("🚨 타임아웃 발생: 서버가 응답을 주지 않음")
    except Exception as e:
        st.error(f"🚨 에러 발생: {e}")
    finally:
        session.close()

st.divider()
st.info("""
**디버깅 체크리스트:**
1. 로그인 소요 시간이 5초에 근접하는지 확인.
2. 특정 단계에서만 타임아웃이 나는지 확인.
3. 시놀로지 응답 데이터에 에러 코드가 있는지 확인.
""")
