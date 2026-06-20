"""
CAPTCHA handler base class and result dataclass.
"""
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CaptchaAnalysis:
    handler_name: str
    captcha_type: str          # "math" | "image_text" | "select" | "checkbox" | "unknown"
    interpretation: str        # human-readable, e.g. "수학 문제: 3 + 4 = ?"
    answer: str                # proposed answer string
    input_selector: str        # CSS selector for the answer input
    submit_selector: str = ""  # CSS selector for submit button; empty = press Enter
    confidence: str = "medium" # "high" | "medium" | "low"
    extra: dict = field(default_factory=dict)


class CaptchaHandler(abc.ABC):
    """
    Subclass and implement detect/analyze/solve to add a new CAPTCHA type.
    Register with CaptchaSolver.register(handler).
    """

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    def detect(self, html: str) -> bool:
        """Return True if this handler thinks a CAPTCHA is present in html."""
        ...

    @abc.abstractmethod
    def analyze(self, driver, screenshot_b64: str) -> Optional[CaptchaAnalysis]:
        """
        Inspect the page (via driver and screenshot) and return a proposed solution.
        Return None if this handler cannot handle the current CAPTCHA.
        """
        ...

    @abc.abstractmethod
    def solve(self, driver, analysis: CaptchaAnalysis) -> bool:
        """
        Fill in the answer and submit.  Return True if the CAPTCHA disappeared.
        """
        ...
