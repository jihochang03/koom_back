import json
import requests
from django.conf import settings

from apps.utils import extract_domain


SCRAPER_BASE_URL = settings.SCRAPER_AGENT_BASE_URL
TIMEOUT = settings.SCRAPER_AGENT_TIMEOUT


class ScraperAgentError(Exception):
    pass


def analyze_url(
    url: str,
    category: str = "shopping",
    page_type: str = "auto",
    max_items: int = None,
    collect_detail: bool = True,
) -> dict:
    """
    scraper-agent /api/analyze 호출.
    고객사 DB에 저장된 템플릿이 있으면 요청에 포함해 scraper-agent가
    Claude 없이 빠르게 실행할 수 있도록 한다.

    page_type:
      - "auto"   : scraper-agent가 목록/상세 자동 판단
      - "list"   : 목록 페이지로 처리 → 페이지 내 모든 상품 수집
      - "detail" : 상세 페이지로 처리 → 단일 상품 수집
    """
    from apps.scrape_template.models import SiteTemplate

    domain = extract_domain(url)
    template_code = None
    template_name = None
    try:
        tmpl = SiteTemplate.objects.get(domain=domain)
        template_code = tmpl.code
        template_name = tmpl.filename or f"{domain}_{tmpl.page_type}.py"
    except SiteTemplate.DoesNotExist:
        pass

    payload = {
        "url": url,
        "category": category,
        "pageType": page_type,
        "collectDetail": collect_detail,
    }
    if template_code:
        payload["template"] = template_code
        payload["templateName"] = template_name
    if max_items is not None:
        payload["maxItems"] = max_items

    try:
        response = requests.post(
            f"{SCRAPER_BASE_URL}/api/analyze",
            json=payload,
            timeout=TIMEOUT,
            stream=True,
            headers={"Accept": "text/event-stream"},
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ScraperAgentError("scraper-agent 서버에 연결할 수 없습니다.")
    except requests.exceptions.Timeout:
        raise ScraperAgentError("scraper-agent 요청 시간이 초과되었습니다.")
    except requests.exceptions.HTTPError as e:
        raise ScraperAgentError(f"scraper-agent 오류: {e}")

    last_data = None
    template_used = ""

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        if decoded.startswith("data:"):
            raw = decoded[5:].strip()
            try:
                parsed = json.loads(raw)
                last_data = parsed
                if isinstance(parsed, dict):
                    template_used = parsed.get("templateUsed", parsed.get("template", ""))
            except json.JSONDecodeError:
                pass

    if last_data is None:
        raise ScraperAgentError("scraper-agent에서 유효한 응답을 받지 못했습니다.")

    items_count = _count_items(last_data)
    return {"data": last_data, "template_used": template_used, "items_count": items_count}


def _count_items(data) -> int:
    """scraper-agent 응답에서 아이템 수 추정"""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("items", "products", "results", "data"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return 1
