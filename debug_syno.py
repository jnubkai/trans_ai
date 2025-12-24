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
    # 표준 브라우저 환경 모사
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
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

        # 1단계: 로그인 시도 (다양한 버전 시도)
        st.subheader("1단계: 로그인 시도 (버전별 순차 테스트)")
        
        # DSM 7.2에서 성공 가능성이 높은 버전 목록
        test_versions = ["7", "6", "4", "3"]
        
        for ver in test_versions:
            st.write(f"--- 테스트 중인 버전: {ver} ---")
            start_time = time.time()
            
            # POST 데이터 구성
            login_data = {
                "api": "SYNO.API.Auth",
                "version": ver, 
                "method": "login",
                "account": SYNO_ID,
                "passwd": SYNO_PW,
                "session": "FileStation",
                "format": "sid"
            }
            
            try:
                response = session.post(
                    f"{SYNO_URL}/webapi/entry.cgi", 
                    data=login_data, 
                    timeout=10
                )
                
                duration = time.time() - start_time
                res_json = response.json()
                
                st.write(f"⏱️ 소요 시간: {duration:.2f}초 | HTTP 상태: {response.status_code}")
                st.json(res_json)
                
                if res_json.get("success"):
                    sid = res_json["data"]["sid"]
                    st.success(f"🎉 버전 {ver}로 로그인 성공! SID 획득.")
                    
                    # 2단계: 목록 조회 시도
                    st.subheader("2단계: 목록 조회 시도")
                    list_params = {
                        "api": "SYNO.FileStation.List",
                        "version": "2", 
                        "method": "list",
                        "folder_path": "/RLRC/509 자료",
                        "_sid": sid
                    }
                    list_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=list_params, timeout=10).json()
                    st.json(list_res)
                    break # 성공하면 반복문 종료
                else:
                    error_code = res_json.get("error", {}).get("code")
                    if error_code == 400:
                        st.warning(f"버전 {ver}: 400 에러 (파라미터 부적합)")
                    elif error_code == 403:
                        st.error(f"버전 {ver}: 403 에러 (2단계 인증 필요 혹은 차단됨)")
                    elif error_code == 401:
                        st.error(f"버전 {ver}: 401 에러 (계정정보 불일치)")
            
            except Exception as e:
                st.error(f"버전 {ver} 테스트 중 에러: {e}")

    except Exception as e:
        st.error(f"🚨 네트워크 에러 발생: {e}")
    finally:
        session.close()

st.divider()
st.caption("DSM 7.2.1-69057 Update 8 대응 디버깅 모드")
