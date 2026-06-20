"""쿠팡 전용 undetected_chromedriver 기반 수집기."""
import logging
import os
import shutil
import tempfile
import time
import random
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_cached_chrome_version: Optional[int] = None


def _purge_uc_caches() -> bool:
    """UC 캐시와 임시 Chrome 프로필을 삭제한다. 성공 여부 반환."""
    deleted_any = False

    # 1. undetected_chromedriver 실행파일 캐시
    try:
        from undetected_chromedriver.patcher import Patcher
        uc_cache = Path(Patcher().data_path)
        if uc_cache.exists():
            shutil.rmtree(uc_cache, ignore_errors=True)
            logger.info(f"UC 캐시 삭제: {uc_cache}")
            deleted_any = True
    except Exception as _e:
        logger.warning(f"UC 캐시 삭제 실패: {_e}")

    # 2. 임시 Chrome 프로필 (chrome_profile_coupang_*)
    try:
        tmp = Path(tempfile.gettempdir())
        for p in tmp.glob("chrome_profile_coupang_*"):
            shutil.rmtree(p, ignore_errors=True)
            logger.info(f"임시 프로필 삭제: {p}")
            deleted_any = True
    except Exception as _e:
        logger.warning(f"임시 프로필 삭제 실패: {_e}")

    return deleted_any


def _build_chrome_ua(version: Optional[int] = None) -> str:
    """설치된 Chrome 버전 기반으로 실제 UA 문자열 생성."""
    v = version or 136
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{v}.0.0.0 Safari/537.36"
    )

