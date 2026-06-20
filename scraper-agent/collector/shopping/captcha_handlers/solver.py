"""
CaptchaSolver — orchestrates CAPTCHA handler chain for a given domain.
"""
from __future__ import annotations
import base64
import logging
import sys
import os
from typing import Callable, Optional

from .base import CaptchaAnalysis, CaptchaHandler
from .known import KnownPatternHandler
from .vision import VisionCaptchaHandler

# site_knowledge 모듈 경로 보장
_COLLECTOR_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _COLLECTOR_DIR not in sys.path:
    sys.path.insert(0, _COLLECTOR_DIR)

import site_knowledge  # noqa: E402

logger = logging.getLogger(__name__)

AskUserFn = Callable[[CaptchaAnalysis], str]  # returns "confirm" | "reject"


class CaptchaSolver:
    """
    Manages a handler chain per domain.
    Default chain: KnownPatternHandler → VisionCaptchaHandler
    Extra handlers can be prepended via register().
    """

    def __init__(self, domain: str):
        self._domain = domain
        self._handlers: list[CaptchaHandler] = [
            KnownPatternHandler(domain),
            VisionCaptchaHandler(),
        ]

    def register(self, handler: CaptchaHandler, *, before_vision: bool = True) -> "CaptchaSolver":
        """Add a custom handler. Inserted before VisionCaptchaHandler by default."""
        if before_vision:
            self._handlers.insert(len(self._handlers) - 1, handler)
        else:
            self._handlers.append(handler)
        return self

    def solve(
        self,
        driver,
        ask_user: Optional[AskUserFn] = None,
    ) -> dict:
        """
        Main solve flow:
        1. Screenshot
        2. Try each applicable handler → CaptchaAnalysis
        3. (Optional) ask_user for confirmation
        4. solve → verify
        5. On success: save pattern to site_knowledge
        Returns {"success": bool, "message": str, "analysis": CaptchaAnalysis | None}
        """
        screenshot_b64 = base64.b64encode(driver.get_screenshot_as_png()).decode()
        html = driver.page_source

        applicable = [h for h in self._handlers if h.detect(html)]

        for handler in applicable:
            analysis = handler.analyze(driver, screenshot_b64)
            if not analysis:
                continue

            if ask_user:
                decision = ask_user(analysis)
                if decision != "confirm":
                    logger.info("[CaptchaSolver] 사용자 거부 → 다음 핸들러")
                    continue

            success = handler.solve(driver, analysis)
            if success:
                # Persist the winning pattern
                site_knowledge.update_captcha(self._domain, {
                    "type": analysis.captcha_type,
                    "input_selector": analysis.input_selector,
                    "submit_selector": analysis.submit_selector or None,
                })
                logger.info("[CaptchaSolver] 성공 → %s 패턴 저장 (%s)", self._domain, handler.name)
                return {"success": True, "message": f"캡차 해결 ({handler.name})", "analysis": analysis}

            return {
                "success": False,
                "message": f"{handler.name}: 제출했지만 캡차가 해결되지 않았습니다.",
                "analysis": analysis,
            }

        return {"success": False, "message": "적합한 캡차 핸들러를 찾을 수 없습니다.", "analysis": None}
