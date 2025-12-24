import streamlit as st
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import xml.etree.ElementTree as ET
import time
import urllib.parse
import base64

st.set_page_config(page_title="시놀로지 WebDAV 연결 테스트")

st.title("🌐 시놀로지 WebDAV 연결 테스트 (포트포워딩 대응)")

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
        SYNO_URL = SYNO_URL.rstrip('/')
        # 외부 포트 7605 고정 처리 (iptime 외부 포트)
        if ":7655" in SYNO_URL:
            SYNO_URL = SYNO_URL.replace(":7655", ":7605")
        elif ":7605" not in SYNO_URL:
            parsed_url = urllib.parse.urlparse(SYNO_URL)
            base_netloc = parsed_url.netloc.split(':')[0]
            SYNO_URL = f"{parsed_url.scheme}://{base_netloc}:7605"

    st.success(f"✅ 설정 로드 성공: {SYNO_URL}")
except Exception as e:
    st.error(f"Secrets 접근 중 에러: {e}")
    st.stop()

st.info(f"""
**💡 네트워크 구조 확인**
- **외부 접속 주소**: {SYNO_URL}
- **포트포워딩**: iptime(7605) → 시놀로지(5005)
- **인증 이슈**: HTTP(비암호화) 환경이므로 시놀로지 WebDAV 설정에서 'HTTP 활성화' 및 'Basic 인증 허용' 여부가 중요함.
""")

if st.button("WebDAV 인증 방식 교차 테스트 시작"):
    # 공용 헤더 및 경로 설정
    target_path = "/RLRC/509 자료"
    encoded_path = urllib.parse.quote(target_path)
    full_url = f"{SYNO_URL}{encoded_path}"
    
    headers = {
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    body = """<?xml version="1.0" encoding="utf-8" ?>
    <D:propfind xmlns:D="DAV:">
      <D:prop><D:displayname/><D:resourcetype/></D:prop>
    </D:propfind>"""

    # 테스트할 인증 방식 목록
    auth_methods = [
        ("Basic Auth (Preemptive)", "headers_only"),
        ("Basic Auth (Standard)", HTTPBasicAuth(SYNO_ID, SYNO_PW)),
        ("Digest Auth", HTTPDigestAuth(SYNO_ID, SYNO_PW))
    ]

    for name, auth_obj in auth_methods:
        st.write(f"--- 테스트 중: {name} ---")
        try:
            current_headers = headers.copy()
            current_auth = None

            if name == "Basic Auth (Preemptive)":
                # 인증 정보를 헤더에 미리 포함 (가장 권장되는 방식)
                auth_str = f"{SYNO_ID}:{SYNO_PW}"
                encoded_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
                current_headers["Authorization"] = f"Basic {encoded_auth}"
            else:
                current_auth = auth_obj

            response = requests.request(
                "PROPFIND", 
                full_url, 
                headers=current_headers,
                auth=current_auth,
                data=body,
                timeout=10
            )

            st.write(f"HTTP 상태: {response.status_code}")

            if response.status_code in [200, 207]:
                st.success(f"🎉 {name} 방식으로 접속 성공!")
                root = ET.fromstring(response.content)
                ns = {'d': 'DAV:'}
                folders = [urllib.parse.unquote(r.find('d:href', ns).text).rstrip('/').split('/')[-1] 
                           for r in root.findall('d:response', ns) if r.find('d:propstat/d:prop/d:resourcetype/d:collection', ns) is not None]
                st.write(f"발견된 항목: {len(folders)}개")
                break 
            elif response.status_code == 401:
                st.warning(f"{name} 인증 실패")
            else:
                st.error(f"기타 에러: {response.status_code}")
                
        except Exception as e:
            st.error(f"실행 중 에러: {e}")

st.divider()
st.caption("외부 7605 포트를 통해 시놀로지 내부 5005 포트로 연결되는 환경을 테스트함.")