def _detect_chrome_version() -> Optional[int]:
    """Chrome 메이저 버전 감지 (프로세스당 1회 캐시)."""
    global _cached_chrome_version
    if _cached_chrome_version is not None:
        return _cached_chrome_version
    try:
        import subprocess, re
        # 레지스트리 우선 — chrome.exe --version은 Windows에서 창을 잠깐 띄우므로 사용 안 함
        for reg_key in (
            r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon',
            r'HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon',
            r'HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon',
        ):
            r = subprocess.run(
                ['reg', 'query', reg_key, '/v', 'version'],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                _cached_chrome_version = int(r.stdout.split()[-1].split('.')[0])
                return _cached_chrome_version
    except Exception as e:
        logger.debug(f"Chrome 버전 감지 실패: {e}")

    return None


class CoupangCollector:
    """쿠팡 전용 undetected_chromedriver 기반 수집기."""
    
    def __init__(
        self,
        profile_dir: Optional[str] = None,
        headless: bool = False,
        timeout: int = 30,
        debug: bool = False,
        persistent: bool = False,
    ):
        """
        Initialize collector.

        Args:
            profile_dir: Chrome 프로필 디렉토리 (캐시/쿠키 유지)
            headless: 헤드리스 모드
            timeout: 타임아웃 (초)
            debug: 디버그 모드 (브라우저 창 표시 및 개발자 도구 활성화)
            persistent: True면 프로필을 삭제하지 않고 재사용 (봇 감지 회피)
        """
        if profile_dir is None:
            # persistent 모드: 고정 경로 사용
            if persistent:
                profile_dir = os.path.join(tempfile.gettempdir(), "chrome_profile_coupang_persistent")
            else:
                timestamp = int(time.time())
                profile_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_coupang_{timestamp}")

        # persistent 모드가 아닐 때만 기존 프로필 삭제
        if not persistent and os.path.exists(profile_dir):
            import shutil
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
                logger.info(f"기존 프로필 디렉토리 삭제: {profile_dir}")
            except Exception as e:
                logger.warning(f"프로필 삭제 실패, 계속 진행: {e}")

        os.makedirs(profile_dir, exist_ok=True)

        self.profile_dir = profile_dir
        self.headless = headless
        self.timeout = timeout
        self.debug = debug
        self.persistent = persistent
        self.driver: Optional[uc.Chrome] = None

        # 디버그 모드면 헤드리스 모드 강제 비활성화
        if self.debug:
            self.headless = False
            logger.info("디버그 모드 활성화: 헤드리스 모드 비활성화됨")

        logger.info(f"쿠팡 Chrome 프로필 디렉토리: {profile_dir} (persistent={persistent})")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def start(self):
        """undetected_chromedriver 시작."""
        if self.driver:
            logger.warning("Driver already started")
            return
        
        if not self.debug:
            logger.debug("쿠팡용 undetected_chromedriver 시작 중...")
        else:
            logger.info("쿠팡용 undetected_chromedriver 시작 중...")
        
        # undetected_chromedriver 옵션 설정
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # 프로필 디렉토리 설정
        profile_path = os.path.abspath(self.profile_dir)

        # SingletonLock / SingletonCookie / DevToolsActivePort 삭제 (크래시 잔여물 → Chrome 재시작 차단)
        for _lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"):
            _lock_path = os.path.join(profile_path, _lock_name)
            if os.path.exists(_lock_path) or os.path.islink(_lock_path):
                try:
                    os.remove(_lock_path)
                    logger.info("크래시 잔여 파일 삭제: %s", _lock_name)
                except Exception as _e:
                    logger.warning("잔여 파일 삭제 실패: %s — %s", _lock_name, _e)

        # Preferences 파일 손상 시 자동 삭제 (손상 파일이 uc 초기화를 크래시시킴)
        import json as _json
        _prefs = os.path.join(profile_path, "Default", "Preferences")
        if os.path.exists(_prefs):
            try:
                with open(_prefs, "r", encoding="utf-8") as _f:
                    _json.load(_f)
            except Exception:
                logger.warning("Preferences 파일 손상됨 → 삭제: %s", _prefs)
                try:
                    os.remove(_prefs)
                except Exception as _e:
                    logger.warning("Preferences 삭제 실패: %s", _e)

        options.add_argument(f"--user-data-dir={profile_path}")
        
        # 기본 최적화 설정
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-features=VizDisplayCompositor")
        
        # 성능 최적화
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        
        # 리소스 로딩 최적화 (필요시 이미지/JS 차단 가능하지만, 쿠팡은 JS 필요)
        prefs = {
            "profile.managed_default_content_settings.images": 1,  # 이미지 허용 (상품 이미지 필요)
            "profile.default_content_setting_values.notifications": 2,  # 알림 차단
            "profile.managed_default_content_settings.cookies": 1,  # 쿠키 허용 (필수)
            "profile.managed_default_content_settings.javascript": 1,  # JS 허용 (필수)
            "profile.managed_default_content_settings.plugins": 1,
            "profile.managed_default_content_settings.popups": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
            "intl.accept_languages": "ko-KR,ko,en-US,en"
        }
        options.add_experimental_option("prefs", prefs)
        
        # 페이지 로드 전략 (eager: DOM 준비되면 바로 진행)
        options.page_load_strategy = 'eager'
        
        # 고정 User-Agent (실제 설치된 Chrome 버전 기반)
        version_main = _detect_chrome_version()
        fixed_ua = _build_chrome_ua(version_main)
        options.add_argument(f'user-agent={fixed_ua}')
        if self.debug:
            logger.info(f"User-Agent: {fixed_ua}")
        else:
            logger.debug(f"User-Agent: {fixed_ua}")
        
        # 메모리 최적화
        options.add_argument("--memory-pressure-off")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=ko-KR")
        
        # 디버그 모드: 개발자 도구 자동 열기
        if self.debug:
            options.add_argument("--auto-open-devtools-for-tabs")
            # undetected_chromedriver는 detach 옵션을 지원하지 않음
            # 디버그 모드에서는 close() 메서드에서 브라우저를 열어둠
        else:
            # 디버그 모드가 아닐 때만 성능 최적화 옵션 추가
            options.add_argument("--disable-logging")  # 로깅 비활성화
            options.add_argument("--log-level=3")  # 로그 레벨 최소화
        
        # uc 3.5.5 버그 우회: patcher.auto()가 캐시 디렉토리가 비어있으면
        # max() arg is an empty sequence 에러를 냄 → webdriver_manager로
        # chromedriver를 먼저 받아서 경로를 직접 넘겨 buggy 코드 경로를 건너뜀
        _driver_path = None
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            _driver_path = ChromeDriverManager().install()
            logger.info(f"ChromeDriver 경로: {_driver_path}")
        except Exception as _wdm_e:
            logger.warning(f"webdriver_manager 실패, uc 자동 감지로 폴백: {_wdm_e}")

        # uc 3.5.5 버그: patcher.auto()가 자체 캐시 디렉토리(data_path)가
        # 비어있으면 max() 에러로 죽음. driver_executable_path를 넘겨도 auto()는
        # 항상 실행되므로, wdm이 받은 chromedriver를 uc 캐시에 미리 심어서 우회.
        if _driver_path:
            try:
                from undetected_chromedriver.patcher import Patcher
                _uc_cache = Path(Patcher().data_path)
                _uc_cache.mkdir(parents=True, exist_ok=True)
                _uc_dst = _uc_cache / "undetected_chromedriver.exe"
                # 항상 덮어쓰기 — 이전 Chrome 버전용 캐시가 남아있으면 버전 불일치 오류 발생
                shutil.copy2(_driver_path, str(_uc_dst))
                logger.info(f"chromedriver → uc 캐시 복사 완료: {_uc_dst}")
            except Exception as _cp_e:
                logger.warning(f"uc 캐시 사전 복사 실패: {_cp_e}")

        try:
            self.driver = uc.Chrome(
                options=options,
                use_subprocess=False,
                version_main=version_main,
                driver_executable_path=None,
                user_multi_procs=True,
            )
        except Exception as e:
            logger.error(f"undetected_chromedriver 시작 실패: {e}")
            if _purge_uc_caches():
                logger.info("캐시 삭제 후 재시도...")
                self.driver = uc.Chrome(
                    options=options,
                    use_subprocess=False,
                    version_main=version_main,
                    driver_executable_path=_driver_path,
                    user_multi_procs=True,
                )
            else:
                raise
        
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.implicitly_wait(2)  # 암시적 대기 시간 최소화 (10초 -> 2초)
        
        # 디버그 모드: 브라우저 최대화
        if self.debug:
            self.driver.maximize_window()
            logger.info("브라우저 창 최대화 완료")
        
        # 추가 봇 감지 우회 스크립트 (undetected_chromedriver가 기본적으로 처리하지만 추가 보강)
        self._apply_stealth_techniques()
        
        if not self.debug:
            logger.debug("쿠팡용 undetected_chromedriver 시작 완료")
        else:
            logger.info("쿠팡용 undetected_chromedriver 시작 완료")
    
    def _apply_stealth_techniques(self):
        """추가 봇 감지 우회 스크립트 적용 (undetected_chromedriver가 기본적으로 처리하지만 보강)."""
        if self.debug:
            logger.info("추가 봇 감지 우회 스크립트 적용 중...")
        else:
            logger.debug("추가 봇 감지 우회 스크립트 적용 중...")
        
        try:
            # 1. window.chrome 객체 보강
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    if (!window.chrome) {
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                    }
                '''
            })
            
            # 2. WebGL 벤더 정보 설정
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        if (parameter === 37445) {
                            return 'Intel Inc.';
                        }
                        if (parameter === 37446) {
                            return 'Intel Iris OpenGL Engine';
                        }
                        return getParameter.call(this, parameter);
                    };
                '''
            })
            
            if self.debug:
                logger.info("추가 봇 감지 우회 스크립트 적용 완료")
            else:
                logger.debug("추가 봇 감지 우회 스크립트 적용 완료")
        except Exception as e:
            logger.debug(f"추가 스크립트 적용 실패 (무시): {e}")
    
    def close(self):
        """ChromeDriver 종료."""
        if self.driver:
            if self.debug:
                # 디버그 모드: 브라우저를 열어둠
                logger.info("⚠️ 디버그 모드: 브라우저 창을 열어둡니다. 확인 후 수동으로 닫아주세요.")
                return

            try:
                self.driver.quit()
                logger.info("ChromeDriver 종료 완료")
            except Exception as e:
                logger.warning(f"ChromeDriver 종료 중 오류: {e}")
            finally:
                self.driver = None

        # PID 추적은 Windows에서 신뢰할 수 없음 (Chrome이 내부적으로 자식 프로세스를 재생성하면
        # browser_pid는 이미 종료된 프로세스 PID가 되어 kill이 무효화됨).
        # 대신, 요청마다 고유한 프로필 디렉토리 경로를 Chrome 커맨드라인에서 매칭해 강제 종료.
        if not self.debug and not self.persistent and self.profile_dir:
            try:
                import subprocess
                profile_marker = os.path.basename(self.profile_dir)
                ps_cmd = (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.Name -eq 'chrome.exe' -and "
                    f"$_.CommandLine -like '*{profile_marker}*' }} | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
                )
                subprocess.call(
                    ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
                logger.info(f"Chrome 프로세스 강제 종료 (프로필 기준): {profile_marker}")
            except Exception as e:
                logger.warning(f"Chrome 프로세스 종료 실패: {e}")

        # 프로필 디렉토리 정리 (디버그/persistent 모드가 아닐 때만)
        if not self.debug and not self.persistent and self.profile_dir:
            try:
                import shutil
                if os.path.exists(self.profile_dir):
                    shutil.rmtree(self.profile_dir, ignore_errors=True)
                    logger.info(f"프로필 디렉토리 정리 완료: {self.profile_dir}")
            except Exception as e:
                logger.debug(f"프로필 디렉토리 정리 실패 (무시): {e}")
    
    def collect_product_page(self, url: str, save_screenshot: bool = True) -> dict:
        """
        쿠팡 상품 페이지 HTML 수집.
        홈페이지 우회 전략 사용: 직접 상품 페이지로 접근.
        
        Args:
            url: 상품 페이지 URL
            save_screenshot: 스크린샷 저장 여부
            
        Returns:
            dict with html, page_title, final_url, screenshot_path
        """
        if not self.driver:
            raise RuntimeError("Driver not started")
        
        if not self.debug:
            logger.debug(f"쿠팡 상품 페이지 접근: {url}")
        else:
            logger.info(f"쿠팡 상품 페이지 접근: {url}")
        
        # 홈페이지 우회: 직접 상품 페이지로 접근
        # Google 검색에서 온 것처럼 Referer 설정
        try:
            self.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                "headers": {
                    "Referer": "https://www.google.com/search?q=coupang",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-User": "?1",
                    "Cache-Control": "max-age=0",
                }
            })
            if self.debug:
                logger.info("HTTP 헤더 설정 완료 (Google 검색에서 온 것처럼)")
            else:
                logger.debug("HTTP 헤더 설정 완료")
        except Exception as e:
            logger.warning(f"헤더 설정 실패: {e}")
        
        # 직접 상품 페이지로 접근
        if self.debug:
            logger.info("상품 페이지 로드 중...")
        else:
            logger.debug("상품 페이지 로드 중...")
        max_retries = 3
        retry_count = 0
        final_url = None
        
        while retry_count < max_retries:
            try:
                self.driver.get(url)
                # 초기 로드 대기 (최소화)
                try:
                    WebDriverWait(self.driver, 2).until(  # 타임아웃 더 줄임 (3초 -> 2초)
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                except:
                    time.sleep(0.3)  # 폴백 대기 더 줄임 (0.5초 -> 0.3초)
                
                # 최종 URL 확인
                final_url = self.driver.current_url
                if self.debug:
                    logger.info(f"접근한 URL: {url}")
                    logger.info(f"최종 URL: {final_url}")
                else:
                    logger.debug(f"최종 URL: {final_url}")
                
                # 메인 화면으로 리다이렉트되었는지 확인
                if 'coupang.com' in final_url.lower():
                    # 메인 화면인지 확인 (상품 페이지가 아닌 경우)
                    is_main_page = (
                        final_url == 'https://www.coupang.com/' or
                        final_url == 'https://www.coupang.com' or
                        '/np/' in final_url.lower() or  # 검색 결과 페이지
                        '/vp/products/' not in final_url.lower() and '/products/' not in final_url.lower()
                    )
                    
                    if is_main_page and retry_count < max_retries - 1:
                        retry_count += 1
                        logger.warning(f"메인 화면으로 리다이렉트됨 (재시도 {retry_count}/{max_retries})")
                        
                        # 사용자 행동 시뮬레이션 후 재시도 (최소화)
                        time.sleep(0.3)  # 더 줄임 (0.5초 -> 0.3초)
                        try:
                            # 랜덤 마우스 움직임 (간단하게)
                            actions = ActionChains(self.driver)
                            actions.move_by_offset(random.randint(100, 300), random.randint(100, 300))
                            actions.perform()
                        except:
                            pass
                        
                        time.sleep(0.3)  # 더 줄임 (0.5초 -> 0.3초)
                        continue
                    elif is_main_page:
                        logger.error("⚠️ 메인 화면으로 리다이렉트됨 - 쿠팡의 봇 감지로 인한 차단 가능성")
                        raise Exception("쿠팡이 상품 페이지 접근을 차단하고 메인 화면으로 리다이렉트함")
                    else:
                        if self.debug:
                            logger.info("상품 페이지 접근 성공")
                        else:
                            logger.debug("상품 페이지 접근 성공")
                        break
                else:
                    logger.warning(f"예상치 못한 URL: {final_url}")
                    break
                    
            except Exception as e:
                if retry_count < max_retries - 1:
                    retry_count += 1
                    logger.warning(f"페이지 로드 실패 (재시도 {retry_count}/{max_retries}): {e}")
                    time.sleep(0.5)  # 재시도 대기 더 최소화 (1초 -> 0.5초)
                    continue
                else:
                    logger.error(f"페이지 로드 실패: {e}")
                    raise
        
        # 페이지 로드 확인 (동적 대기 - 최소화)
        if self.debug:
            logger.info("페이지 로드 확인 중...")
        try:
            WebDriverWait(self.driver, 2).until(  # 타임아웃 더 줄임 (5초 -> 2초)
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            if self.debug:
                logger.info("페이지 body 로드 완료")
        except Exception as e:
            logger.debug(f"페이지 로드 확인 실패, 계속 진행: {e}")
        
        # Cloudflare 체크 대기 생략 (undetected_chromedriver가 이미 우회 처리)
        
        # 최종 URL 재확인
        final_url_check = self.driver.current_url
        if final_url_check != final_url:
            if self.debug:
                logger.info(f"URL 변경 감지: {final_url} -> {final_url_check}")
            else:
                logger.debug(f"URL 변경 감지: {final_url} -> {final_url_check}")
            final_url = final_url_check
        
        # 상품 정보가 로드될 때까지 대기 (CSS 선택자 OR로 한 번에 확인 — 순차 대기 제거)
        _combined_selector = (
            "h1.prod-buy-header__title, .prod-buy-header, #productTitle, "
            "h1[class*='prod'], .prod-product-information, [data-product-id]"
        )
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _combined_selector))
            )
            logger.debug("상품 정보 로드 완료")
        except Exception as e:
            # 타임아웃이어도 HTML은 있을 수 있음 — 메인 화면 리다이렉트만 차단
            current_url = self.driver.current_url
            if current_url in ('https://www.coupang.com/', 'https://www.coupang.com'):
                raise Exception("쿠팡이 상품 페이지 접근을 차단하고 메인 화면으로 리다이렉트함")
            logger.warning(f"상품 정보 요소 미확인, 계속 진행: {e}")
        
        # 간단한 스크롤 시뮬레이션 (봇 감지 우회)
        try:
            self.driver.execute_script("window.scrollTo(0, 100);")
            self.driver.execute_script("window.scrollTo(0, 0);")
            if self.debug:
                logger.info("사용자 행동 시뮬레이션 완료")
        except Exception as e:
            logger.debug(f"사용자 행동 시뮬레이션 실패: {e}")
        
        # HTML 먼저 가져오기 (스크린샷보다 빠름)
        html_content = self.driver.page_source
        page_title = self.driver.title
        final_url_check = self.driver.current_url
        
        if self.debug:
            logger.info(f"최종 확인 - URL: {final_url_check}, 제목: {page_title[:50]}...")
        else:
            logger.debug(f"최종 확인 - URL: {final_url_check}")
        
        # Access Denied 체크
        if "access denied" in page_title.lower() or "access denied" in html_content.lower()[:10000]:
            logger.error("⚠️ Access Denied 발생")
            if self.debug:
                logger.info("디버그 모드: 브라우저 창에서 상황을 확인할 수 있습니다.")
                time.sleep(5)  # 확인 시간 제공 (더 최소화: 10초 -> 5초)
            raise Exception("쿠팡 페이지 Access Denied - IP 차단 또는 네트워크 문제 가능성")
        
        # 메인 화면 체크
        if final_url_check == 'https://www.coupang.com/' or final_url_check == 'https://www.coupang.com':
            logger.error("⚠️ 메인 화면으로 리다이렉트됨")
            if self.debug:
                logger.info("디버그 모드: 브라우저 창에서 상황을 확인할 수 있습니다.")
                time.sleep(5)  # 확인 시간 제공 (더 최소화: 10초 -> 5초)
            raise Exception("쿠팡이 상품 페이지 접근을 차단하고 메인 화면으로 리다이렉트함")
        
        # HTML 길이 체크
        if len(html_content) < 5000:
            logger.warning(f"⚠️ HTML이 너무 짧음: {len(html_content)} 문자")
            if self.debug:
                logger.info("디버그 모드: 브라우저 창에서 상황을 확인할 수 있습니다.")
                time.sleep(5)  # 확인 시간 제공 (더 최소화: 10초 -> 5초)
        
        if self.debug:
            # 디버그 모드: 개발자 도구를 열 수 있도록 충분한 대기 시간 제공
            logger.info("디버그 모드: 개발자 도구를 열어 확인할 수 있습니다.")
            logger.info("브라우저 창에서 F12를 눌러 개발자 도구를 열 수 있습니다.")
            time.sleep(5)  # 확인 시간 제공 (더 최소화: 10초 -> 5초)
        
        # 스크린샷 저장 (HTML 수집 후 - 선택적)
        screenshot_path = None
        if save_screenshot:
            import tempfile
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            screenshot_path = os.path.join(tempfile.gettempdir(), f"coupang_screenshot_{url_hash}.png")
            try:
                self.driver.save_screenshot(screenshot_path)
                if self.debug:
                    logger.info(f"스크린샷 저장: {screenshot_path}")
                else:
                    logger.debug(f"스크린샷 저장: {screenshot_path}")
            except Exception as e:
                logger.warning(f"스크린샷 저장 실패: {e}")
        
        html = html_content
        final_url = final_url_check
        
        # 최종 URL 확인 (상품 페이지인지)
        if '/vp/products/' not in final_url.lower() and '/products/' not in final_url.lower():
            logger.warning(f"⚠️ 상품 페이지가 아닌 URL: {final_url}")
            if self.debug:
                logger.info("디버그 모드: 브라우저 창에서 상황을 확인할 수 있습니다.")
                time.sleep(10)
        
        if not self.debug:
            logger.debug(f"수집 완료: {len(html)} 문자")
        else:
            if self.debug:
                logger.info(f"수집 완료: {len(html)} 문자, 제목: {page_title}, URL: {final_url}")
            else:
                logger.debug(f"수집 완료: {len(html)} 문자")
        
        return {
            "html": html,
            "page_title": page_title,
            "final_url": final_url,
            "screenshot_path": screenshot_path,
            "success": True
        }
