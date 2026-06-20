"""
scraper-agent 전용 수집 서버 (포트 18080).
undetected_chromedriver 기반 Chrome으로 모든 마켓 URL 수집.

시작:  python collector/server.py
포트:  COLLECTOR_PORT (기본 18080)
슬롯:  COLLECTOR_MAX_WORKERS (기본 1)
"""
import io
import logging
import os
import re as _re
import sys
import tempfile
import threading
import time

# Windows stdout/stderr를 UTF-8로 강제 설정
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# collector 디렉토리를 sys.path에 추가 (coupang_collector 임포트용)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from flask import Flask, jsonify, request
from flask_cors import CORS

# 프로젝트 루트의 .env 로드 (ANTHROPIC_API_KEY 등)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(os.path.dirname(_HERE), ".env"), override=False)
except ImportError:
    pass  # python-dotenv 미설치 시 환경변수를 직접 설정해야 함
from shopping.coupang_collector import CoupangCollector
from shopping.naver_collector import NaverCollector
import site_knowledge


# ── HTML 전용 파서 (옵션/가격 선추출) ────────────────────────────────────────

def _detect_shop_type(url: str) -> str:
    """URL에서 쇼핑몰 타입 감지."""
    url_lower = url.lower()
    if 'coupang.com' in url_lower:      return 'coupang'
    if 'smartstore.naver.com' in url_lower or 'shopping.naver.com' in url_lower: return 'naver'
    if 'gmarket.co.kr' in url_lower:    return 'gmarket'
    if 'auction.co.kr' in url_lower:    return 'auction'
    if '11st.co.kr' in url_lower:       return '11st'
    if 'ssg.com' in url_lower:          return 'ssg'
    if 'lotteon.com' in url_lower:      return 'lotteon'
    if 'oliveyoung.co.kr' in url_lower: return 'oliveyoung'
    if 'musinsa.com' in url_lower:      return 'musinsa'
    if 'ably.com' in url_lower:         return 'ably'
    if 'zigzag.kr' in url_lower:        return 'zigzag'
    if '29cm.co.kr' in url_lower:       return '29cm'
    if 'wconcept.co.kr' in url_lower:   return 'wconcept'
    if 'ohou.se' in url_lower:          return 'ohou'
    if 'hmall.com' in url_lower:        return 'hmall'
    return 'generic'


def _find_option_groups_generic(data, _depth: int = 0) -> list:
    """Naver v2 API 등 다양한 JSON 구조에서 옵션 그룹 범용 추출."""
    import re as _re
    if _depth > 6 or not isinstance(data, (dict, list)):
        return []
    if isinstance(data, list):
        for item in data:
            r = _find_option_groups_generic(item, _depth + 1)
            if r:
                return r
        return []

    # ── 패턴 N1: optionGroups / options with groupName + values/items ───────
    for key in ('optionGroups', 'productOptionGroups', 'optionGroupList',
                'optionInfo', 'optionDetails'):
        groups_raw = data.get(key)
        if not isinstance(groups_raw, list) or not groups_raw:
            continue
        result = []
        for g in groups_raw:
            if not isinstance(g, dict):
                continue
            gname = (g.get('groupName') or g.get('name') or g.get('label') or '옵션').strip()
            vals = (g.get('options') or g.get('values') or g.get('items')
                    or g.get('optionValues') or g.get('optionNameList') or [])
            # vals could be list of strings or list of dicts
            parsed_vals = []
            soldout = []
            for v in vals:
                if isinstance(v, str):
                    parsed_vals.append(v.strip())
                elif isinstance(v, dict):
                    name = (v.get('optionName') or v.get('name') or v.get('value') or '').strip()
                    if name:
                        parsed_vals.append(name)
                        if (v.get('stockQuantity', 1) == 0 or v.get('soldOut')
                                or v.get('soldOutYn') in ('Y', True)):
                            soldout.append(name)
            if parsed_vals:
                result.append({'type': gname, 'values': parsed_vals, 'soldout': soldout})
        if result:
            return result

    # ── 패턴 N2: optionCombinations 단독 (그룹 인덱스 유추) ─────────────────
    combos = data.get('optionCombinations') or data.get('optionCombinationList')
    if isinstance(combos, list) and combos:
        from shopping.html_only_parser import _find_state_option_groups as _fsog
        fake = {'optionCombinationGroupList': [{'groupName': '옵션', 'optionCombinations': combos}]}
        r = _fsog(fake)
        if r:
            return r

    # ── 패턴 N3: product 또는 item 래퍼 벗기기 ──────────────────────────────
    for key in ('product', 'item', 'result', 'data', 'body',
                'productDetail', 'productInfo', 'goodsDetail'):
        sub = data.get(key)
        if isinstance(sub, dict):
            r = _find_option_groups_generic(sub, _depth + 1)
            if r:
                return r

    return []


