import streamlit as st
import requests
import time
import json

st.set_page_config(page_title="시놀로지 접속 디버깅")

st.title("🔍 시놀로지 접속 상세 디버깅 (DSM 7.2 대응)")

# 1. Secrets 로드 로직 (사용자 제공 구조 반영)
try:
    # [credentials] 섹션 직접 접근
    if "credentials" in st.secrets:
        CRED = st.secrets["credentials"]
        SYNO_ID = CRED.get("SYNO_ID")
        SYNO_PW = CRED.get("SYNO_PW")
        SYNO_URL = CRED.get("SYNO_URL")
    else:
        # 섹션 없이 루트에 있을 경우 대비
        SYNO_ID = st.secrets.get("SYNO_ID")
        SYNO_PW = st.secrets.get("SYNO_PW")
        SYNO_URL = st.secrets.get("SYNO_URL")
    
    if SYNO_URL:
        SYNO_URL = SYNO_URL.rstrip('/')

    # 필수 값 존재 여부 최종 확인
    if not all([SYNO_ID, SYNO_PW, SYNO_URL]):
        st.error("🚨 필수 값 누락!")
        st.write("확인된 키 목록:", list(st.secrets.keys()))
        if "credentials" in st.secrets:
            st.write("credentials 내부 키:", list(st.secrets["credentials"].keys()))
        st.stop()
        
    st.success(f"✅ 설정 로드 성공: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 접근 중 에러: {e}")
    st.stop()

if st.button("통신 테스트 시작"):
    session = requests.Session()
    
    try:
        # 1단계: 로그인 시도 (DSM 7.2 대응을 위해 버전 6 시도)
        st.subheader("1단계: 로그인 시도 (Version 6)")
        start_time = time.time()
        
        login_params = {
            "api": "SYNO.API.Auth",
            "version": "6", # DSM 7.2 최적화 버전
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "sid" 
        }
        
        response = session.get(f"{SYNO_URL}/webapi/auth.cgi", params=login_params, timeout=10)
        st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초")
        
        res_data = response.json()
        st.json(res_data)
        
        if res_data.get("success"):
            sid = res_data["data"]["sid"]
            st.success(f"로그인 성공! SID: {sid}")
            
            # 2단계: 목록 조회 시도 (버전 2로 상향)
            st.subheader("2단계: 목록 조회 시도 (Version 2)")
            start_time = time.time()
            list_params = {
                "api": "SYNO.FileStation.List",
                "version": "2", 
                "method": "list",
                "folder_path": "/RLRC/509 자료",
                "_sid": sid
            }
            list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=10)
            st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초")
            st.json(list_res.json())
            
        else:
            error_info = res_data.get("error", {})
            error_code = error_info.get("code")
            st.error(f"로그인 실패 (에러 코드: {error_code})")
            
            if error_code == 400:
                st.warning("⚠️ Version 6 거부됨. Version 3으로 재시도 중...")
                login_params["version"] = "3"
                retry_res = session.get(f"{SYNO_URL}/webapi/auth.cgi", params=login_params, timeout=10).json()
                st.json(retry_res)
            
    except Exception as e:
        st.error(f"🚨 네트워크 에러 발생: {e}")
    finally:
        session.close()
