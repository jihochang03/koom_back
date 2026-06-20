import requests, time

def scrape(url: str):
    for i in range(10):
        time.sleep(8)
        try:
            resp = requests.post(
                "http://localhost:18080/collect/general",
                json={"url": url},
                timeout=180,
            )
            print(f"[try {i+1}] status={resp.status_code} body_len={len(resp.text)}")
            if resp.status_code == 200:
                data = resp.json()
                html = data.get("html","")
                print("html len:", len(html))
                idx = html.find("<title")
                if idx >= 0:
                    print("title snip:", html[idx:idx+300])
                return data
            else:
                print("body:", resp.text[:200])
        except Exception as e:
            print("err:", repr(e))
    return None

if __name__ == "__main__":
    scrape("https://smartstore.naver.com/hngold/products/8452920690")