def _extract_options_from_network_log(net_log: list) -> list:
    """네트워크 로그 JSON 응답에서 옵션 그룹 추출."""
    import json as _j
    try:
        from shopping.html_only_parser import _find_state_option_groups
    except ImportError:
        return []
    logger.info("[네트워크 옵션] 로그 %d개 URL: %s", len(net_log),
                [e.get('url', '')[-80:] for e in net_log])
    best: list = []
    for entry in net_log:
        url = entry.get('url', '')
        body = entry.get('body', '')
        if not body or len(body) < 50:
            continue
        try:
            data = _j.loads(body)
        except Exception:
            continue
        try:
            # 상품 API URL이면 구조 진단 로그 (최초 1회)
            _is_product_api = any(k in url for k in ('/products/', '/option', '/item', '/goods'))
            if _is_product_api and isinstance(data, dict):
                # 2단계 키 구조 출력
                def _key_tree(d, max_depth=2, cur=0):
                    if cur >= max_depth or not isinstance(d, dict):
                        return list(d.keys())[:8] if isinstance(d, dict) else type(d).__name__
                    return {k: _key_tree(v, max_depth, cur + 1) for k, v in list(d.items())[:12]}
                logger.info("[네트워크 옵션] 상품API 구조 (%s...): %s",
                            url[-60:], _key_tree(data))

            groups = _find_state_option_groups(data)
            if not groups:
                groups = _find_option_groups_generic(data)
            if len(groups) > len(best):
                best = groups
                logger.info("[네트워크 옵션] %s → %d그룹: %s",
                            url[-80:], len(groups), [g['type'] for g in groups])
        except Exception as e:
            logger.debug("[네트워크 옵션] 파싱 오류 %s: %s", url[-40:], e)
    return best


def _run_html_parser(html: str, url: str, page_title: str = '', network_log: list | None = None) -> dict:
    """HTML 전용 파서로 상품 정보 추출 후 dict 반환. 실패해도 {} 반환."""
    try:
        from shopping.html_only_parser import parse_html_only
        shop_type = _detect_shop_type(url)
        info = parse_html_only(html=html, shop_type=shop_type, page_title=page_title, url=url)
        result = info.model_dump(exclude_none=True)
        opts = []
        for opt in (info.product_options or []):
            opts.append(opt.model_dump(exclude_none=True))

        # 네트워크 로그에서 더 많은 옵션 그룹을 찾으면 교체
        if network_log:
            net_groups = _extract_options_from_network_log(network_log)
            if len(net_groups) > len(opts):
                from models import ProductOption
                opts = [ProductOption(**{
                    'option_type': g['type'],
                    'available_values': g['values'],
                    'soldout_values': g['soldout'] or None,
                }).model_dump(exclude_none=True) for g in net_groups]
                logger.info("[네트워크 옵션] HTML파서 %d그룹 → 네트워크 %d그룹으로 교체",
                            len(info.product_options), len(net_groups))

        result['product_options'] = opts
        logger.info("[HTML파서] %s: 가격=%s 옵션=%d그룹", shop_type, info.discounted_price, len(opts))
        return result
    except Exception as e:
        logger.warning("[HTML파서] 실패 (무시): %s", e)
        return {}


# ── 로깅 ─────────────────────────────────────────────────────────────────────

