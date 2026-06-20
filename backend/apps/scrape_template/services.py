"""
Template services — 고객사 DB가 템플릿의 진실의 원천.

scraper-agent는 stateless 크롤 라이브러리로만 사용.
- 빌드 시: scraper-agent가 코드를 생성·스트리밍 → Django DB에 저장
- 크롤 시: Django DB에서 코드를 꺼내 scraper-agent 요청에 포함
"""
import json
import requests
from django.conf import settings
from .models import SiteTemplate


SCRAPER_BASE_URL = settings.SCRAPER_AGENT_BASE_URL
TIMEOUT = settings.SCRAPER_AGENT_TIMEOUT


class ScraperAgentError(Exception):
    pass


# ── DB-based template management ─────────────────────────────────────────────

def list_templates() -> list:
    return [
        {
            "domain": t.domain,
            "filename": t.filename or f"{t.domain}_{t.page_type}.py",
            "page_type": t.page_type,
            "category": t.category,
            "updated_at": t.updated_at.isoformat(),
        }
        for t in SiteTemplate.objects.all()
    ]


def get_template(domain_or_filename: str) -> dict:
    """도메인 또는 파일명으로 템플릿 조회."""
    domain = (
        domain_or_filename
        .removesuffix(".py")
        .removesuffix("_detail")
        .removesuffix("_list")
        .removesuffix("_both")
    )
    try:
        t = SiteTemplate.objects.get(domain=domain)
    except SiteTemplate.DoesNotExist:
        raise ScraperAgentError(f"템플릿 없음: {domain_or_filename}")
    return {
        "domain": t.domain,
        "filename": t.filename or f"{t.domain}_{t.page_type}.py",
        "content": t.code,
        "page_type": t.page_type,
    }


def delete_template(domain_or_filename: str) -> dict:
    domain = (
        domain_or_filename
        .removesuffix(".py")
        .removesuffix("_detail")
        .removesuffix("_list")
        .removesuffix("_both")
    )
    deleted, _ = SiteTemplate.objects.filter(domain=domain).delete()
    if not deleted:
        raise ScraperAgentError(f"템플릿 없음: {domain_or_filename}")
    return {"success": True}


def list_templates_by_domain(domain: str) -> list:
    """도메인에 해당하는 템플릿 목록 (병합 컨텍스트용)."""
    return [
        {
            "filename": t.filename or f"{t.domain}_{t.page_type}.py",
            "content": t.code,
        }
        for t in SiteTemplate.objects.filter(domain__icontains=domain)
    ]


def _save_template_from_tool_call(inp: dict, category: str) -> None:
    """save_template 툴 호출 입력으로부터 DB에 저장."""
    domain = inp.get("domain", "").strip()
    code = inp.get("code", "").strip()
    if not domain or not code:
        return
    page_type = inp.get("page_type", "both")
    filename = f"{domain.replace('.', '_')}_{page_type}.py"
    SiteTemplate.objects.update_or_create(
        domain=domain,
        defaults={
            "filename": filename,
            "code": code,
            "page_type": page_type,
            "category": category,
        },
    )


# ── scraper-agent call ────────────────────────────────────────────────────────

def build_template(
    url: str,
    category: str = "shopping",
    page_type: str = "detail",
    message: str = "",
    existing_templates: list = None,
) -> dict:
    """
    scraper-agent에 템플릿 빌드를 요청한다.
    SSE 스트림의 save_template 툴 호출을 캡처해 고객사 DB에 저장.
    """
    payload: dict = {"url": url, "category": category, "page_type": page_type}
    if message:
        payload["message"] = message
    if existing_templates:
        payload["existingTemplates"] = existing_templates
        payload["mergeWithExisting"] = True

    try:
        response = requests.post(
            f"{SCRAPER_BASE_URL}/api/template/build",
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
    current_event = None

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line

        if decoded.startswith("event:"):
            current_event = decoded[6:].strip()
        elif decoded.startswith("data:"):
            raw = decoded[5:].strip()
            try:
                parsed = json.loads(raw)
                last_data = parsed

                if current_event == "tool_call" and isinstance(parsed, dict):
                    if parsed.get("name") == "save_template":
                        _save_template_from_tool_call(
                            parsed.get("input", {}), category
                        )

                if current_event == "done":
                    break
            except json.JSONDecodeError:
                pass

    if last_data is None:
        raise ScraperAgentError("scraper-agent에서 유효한 응답을 받지 못했습니다.")

    return last_data
