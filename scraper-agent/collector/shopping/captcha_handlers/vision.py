"""
VisionCaptchaHandler — Claude Vision으로 캡차를 분석하는 범용 핸들러.
알려진 패턴이 없을 때 fallback으로 사용.
"""
from __future__ import annotations
import base64
import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

from .base import CaptchaAnalysis, CaptchaHandler

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a CAPTCHA analysis expert. "
    "Given a screenshot and page HTML, determine if a CAPTCHA is present and how to solve it. "
    "Respond with ONLY a JSON object, no markdown fences."
)

_USER_TMPL = """\
HTML snippet (first 3000 chars):
{html}

Return JSON:
{{
  "has_captcha": true/false,
  "captcha_type": "math|image_text|select|checkbox|unknown",
  "interpretation": "한국어로 캡차 설명 및 정답",
  "answer": "정답 문자열",
  "input_selector": "CSS selector for the answer input",
  "submit_selector": "CSS selector for submit button, or empty string if Enter works",
  "confidence": "high|medium|low"
}}"""


def _call_claude(screenshot_b64: str, html: str) -> Optional[dict]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": _USER_TMPL.format(html=html[:3000])},
                ],
            }],
        )
        text = resp.content[0].text if resp.content else ""
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return None
        return json.loads(m.group())
    except Exception as e:
        logger.warning("[VisionCaptchaHandler] Claude 호출 실패: %s", e)
        return None


def _take_screenshot(driver) -> str:
    """Return base64-encoded PNG of the current viewport."""
    return base64.b64encode(driver.get_screenshot_as_png()).decode()


def _fill_and_submit(driver, analysis: CaptchaAnalysis) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    try:
        el = None
        if analysis.input_selector:
            try:
                el = driver.find_element(By.CSS_SELECTOR, analysis.input_selector)
            except Exception:
                pass

        if el is None:
            # Fallback: first visible text/number input
            for sel in ('input[type="text"]', 'input[type="number"]', 'input:not([type])'):
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    break
                except Exception:
                    pass

        if el is None:
            return False

        el.clear()
        el.send_keys(analysis.answer)
        time.sleep(0.3)

        if analysis.submit_selector:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, analysis.submit_selector)
                btn.click()
            except Exception:
                el.send_keys(Keys.RETURN)
        else:
            el.send_keys(Keys.RETURN)

        time.sleep(2)

        # Verify: CAPTCHA input gone
        try:
            driver.find_element(By.CSS_SELECTOR, analysis.input_selector)
            return False  # still there
        except Exception:
            return True   # gone — success
    except Exception as e:
        logger.warning("[VisionCaptchaHandler] fill/submit 실패: %s", e)
        return False


class VisionCaptchaHandler(CaptchaHandler):
    """Catch-all CAPTCHA handler using Claude Haiku vision."""

    @property
    def name(self) -> str:
        return "VisionCaptcha"

    def detect(self, html: str) -> bool:
        # Always True — this is the final fallback
        return True

    def analyze(self, driver, screenshot_b64: str) -> Optional[CaptchaAnalysis]:
        html = driver.page_source
        result = _call_claude(screenshot_b64, html)
        if not result or not result.get("has_captcha"):
            return None

        return CaptchaAnalysis(
            handler_name=self.name,
            captcha_type=result.get("captcha_type", "unknown"),
            interpretation=result.get("interpretation", ""),
            answer=result.get("answer", ""),
            input_selector=result.get("input_selector") or 'input[type="text"]',
            submit_selector=result.get("submit_selector", ""),
            confidence=result.get("confidence", "medium"),
            # 분석 시점 스크린샷 해시 저장 — solve()에서 갱신 여부 확인용
            extra={"screenshot_hash": hashlib.md5(screenshot_b64.encode()).hexdigest()},
        )

    def solve(self, driver, analysis: CaptchaAnalysis) -> bool:
        # Claude 응답 대기 중 캡차가 갱신됐을 수 있으므로 직전에 재확인
        fresh_b64 = _take_screenshot(driver)
        fresh_hash = hashlib.md5(fresh_b64.encode()).hexdigest()
        orig_hash = analysis.extra.get("screenshot_hash", "")

        if orig_hash and fresh_hash != orig_hash:
            logger.info("[VisionCaptchaHandler] 캡차 이미지 변경 감지 — 새 스크린샷으로 재분석")
            html = driver.page_source
            result = _call_claude(fresh_b64, html)
            if result and result.get("has_captcha") and result.get("answer"):
                analysis = CaptchaAnalysis(
                    handler_name=self.name,
                    captcha_type=result.get("captcha_type", "unknown"),
                    interpretation=result.get("interpretation", ""),
                    answer=result.get("answer", ""),
                    input_selector=result.get("input_selector") or analysis.input_selector,
                    submit_selector=result.get("submit_selector", "") or analysis.submit_selector,
                    confidence=result.get("confidence", "medium"),
                    extra={"screenshot_hash": fresh_hash},
                )
                logger.info("[VisionCaptchaHandler] 재분석 완료: %s", analysis.interpretation)
            else:
                logger.warning("[VisionCaptchaHandler] 재분석 실패 — 기존 답 사용 (위험)")

        return _fill_and_submit(driver, analysis)
