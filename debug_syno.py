import streamlit as st
import requests
import time
import json

st.set_page_config(page_title="시놀로지 접속 디버깅")

st.title("🔍 시놀로지 접속 상세 디버깅 (DSM 7.2 정밀 대응)")

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

if st.button("통신 테스트 시작"):
    session = requests.Session()
    # DSM 7.2는 표준 브라우저 헤더를 선호함
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    
    try:
        # 0단계: API 정보 확인
        st.subheader("0단계: API 정보 조회 (Info API)")
        info_params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": "SYNO.API.Auth,SYNO.FileStation.List"
        }
        info_res = session.get(f"{SYNO_URL}/webapi/query.cgi", params=info_params, timeout=10).json()
        st.json(info_res)

        # 1단계: 로그인 시도 (POST 방식 변경 및 인코딩 무결성 강화)
        st.subheader("1단계: 로그인 시도 (POST 방식 및 Version 7)")
        start_time = time.time()
        
        # 비밀번호 내 특수문자(@ 등) 이슈 방지를 위해 데이터를 딕셔너리로 구성 후 POST 전송
        login_data = {
            "api": "SYNO.API.Auth",
            "version": "7", 
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW,
            "session": "FileStation",
            "format": "sid"
        }
        
        # entry.cgi로 POST 요청 발송
        response = session.post(
            f"{SYNO_URL}/webapi/entry.cgi", 
            data=login_data, 
            headers=headers,
            timeout=10
        )
        
        st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초")
        res_data = response.json()
        st.json(res_data)
        
        if res_data.get("success"):
            sid = res_data["data"]["sid"]
            st.success(f"로그인 성공! SID: {sid}")
            
            # 2단계: 목록 조회 시도
            st.subheader("2단계: 목록 조회 시도")
            start_time = time.time()
            list_params = {
                "api": "SYNO.FileStation.List",
                "version": "2", 
                "method": "list",
                "folder_path": "/RLRC/509 자료",
                "_sid": sid
            }
            # 목록 조회는 관습적으로 GET 사용하나 보안 세션은 유지됨
            list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=10)
            st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초")
            st.json(list_res.json())
            
        else:
            error_code = res_data.get("error", {}).get("code")
            st.error(f"로그인 실패 (에러 코드: {error_code})")
            
            if error_code == 400:
                st.warning("⚠️ 400 에러 지속: POST 방식으로도 거절됨.")
                st.info("디버깅 포인트: 비밀번호를 따옴표 없이 입력했거나, 시놀로지에서 '특수문자 포함 비밀번호' 전송 시 추가 보안 요구 중일 수 있음.")
            
    except Exception as e:
        st.error(f"🚨 네트워크 에러 발생: {e}")
    finally:
        session.close()
