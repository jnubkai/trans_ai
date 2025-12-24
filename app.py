import streamlit as st
import requests

st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 1. Secrets 로드
try:
    CRED = st.secrets["credentials"]
    SYNO_ID, SYNO_PW = CRED["SYNO_ID"], CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"].rstrip('/') # 주소 끝 슬래시 제거
except:
    st.error("Secrets 설정을 확인해 주세요.")
    st.stop()

st.title("🎤 실시간 강의 통역 시스템")

with st.sidebar:
    st.header("시놀로지 연동")
    
    if st.button("파일 목록 새로고침"):
        # 로그인 URL
        auth_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
        
        try:
            with st.spinner("시놀로지 통신 중..."):
                # 1단계: 로그인 시도
                auth_res = requests.get(auth_url, timeout=5).json()
                
                if auth_res.get("success"):
                    sid = auth_res["data"]["sid"]
                    
                    # 2단계: 알려주신 'RLRC/509 자료' 경로 테스트
                    # 시놀로지 API 특성상 폴더명 사이의 공백을 처리해야 함
                    target_path = "/RLRC/509 자료"
                    list_url = f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.FileStation.List&version=2&method=list&folder_path={target_path}&_sid={sid}"
                    
                    list_res = requests.get(list_url, timeout=5).json()
                    
                    if list_res.get("success"):
                        folders = [f['name'] for f in list_res['data']['files'] if f['isdir']]
                        st.session_state['folder_list'] = folders
                        st.success(f"✅ {len(folders)}개의 주제를 찾았습니다.")
                    else:
                        # 경로가 틀렸을 경우 에러 코드 확인용
                        st.error(f"❌ 목록 조회 실패 (에러코드: {list_res.get('error')})")
                        st.info("Tip: 'RLRC' 폴더가 최상위(공유폴더)인지 확인해 보세요.")
                else:
                    st.error(f"❌ 로그인 실패 (에러코드: {auth_res.get('error')})")
        except Exception as e:
            st.error(f"접속 에러: {e}")

    display_list = st.session_state.get('folder_list', ["목록이 비어있음"])
    selected_subject = st.selectbox("오늘의 강의 주제 선택", display_list)

# 메인 화면 레이아웃
st.subheader(f"현재 선택된 강의: {selected_subject}")
col1, col2 = st.columns(2)
with col1: st.info("### 🇬🇧 English"); st.write("Waiting for speech...")
with col2: st.success("### 🇰🇷 한국어"); st.write("자막 표시 영역")
