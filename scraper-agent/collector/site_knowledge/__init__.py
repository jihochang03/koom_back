"""
Per-site knowledge store.
JSON file per domain: collector/site_knowledge/<domain>.json

Schema:
{
  "domain": "example.com",
  "created_at": "ISO",
  "updated_at": "ISO",
  "captcha": {
    "type": "image_text|math|select",
    "input_selector": "#captcha_answer",
    "submit_selector": "button.submit",   // null if Enter works
    "solved_count": 3,
    "last_solved": "ISO"
  },
  "collection": {
    "notes": "Options loaded via XHR after 2s",
    "extra_clicks": [".option-btn"],
    "wait_for_selector": ".product-detail",
    "network_patterns": ["api/v1/products"]
  }
}
"""
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_LOCK = threading.Lock()


def _safe_domain(domain: str) -> str:
    return domain.replace('/', '_').replace(':', '_').replace('*', '_')


def _path(domain: str) -> Path:
    return _HERE / f"{_safe_domain(domain)}.json"


def load(domain: str) -> Optional[dict]:
    p = _path(domain)
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning('[SiteKnowledge] load 실패 (%s): %s', domain, e)
        return None


def save(domain: str, updates: dict):
    with _LOCK:
        p = _path(domain)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                pass
        # Deep merge
        for k, v in updates.items():
            if isinstance(v, dict) and isinstance(existing.get(k), dict):
                existing[k] = {**existing[k], **v}
            else:
                existing[k] = v
        now = time.strftime('%Y-%m-%dT%H:%M:%S')
        existing['domain'] = domain
        existing.setdefault('created_at', now)
        existing['updated_at'] = now
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info('[SiteKnowledge] 저장: %s → %s', domain, p.name)


def update_captcha(domain: str, captcha_info: dict):
    """CAPTCHA 해결 후 패턴 저장."""
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    existing = load(domain) or {}
    prev_count = (existing.get('captcha') or {}).get('solved_count', 0)
    save(domain, {
        'captcha': {
            **captcha_info,
            'solved_count': prev_count + 1,
            'last_solved': now,
        }
    })


def update_collection(domain: str, collection_info: dict):
    """수집 패턴(클릭 힌트, wait 셀렉터 등) 저장."""
    save(domain, {'collection': collection_info})


def get_captcha(domain: str) -> Optional[dict]:
    return (load(domain) or {}).get('captcha')


def get_collection(domain: str) -> Optional[dict]:
    return (load(domain) or {}).get('collection')


def list_domains() -> list:
    return [p.stem for p in _HERE.glob('*.json')]
