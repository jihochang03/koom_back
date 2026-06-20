"""네이버 스마트스토어 수집기 - 캐시 사용, 검색, HTML 수집."""
import logging
import os
import tempfile
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NaverCollector:
    """네이버 스마트스토어 수집기 - 캐시/쿠키 유지."""
    
    def __init__(
        self,
        profile_dir: Optional[str] = None,
        headless: bool = False,
        timeout: int = 30,
        debug: bool = False,
        debug_port: Optional[int] = None,
    ):
        """
        Initialize Naver collector.
        
        Args:
            profile_dir: Chrome 프로필 디렉토리 (캐시/쿠키 유지)
            headless: 헤드리스 모드
            timeout: 타임아웃 (초)
            debug: 디버그 모드 (브라우저 창 표시 및 개발자 도구 활성화)
        """
        if profile_dir is None:
            # 매번 새로운 프로필 생성 (캐시 갱신)
            import time
            timestamp = int(time.time())
            profile_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_naver_{timestamp}")
        os.makedirs(profile_dir, exist_ok=True)
        
        self.profile_dir = profile_dir
        self.persistent_profile = os.path.basename(profile_dir).endswith("_persistent")
        self.profile_ready_marker = os.path.join(profile_dir, ".naver_profile_ready")
        self.profile_ready = os.path.exists(self.profile_ready_marker)
        self.headless = headless
        self.timeout = timeout
        self.debug = debug
        self.debug_port = debug_port  # --remote-debugging-port (재접속용)
        self.driver: Optional[webdriver.Chrome] = None
        
        # 디버그 모드면 헤드리스 모드 강제 비활성화
        if self.debug:
            self.headless = False
            logger.info("디버그 모드 활성화: 헤드리스 모드 비활성화됨")
        
        logger.info(f"Chrome 프로필 디렉토리: {profile_dir}")
        if self.profile_ready:
            logger.info("네이버 프로필 캐시 재사용 모드: 이전 인증 세션을 사용합니다.")
        else:
            logger.info("네이버 프로필 초기 설정 모드: 첫 인증 후 세션을 저장합니다.")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def start(self):
        """ChromeDriver 시작."""
        if not self.debug:
            logger.debug("ChromeDriver 시작 중...")  # 디버그 모드가 아닐 때는 로그 레벨 낮춤
        else:
            logger.info("ChromeDriver 시작 중...")
        
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument("--headless=new")

        # 캐시/쿠키 유지를 위한 프로필 디렉토리 (절대 경로로 변환)
        profile_path = os.path.abspath(self.profile_dir)
        chrome_options.add_argument(f"--user-data-dir={profile_path}")
        chrome_options.add_argument("--profile-directory=Profile 1")  # 프로필 피커 없이 Profile 1로 직접 진입

        # Chrome 시작 전 Local State 파일을 미리 써서 프로필 선택 창 억제
        # last_used=Default 로 지정하면 picker 없이 바로 해당 프로필로 진입
        self._ensure_local_state(profile_path)

        # 첫 실행 시 Chrome 자체 팝업/로그인 유도 화면 억제
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-features=ChromeWhatsNewUI,Translate")
        chrome_options.add_argument("--disable-session-crashed-bubble")
        chrome_options.add_argument("--disable-infobars")

        # 원격 디버그 포트 (재접속용 — Google 로그인 후 창 교체돼도 재연결 가능)
        if self.debug_port:
            chrome_options.add_argument(f"--remote-debugging-port={self.debug_port}")

        chrome_options.add_argument("--disable-gpu")
        
        # 성능 최적화 옵션
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-sync")  # 동기화 비활성화
        chrome_options.add_argument("--metrics-recording-only")  # 메트릭스만 기록
        chrome_options.add_argument("--disable-default-apps")  # 기본 앱 비활성화
        
        # Anti-bot 우회 설정
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # User-Agent: 명시하지 않고 실제 설치된 Chrome 버전 그대로 사용
        # (하드코딩하면 실제 Chrome 버전과 불일치 → 봇 감지)
        
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--lang=ko-KR")
        
        # 리소스 로딩 최적화 (이미지는 HTML에서 추출 가능하므로 차단 가능)
        prefs = {
            'intl.accept_languages': 'ko-KR,ko,en-US,en',
            'profile.managed_default_content_settings.images': 2,  # 이미지 차단 (속도 향상)
            'profile.default_content_setting_values.notifications': 2,  # 알림 차단
            'profile.default_content_setting_values.media_stream': 2,  # 미디어 스트림 차단
            'profile.default_content_setting_values.geolocation': 2,  # 위치 정보 차단
            'profile.exit_type': 'Normal',  # Chrome 재시작 시 "복구" 팝업 억제
        }
        chrome_options.add_experimental_option('prefs', prefs)
        
        # 디버그 모드 (새 프로필 초기 설정): devtools 자동 오픈은 창 못 찾는 버그 유발 → 제거
        if self.debug:
            pass  # headless=False 이면 충분, 추가 플래그 불필요
        else:
            # 디버그 모드가 아닐 때만 성능 최적화 옵션 추가
            chrome_options.add_argument("--disable-logging")  # 로깅 비활성화
            chrome_options.add_argument("--log-level=3")  # 로그 레벨 최소화
        
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except ImportError:
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.error(f"ChromeDriver 시작 실패: {e}")
            if self.persistent_profile:
                raise RuntimeError(
                    "네이버 고정 프로필을 열지 못했습니다. 이전 브라우저 창이 아직 열려 있거나 "
                    "프로필이 잠겨 있을 수 있습니다. 열려 있는 네이버/Chrome 창을 모두 닫고 다시 시도해주세요."
                ) from e
            # 프로필 잠금 문제일 수 있으므로, 프로필 디렉토리 이름에 타임스탬프 추가해서 재시도
            import time
            profile_path_with_timestamp = f"{profile_path}_{int(time.time())}"
            os.makedirs(profile_path_with_timestamp, exist_ok=True)
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            chrome_options.add_argument(f"--user-data-dir={profile_path_with_timestamp}")
            chrome_options.add_argument("--profile-directory=Profile 1")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--lang=ko-KR")
            chrome_options.add_experimental_option('prefs', {
                'intl.accept_languages': 'ko-KR,ko,en-US,en',
                'profile.managed_default_content_settings.images': 2,  # 이미지 차단
            })
            logger.info(f"새 프로필 디렉토리로 재시도: {profile_path_with_timestamp}")
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except ImportError:
                self.driver = webdriver.Chrome(options=chrome_options)

        self._dismiss_profile_picker()

        # _dismiss_profile_picker 후 창이 교체됐을 수 있으므로 유효한 창으로 복구
        try:
            _ = self.driver.current_url
        except Exception:
            try:
                handles = self.driver.window_handles
                if handles:
                    self.driver.switch_to.window(handles[-1])
            except Exception:
                pass

        self.driver.set_page_load_timeout(self.timeout)
        self.driver.implicitly_wait(2)  # 암시적 대기 시간 더 최소화 (3초 -> 2초)
        
        # 페이지 로드 전략 최적화 (DOM 준비되면 바로 진행)
        try:
            self.driver.execute_cdp_cmd('Page.setLifecycleEventsEnabled', {'enabled': False})
        except:
            pass  # CDP 명령 실패해도 계속 진행
        
        # 디버그 모드: 브라우저 최대화
        if self.debug:
            self.driver.maximize_window()
            logger.info("브라우저 창 최대화 완료")
        
        # Anti-bot 스크립트
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            '''
        })
        
        if not self.debug:
            logger.debug("ChromeDriver 시작 완료")
        else:
            logger.info("ChromeDriver 시작 완료")
    
    def _ensure_local_state(self, profile_path: str):
        """Chrome 시작 전 Local State 파일에 last_used 프로필을 설정해 프로필 선택 창을 방지."""
        import json
        os.makedirs(profile_path, exist_ok=True)
        local_state_path = os.path.join(profile_path, "Local State")

        try:
            if os.path.exists(local_state_path):
                with open(local_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            else:
                state = {}

            profile_section = state.setdefault("profile", {})

            # last_used 가 이미 설정돼 있으면 그대로 유지, 없으면 Default 로 초기화
            if not profile_section.get("last_used"):
                profile_section["last_used"] = "Default"

            # info_cache 에 해당 프로필 항목이 없으면 추가
            last_used = profile_section["last_used"]
            info_cache = profile_section.setdefault("info_cache", {})
            if last_used not in info_cache:
                info_cache[last_used] = {
                    "active_time": 1.0,
                    "is_using_default_name": True,
                    "name": "사용자 이름 1",
                }

            with open(local_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)

        except Exception as e:
            logger.debug("Local State 사전 설정 실패 (무시): %s", e)

    def _dismiss_profile_picker(self):
        """Chrome 프로필 선택 창이 뜨면 '사용자 이름 1' 프로필을 클릭.

        클릭 후 픽커 창이 닫히고 새 창이 열리는 전환을 기다린 뒤 새 창으로 switch.
        실패해도 예외를 전파하지 않는다 — 사용자가 직접 클릭하면 됨.
        """
        import time

        # profile-picker URL이 뜰 때까지 최대 5초 대기
        for _ in range(10):
            time.sleep(0.5)
            try:
                if "profile-picker" in self.driver.current_url.lower():
                    break
            except Exception:
                return  # driver 자체 문제 → 그냥 복귀
        else:
            return  # profile-picker 아님

        logger.info("Chrome 프로필 선택 창 감지 → '사용자 이름 1' 선택 시도 (최대 4초 대기)")

        _FIND = """
            function findItems(root, out, depth) {
                if (!root || depth > 15) return;
                for (const el of Array.from(root.querySelectorAll('*'))) {
                    if ((el.tagName || '').toLowerCase() === 'profile-list-item-v2') out.push(el);
                    if (el.shadowRoot) findItems(el.shadowRoot, out, depth + 1);
                }
            }
            const items = [];
            findItems(document, items, 0);
            if (items.length === 0) return null;
            items[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
            return 'ok:x' + items.length;
        """

        try:
            before_handles = set(self.driver.window_handles)
        except Exception:
            return

        clicked = False
        for attempt in range(8):  # 0.5 × 8 = 4초
            time.sleep(0.5)
            try:
                result = self.driver.execute_script(_FIND)
            except Exception:
                # 창이 이미 전환 중 → 클릭이 성공해 픽커 창이 닫힌 것
                logger.info("프로필 선택 창 전환 감지 (정상 종료)")
                clicked = True
                break
            if result and result.startswith("ok:"):
                logger.info("'사용자 이름 1' 프로필 선택 완료: %s", result)
                clicked = True
                break

        if not clicked:
            logger.warning("'사용자 이름 1' 프로필을 찾지 못함 (4초 대기 후 포기 — 수동 클릭 필요)")
            return

        # 픽커 창이 닫히고 새 창이 열릴 때까지 최대 3초 대기 후 전환
        for _ in range(6):
            time.sleep(0.5)
            try:
                handles = self.driver.window_handles
                if not handles:
                    continue
                try:
                    url = self.driver.current_url
                    if "profile-picker" not in url.lower():
                        return  # 이미 올바른 창에 있음
                except Exception:
                    # 현재 창 무효 → 새 창으로 switch
                    self.driver.switch_to.window(handles[-1])
                    logger.info("새 창으로 전환 완료")
                    return
                # 새로 생긴 핸들이 있으면 그쪽으로 이동
                new_handles = set(handles) - before_handles
                if new_handles:
                    self.driver.switch_to.window(list(new_handles)[0])
                    logger.info("새 창으로 전환 완료")
                    return
            except Exception:
                return  # driver가 자동으로 전환됐거나 이미 새 창에 있음

    def close(self):
        """브라우저 종료."""
        if self.driver:
            if self.debug and not self.persistent_profile:
                # 디버그 모드: 브라우저를 열어둠 (사용자가 직접 확인 가능)
                logger.info("⚠️ 디버그 모드: 브라우저 창을 열어둡니다. 확인 후 수동으로 닫아주세요.")
                logger.info("브라우저를 닫으려면 창을 직접 닫거나 Python 프로세스를 종료하세요.")
                # 디버그 모드에서는 브라우저를 자동으로 닫지 않음
                return
            elif self.debug and self.persistent_profile:
                logger.info("네이버 고정 프로필 재사용을 위해 브라우저를 자동 종료합니다.")
            
            try:
                self.driver.quit()
                logger.info("ChromeDriver 종료")
            except:
                pass
            finally:
                self.driver = None
        
        # 프로필 디렉토리 정리 (디버그 모드가 아닐 때만)
        if not self.debug and self.profile_dir and not self.persistent_profile:
            try:
                import shutil
                if os.path.exists(self.profile_dir):
                    shutil.rmtree(self.profile_dir, ignore_errors=True)
                    logger.info(f"프로필 디렉토리 정리 완료: {self.profile_dir}")
            except Exception as e:
                logger.debug(f"프로필 디렉토리 정리 실패 (무시): {e}")

    def _mark_profile_ready(self):
        """프로필이 초기 인증을 통과했음을 기록."""
        try:
            with open(self.profile_ready_marker, "w", encoding="utf-8") as marker:
                marker.write(str(int(time.time())))
            self.profile_ready = True
            logger.info("네이버 프로필 준비 완료: 이후 요청부터 캐시를 재사용합니다.")
        except Exception as e:
            logger.warning(f"네이버 프로필 준비 상태 저장 실패: {e}")

    def _is_security_page(self, html: str, title: str, current_url: str) -> bool:
        """보안/봇 인증 페이지 감지."""
        url_lower = current_url.lower()

        # URL이 인증/보안 페이지로 바뀐 경우 → 확실한 신호
        security_url_patterns = [
            "nid.naver.com", "login.naver.com", "cert.naver.com",
            "check.naver.com", "security", "captcha", "robot",
        ]
        if any(p in url_lower for p in security_url_patterns):
            return True

        # 정상 상품 URL 여부 판단
        normal_url_patterns = [
            "smartstore.naver.com", "brand.naver.com",
            "shopping.naver.com", "naver.me",
        ]
        is_normal_url = any(p in url_lower for p in normal_url_patterns)

        # HTML 확인 — URL이 정상 스마트스토어여도 캡차 페이지가 같은 URL로 뜰 수 있음
        html_sample = html[:20000]
        security_html_patterns = [
            "보안 확인을 완료해 주세요",
            'id="message_text"',
            "자동화된 요청", "비정상적인 접근", "robot check",
            "security check", "captcha", "naver-robot", 'class="robot"',
            "비정상 접속", "비정상적인 트래픽",
            "wtm_captcha", "rcpt_form", "ncpt.naver.com",
        ]
        if any(p in html_sample for p in security_html_patterns):
            return True

        # 제목이 비어있어도 URL이 정상 스마트스토어/네이버 상품 페이지면 통과
        if not title or not title.strip():
            if is_normal_url:
                return False
            return True

        # 정상 URL이면 제목 키워드 검사 생략
        # (상품명·판매자명에 "인증", "확인" 등이 포함될 수 있어 오탐 발생)
        if is_normal_url:
            return False

        # 제목에 보안/인증 키워드 (비정상 URL일 때만 검사)
        title_lower = title.lower()
        security_title_patterns = ["보안", "인증", "로그인", "로봇", "robot", "captcha", "확인"]
        if any(p in title_lower for p in security_title_patterns):
            return True

        return False

    def _is_not_found_page(self, html: str, title: str) -> bool:
        """상품 없음/에러 페이지 감지 (HTML 텍스트 기반)."""
        not_found_patterns = [
            "상품이 존재하지 않습니다",
            "존재하지 않는 상품",
            "상품을 찾을 수 없",
            "삭제된 상품입니다",
            "판매자가 삭제한 상품",
        ]
        # document.body.innerText가 아닌 raw HTML에도 텍스트가 남는 경우 대비
        html_sample = html[:20000]
        if any(p in html_sample for p in not_found_patterns):
            return True

        title_lower = (title or "").lower()
        if any(p in title_lower for p in ["존재하지 않", "찾을 수 없"]):
            return True

        return False

    @staticmethod
    def _image_media_type(data: bytes) -> str:
        """파일 바이트에서 실제 이미지 MIME 타입 감지."""
        if data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/png'

    def _detect_not_found_in_screenshot(self, screenshot_path: str) -> bool:
        """스크린샷에서 '상품이 존재하지 않습니다' 오류 감지 (Claude vision)."""
        import base64
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or not screenshot_path:
            return False
        try:
            with open(screenshot_path, 'rb') as f:
                img_bytes = f.read()
            img_b64 = base64.standard_b64encode(img_bytes).decode()
            media_type = self._image_media_type(img_bytes)
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "이 스크린샷에 '상품이 존재하지 않습니다', '존재하지 않는 상품', "
                                "'상품을 찾을 수 없습니다' 같은 상품 없음 오류 메시지가 보이나요? "
                                "yes 또는 no 만 답하세요."
                            ),
                        },
                    ],
                }],
            )
            answer = resp.content[0].text.strip().lower()
            detected = "yes" in answer
            if detected:
                logger.info("[상품없음] 스크린샷 vision 감지: '%s'", answer)
            return detected
        except Exception as e:
            logger.debug("[상품없음] 스크린샷 감지 실패: %s", e)
            return False

    def _handle_security_page(self) -> dict:
        """보안 페이지 감지 시: 이미지 URL 추출 → 일반 Chrome으로 열기 → 스크린샷 캡처 → 이미지 저장.

        Returns:
            {
                'screenshot_path': 보안 페이지 스크린샷 경로,
                'image_path':      다운로드된 이미지 경로 (실패 시 없음),
                'main_image_url':  이미지 URL (없으면 없음),
                'image_urls':      페이지 내 전체 이미지 URL 목록,
            }
        """
        import subprocess

        result: dict = {}

        # 1. 보안 페이지 스크린샷 저장
        screenshot_path = os.path.join(
            tempfile.gettempdir(), f"security_page_{int(time.time())}.png"
        )
        try:
            self.driver.save_screenshot(screenshot_path)
            logger.info("[보안페이지] 스크린샷 저장: %s", screenshot_path)
            result['screenshot_path'] = screenshot_path
        except Exception as e:
            logger.warning("[보안페이지] 스크린샷 실패: %s", e)

        # 2. DOM에서 이미지 URL 추출
        try:
            img_elements = self.driver.find_elements(By.TAG_NAME, 'img')
            raw_urls = [
                img.get_attribute('src') or ''
                for img in img_elements
            ]
            image_urls = [u for u in raw_urls if u.startswith('http')]

            # 캡차/보안 관련 이미지 우선 정렬
            priority_kw = ['captcha', 'check', 'robot', 'verify', 'security', 'chk']
            priority = [u for u in image_urls if any(k in u.lower() for k in priority_kw)]
            rest = [u for u in image_urls if u not in priority]
            image_urls = priority + rest

            result['image_urls'] = image_urls
            logger.info("[보안페이지] 이미지 %d개 발견: %s", len(image_urls), image_urls[:3])
        except Exception as e:
            logger.warning("[보안페이지] 이미지 추출 실패: %s", e)
            image_urls = []

        if not image_urls:
            logger.warning("[보안페이지] 페이지에서 이미지를 찾지 못했습니다.")
            return result

        main_image_url = image_urls[0]
        result['main_image_url'] = main_image_url

        # 3. 일반 Chrome으로 이미지 URL 열기 (Windows)
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for chrome_exe in chrome_candidates:
            if os.path.exists(chrome_exe):
                try:
                    subprocess.Popen([chrome_exe, main_image_url])
                    logger.info("[보안페이지] Chrome으로 이미지 열기: %s", main_image_url)
                except Exception as e:
                    logger.warning("[보안페이지] Chrome 실행 실패: %s", e)
                break
        else:
            logger.warning("[보안페이지] Chrome 실행 파일을 찾지 못했습니다. 이미지 URL: %s", main_image_url)

        # 4. 이미지 다운로드 저장 (selenium 쿠키 포함)
        try:
            import requests as _requests
            cookies = {c['name']: c['value'] for c in self.driver.get_cookies()}
            resp = _requests.get(main_image_url, cookies=cookies, timeout=10)
            if resp.ok:
                img_path = os.path.join(
                    tempfile.gettempdir(), f"security_image_{int(time.time())}.png"
                )
                with open(img_path, 'wb') as f:
                    f.write(resp.content)
                result['image_path'] = img_path
                logger.info("[보안페이지] 이미지 저장: %s", img_path)
            else:
                logger.warning("[보안페이지] 이미지 다운로드 실패 (HTTP %d): %s", resp.status_code, main_image_url)
        except Exception as e:
            logger.warning("[보안페이지] 이미지 다운로드 오류: %s", e)

        logger.info(
            "[보안페이지] 처리 완료 — 스크린샷: %s | 이미지: %s",
            result.get('screenshot_path'), result.get('image_path'),
        )
        return result

    def _auto_solve_captcha(self, image_path: str) -> str:
        """Claude API vision으로 캡차 이미지 인식. 실패 시 빈 문자열."""
        import base64
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[보안페이지] ANTHROPIC_API_KEY 없음 — 자동 풀기 불가")
            return ''
        try:
            with open(image_path, 'rb') as f:
                img_bytes = f.read()
            img_b64 = base64.standard_b64encode(img_bytes).decode()
            media_type = self._image_media_type(img_bytes)
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "이미지에 표시된 문자나 숫자를 읽어서 그대로 출력하세요. "
                                "다른 설명 없이 텍스트만 출력하세요."
                            ),
                        },
                    ],
                }],
            )
            result = resp.content[0].text.strip()
            logger.info("[보안페이지] Claude 캡차 인식: '%s'", result)
            return result
        except Exception as e:
            logger.warning("[보안페이지] Claude 캡차 인식 실패: %s", e)
        return ''

    def _solve_security_with_full_screenshot(self) -> bool:
        """전체 화면 스크린샷을 Claude Vision에 보내 보안 질문 자동 답변 입력.

        에러페이지 감지와 동일한 방식으로 보안 페이지를 인식한 뒤,
        전체 화면을 캡처해 Claude에게 질문과 캡차를 한 번에 보여주고 답을 받아 입력한다.
        """
        import base64
        import anthropic
        from selenium.webdriver.common.keys import Keys

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[보안페이지] ANTHROPIC_API_KEY 없음 — 자동 풀기 불가")
            return False

        # 전체 페이지 스크린샷
        screenshot_path = os.path.join(
            tempfile.gettempdir(), f"security_full_{int(time.time())}.png"
        )
        try:
            self.driver.save_screenshot(screenshot_path)
            logger.info("[보안페이지] 전체 스크린샷 저장: %s", screenshot_path)
        except Exception as e:
            logger.warning("[보안페이지] 스크린샷 실패: %s", e)
            return False

        import hashlib
        import re as _re

        def _ask_claude(img_b64: str, media_type: str) -> str:
            """스크린샷을 Claude에 보내 캡차 답 반환. 실패 시 빈 문자열."""
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "화면의 캡차를 분석하고 아래 형식으로 출력하세요.\n\n"
                                "질문: [화면에 보이는 질문 전체]\n"
                                "정보: [화면에서 찾은 전화번호 또는 주소 전체, 있는 그대로]\n"
                                "풀이: [하이픈 제거 후 숫자 나열, 몇 번째인지 계산]\n"
                                "답: [숫자만]\n\n"
                                "규칙:\n"
                                "- 주소 질문: 길/로 바로 뒤 번지 숫자 (예: 북악로 687 → 687)\n"
                                "- 전화번호 질문: 하이픈 모두 제거 후 앞/뒤에서 N번째 숫자 1자리만\n"
                                "  예) 02-1-4267 앞에서 4번째 → 0214267 → 4\n"
                                "  예) 010-1234-5678 뒤에서 2번째 → 01012345678 → 7"
                            ),
                        },
                    ],
                }],
            )
            raw = resp.content[0].text.strip()
            def _extract(label, text):
                m = _re.search(label + r'\s*:\s*(.+)', text)
                return m.group(1).strip() if m else ''
            logger.info("[보안페이지] 질문: %s", _extract('질문', raw))
            logger.info("[보안페이지] 정보: %s", _extract('정보', raw))
            logger.info("[보안페이지] 풀이: %s", _extract('풀이', raw))
            m = _re.search(r'답\s*:\s*([0-9]+)', raw)
            return m.group(1) if m else _re.sub(r'[^0-9]', '', raw.split('\n')[-1])

        answer = ''
        orig_hash = ''
        try:
            with open(screenshot_path, 'rb') as f:
                img_bytes = f.read()
            orig_hash = hashlib.md5(img_bytes).hexdigest()
            img_b64 = base64.standard_b64encode(img_bytes).decode()
            media_type = self._image_media_type(img_bytes)

            # ① Claude에 분석 요청 (2-3초 소요)
            answer = _ask_claude(img_b64, media_type)
            logger.info("[보안페이지] 최종 답 (1차): '%s'", answer)
        except Exception as e:
            logger.warning("[보안페이지] Claude 인식 실패: %s", e)
            return False
        finally:
            try:
                os.remove(screenshot_path)
            except Exception:
                pass

        # ② Claude 응답 대기 중 캡차가 갱신됐을 수 있으므로 직전에 재확인
        try:
            fresh_bytes = self.driver.get_screenshot_as_png()
            fresh_hash = hashlib.md5(fresh_bytes).hexdigest()
            if orig_hash and fresh_hash != orig_hash:
                logger.info("[보안페이지] 캡차 이미지 변경 감지 — 새 스크린샷으로 재분석")
                fresh_b64 = base64.standard_b64encode(fresh_bytes).decode()
                fresh_media = self._image_media_type(fresh_bytes)
                fresh_answer = _ask_claude(fresh_b64, fresh_media)
                if fresh_answer:
                    logger.info("[보안페이지] 재분석 답: '%s' (이전: '%s')", fresh_answer, answer)
                    answer = fresh_answer
                else:
                    logger.warning("[보안페이지] 재분석 실패 — 기존 답 '%s' 사용", answer)
        except Exception as e:
            logger.warning("[보안페이지] 재확인 스크린샷 실패: %s", e)

        if not answer:
            logger.warning("[보안페이지] Claude 답변 비어있음")
            return False

        # 입력 필드 탐색 (보이고 활성화된 것 우선)
        try:
            candidates = self.driver.find_elements(
                By.CSS_SELECTOR,
                'input[type="text"], input[type="number"], input:not([type])',
            )
            target_input = next(
                (el for el in candidates if el.is_displayed() and el.is_enabled()),
                None,
            )
            if target_input is None:
                logger.warning("[보안페이지] 입력 필드를 찾지 못했습니다.")
                return False

            target_input.clear()
            time.sleep(0.2)  # clear 이벤트 안정화
            target_input.send_keys(answer)
            logger.info("[보안페이지] 답변 입력: '%s'", answer)
            time.sleep(0.3)  # 입력값 등록 대기

            # Enter 키로 우선 제출 (any-button 클릭은 새 캡차 버튼을 잡을 위험이 있음)
            target_input.send_keys(Keys.RETURN)
            logger.info("[보안페이지] Enter 키로 제출")
            time.sleep(1.5)

            # Enter로 제출됐는지 확인 — 아직 보안 페이지면 확인 버튼 직접 클릭
            still_sec_after_enter = self._is_security_page(
                self.driver.page_source, self.driver.title, self.driver.current_url
            )
            if still_sec_after_enter:
                # "확인" 텍스트를 포함하거나 type="submit"인 버튼만 탐색
                confirm_btn = next(
                    (
                        el for el in self.driver.find_elements(
                            By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]'
                        )
                        if el.is_displayed() and el.is_enabled()
                    ),
                    None,
                )
                if confirm_btn is None:
                    # type 없는 버튼 중 텍스트가 "확인"인 것만
                    for el in self.driver.find_elements(By.TAG_NAME, "button"):
                        if el.is_displayed() and el.is_enabled() and "확인" in (el.text or ""):
                            confirm_btn = el
                            break
                if confirm_btn:
                    confirm_btn.click()
                    logger.info("[보안페이지] 확인 버튼 클릭 (Enter 실패 후 fallback)")

            time.sleep(3)

            # 성공 확인: 보안 페이지가 사라졌으면 통과
            still_security = self._is_security_page(
                self.driver.page_source, self.driver.title, self.driver.current_url
            )
            if still_security:
                logger.warning("[보안페이지] 제출 후에도 보안 페이지 — 자동 풀기 실패")
                return False

            logger.info("[보안페이지] 보안 인증 자동 통과")
            return True

        except Exception as e:
            logger.warning("[보안페이지] 입력/제출 중 예외: %s", e)
            return False

    def _try_solve_naver_captcha_form(self) -> bool:
        """#rcpt_answer / #cpt_confirm 형태의 네이버 숫자 CAPTCHA 전용 처리.

        1. 폼 요소 확인
        2. 페이지 스크린샷 → Claude vision으로 숫자 추출
           (스크린샷으로 못 읽으면 캡차 이미지 URL 직접 다운로드 후 재시도)
        3. #rcpt_answer 에 입력 → #cpt_confirm 클릭
        """
        import base64
        import re

        # 1. 폼 존재 확인
        try:
            answer_input = self.driver.find_element(By.ID, 'rcpt_answer')
            confirm_btn = self.driver.find_element(By.ID, 'cpt_confirm')
        except Exception:
            return False

        if not (answer_input.is_displayed() and answer_input.is_enabled()):
            return False

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[캡차] ANTHROPIC_API_KEY 없음 — 자동 풀기 불가")
            return False

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        numbers = ''

        # 2. DOM에서 질문 텍스트(#rcpt_info)와 캡차 이미지(#rcpt_img) 직접 추출
        try:
            question_text = self.driver.find_element(By.ID, 'rcpt_info').text.strip()
            logger.info("[캡차] 질문(DOM): %s", question_text)
        except Exception as e:
            logger.warning("[캡차] #rcpt_info 추출 실패: %s", e)
            question_text = ''

        try:
            img_src = self.driver.find_element(By.ID, 'rcpt_img').get_attribute('src') or ''
            if img_src.startswith('data:'):
                import base64 as _b64
                img_b64 = img_src.split(',', 1)[1]
                img_bytes = _b64.b64decode(img_b64)
                media_type = self._image_media_type(img_bytes)
            else:
                img_b64 = ''
                media_type = 'image/png'
        except Exception as e:
            logger.warning("[캡차] #rcpt_img 추출 실패: %s", e)
            img_b64 = ''
            media_type = 'image/png'

        if img_b64:
            try:
                prompt = (
                    f"질문: {question_text}\n\n"
                    "위 질문에 맞는 답을 캡차 이미지에서 찾아 아래 형식으로 출력하세요.\n\n"
                    "정보: [이미지에서 찾은 전화번호 또는 주소 전체, 있는 그대로]\n"
                    "풀이: [하이픈 제거 후 숫자 나열, 몇 번째인지 계산]\n"
                    "답: [숫자만]\n\n"
                    "규칙:\n"
                    "- 주소 질문: 길/로 바로 뒤 번지 숫자 (예: 초안산로 687 → 687)\n"
                    "- 전화번호 질문: 하이픈 제거 후 앞/뒤에서 N번째 숫자 1자리만\n"
                    "  예) 031-8049 앞에서 4번째 → 0318049 → 4번째 → 8\n"
                    "  예) 031-8049 뒤에서 2번째 → 0318049 → 뒤2번째 → 4"
                )
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                raw = resp.content[0].text.strip()
                def _ext(label, text):
                    m = re.search(label + r'\s*:\s*(.+)', text)
                    return m.group(1).strip() if m else ''
                logger.info("[캡차] 정보: %s", _ext('정보', raw))
                logger.info("[캡차] 풀이: %s", _ext('풀이', raw))
                answer_match = re.search(r'답\s*:\s*([0-9]+)', raw)
                numbers = answer_match.group(1) if answer_match else re.sub(r'[^0-9]', '', raw.split('\n')[-1])
                logger.info("[캡차] 최종 답: '%s'", numbers)
            except Exception as e:
                logger.warning("[캡차] Claude API 호출 실패: %s", e)

        if not numbers:
            logger.warning("[캡차] 숫자 추출 실패 — 수동 처리 필요")
            return False

        # 3. 입력 및 제출
        try:
            answer_input.clear()
            answer_input.send_keys(numbers)
            time.sleep(0.3)
            confirm_btn.click()
            logger.info("[캡차] '%s' 입력 후 확인 클릭", numbers)
            time.sleep(3)

            # 성공 확인: 폼이 사라졌으면 통과
            try:
                still_visible = self.driver.find_element(By.ID, 'rcpt_answer').is_displayed()
                if still_visible:
                    logger.warning("[캡차] 제출 후 폼 잔존 — 오답 가능성")
                    return False
            except Exception:
                pass  # 요소 없어짐 = 통과

            logger.info("[캡차] 보안 인증 통과")
            return True
        except Exception as e:
            logger.warning("[캡차] 입력/클릭 오류: %s", e)
            return False

    def _try_auto_solve_security_page(self, security_info: dict) -> bool:
        """캡차 자동 풀기 시도. 성공하면 True, 실패하면 False(수동 폴백용).

        네이버 폼(#rcpt_answer/#cpt_confirm)이 있으면 폼 방식만,
        없으면 전체 스크린샷 방식만 사용한다.
        두 방식을 한 시도 내에서 연달아 실행하면 첫 번째 제출 후 새 캡차가
        등장한 상태에서 두 번째 방식이 다른 캡차에 답을 내는 타이밍 문제가 생긴다.
        """
        try:
            inp = self.driver.find_element(By.ID, 'rcpt_answer')
            btn = self.driver.find_element(By.ID, 'cpt_confirm')
            naver_form_present = inp.is_displayed() and inp.is_enabled()
        except Exception:
            naver_form_present = False

        if naver_form_present:
            result = self._try_solve_naver_captcha_form()
            if not result:
                logger.warning("[보안페이지] 네이버 폼 방식 실패")
            return result

        result = self._solve_security_with_full_screenshot()
        if not result:
            logger.warning("[보안페이지] 전체 스크린샷 방식 실패")
        return result

    def collect_store_page(self, store_slug: str) -> dict:
        """
        스토어 페이지 열고 HTML 수집.
        
        Args:
            store_slug: 스토어 슬러그 (예: "seolcom")
            
        Returns:
            dict with html, page_title, final_url
        """
        if not self.driver:
            raise RuntimeError("Driver not started")
        
        url = f"https://smartstore.naver.com/{store_slug}"
        logger.info(f"스토어 페이지 열기: {url}")
        
        self.driver.get(url)
        # 페이지 로드 대기 (최소화)
        try:
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            time.sleep(0.5)  # 폴백 대기 최소화
        
        html = self.driver.page_source
        page_title = self.driver.title
        final_url = self.driver.current_url
        
        logger.info(f"수집 완료: {len(html)} 문자, 제목: {page_title}")
        
        return {
            "html": html,
            "page_title": page_title,
            "final_url": final_url,
            "success": True
        }
    
    def find_and_click_product(self, store_slug: str, product_id: str) -> Optional[str]:
        """
        스토어 페이지에서 상품 찾아서 클릭.
        
        Args:
            store_slug: 스토어 슬러그
            product_id: 상품 ID
            
        Returns:
            클릭 후 최종 URL 또는 None
        """
        if not self.driver:
            raise RuntimeError("Driver not started")
        
        # 스토어 페이지 열기
        store_url = f"https://smartstore.naver.com/{store_slug}"
        logger.info(f"스토어 페이지 열기: {store_url}")
        self.driver.get(store_url)
        # 페이지 로드 대기 (최소화)
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            time.sleep(1)  # 폴백 대기
        
        # data-shp-contents-id로 상품 찾기
        logger.info(f"상품 찾기: data-shp-contents-id={product_id}")
        try:
            wait = WebDriverWait(self.driver, 5)  # 타임아웃 줄임 (10초 -> 5초)
            element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'[data-shp-contents-id="{product_id}"]'))
            )
            
            # 스크롤 (즉시 실행, 부드러운 스크롤 제거)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)  # 대기 시간 최소화
            
            # 클릭 가능한 요소 찾기
            clickable = None
            try:
                clickable = element.find_element(By.XPATH, ".//a | ./ancestor::a")
            except:
                clickable = element
            
            # 클릭 (JavaScript 클릭으로 더 빠름)
            logger.info("상품 클릭 중...")
            try:
                # JavaScript 클릭이 더 빠름
                self.driver.execute_script("arguments[0].click();", clickable)
            except:
                # 폴백: ActionChains 사용
                actions = ActionChains(self.driver)
                actions.move_to_element(clickable).click().perform()
            time.sleep(0.3)  # 대기 시간 최소화
            
            final_url = self.driver.current_url
            logger.info(f"클릭 완료, 최종 URL: {final_url}")
            return final_url
            
        except Exception as e:
            logger.error(f"상품 찾기/클릭 실패: {e}")
            return None
    
    def _ensure_valid_window(self):
        """현재 창 핸들이 유효한지 확인하고, 닫혔으면 다른 창으로 전환.

        Google 계정 로그인 / debuggerAddress 재접속 등으로 창이 교체된 경우 처리.
        """
        # 1단계: window_handles 먼저 확인 (current_url보다 안정적)
        try:
            handles = self.driver.window_handles
        except Exception:
            raise RuntimeError("사용 가능한 Chrome 창 없음 — Chrome이 닫혔습니다.")

        if not handles:
            raise RuntimeError("사용 가능한 Chrome 창 없음 — Chrome이 닫혔습니다.")

        # 2단계: current_url이 실패하면 마지막 창으로 전환 후 재확인
        try:
            _ = self.driver.current_url
            return  # 현재 창 정상
        except Exception:
            pass

        try:
            self.driver.switch_to.window(handles[-1])
            _ = self.driver.current_url
            logger.info("창 전환 성공 → %s", handles[-1])
        except Exception:
            raise RuntimeError("사용 가능한 Chrome 창 없음 — Chrome이 닫혔습니다.")

    def collect_product_page(self, url: str, save_screenshot: bool = True) -> dict:
        """
        상품 페이지 HTML 수집 및 스크린샷 저장.

        Args:
            url: 상품 페이지 URL
            save_screenshot: 스크린샷 저장 여부

        Returns:
            dict with html, page_title, final_url, screenshot_path
        """
        if not self.driver:
            raise RuntimeError("Driver not started")

        # Google 로그인 등으로 창이 교체된 경우 유효한 창으로 전환
        self._ensure_valid_window()

        if not self.debug:
            logger.debug(f"상품 페이지 수집: {url}")
        else:
            logger.info(f"상품 페이지 수집: {url}")

        def _load_page(target_url: str):
            import json as _json
            try:
                # driver.get() 대신 JS 이동: 워밍업과 동일한 방식으로 이동해야
                # Naver가 CDP 명령(driver.get)을 봇으로 판정하는 것을 피할 수 있음
                prev_url = self.driver.current_url
                self.driver.execute_script(
                    f"window.location.href = {_json.dumps(target_url)};"
                )
                try:
                    WebDriverWait(self.driver, 5).until(EC.url_changes(prev_url))
                except Exception:
                    pass
                try:
                    WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"페이지 로드 확인 실패, 계속 진행: {e}")
                time.sleep(0.3)

        _load_page(url)

        # JS 렌더링 / 봇 체크 자동 통과 대기: 제목이 채워지거나 캡차 페이지 감지될 때까지 최대 30초
        # 세션 쿠키가 유효하면 네이버 봇 체크가 자동 통과되므로 기다리면 됨
        try:
            WebDriverWait(self.driver, 30).until(lambda d: (
                d.title.strip() or
                d.execute_script(
                    "var h = document.documentElement.innerHTML || '';"
                    "return h.includes('보안 확인을 완료해 주세요') || "
                    "h.includes('id=\"message_text\"') || "
                    "h.includes('wtm_captcha') || h.includes('rcpt_form') || "
                    "h.includes('ncpt.naver.com');"
                )
            ))
        except Exception:
            pass  # 30초 후에도 비어있으면 아래 _is_security_page 에서 판단

        # 가격·옵션 등 동적 컨텐츠 대기 (React XHR 렌더링 완료까지)
        # 1) document.readyState === 'complete'
        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        # 2) __PRELOADED_STATE__ 또는 가격 DOM 또는 상품없음/에러/캡차 페이지 중 하나라도 등장할 때까지 최대 8초
        try:
            WebDriverWait(self.driver, 8).until(
                lambda d: d.execute_script(
                    "var t = document.body ? document.body.innerText : '';"
                    "var title = document.title || '';"
                    "var h = document.documentElement.innerHTML || '';"
                    "return !!(window.__PRELOADED_STATE__) || "
                    "document.querySelectorAll('[class*=price],[class*=Price],[class*=_price]').length > 0 || "
                    "t.includes('상품이 존재하지 않습니다') || "
                    "t.includes('존재하지 않는 상품') || "
                    "t.includes('상품을 찾을 수 없') || "
                    "t.includes('삭제된 상품입니다') || "
                    "title.includes('에러') || title.includes('오류') || title.includes('Error') || "
                    "h.includes('보안 확인을 완료해 주세요') || "
                    "h.includes('wtm_captcha') || h.includes('rcpt_form');"
                )
            )
        except Exception:
            time.sleep(2)  # 폴백: 2초 고정 대기
        # 3) 스크롤로 lazy-load 트리거 후 복귀
        try:
            self.driver.execute_script("window.scrollTo(0, Math.min(600, document.body.scrollHeight * 0.4));")
            time.sleep(0.8)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)
        except Exception:
            pass

        html = self.driver.page_source
        page_title = self.driver.title
        final_url = self.driver.current_url

        # 보안/봇 인증 페이지 감지 → 스크린샷/이미지 추출 후 Enter 대기 → 재수집
        if self._is_security_page(html, page_title, final_url):
            logger.warning(f"보안 페이지 감지 (제목: '{page_title}', URL: {final_url})")
            logger.warning("브라우저에서 보안 인증을 완료해주세요.")
            security_info = self._handle_security_page()
            logger.info(
                "== 보안 페이지 캡처 결과 ==\n"
                "  스크린샷: %s\n"
                "  이미지:   %s\n"
                "  이미지URL: %s",
                security_info.get('screenshot_path', '없음'),
                security_info.get('image_path', '없음'),
                security_info.get('main_image_url', '없음'),
            )
            _MAX_CAPTCHA_RETRIES = 5
            _solved = False
            for _attempt in range(1, _MAX_CAPTCHA_RETRIES + 1):
                if self._try_auto_solve_security_page(security_info):
                    _solved = True
                    break
                if _attempt < _MAX_CAPTCHA_RETRIES:
                    logger.warning("[보안페이지] %d/%d회 실패 — 새 캡차로 재시도", _attempt, _MAX_CAPTCHA_RETRIES)
                    time.sleep(3)  # 새 캡차 로드 대기
                else:
                    logger.warning("[보안페이지] %d/%d회 모두 실패 — 다음 슬롯으로 넘어갑니다.", _attempt, _MAX_CAPTCHA_RETRIES)
            if not _solved:
                raise RuntimeError("보안 페이지 자동 풀기 실패 (5회) — 재요청 필요")
            # 사용자가 이미 캡챠를 풀고 페이지를 이동했을 수 있으므로 현재 URL 먼저 확인
            # 캡챠 해결 후 redirect가 완전히 끝날 때까지 대기 (nid.naver.com 통과 포함)
            time.sleep(3)
            try:
                current_url_after = self.driver.current_url
                still_on_security = self._is_security_page(
                    self.driver.page_source, self.driver.title, current_url_after
                )
            except Exception:
                still_on_security = True
            if still_on_security:
                # 아직 보안/redirect 페이지에 있으면 원래 URL로 이동
                _load_page(url)
                # 페이지 완전 로드 대기
                try:
                    WebDriverWait(self.driver, 10).until(lambda d: d.title.strip())
                except Exception:
                    time.sleep(3)
            else:
                # 이미 이동 완료 — 네비게이션 충돌 방지를 위해 추가 이동 생략
                logger.info("[보안페이지] 사용자가 이미 페이지 이동 완료, 재이동 생략")
                # 페이지가 완전히 로드될 때까지 대기
                try:
                    WebDriverWait(self.driver, 10).until(lambda d: d.title.strip())
                except Exception:
                    time.sleep(3)
            html = self.driver.page_source
            page_title = self.driver.title
            final_url = self.driver.current_url
            logger.info(f"재수집 완료: {len(html)} 문자, 제목: '{page_title}'")
        
        # 스크린샷 저장 (선택적, HTML 수집 후)
        screenshot_path = None
        if save_screenshot:
            import tempfile
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            screenshot_path = os.path.join(tempfile.gettempdir(), f"naver_screenshot_{url_hash}.png")
            try:
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"스크린샷 저장: {screenshot_path}")
            except Exception as e:
                logger.warning(f"스크린샷 저장 실패 (Chrome 상태 이상 아님, 무시): {e}")
                screenshot_path = None

        # 상품 없음 페이지 감지: HTML 텍스트 먼저 확인 → 못 잡으면 스크린샷 vision으로 재확인
        _not_found = self._is_not_found_page(html, page_title)
        if not _not_found and screenshot_path:
            _not_found = self._detect_not_found_in_screenshot(screenshot_path)

        if _not_found:
            logger.warning(f"[상품없음] 감지 (제목: '{page_title}') — 새로고침 1회 재시도")
            _load_page(url)
            # readyState 완료 + 에러/콘텐츠 등장까지 최대 8초 대기
            try:
                WebDriverWait(self.driver, 8).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                time.sleep(2)
            html = self.driver.page_source
            page_title = self.driver.title
            final_url = self.driver.current_url
            if save_screenshot and screenshot_path:
                try:
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"[상품없음] 재시도 후 스크린샷 갱신: {screenshot_path}")
                except Exception as e:
                    logger.warning(f"[상품없음] 스크린샷 갱신 실패 (무시): {e}")
            logger.info(f"[상품없음] 재시도 완료: {len(html)} 문자, 제목: '{page_title}'")

        logger.info(f"수집 완료: {len(html)} 문자, 제목: {page_title}")
        
        return {
            "html": html,
            "page_title": page_title,
            "final_url": final_url,
            "screenshot_path": screenshot_path,
            "success": True
        }


def main():
    """메인 함수 - URL 입력하면 바로 이동하고 파싱."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="네이버 스마트스토어 수집기 및 파서")
    parser.add_argument("url", nargs="?", help="네이버 스마트스토어 URL")
    parser.add_argument("--headless", action="store_true", help="헤드리스 모드")
    parser.add_argument("--profile-dir", help="Chrome 프로필 디렉토리")
    parser.add_argument("--no-parse", action="store_true", help="파싱 없이 HTML만 수집")
    
    args = parser.parse_args()
    
    if not args.url:
        # URL이 없으면 입력받기
        args.url = input("네이버 스마트스토어 URL을 입력하세요: ").strip()
        if not args.url:
            print("URL이 필요합니다.")
            return
    
    print("=" * 60)
    print("네이버 스마트스토어 수집기 및 파서")
    print("=" * 60)
    print(f"\nURL: {args.url}")
    print(f"헤드리스: {args.headless}")
    if args.profile_dir:
        print(f"프로필 디렉토리: {args.profile_dir}")
    print("-" * 60)
    
    with NaverCollector(
        profile_dir=args.profile_dir,
        headless=args.headless
    ) as collector:
        # URL로 바로 이동하고 HTML/스크린샷 수집
        result = collector.collect_product_page(args.url, save_screenshot=True)
        
        print("\n" + "=" * 60)
        print("수집 결과")
        print("=" * 60)
        print(f"제목: {result['page_title']}")
        print(f"최종 URL: {result['final_url']}")
        print(f"HTML 길이: {len(result['html']):,} 문자")
        print(f"스크린샷: {result.get('screenshot_path', 'N/A')}")
        
        # 파싱 수행
        if not args.no_parse:
            print("\n" + "=" * 60)
            print("상품 정보 파싱 중...")
            print("=" * 60)
            
            try:
                from naver_parser import parse_naver_product
                
                product_info = parse_naver_product(
                    html=result['html'],
                    screenshot_path=result.get('screenshot_path'),
                    page_title=result['page_title'],
                    url=result['final_url']
                )
                
                print("\n" + "=" * 60)
                print("파싱된 상품 정보")
                print("=" * 60)
                
                # 상품 정보 출력
                print(f"제목: {product_info.title or 'N/A'}")
                if product_info.original_price:
                    print(f"원래 가격: {product_info.original_price:,.0f}원")
                if product_info.discounted_price:
                    print(f"할인 가격: {product_info.discounted_price:,.0f}원")
                if product_info.discount_rate:
                    print(f"할인율: {product_info.discount_rate}%")
                print(f"배송기간: {product_info.shipping_period or 'N/A'}")
                print(f"상품 무게: {product_info.product_weight or 'N/A'}")
                
                # 옵션 상세 출력
                if product_info.product_options:
                    print(f"\n상품 옵션 ({len(product_info.product_options)}개):")
                    for i, opt in enumerate(product_info.product_options, 1):
                        print(f"  {i}. {opt.option_type}:")
                        print(f"     사용 가능: {', '.join(opt.available_values)}")
                        if opt.selected_value:
                            print(f"     현재 선택: {opt.selected_value} (✓)")
                        else:
                            print(f"     현재 선택: 없음")
                else:
                    print("\n상품 옵션: 없음")
                
                # 전체 JSON 출력
                print("\n전체 JSON:")
                print(json.dumps(product_info.model_dump(exclude_none=True), indent=2, ensure_ascii=False))
                
                # JSON 파일로 저장
                save_json = input("\n파싱 결과를 JSON 파일로 저장하시겠습니까? (y/n): ").strip().lower()
                if save_json == 'y':
                    from datetime import datetime
                    filename = f"naver_product_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(product_info.model_dump(exclude_none=True), f, indent=2, ensure_ascii=False)
                    print(f"JSON 저장 완료: {filename}")
                
            except Exception as e:
                print(f"\n파싱 실패: {e}")
                import traceback
                traceback.print_exc()
        
        # HTML 저장 옵션
        save_html = input("\nHTML을 파일로 저장하시겠습니까? (y/n): ").strip().lower()
        if save_html == 'y':
            from datetime import datetime
            filename = f"naver_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(result['html'])
            print(f"HTML 저장 완료: {filename}")


if __name__ == "__main__":
    main()
