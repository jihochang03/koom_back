from __future__ import annotations
from urllib.parse import urlparse
from .models import SupportedSite


def classify_url(url: str) -> dict:
    """
    URL을 분석해 사이트와 URL 유형(product/search/unknown)을 반환한다.
    Returns:
        {
            "url_type": "product" | "search" | "unknown",
            "site": SupportedSite | None,
            "domain": str,
        }
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc.lower().lstrip("www.")
        path = parsed.path or "/"
    except Exception:
        return {"url_type": "unknown", "site": None, "domain": ""}

    site: SupportedSite | None = None
    for s in SupportedSite.objects.filter(is_active=True):
        if hostname == s.domain or hostname.endswith("." + s.domain):
            site = s
            break

    if site is None:
        return {"url_type": "unknown", "site": None, "domain": hostname}

    for pattern in site.product_url_patterns:
        if pattern in path:
            return {"url_type": "product", "site": site, "domain": hostname}

    for pattern in site.search_url_patterns:
        if pattern in path:
            return {"url_type": "search", "site": site, "domain": hostname}

    return {"url_type": "unknown", "site": site, "domain": hostname}
