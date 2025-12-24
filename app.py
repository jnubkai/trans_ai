import streamlit as st
import requests

st.set_page_config(layout="wide", page_title="AI 실시간 통역 시스템")

# 1. Secrets 로드
try:
    CRED = st.secrets["credentials"]
    SYNO_ID, SYNO_PW = CRED["SYNO_ID"], CRED["SYNO_PW"]
    SYNO_URL = CRED["SYNO_URL"]
except:
    st.error("Secrets 설정을 확인해 주세요.")
    st.stop()

st.title("🎤 실시간 강의 통역 시스템")

with st.sidebar:
    st.header("시놀로지 연동")
    
    # 세션 유지를 위한 변수 설정
    if st.button("파일 목록 새로고침"):
        # 1단계: 로그인하여 SID 획득
        auth_url = f"{SYNO_URL}/webapi/auth.cgi?api=SYNO.API.Auth&version=3&method=login&account={SYNO_ID}&passwd={SYNO_PW}&session=FileStation&format=cookie"
        
        try:
            auth_res = requests.get(auth_url, timeout=5).json()
            if auth_res.get("success"):
                sid = auth_res["data"]["sid"]
                st.success("✅ 로그인 성공")
                
                # 2단계: 특정 경로의 폴더 목록 가져오기
                # 경로를 'rlrc' 폴더 내부의 '509 자료'로 지정
                list_url = f"{SYNO_URL}/webapi/entry.cgi?api=SYNO.FileStation.List&version=2&method=list&folder_path=/rlrc/509 자료/&_sid={sid}"
                list_res = requests.get(list_url, timeout=5).json()
                
                if list_res.get("success"):
                    # 폴더만 필터링하여 리스트업
                    folders = [f['name'] for f in list_res['data']['files'] if f['isdir']]
                    st.session_state['folder_list'] = folders
                    st.info(f"📁 {len(folders)}개의 주제를 찾았습니다.")
                else:
                    st.error(f"❌ 목록 조회 실패: {list_res.get('error')}")
            else:
                st.error("❌ 로그인 실패: ID/PW를 확인하세요.")
        except Exception as e:
            st.error(f"접속 에러: {e}")

    # 가져온 목록을 선택창에 표시
    display_list = st.session_state.get('folder_list', ["먼저 새로고침을 눌러주세요"])
    selected_subject = st.selectbox("오늘의 강의 주제 선택", display_list)

# 메인 화면
st.subheader(f"현재 선택된 강의: {selected_subject}")
col1, col2 = st.columns(2)
with col1: st.info("### 🇬🇧 English"); st.write("Translation will appear here.")
with col2: st.success("### 🇰🇷 한국어"); st.write("실시간 자막이 표시됩니다.")
