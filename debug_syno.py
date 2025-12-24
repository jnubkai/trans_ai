import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
import time
import urllib.parse

st.set_page_config(page_title="시놀로지 WebDAV 연결 테스트")

st.title("🌐 시놀로지 WebDAV 연결 테스트 (대안 모드)")

# 1. Secrets 로드 및 WebDAV 설정
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
        # URL에서 기존 포트가 있다면 제거하고 7605로 재구성하거나 확인하는 로직
        SYNO_URL = SYNO_URL.rstrip('/')
        if ":7655" in SYNO_URL:
            SYNO_URL = SYNO_URL.replace(":7655", ":7605")
        elif ":7605" not in SYNO_URL:
            # 포트가 명시되지 않은 경우 강제 지정 (필요 시)
            pass

    st.success(f"✅ 설정 로드 성공: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 접근 중 에러: {e}")
    st.stop()

st.info("""
**💡 WebDAV 사용 전 체크리스트 (시놀로지 설정)**
1. 시놀로지 패키지 센터에서 **'WebDAV Server'** 설치 및 실행 중인지 확인.
2. WebDAV 설정에서 **HTTP(7605)** 포트가 활성화되었는지 확인.
3. 공유기(iptime 등)에서 **외부 포트 7605**가 시놀로지의 WebDAV 내부 포트(기본 5005 등)로 **포트포워딩** 되어 있는지 확인.
""")

if st.button("WebDAV 방식으로 목록 조회 시작"):
    # WebDAV는 표준 PROPFIND 메서드를 사용함
    headers = {
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8"
    }
    
    # PROPFIND 요청을 위한 기본 XML 바디
    body = """<?xml version="1.0" encoding="utf-8" ?>
    <D:propfind xmlns:D="DAV:">
      <D:prop>
        <D:displayname/>
        <D:resourcetype/>
      </D:prop>
    </D:propfind>"""

    try:
        st.subheader("1단계: WebDAV 연결 시도 (Port: 7605)")
        start_time = time.time()
        
        # 타겟 경로: /RLRC/509 자료 (URL 인코딩 처리)
        target_path = urllib.parse.quote("/RLRC/509 자료")
        full_url = f"{SYNO_URL}{target_path}"
        
        st.write(f"📡 요청 URL: {full_url}")
        
        # WebDAV는 Basic Auth를 주로 사용함
        response = requests.request(
            "PROPFIND", 
            full_url, 
            auth=HTTPBasicAuth(SYNO_ID, SYNO_PW),
            headers=headers,
            data=body,
            timeout=15
        )
        
        st.write(f"⏱️ 소요 시간: {time.time() - start_time:.2f}초 | HTTP 상태: {response.status_code}")

        if response.status_code in [200, 207]:
            st.success("🎉 WebDAV 접속 및 목록 조회 성공!")
            
            # XML 응답 파싱
            root = ET.fromstring(response.content)
            ns = {'d': 'DAV:'}
            folders = []
            
            for resp in root.findall('d:response', ns):
                href = resp.find('d:href', ns).text
                propstat = resp.find('d:propstat', ns)
                prop = propstat.find('d:prop', ns)
                resourcetype = prop.find('d:resourcetype', ns)
                
                if resourcetype is not None and resourcetype.find('d:collection', ns) is not None:
                    name = urllib.parse.unquote(href).rstrip('/').split('/')[-1]
                    if name and name != "509 자료":
                        folders.append(name)
            
            st.write("### 📂 발견된 폴더 목록")
            st.write(folders)
            
        elif response.status_code == 401:
            st.error("🚨 인증 실패: 아이디 또는 비밀번호가 틀렸거나 WebDAV 권한이 없습니다.")
        elif response.status_code == 405:
            st.error("🚨 메서드 허용 안 됨: 시놀로지에서 WebDAV 서비스가 꺼져 있거나 포트포워딩 설정 오류일 수 있습니다.")
        else:
            st.error(f"🚨 오류 발생 (상태 코드: {response.status_code})")
            st.text(response.text)

    except Exception as e:
        st.error(f"🚨 네트워크 에러: {e}")

st.divider()
st.caption("포트 7605를 사용하여 WebDAV 프로토콜 연결을 테스트함.")
