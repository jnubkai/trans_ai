import streamlit as st
import requests
import time
import json
import urllib.parse

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
    # DSM 7.2 보안 정책 준수 헤더
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    })
    
    try:
        # 0단계: API 정보 확인
        st.subheader("0단계: API 정보 조회")
        info_params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": "SYNO.API.Auth"
        }
        info_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=info_params, timeout=10).json()
        st.json(info_res)

        # 1단계: 로그인 시도 (파라미터 조합 최적화)
        st.subheader("1단계: 로그인 시도 (최종 호환성 팩)")
        
        # DSM 7.2.1 Update 8 대응 파라미터
        # passwd에 특수문자가 있을 경우 requests가 자동 인코딩하지만, 
        # 서버 설정에 따라 수동 인코딩이 필요할 수 있음.
        login_data = {
            "api": "SYNO.API.Auth",
            "version": "6", # DSM 7.x 권장 버전
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW, 
            "session": "FileStation",
            "format": "sid",
            "enable_device_token": "no",
            "device_name": "Streamlit_Debug"
        }
        
        start_time = time.time()
        # 시놀로지는 보안상 특정 엔드포인트(entry.cgi vs auth.cgi)에 민감함
        # 0단계에서 entry.cgi라고 했지만, 실제 인증은 auth.cgi에서만 받는 경우도 존재
        target_urls = [
            f"{SYNO_URL}/webapi/entry.cgi",
            f"{SYNO_URL}/webapi/auth.cgi"
        ]
        
        for url in target_urls:
            st.write(f"📡 요청 경로 테스트: {url}")
            # POST 시도
            response = session.post(url, data=login_data, timeout=10)
            st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초 | HTTP: {response.status_code}")
            
            try:
                res_json = response.json()
                st.json(res_json)
                
                if res_json.get("success"):
                    st.success(f"🎉 {url} 경로에서 로그인 성공!")
                    break
                else:
                    code = res_json.get("error", {}).get("code")
                    if code == 400:
                        st.warning(f"해당 경로 400 에러. 다음 경로 혹은 GET 방식으로 전환 시도...")
                        # GET 재시도
                        get_res = session.get(url, params=login_data, timeout=10).json()
                        st.json(get_res)
                        if get_res.get("success"):
                            st.success("🎉 GET 방식으로 성공!")
                            break
            except:
                st.error(f"{url}에서 유효하지 않은 응답")

    except Exception as e:
        st.error(f"🚨 네트워크 에러: {e}")
    finally:
        session.close()

st.divider()
st.info("💡 모든 시도가 400이라면, 시놀로지 제어판 > 보안 > 계정에서 '2단계 인증(OTP)'이 강제로 켜져있는지 확인 필수.")
