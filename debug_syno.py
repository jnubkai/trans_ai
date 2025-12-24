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
    # DSM 7.2 보안 정책상 User-Agent는 필수임
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    try:
        # 0단계: API 정보 확인 (성공 확인됨)
        st.subheader("0단계: API 정보 조회")
        info_params = {
            "api": "SYNO.API.Info",
            "version": "1",
            "method": "query",
            "query": "SYNO.API.Auth"
        }
        info_res = session.get(f"{SYNO_URL}/webapi/entry.cgi", params=info_params, timeout=10).json()
        st.json(info_res)

        # 1단계: 로그인 시도 (최종 호환성 팩 적용)
        st.subheader("1단계: 로그인 시도 (파라미터 강제 조정)")
        
        # DSM 7.2.1 Update 8에서 400 에러를 피하기 위한 최후의 파라미터 조합
        # passwd 내 특수문자(@)를 안전하게 전달하기 위해 수동 인코딩 시도 여부 결정
        login_data = {
            "api": "SYNO.API.Auth",
            "version": "3", # 6, 7 버전에서 실패 시 가장 안정적인 3으로 고정 테스트
            "method": "login",
            "account": SYNO_ID,
            "passwd": SYNO_PW, 
            "session": "FileStation",
            "format": "sid"
        }
        
        start_time = time.time()
        # GET 방식과 POST 방식 중 서버가 더 잘 받아들이는 POST로 유지하되, 데이터 구조 단순화
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
                
                # 400 에러 발생 시 최후의 수단: GET 방식으로 재시도
                if code == 400:
                    st.warning("POST 거부됨. GET 방식으로 즉시 재시도...")
                    retry_res = session.get(
                        f"{SYNO_URL}/webapi/entry.cgi", 
                        params=login_data, 
                        timeout=10
                    ).json()
                    st.json(retry_res)
                
                guide = {
                    400: "파라미터 부적합 (API 명칭/버전 불일치 혹은 필수 인코딩 누락)",
                    401: "계정 정보 오류",
                    402: "권한 없음",
                    403: "2단계 인증 필요",
                    404: "계정 차단"
                }
                st.warning(f"도움말: {guide.get(code, '알 수 없는 에러')}")
                
        except Exception:
            st.error("서버 응답이 JSON 형식이 아님 (경로 혹은 포트 설정 확인 필요)")
            st.code(response.text[:500])

    except Exception as e:
        st.error(f"🚨 네트워크 에러: {e}")
    finally:
        session.close()

st.divider()
st.info("💡 400 에러가 계속된다면 시놀로지 패스워드에서 특수문자를 빼고 임시로 테스트해 보는 것을 추천함.")
