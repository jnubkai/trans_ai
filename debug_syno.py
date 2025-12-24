import streamlit as st
import requests
import time
import json

st.set_page_config(page_title="시놀로지 접속 디버깅")

st.title("🔍 시놀로지 접속 상세 디버깅")

# Secrets 로드 확인 (가장 유연한 방식으로 수정)
try:
    # 1. credentials 섹션이 있는지 먼저 확인
    if "credentials" in st.secrets:
        CRED = st.secrets["credentials"]
    else:
        # 2. 섹션 없이 루트에 바로 적었을 경우를 대비해 전체를 CRED로 간주
        CRED = st.secrets

    # 값 할당 (KeyError 방지를 위해 .get() 사용)
    SYNO_ID = CRED.get("SYNO_ID")
    SYNO_PW = CRED.get("SYNO_PW")
    SYNO_URL = CRED.get("SYNO_URL", "").rstrip('/')
    
    if not all([SYNO_ID, SYNO_PW, SYNO_URL]):
        st.error("Secrets 내부에 SYNO_ID, SYNO_PW, SYNO_URL 중 누락된 값이 있음")
        st.json(list(CRED.keys())) # 현재 인식된 키 목록 표시
        st.stop()
        
    st.success(f"설정 로드 완료: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 접근 중 치명적 에러: {e}")
    st.info("Streamlit Cloud의 Secrets 설정 창에 [credentials] 섹션 이름이 정확한지 확인 바람")
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
1. Secrets 설정 시 첫 줄에 `[credentials]`가 정확히 들어갔는지 확인.
2. 값 앞뒤에 따옴표(`"`)가 누락되지 않았는지 확인.
3. 저장(Save) 버튼을 누른 뒤 앱이 리로드될 때까지 5초 정도 대기.
""")
