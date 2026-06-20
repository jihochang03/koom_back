"""
CAPTCHA handler package.

Built-in handlers (tried in order):
  KnownPatternHandler  — site_knowledge JSON에 저장된 패턴 재사용
  VisionCaptchaHandler — Claude Haiku vision 범용 fallback

Usage (via CaptchaSolver):
  from shopping.captcha_handlers import CaptchaSolver
  solver = CaptchaSolver(domain="example.com")
  result = solver.solve(driver, ask_user_fn)
"""
from .base import CaptchaAnalysis, CaptchaHandler
from .vision import VisionCaptchaHandler
from .known import KnownPatternHandler
from .solver import CaptchaSolver

__all__ = [
    "CaptchaAnalysis",
    "CaptchaHandler",
    "VisionCaptchaHandler",
    "KnownPatternHandler",
    "CaptchaSolver",
]
