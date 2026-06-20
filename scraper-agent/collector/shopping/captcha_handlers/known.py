"""
KnownPatternHandler — site_knowledge JSON에 저장된 패턴으로 캡차를 푸는 핸들러.
VisionCaptchaHandler보다 먼저 시도되어야 한다 (등록 순서 주의).
"""
from __future__ import annotations
import logging
import sys
import os
import time
from typing import Optional

from .base import CaptchaAnalysis, CaptchaHandler

# site_knowledge 모듈 경로 보장 (collector/ 루트)
_COLLECTOR_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _COLLECTOR_DIR not in sys.path:
    sys.path.insert(0, _COLLECTOR_DIR)

import site_knowledge  # noqa: E402

logger = logging.getLogger(__name__)


def _fill_and_submit(driver, analysis: CaptchaAnalysis) -> bool:
    """Reuse the same fill logic — avoids circular import from vision.py."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    try:
        el = driver.find_element(By.CSS_SELECTOR, analysis.input_selector)
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
        try:
            driver.find_element(By.CSS_SELECTOR, analysis.input_selector)
            return False
        except Exception:
            return True
    except Exception as e:
        logger.warning("[KnownPatternHandler] fill/submit 실패: %s", e)
        return False


class KnownPatternHandler(CaptchaHandler):
    """
    Uses stored site_knowledge to skip Claude Vision when a known pattern exists.
    detect() checks if site_knowledge has a captcha entry with a known input_selector.
    analyze() reconstructs a CaptchaAnalysis from the stored pattern (answer blank —
    the actual answer must still be solved by Vision; this handler just supplies selectors).

    NOTE: This handler does NOT supply the answer itself — it just pre-fills selectors
    so that when Vision fails, the correct selectors are already known.  The real value
    is that on *subsequent* visits Vision gets the right selector hint immediately.
    """

    def __init__(self, domain: str):
        self._domain = domain

    @property
    def name(self) -> str:
        return "KnownPattern"

    def detect(self, html: str) -> bool:
        captcha_info = site_knowledge.get_captcha(self._domain)
        if not captcha_info:
            return False
        # Only activate if we have a known input selector
        return bool(captcha_info.get("input_selector"))

    def analyze(self, driver, screenshot_b64: str) -> Optional[CaptchaAnalysis]:
        captcha_info = site_knowledge.get_captcha(self._domain)
        if not captcha_info:
            return None

        input_sel = captcha_info.get("input_selector", "")
        if not input_sel:
            return None

        # We know the selectors but still need Vision to get the actual answer.
        # Delegate answer resolution to VisionCaptchaHandler, but return a partial
        # analysis with the known selectors so Vision can override just the answer field.
        from .vision import _call_claude, _take_screenshot
        html = driver.page_source
        result = _call_claude(screenshot_b64, html)
        if not result or not result.get("has_captcha"):
            return None

        return CaptchaAnalysis(
            handler_name=self.name,
            captcha_type=captcha_info.get("type", result.get("captcha_type", "unknown")),
            interpretation=result.get("interpretation", ""),
            answer=result.get("answer", ""),
            # Prefer stored selectors over vision guess
            input_selector=input_sel,
            submit_selector=captcha_info.get("submit_selector", "") or result.get("submit_selector", ""),
            confidence="high",  # selectors are known-good
        )

    def solve(self, driver, analysis: CaptchaAnalysis) -> bool:
        return _fill_and_submit(driver, analysis)
