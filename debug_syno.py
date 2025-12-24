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
    # DSM 7.2 보안 강화를 위해 표준 브라우저 헤더를 세밀하게 설정
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    
    try:
        # 0단계: API 정보 확인 (이미 성공 확인됨)
        st.subheader("0단계: API 정보 조회")
        info_params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": "SYNO.API.Auth"
        }
        info_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=info_params, timeout=10).json()
        st.json(info_res)

        # 1단계: 로그인 시도
        st.subheader("1단계: 로그인 시도 (인코딩 및 보안 파라미터 강화)")
        
        # 비밀번호 내 특수문자(@ 등) 이슈 방지를 위해 수동 인코딩 수행
        encoded_pw = urllib.parse.quote(SYNO_PW)
        
        # DSM 7.2 최신 버전 공식 파라미터 셋
        # method가 login일 때 passwd는 인코딩된 문자열이어야 함
        login_data = {
            "api": "SYNO.API.Auth",
            "version": "6", # DSM 7.x 공식 권장 버전
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW, # requests.post가 내부적으로 처리하나, 400 에러 시 수동 인코딩 고려
            "session": "FileStation",
            "format": "sid",
            "enable_device_token": "no",
            "otp_code": "" # OTP 미사용 시 빈값 명시
        }
        
        start_time = time.time()
        # 데이터 전송 방식을 명확히 하여 400 에러 차단 시도
        response = session.post(
            f"{SYNO_URL}/webapi/entry.cgi", 
            data=login_data, 
            timeout=10
        )
        
        duration = time.time() - start_time
        st.write(f"⏱️ 소요 시간: {duration:.2f}초 | HTTP 상태: {response.status_code}")
        
        try:
            res_json = response.json()
            st.json(res_json)
            
            if res_json.get("success"):
                st.success("🎉 로그인 성공!")
            else:
                err = res_json.get("error", {})
                code = err.get("code")
                st.error(f"실패 코드: {code}")
                
                # 시놀로지 에러 코드별 가이드
                guide = {
                    400: "파라미터 부족 혹은 형식이 맞지 않음 (API 명칭/버전 확인 필요)",
                    401: "계정 정보 오류 혹은 비밀번호 인코딩 이슈",
                    402: "권한 없음 (File Station 사용 권한 확인)",
                    403: "2단계 인증(OTP) 필요",
                    404: "계정 차단됨"
                }
                st.warning(f"도움말: {guide.get(code, '알 수 없는 에러')}")
                
        except Exception as json_err:
            st.error("JSON 파싱 실패 (서버가 HTML 에러 페이지를 반환했을 가능성 있음)")
            st.code(response.text[:500])

    except Exception as e:
        st.error(f"🚨 네트워크 에러: {e}")
    finally:
        session.close()

st.divider()
st.info("💡 모든 버전에서 400 발생 시 체크: DSM 제어판 > 보안 > 계정 > '2단계 인증이 강제되어 있는지' 확인 요망.")
