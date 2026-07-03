import sys; sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')

import requests
import re
import json

# collect/general로 API URL 직접 수집 테스트
api_url = "https://www.hago.kr/goods/allProduct/004000000?order_by=selling&page=1"
sub = requests.post(
    "http://localhost:18080/collect/general",
    json={"url": api_url},
    timeout=90
).json()

html_body = sub.get("html", "")
print(f"html 길이: {len(html_body)}")
print("앞 500자:", html_body[:500])


if __name__ == "__main__":
    _url = sys.argv[1] if len(sys.argv) > 1 else ""
    _r = scrape(_url)
    print(__import__("json").dumps(_r, ensure_ascii=False, indent=2))
