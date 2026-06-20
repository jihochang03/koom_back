
import requests
from bs4 import BeautifulSoup
import json
import time

def scrape(url: str) -> dict:
    """G마켓 상품 페이지 스크레이퍼 - 수집 서버 대기 포함"""
    import re
    
    # goodscode 추출
    match = re.search(r'goodscode=(\d+)', url)
    goodscode = match.group(1) if match else "3077560706"
    canonical_url = f"https://item.gmarket.co.kr/Item?goodscode={goodscode}"
    
    # 수집 서버 대기 (최대 60초)
    max_wait = 60
    wait_interval = 5
    html = None
    
    for i in range(max_wait // wait_interval):
        collect_resp = requests.post(
            "http://localhost:18080/collect/general",
            json={"url": canonical_url},
            timeout=90
        )
        print(f"[{i+1}] status={collect_resp.status_code}")
        if collect_resp.status_code == 200:
            data = collect_resp.json()
            html = data.get("html", "")
            print(f"HTML length: {len(html)}")
            break
        else:
            if "busy" in collect_resp.text:
                print(f"Server busy, waiting {wait_interval}s...")
                time.sleep(wait_interval)
            else:
                print(f"Error: {collect_resp.text[:200]}")
                break
    
    if not html:
        return {"error": "수집 실패"}
    
    # 파싱 시작
    soup = BeautifulSoup(html, "html.parser")
    
    # 타이틀
    title = ""
    title_el = (soup.select_one(".itemtit") or 
                soup.select_one("h1.tit_item") or 
                soup.select_one(".item_name") or
                soup.select_one("title"))
    if title_el:
        title = title_el.get_text(strip=True)
    print(f"Title: {title}")
    print(f"\n--- HTML snippet ---\n{html[:2000]}")
    
    return {"title": title, "html_length": len(html)}



if __name__ == "__main__":
    import sys
    _url = sys.argv[1] if len(sys.argv) > 1 else ""
    _r = scrape(_url)
    print(__import__("json").dumps(_r, ensure_ascii=False, indent=2))
