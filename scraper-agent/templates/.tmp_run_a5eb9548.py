
import requests
import json

def scrape(url: str) -> dict:
    resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=30
    )
    # 서버 응답 인코딩 정보 출력
    print("resp.encoding:", resp.encoding)
    print("resp.apparent_encoding:", resp.apparent_encoding)
    print("Content-Type header:", resp.headers.get("Content-Type"))
    
    # HTML 첫 500자 raw bytes
    raw_bytes = resp.content[:200]
    print("raw_bytes[:200]:", raw_bytes)
    
    # JSON 파싱
    data = resp.json()
    html = data.get("html", "")
    print("html 앞 300자:", repr(html[:300]))
    
    return {"debug": "ok"}


if __name__ == "__main__":
    import sys
    _url = sys.argv[1] if len(sys.argv) > 1 else ""
    _r = scrape(_url)
    print(__import__("json").dumps(_r, ensure_ascii=False, indent=2))
