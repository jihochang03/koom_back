"""
OptionRevealer — 클릭해야만 나타나는 옵션을 자동으로 펼치는 모듈.

동작:
  1. site_knowledge의 extra_clicks가 있으면 먼저 적용 (검증된 패턴)
  2. 없으면 휴리스틱 후보 셀렉터들을 순회하며 클릭 → 새 옵션 등장 여부 확인
  3. 성공한 셀렉터 목록 반환 (호출자가 site_knowledge에 저장)
"""
from __future__ import annotations
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 클릭하면 옵션이 펼쳐질 가능성이 높은 휴리스틱 셀렉터 목록
# 구체적인 것 → 범용 순서로 정렬 (앞쪽 우선 시도)
_HEURISTIC_SELECTORS = [
    # ── 탭/카테고리 버튼 ────────────────────────────────────────────────────
    '[role="tab"]',
    '.tab-item', '.tab_item', '.tab-btn', '.tabItem',
    'ul.tabs li', 'ul.tab-list li',
    '[class*="optionTab"]', '[class*="option-tab"]',
    '[class*="colorTab"]', '[class*="sizeTab"]',
    '[class*="category-btn"]', '[class*="category_btn"]',

    # ── 옵션 그룹 토글/아코디언 ─────────────────────────────────────────────
    '[class*="accordion"] button', '[class*="accordion"] summary',
    '[class*="toggle"] button', 'details > summary',
    '[class*="optionGroup"] button', '[class*="option-group"] button',
    '[class*="optionTitle"]', '[class*="option_title"]',
    '[class*="optionHeader"]', '[class*="option_header"]',

    # ── 색상/사이즈 스워치 첫 번째 항목 ────────────────────────────────────
    '[class*="colorSwatch"]:first-child', '[class*="color-swatch"]:first-child',
    '[class*="sizeSwatch"]:first-child',  '[class*="size-swatch"]:first-child',
    '[class*="variant"]:first-child',

    # ── 더보기 버튼 ─────────────────────────────────────────────────────────
    'button[class*="more"]', 'a[class*="more"]',
    '[class*="viewMore"]', '[class*="view-more"]',
    '[class*="showMore"]', '[class*="show-more"]',
    'button[class*="expand"]', '[class*="unfold"]',
]

# 클릭 후 새 옵션이 등장했는지 판단할 때 비교하는 옵션성 셀렉터
_OPTION_SIGNAL_SELECTORS = [
    '[class*="option"]', '[class*="variant"]', '[class*="swatch"]',
    '[class*="color"]',  '[class*="size"]',    '[class*="choice"]',
    '[class*="select"]', 'select > option',
]


def _count_option_signals(driver) -> int:
    """현재 DOM에서 옵션성 요소 개수 합산."""
    from selenium.webdriver.common.by import By
    total = 0
    for sel in _OPTION_SIGNAL_SELECTORS:
        try:
            total += len(driver.find_elements(By.CSS_SELECTOR, sel))
        except Exception:
            pass
    return total


def _click_selector(driver, selector: str) -> bool:
    """셀렉터에 해당하는 첫 번째 보이는 요소 클릭. 성공하면 True."""
    from selenium.webdriver.common.by import By
    try:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        for el in els[:8]:  # is_displayed() RPC 비용 제한
            try:
                if not el.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.1)
                driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def reveal(driver, domain: str, *, wait_ms: int = 600, use_heuristics: bool = False) -> list[str]:
    """
    클릭해야 나타나는 옵션을 펼침.

    use_heuristics=False (기본): 저장된 패턴만 적용 (빠름, 일반 수집용)
    use_heuristics=True: 저장된 패턴 + 27개 휴리스틱 탐색 (느림, 템플릿 빌더용)

    Returns:
        성공한 셀렉터 목록 (site_knowledge.extra_clicks에 저장용)
    """
    import sys, os
    _COLLECTOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _COLLECTOR_DIR not in sys.path:
        sys.path.insert(0, _COLLECTOR_DIR)
    import site_knowledge

    collection = site_knowledge.get_collection(domain) or {}
    known_clicks: list[str] = collection.get("extra_clicks") or []

    successful: list[str] = []
    before = _count_option_signals(driver)

    # 1) 저장된 패턴 먼저 (항상 적용)
    for sel in known_clicks:
        if _click_selector(driver, sel):
            time.sleep(wait_ms / 1000)
            after = _count_option_signals(driver)
            if after >= before:
                logger.info("[OptionRevealer] 알려진 클릭 적용: %s (+%d 신호)", sel, after - before)
                successful.append(sel)
                before = after

    # 2) 휴리스틱 — 템플릿 빌더 전용 (일반 수집에서는 스킵)
    if not use_heuristics:
        return successful

    known_set = set(known_clicks)
    for sel in _HEURISTIC_SELECTORS:
        if sel in known_set:
            continue
        before_click = _count_option_signals(driver)
        clicked = _click_selector(driver, sel)
        if not clicked:
            continue
        time.sleep(wait_ms / 1000)
        after_click = _count_option_signals(driver)
        if after_click > before_click:
            logger.info("[OptionRevealer] 새 클릭 발견: %s (+%d 신호)", sel, after_click - before_click)
            successful.append(sel)
            before = after_click

    return successful


def reveal_by_selectors(driver, selectors: list[str], *, wait_ms: int = 600) -> list[str]:
    """
    에이전트가 명시적으로 지정한 셀렉터 목록을 순서대로 클릭하고 성공 목록 반환.
    /collect/click 엔드포인트용.

    배열 순서대로 실행되므로 2단계 아코디언 패턴도 지원:
      [선택1_항목_sel, 선택2_아코디언_헤더_sel] → 선택1 클릭 후 대기, 선택2 열기
    클릭 성공 여부는 DOM 신호 증감이 아닌 요소 클릭 가능 여부로 판단
    (aria-disabled 해제는 신호 수 변화 없이도 실제 클릭이면 성공으로 기록)
    """
    successful = []
    for sel in selectors:
        if _click_selector(driver, sel):
            time.sleep(wait_ms / 1000)
            successful.append(sel)
    return successful