_LOG_DIR = os.path.join(_HERE, '..', 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, 'collector_server.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_FILE, encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

PORT = int(os.getenv("COLLECTOR_PORT", "18080"))
_MAX_WORKERS = max(1, min(4, int(os.getenv("COLLECTOR_MAX_WORKERS", "1"))))
BUSY_RETRY_AFTER_SEC = 15

# dk 프로젝트가 사용하는 프로필 경로 (쿠팡 쿠키 축적됨)
# 같은 경로를 사용해 기존 세션을 재사용
def _profile_dir(slot_id: int) -> str:
    return os.path.join(tempfile.gettempdir(), f"chrome_profile_coupang_p{slot_id}")


# ── HTML 정리 (script/style/svg 내용 제거) ───────────────────────────────────

def _strip_nonessential_tags(html: str) -> str:
    for tag in ('script', 'style', 'svg', 'noscript'):
        html = _re.sub(
            rf'<{tag}(\s[^>]*)?>.*?</{tag}>',
            f'<{tag}></{tag}>',
            html,
            flags=_re.DOTALL | _re.IGNORECASE,
        )
    return html


# ── Chrome 슬롯 ───────────────────────────────────────────────────────────────

# ── 페이지 fetch/XHR 캡처 스크립트 (CDP로 모든 문서에 주입) ─────────────────────
_NETWORK_CAPTURE_JS = r"""
window._netLog = [];
(function() {
    function _skip(url) {
        if (!url) return true;
        return /\.(jpg|jpeg|png|gif|webp|svg|css|woff2?|ttf|eot|ico|mp4|mp3|ogg)(\?|$)/i.test(url);
    }
    var _origFetch = window.fetch;
    window.fetch = function() {
        var url = String(arguments[0] instanceof Request ? arguments[0].url : arguments[0]);
        return _origFetch.apply(this, arguments).then(function(r) {
            if (!_skip(url)) {
                try {
                    r.clone().text().then(function(t) {
                        if (t && t.length > 50)
                            window._netLog.push({url: url, body: t.slice(0, 100000), ct: r.headers.get('content-type')||''});
                    }).catch(function(){});
                } catch(e) {}
            }
            return r;
        });
    };
    var _origOpen = XMLHttpRequest.prototype.open;
    var _origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, u) {
        this._capUrl = String(u);
        return _origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
        var self = this;
        this.addEventListener('load', function() {
            try {
                var ct = self.getResponseHeader('content-type') || '';
                if (!_skip(self._capUrl) && self.responseText && self.responseText.length > 50)
                    window._netLog.push({url: self._capUrl, body: self.responseText.slice(0, 100000), ct: ct});
            } catch(e) {}
        });
        return _origSend.apply(this, arguments);
    };
})();
"""

_CHALLENGE_PATTERNS = [
    '상품 접근 확인', '접근 확인이 필요', 'robot check', 'captcha',
    'access denied', 'access_denied', '비정상적인 접근', '잠시 후 다시',
    '보안 확인', '자동화된 요청',
]


class _Slot:
    def __init__(self, slot_id: int):
        self.slot_id = slot_id
        self._lock = threading.Lock()
        profile_dir = _profile_dir(slot_id)
        logger.info("[슬롯%d] 초기화 (프로필: %s)", slot_id, profile_dir)

        # 시도 1~2: 원래 프로필 / 시도 3: 임시 새 프로필
        profiles_to_try = [profile_dir, profile_dir, profile_dir + '_fresh']
        for attempt, pdir in enumerate(profiles_to_try):
            try:
                if attempt > 0:
                    _kill_chrome_using_profile(pdir)
                    _clean_profile_locks(pdir)
                    time.sleep(1)
                self.collector = CoupangCollector(
                    headless=False,
                    timeout=30,
                    profile_dir=pdir,
                    persistent=True,
                )
                self.collector.start()
                logger.info("[슬롯%d] Chrome 시작 완료 (시도 %d, 프로필: %s)", slot_id, attempt + 1, pdir)
                self._inject_network_capture()
                self._warmup_init()
                return
            except Exception as e:
                logger.error("[슬롯%d] 시작 실패 (시도 %d/%d): %s", slot_id, attempt + 1, len(profiles_to_try), e)
                try:
                    self.collector.close()
                except Exception:
                    pass
        raise RuntimeError(f"슬롯{slot_id} 초기화 실패")

    def _inject_network_capture(self):
        """CDP로 fetch/XHR 인터셉트 스크립트를 모든 신규 문서에 주입."""
        try:
            self.collector.driver.execute_cdp_cmd(
                'Page.addScriptToEvaluateOnNewDocument',
                {'source': _NETWORK_CAPTURE_JS},
            )
            logger.info("[슬롯%d] 네트워크 캡처 스크립트 주입 완료", self.slot_id)
        except Exception as e:
            logger.warning("[슬롯%d] 네트워크 캡처 주입 실패: %s", self.slot_id, e)

    def _warmup_init(self):
        """Chrome 시작 직후 쿠팡 홈 방문 — 쿠키/세션 초기화."""
        try:
            driver = self.collector.driver
            if not driver:
                return
            current = ''
            try:
                current = driver.current_url
            except Exception:
                pass
            # 이미 쿠팡에 있으면 스킵
            if 'coupang.com' in current:
                logger.info("[슬롯%d] 이미 쿠팡 페이지 — warm-up 스킵", self.slot_id)
                return
            logger.info("[슬롯%d] 쿠팡 홈 warm-up 시작...", self.slot_id)
            driver.get('https://www.coupang.com/')
            time.sleep(4)
            try:
                driver.execute_script("window.scrollTo(0, 400);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
            except Exception:
                pass
            logger.info("[슬롯%d] warm-up 완료", self.slot_id)
        except Exception as e:
            logger.warning("[슬롯%d] warm-up 실패 (계속 진행): %s", self.slot_id, e)

    def acquire(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self):
        self._lock.release()

    def _is_alive(self) -> bool:
        try:
            if not self.collector.driver:
                return False
            if self.collector.driver.service.process.poll() is not None:
                return False
            _ = self.collector.driver.current_url
            return True
        except Exception:
            return False

    def _restart(self):
        logger.warning("[슬롯%d] Chrome 재시작...", self.slot_id)
        try:
            self.collector.close()
        except Exception:
            pass
        self.collector.driver = None
        _clean_profile_locks(_profile_dir(self.slot_id))
        try:
            self.collector.start()
            self._warmup_init()
            logger.info("[슬롯%d] Chrome 재시작 완료", self.slot_id)
        except Exception as e:
            logger.error("[슬롯%d] 재시작 실패: %s", self.slot_id, e)

    def _is_challenge_page(self, html: str, title: str = '') -> bool:
        if len(html) < 5000:
            return True
        haystack = (html[:20000] + title).lower()
        return any(p.lower() in haystack for p in _CHALLENGE_PATTERNS)

    def _try_pass_challenge(self):
        """챌린지/확인 페이지에서 버튼 클릭 시도."""
        driver = self.collector.driver
        try:
            from selenium.webdriver.common.by import By
            btns = driver.find_elements(By.CSS_SELECTOR, 'button, input[type="button"], a[role="button"]')
            for btn in btns:
                try:
                    text = (btn.text or btn.get_attribute('value') or '').strip()
                    if any(kw in text for kw in ['확인', '계속', '다음', '시작', 'OK', 'Continue', '진행']):
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)
                        logger.info("[슬롯%d] 챌린지 버튼 클릭: '%s'", self.slot_id, text)
                        time.sleep(2)
                        return True
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[슬롯%d] 챌린지 처리 실패: %s", self.slot_id, e)
        return False

    def _try_solve_captcha(self, url: str) -> bool:
        """CAPTCHA 자동 풀기 — site_knowledge 패턴 우선, 없으면 Vision fallback."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            from shopping.captcha_handlers import CaptchaSolver
            solver = CaptchaSolver(domain=domain)
            result = solver.solve(self.collector.driver, ask_user=None)
            if result['success']:
                logger.info("[슬롯%d] CAPTCHA 자동 해결 완료 (%s)", self.slot_id, domain)
                return True
            logger.warning("[슬롯%d] CAPTCHA 자동 해결 실패: %s", self.slot_id, result['message'])
        except Exception as e:
            logger.warning("[슬롯%d] CAPTCHA 솔버 오류: %s", self.slot_id, e)
        return False

    def _navigate_js(self, url: str) -> dict:
        """
        window.location.href로 이동 (CDP 네비게이션보다 봇 탐지 우회에 유리).
        처음 방문(about:blank)이면 driver.get() 사용.
        """
        driver = self.collector.driver

        # CDP 헤더 설정
        try:
            driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                "headers": {
                    "Referer": "https://www.google.com/search?q=" + url.split('/')[2],
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            })
        except Exception:
            pass

        # 네비게이션
        current = ''
        try:
            current = driver.current_url
        except Exception:
            pass

        if not current or current in ('data:,', 'about:blank', 'chrome://newtab/'):
            driver.get(url)
        else:
            driver.execute_script("window.location.href = arguments[0];", url)

        # 콘텐츠 로드 대기
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script(
                    "return document.readyState === 'complete' && "
                    "!!document.body && document.body.innerText.length > 100;"
                )
            )
        except Exception:
            time.sleep(3)

        # 스크롤 시뮬레이션
        try:
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass

        html = driver.page_source
        title = driver.title
        final_url = driver.current_url

        # 챌린지 페이지 감지 및 처리
        if self._is_challenge_page(html, title):
            logger.warning("[슬롯%d] 챌린지 페이지 감지 (HTML %d자, 제목: '%s')",
                           self.slot_id, len(html), title)
            passed = self._try_pass_challenge()
            if not passed:
                # CAPTCHA 자동 풀기 시도
                passed = self._try_solve_captcha(url)
            if passed:
                html = driver.page_source
                title = driver.title
                final_url = driver.current_url

        # 옵션 reveal 클릭 (site_knowledge 패턴 + 휴리스틱)
        try:
            from urllib.parse import urlparse as _urlparse
            _domain = _urlparse(url).netloc
            from shopping.option_revealer import reveal as _reveal
            clicked = _reveal(driver, _domain, wait_ms=300, use_heuristics=False)
            if clicked:
                logger.info("[슬롯%d] 옵션 reveal 클릭 %d개 적용 → HTML 재캡처", self.slot_id, len(clicked))
                html = driver.page_source
                # 새로 발견된 클릭 패턴 site_knowledge에 자동 저장
                existing = (site_knowledge.get_collection(_domain) or {}).get('extra_clicks', [])
                new_clicks = [s for s in clicked if s not in existing]
                if new_clicks:
                    site_knowledge.update_collection(_domain, {'extra_clicks': existing + new_clicks})
        except Exception as e:
            logger.warning("[슬롯%d] 옵션 reveal 실패 (무시): %s", self.slot_id, e)

        # fetch/XHR 로그 수집
        import json as _j
        net_log = []
        try:
            raw = driver.execute_script("return JSON.stringify((window._netLog||[]).slice(0,40));")
            net_log = _j.loads(raw or '[]')
            logger.info("[슬롯%d] 네트워크 로그 %d개 캡처", self.slot_id, len(net_log))
        except Exception as e:
            logger.warning("[슬롯%d] 네트워크 로그 수집 실패: %s", self.slot_id, e)

        return {'html': html, 'page_title': title, 'final_url': final_url, 'network_log': net_log}

    def collect(self, url: str) -> dict:
        """URL 수집. JS 네비게이션 1순위, 빈 결과면 warm-up 후 재시도."""
        if not self._is_alive():
            logger.warning("[슬롯%d] 드라이버 사망 → 재시작", self.slot_id)
            self._restart()

        result = self._navigate_js(url)

        if self._is_challenge_page(result['html'], result.get('page_title', '')):
            logger.warning("[슬롯%d] 빈 페이지/챌린지 (HTML %d자) → warm-up 후 재시도",
                           self.slot_id, len(result['html']))
            # 홈 방문으로 세션 초기화
            try:
                domain = url.split('/')[2]
                self.collector.driver.get(f'https://{domain}/')
                time.sleep(4)
            except Exception:
                pass
            time.sleep(1.5)
            result = self._navigate_js(url)

        return result

    def collect_musinsa(self, url: str) -> dict:
        result = self.collect(url)
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            driver = self.collector.driver
            buttons = driver.find_elements(
                By.CSS_SELECTOR,
                'button[data-mds="IconButton"]:has(svg[data-mds="IcArrowDown"])',
            )
            clicked = 0
            for btn in buttons:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.15)
                    ActionChains(driver).move_to_element(btn).click().perform()
                    time.sleep(0.5)
                    clicked += 1
                except Exception:
                    pass
            if clicked:
                time.sleep(0.3)
                result = {'html': driver.page_source, 'page_title': result['page_title'], 'final_url': result['final_url']}
                logger.info("[무신사] 드랍다운 %d개 클릭 후 재수집", clicked)
        except Exception as e:
            logger.warning("[무신사] 드랍다운 클릭 실패: %s", e)
        return result

    def collect_gmarket(self, url: str) -> dict:
        result = self.collect(url)
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            driver = self.collector.driver
            # 지마켓 옵션 셀렉트박스 및 옵션 버튼 클릭
            selectors = [
                'select[name*="option"]', 'select[id*="option"]', 'select[class*="option"]',
                '.option_wrap select', '#opt_select', '.item_option select',
                'button[class*="option"]', '.option_list li', '.choice_option li',
            ]
            clicked = 0
            for sel in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elements[:3]:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.1)
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.25)
                            clicked += 1
                        except Exception:
                            pass
                except Exception:
                    pass
            if clicked:
                time.sleep(0.3)
                result = {'html': driver.page_source, 'page_title': result['page_title'], 'final_url': result['final_url']}
                logger.info("[지마켓] 옵션 요소 %d개 클릭 후 재수집", clicked)
        except Exception as e:
            logger.warning("[지마켓] 옵션 클릭 실패: %s", e)
        return result

    def collect_oliveyoung(self, url: str) -> dict:
        result = self.collect(url)
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            driver = self.collector.driver
            buttons = driver.find_elements(By.CSS_SELECTOR, 'button[class*="OptionSelector_btn-option"]')
            clicked = 0
            for btn in buttons:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.15)
                    ActionChains(driver).move_to_element(btn).click().perform()
                    time.sleep(0.5)
                    clicked += 1
                except Exception:
                    pass
            if clicked:
                time.sleep(0.3)
                result = {'html': driver.page_source, 'page_title': result['page_title'], 'final_url': result['final_url']}
                logger.info("[올리브영] 옵션 버튼 %d개 클릭 후 재수집", clicked)
        except Exception as e:
            logger.warning("[올리브영] 옵션 클릭 실패: %s", e)
        return result


# ── 네이버 슬롯 ──────────────────────────────────────────────────────────────

def _naver_profile_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "chrome_profile_naver_p0")


class _NaverSlot:
    """NaverCollector를 래핑한 단일 슬롯 (캡차 자동 풀기 포함)."""

    def __init__(self):
        self._lock = threading.Lock()
        profile_dir = _naver_profile_dir()
        logger.info("[네이버슬롯] 초기화 (프로필: %s)", profile_dir)
        try:
            self.collector = NaverCollector(
                profile_dir=profile_dir,
                headless=False,
                timeout=30,
            )
            self.collector.start()
            self._inject_network_capture()
            logger.info("[네이버슬롯] Chrome 시작 완료")
        except Exception as e:
            logger.error("[네이버슬롯] 초기화 실패: %s", e)
            raise

    def _inject_network_capture(self):
        """CDP로 fetch/XHR 인터셉트 스크립트를 모든 신규 문서에 주입."""
        try:
            self.collector.driver.execute_cdp_cmd(
                'Page.addScriptToEvaluateOnNewDocument',
                {'source': _NETWORK_CAPTURE_JS},
            )
            logger.info("[네이버슬롯] 네트워크 캡처 스크립트 주입 완료")
        except Exception as e:
            logger.warning("[네이버슬롯] 네트워크 캡처 주입 실패: %s", e)

    def acquire(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self):
        self._lock.release()

    def _is_alive(self) -> bool:
        try:
            if not self.collector.driver:
                return False
            _ = self.collector.driver.current_url
            return True
        except Exception:
            return False

    def _restart(self):
        logger.warning("[네이버슬롯] Chrome 재시작...")
        try:
            self.collector.close()
        except Exception:
            pass
        _clean_profile_locks(_naver_profile_dir())
        try:
            self.collector.start()
            self._inject_network_capture()
            logger.info("[네이버슬롯] Chrome 재시작 완료")
        except Exception as e:
            logger.error("[네이버슬롯] 재시작 실패: %s", e)

    def collect(self, url: str) -> dict:
        if not self._is_alive():
            logger.warning("[네이버슬롯] 드라이버 사망 → 재시작")
            self._restart()
        result = self.collector.collect_product_page(url, save_screenshot=False)

        # 동적 옵션 API 호출이 완료될 시간을 줌 (Naver SPA 특성상 페이지 로드 후 XHR 발생)
        time.sleep(2)

        # fetch/XHR 로그 수집 (옵션 API 응답 포함)
        import json as _j
        net_log = []
        try:
            raw = self.collector.driver.execute_script(
                "return JSON.stringify((window._netLog||[]).slice(0,60));"
            )
            net_log = _j.loads(raw or '[]')
            logger.info("[네이버슬롯] 네트워크 로그 %d개 캡처", len(net_log))
        except Exception as e:
            logger.warning("[네이버슬롯] 네트워크 로그 추출 실패: %s", e)
        return {
            'html': result.get('html', ''),
            'page_title': result.get('page_title', ''),
            'final_url': result.get('final_url', url),
            'network_log': net_log,
        }


_naver_slot: "_NaverSlot | None" = None


def _is_naver_url(url: str) -> bool:
    url_lower = url.lower()
    return any(d in url_lower for d in (
        'smartstore.naver.com', 'shopping.naver.com',
        'brand.naver.com', 'naver.me',
    ))


# ── 슬롯 풀 ───────────────────────────────────────────────────────────────────

_slots: list[_Slot] = []
_rr_index = 0
_rr_lock = threading.Lock()


def _acquire_slot() -> "_Slot | None":
    global _rr_index
    n = len(_slots)
    if n == 0:
        return None
    with _rr_lock:
        start = _rr_index
        _rr_index = (_rr_index + 1) % n
    for i in range(n):
        s = _slots[(start + i) % n]
        if s.acquire():
            return s
    return None


def _busy_response():
    r = jsonify({'success': False, 'error': '수집 중입니다. 잠시 후 다시 시도해 주세요.', 'busy': True})
    r.status_code = 503
    r.headers['Retry-After'] = str(BUSY_RETRY_AFTER_SEC)
    return r


# ── 라우트 ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'runtime': 'scraper-local', 'slots': len(_slots)})


@app.route('/collect/general', methods=['POST'])
def collect_general():
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    raw = bool(data.get('raw', False))
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400

    logger.info("[일반] 수집 요청: %s", url)

    # ── 네이버 전용 경로 (캡차 자동 풀기) ────────────────────────────────
    if _is_naver_url(url):
        if _naver_slot is None or not _naver_slot.acquire():
            return _busy_response()
        try:
            result = _naver_slot.collect(url)
        except Exception as e:
            logger.error("[네이버] 수집 실패: %s", e)
            return jsonify({'error': str(e), 'success': False}), 500
        finally:
            _naver_slot.release()

        raw_len = len(result.get('html', ''))
        html_out = result['html'] if raw else _strip_nonessential_tags(result['html'])
        logger.info("[네이버] 완료: %d→%d 문자", raw_len, len(html_out))

        if raw_len < 5000:
            logger.warning("[네이버] HTML 너무 짧음 (%d자)", raw_len)
            return jsonify({
                'success': False,
                'error': f'수집된 HTML이 너무 짧습니다 ({raw_len}자).',
                'html': html_out,
            }), 200

        page_title = result.get('page_title', '')
        product_info = _run_html_parser(result['html'], url, page_title, result.get('network_log', []))
        return jsonify({
            'html': html_out,
            'page_title': page_title,
            'final_url': result.get('final_url', url),
            'network_log': [],
            'product_info': product_info,
            'success': True,
        })

    # ── 일반 슬롯 (쿠팡 등) ──────────────────────────────────────────────
    slot = _acquire_slot()
    if slot is None:
        return _busy_response()

    try:
        if 'musinsa.com' in url:
            result = slot.collect_musinsa(url)
        elif 'oliveyoung.co.kr' in url:
            result = slot.collect_oliveyoung(url)
        elif 'gmarket.co.kr' in url:
            result = slot.collect_gmarket(url)
        else:
            result = slot.collect(url)

        raw_len = len(result.get('html', ''))
        html_out = result['html'] if raw else _strip_nonessential_tags(result['html'])
        logger.info("[일반] 완료: %d→%d 문자 (슬롯%d)", raw_len, len(html_out), slot.slot_id)

        # 최소 콘텐츠 기준 미달이면 실패로 반환 (TypeScript가 Playwright로 fallback하도록)
        if raw_len < 5000:
            logger.warning("[일반] HTML 너무 짧음 (%d자) — 실패 반환", raw_len)
            return jsonify({
                'success': False,
                'error': f'수집된 HTML이 너무 짧습니다 ({raw_len}자). 챌린지 페이지일 수 있습니다.',
                'html': html_out,
            }), 200

        # HTML 전용 파서로 상품 정보 선추출 (옵션/가격 정확도 향상)
        page_title = result.get('page_title', '')
        product_info = _run_html_parser(result['html'], url, page_title)

        return jsonify({
            'html': html_out,
            'page_title': page_title,
            'final_url': result.get('final_url', url),
            'network_log': result.get('network_log', []),
            'product_info': product_info,
            'success': True,
        })
    except Exception as e:
        logger.error("[일반] 실패 (슬롯%d): %s", slot.slot_id, e)
        return jsonify({'error': str(e), 'success': False}), 500
    finally:
        slot.release()


# ── Simple collect (plain requests, 브라우저 없음) ───────────────────────────

_SIMPLE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
}

_BLOCK_SIGNALS = [
    'access denied', 'access_denied', '403 forbidden', 'forbidden',
    'robot check', 'captcha', 'blocked', 'unusual traffic',
    'automated access', '비정상적인 접근', '잠시 후 다시',
    'cloudflare', 'ddos-guard', 'challenge',
]


@app.route('/collect/simple', methods=['POST'])
def collect_simple():
    """
    Plain requests — 브라우저 없이 직접 HTTP GET.
    JS 렌더링 없음. 빠르고 서버 자원 소모 없음.
    결과에 blocked=True가 있으면 Chrome 슬롯으로 재시도 필요.
    raw=true 전달 시 script/style 내용을 유지한 원본 HTML 반환 (템플릿 빌더용).
    """
    import requests as _req
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    raw = bool(data.get('raw', False))
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400

    logger.info("[심플] 수집 요청: %s", url)
    try:
        resp = _req.get(url, headers=_SIMPLE_HEADERS, timeout=15, allow_redirects=True)
        html = resp.text
        status_code = resp.status_code

        if status_code >= 400:
            logger.info("[심플] HTTP %d → 차단", status_code)
            return jsonify({
                'success': False,
                'blocked': True,
                'status_code': status_code,
                'error': f'HTTP {status_code}',
                'html': '',
            })

        haystack = html[:8000].lower()
        is_blocked = (
            len(html) < 3000
            or any(s in haystack for s in _BLOCK_SIGNALS)
        )

        if is_blocked:
            logger.info("[심플] 차단 감지 (HTML %d자)", len(html))
        else:
            logger.info("[심플] 완료 (HTML %d자)", len(html))

        html_out = html if raw else _strip_nonessential_tags(html)
        product_info = _run_html_parser(html, url) if not is_blocked else {}

        return jsonify({
            'html': html_out,
            'page_title': '',
            'final_url': resp.url,
            'network_log': [],
            'product_info': product_info,
            'success': not is_blocked,
            'blocked': is_blocked,
            'status_code': status_code,
            'source': 'simple',
        })
    except Exception as e:
        logger.warning("[심플] 요청 실패: %s", e)
        return jsonify({'success': False, 'blocked': True, 'error': str(e), 'html': ''})


# ── Click-and-capture (에이전트 드리븐 옵션 탐색) ────────────────────────────

@app.route('/collect/click', methods=['POST'])
def collect_click():
    """
    지정한 셀렉터들을 클릭한 뒤 변경된 HTML과 발견된 옵션 신호 수를 반환.
    에이전트가 "이걸 누르면 옵션이 나오나?" 실험할 때 사용.
    Body: {"url": "...", "selectors": ["sel1", ...], "wait_ms": 600}
    """
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    selectors: list = data.get('selectors') or []
    wait_ms: int = int(data.get('wait_ms', 600))

    if not url or not selectors:
        return jsonify({'error': 'url과 selectors가 필요합니다.'}), 400

    if _is_naver_url(url):
        slot_obj = _naver_slot
        if slot_obj is None or not slot_obj.acquire():
            return _busy_response()
    else:
        slot_obj = _acquire_slot()  # _acquire_slot already calls acquire() internally
        if slot_obj is None:
            return _busy_response()

    try:
        driver = slot_obj.collector.driver
        # 현재 페이지가 해당 URL이 아니면 먼저 이동
        try:
            if driver.current_url.rstrip('/') != url.rstrip('/'):
                slot_obj._navigate_js(url)
        except Exception:
            slot_obj._navigate_js(url)

        from shopping.option_revealer import reveal_by_selectors, _count_option_signals

        # 클릭 전 네트워크 로그 크기 기억 — 클릭 후 새로 추가된 것만 추출
        try:
            pre_count = driver.execute_script("return (window._netLog||[]).length;") or 0
        except Exception:
            pre_count = 0

        before = _count_option_signals(driver)
        clicked = reveal_by_selectors(driver, selectors, wait_ms=wait_ms)
        after = _count_option_signals(driver)

        html = driver.page_source
        trimmed = _strip_nonessential_tags(html)

        # 클릭 후 새로 발생한 네트워크 요청만 추출
        net_log = []
        try:
            raw = driver.execute_script(
                f"return JSON.stringify((window._netLog||[]).slice({pre_count}, {pre_count + 20}));"
            )
            if raw:
                import json as _json
                net_log = _json.loads(raw) or []
        except Exception:
            pass

        return jsonify({
            'success': True,
            'clicked': clicked,
            'option_signals_before': before,
            'option_signals_after': after,
            'new_signals': after - before,
            'html': trimmed[:60_000],
            'network_log': net_log,   # 클릭으로 트리거된 XHR/fetch 요청
        })
    except Exception as e:
        logger.error("[click] 실패: %s", e)
        return jsonify({'error': str(e), 'success': False}), 500
    finally:
        slot_obj.release()


# ── Site knowledge API ───────────────────────────────────────────────────────

@app.route('/api/knowledge/<path:domain>', methods=['GET'])
def get_knowledge(domain: str):
    """도메인의 site_knowledge JSON 반환."""
    data = site_knowledge.load(domain)
    if data is None:
        return jsonify({'domain': domain, 'exists': False}), 404
    return jsonify({**data, 'exists': True})


@app.route('/api/knowledge/<path:domain>', methods=['POST'])
def update_knowledge(domain: str):
    """
    site_knowledge를 업데이트합니다.
    Body: {"captcha": {...}, "collection": {...}}  (각 키는 선택 사항)
    """
    body = request.get_json() or {}
    if not isinstance(body, dict):
        return jsonify({'error': 'JSON 객체가 필요합니다.'}), 400

    captcha_info = body.get('captcha')
    collection_info = body.get('collection')

    if captcha_info and isinstance(captcha_info, dict):
        site_knowledge.update_captcha(domain, captcha_info)
    if collection_info and isinstance(collection_info, dict):
        site_knowledge.update_collection(domain, collection_info)

    if not captcha_info and not collection_info:
        # 임의 키 직접 저장
        site_knowledge.save(domain, body)

    return jsonify({'success': True, 'domain': domain, 'data': site_knowledge.load(domain)})


@app.route('/api/knowledge/<path:domain>', methods=['DELETE'])
def delete_knowledge(domain: str):
    """도메인의 site_knowledge JSON 삭제."""
    import pathlib
    p = pathlib.Path(__file__).parent / 'site_knowledge' / f"{domain.replace('/', '_').replace(':', '_')}.json"
    if not p.exists():
        return jsonify({'error': '없는 도메인'}), 404
    p.unlink()
    logger.info("[SiteKnowledge] 삭제: %s", domain)
    return '', 204


@app.route('/api/knowledge', methods=['GET'])
def list_knowledge():
    """저장된 모든 도메인 목록 반환."""
    return jsonify({'domains': site_knowledge.list_domains()})


# ── 메인 ─────────────────────────────────────────────────────────────────────

def _watchdog_loop():
    while True:
        time.sleep(120)
        for slot in _slots:
            if not slot.acquire():
                continue
            try:
                if not slot._is_alive():
                    logger.info("[Watchdog] 슬롯%d 재시작", slot.slot_id)
                    slot._restart()
            except Exception as e:
                logger.warning("[Watchdog] 슬롯%d 오류: %s", slot.slot_id, e)
            finally:
                slot.release()
        # 네이버 슬롯 watchdog
        if _naver_slot is not None and _naver_slot.acquire():
            try:
                if not _naver_slot._is_alive():
                    logger.info("[Watchdog] 네이버슬롯 재시작")
                    _naver_slot._restart()
            except Exception as e:
                logger.warning("[Watchdog] 네이버슬롯 오류: %s", e)
            finally:
                _naver_slot.release()


def _clean_profile_locks(profile_dir: str):
    lock_names = (
        'SingletonLock', 'SingletonCookie', 'SingletonSocket',
        'DevToolsActivePort',
    )
    for lock_name in lock_names:
        lock_path = os.path.join(profile_dir, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info("[정리] 락 파일 삭제: %s", lock_path)
            except Exception as e:
                logger.warning("[정리] 락 파일 삭제 실패 %s: %s", lock_path, e)
    # .org.chromium.Chromium.* temp files
    if os.path.isdir(profile_dir):
        for name in os.listdir(profile_dir):
            if name.startswith('.org.chromium.'):
                try:
                    os.remove(os.path.join(profile_dir, name))
                except Exception:
                    pass


def _kill_chrome_using_profile(profile_dir: str):
    """프로필 디렉토리를 사용 중인 Chrome 프로세스를 강제 종료."""
    import subprocess
    try:
        # wmic으로 profile_dir 경로를 포함한 chrome.exe 프로세스 찾기
        profile_fragment = os.path.basename(profile_dir)  # e.g. chrome_profile_coupang_p0
        result = subprocess.run(
            ['wmic', 'process', 'where',
             f'name="chrome.exe" and commandline like "%{profile_fragment}%"',
             'get', 'ProcessId', '/format:value'],
            capture_output=True, text=True, timeout=10,
        )
        pids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith('processid=') and '=' in line:
                pid_str = line.split('=', 1)[1].strip()
                if pid_str.isdigit():
                    pids.append(pid_str)
        if pids:
            for pid in pids:
                subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
            logger.info("[정리] 프로필 '%s' 사용 Chrome PID %s 종료", profile_fragment, pids)
        else:
            logger.info("[정리] 프로필 '%s' 사용 Chrome 프로세스 없음", profile_fragment)
    except Exception as e:
        logger.warning("[정리] Chrome 프로세스 검색 실패: %s", e)


def _cleanup_uc_driver():
    """잠긴 undetected_chromedriver.exe 파일 정리 — 기존 프로세스 종료 후 삭제."""
    import subprocess
    import shutil

    uc_exe = os.path.join(
        os.environ.get('APPDATA', ''),
        'undetected_chromedriver',
        'undetected_chromedriver.exe',
    )
    uc_dir = os.path.dirname(uc_exe)

    # 1) 모든 chromedriver / undetected_chromedriver 프로세스 종료
    for name in ('chromedriver.exe', 'undetected_chromedriver.exe'):
        try:
            subprocess.run(['taskkill', '/F', '/IM', name], capture_output=True)
        except Exception:
            pass

    time.sleep(0.5)

    # 2) 잠긴 파일 삭제 시도
    if os.path.exists(uc_exe):
        try:
            os.remove(uc_exe)
            logger.info("[정리] uc driver 삭제 완료: %s", uc_exe)
        except Exception as e:
            logger.warning("[정리] uc driver 삭제 실패 (계속 진행): %s", e)
            # 폴더째 삭제 후 재생성 시도
            try:
                shutil.rmtree(uc_dir, ignore_errors=True)
                os.makedirs(uc_dir, exist_ok=True)
                logger.info("[정리] uc driver 폴더 재생성: %s", uc_dir)
            except Exception as e2:
                logger.warning("[정리] uc driver 폴더 재생성 실패: %s", e2)


def _cleanup_orphaned():
    import subprocess
    _cleanup_uc_driver()
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], capture_output=True)
        logger.info("[정리] 이전 chrome.exe 종료")
    except Exception:
        pass
    for slot_id in range(_MAX_WORKERS):
        pdir = _profile_dir(slot_id)
        _kill_chrome_using_profile(pdir)
        _clean_profile_locks(pdir)
    _clean_profile_locks(_naver_profile_dir())
    # 프로세스가 완전히 종료되도록 대기
    time.sleep(2)


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("scraper-agent 수집 서버 시작 (포트 %d, 슬롯 %d개)", PORT, _MAX_WORKERS)
    logger.info("=" * 60)

    _cleanup_orphaned()

    ok = 0
    for i in range(_MAX_WORKERS):
        try:
            _slots.append(_Slot(i))
            ok += 1
            logger.info("[슬롯%d] 준비 완료 (%d/%d)", i, ok, _MAX_WORKERS)
        except Exception as e:
            logger.error("[슬롯%d] 초기화 실패 — 건너뜀: %s", i, e)

    if ok == 0:
        logger.error("슬롯이 하나도 준비되지 않았습니다. 종료합니다.")
        sys.exit(1)

    # 네이버 슬롯 초기화 (실패해도 서버는 계속 기동)
    try:
        _clean_profile_locks(_naver_profile_dir())
        _naver_slot = _NaverSlot()
        logger.info("[네이버슬롯] 준비 완료")
    except Exception as e:
        logger.warning("[네이버슬롯] 초기화 실패 (네이버 수집 불가): %s", e)
        _naver_slot = None

    logger.info("서버 준비 완료 — 슬롯 %d/%d개 + 네이버슬롯 %s",
                ok, _MAX_WORKERS, "OK" if _naver_slot else "실패")

    threading.Thread(target=_watchdog_loop, daemon=True).start()
    app.run(host='127.0.0.1', port=PORT, debug=False, threaded=True)
