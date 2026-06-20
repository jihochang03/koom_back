"""HTML 정리 및 전처리 - 상품 정보 추출에 필요한 부분만 남기기."""
import re
import logging
from typing import Optional
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)


class HTMLCleaner:
    """HTML을 정리하여 상품 정보 추출에 필요한 부분만 남기기."""
    
    # 제거할 태그들
    REMOVE_TAGS = [
        'script', 'style', 'noscript', 'iframe', 'embed', 'object',
        'link', 'meta', 'base', 'head', 'svg', 'path', 'g', 'circle', 'rect',
        'polygon', 'line', 'ellipse', 'defs', 'pattern', 'clipPath', 'mask',
        'use', 'image', 'text', 'tspan', 'font', 'icon', 'i', 'em', 'strong',
        'br', 'hr', 'button', 'input', 'form', 'select', 'textarea', 'label',
        'canvas', 'video', 'audio', 'source', 'track', 'map', 'area'
    ]
    
    # 제거할 클래스/ID 패턴들 (네이버 스마트스토어 특화)
    REMOVE_PATTERNS = [
        r'footer', r'header', r'nav', r'navigation',
        r'advertisement', r'광고', r'banner', r'배너',
        r'cookie', r'쿠키', r'popup', r'팝업',
        r'sidebar', r'사이드바', r'aside',
        r'recommend', r'추천', r'related', r'관련',
        r'review', r'리뷰', r'comment', r'댓글',
        r'social', r'소셜', r'share', r'공유',
        r'tracking', r'analytics', r'gtm', r'ga-',
        r'icon', r'아이콘', r'logo', r'로고', r'svg',
        r'loading', r'로딩', r'spinner', r'loader',
        r'modal', r'모달', r'dialog', r'다이얼로그',
        r'tooltip', r'툴팁', r'dropdown', r'드롭다운',
        r'menu', r'메뉴', r'tab', r'탭',
    ]
    
    # 유지할 클래스/ID 패턴들 (상품 정보 관련)
    KEEP_PATTERNS = [
        r'product', r'상품', r'item',
        r'price', r'가격', r'원가', r'할인',
        r'option', r'옵션', r'select', r'선택',
        r'title', r'제목', r'name', r'이름',
        r'image', r'이미지', r'photo', r'사진',
        r'shipping', r'배송', r'무게', r'weight',
        r'description', r'설명', r'content', r'내용',
        r'buy', r'구매', r'cart', r'장바구니',
        r'main', r'메인', r'body', r'본문',
    ]

    CRITICAL_TEXT_PATTERNS = [
        r'원',
        r'₩',
        r'할인',
        r'정가',
        r'판매가',
        r'쿠폰',
        r'배송',
        r'출고',
        r'무게',
        r'중량',
        r'용량',
        r'%'
    ]
    
    @staticmethod
    def clean_html(html: str, keep_scripts: bool = False, aggressive: bool = True) -> str:
        """
        HTML을 정리하여 상품 정보 추출에 필요한 부분만 남기기.
        
        Args:
            html: 원본 HTML
            keep_scripts: 스크립트 태그 유지 여부 (기본: False)
            
        Returns:
            정리된 HTML
        """
        logger.info(f"HTML 정리 시작: {len(html)} 문자")
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception as e:
            logger.warning(f"BeautifulSoup 파싱 실패, 기본 정리만 수행: {e}")
            return HTMLCleaner._basic_clean(html)
        
        # 1. 주석 제거
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # 2. 스크립트/스타일 제거
        remove_tags = HTMLCleaner.REMOVE_TAGS
        if not aggressive:
            # 덜 공격적일 때는 텍스트를 담을 수 있는 요소는 최대한 보존
            remove_tags = [
                'script', 'style', 'noscript', 'iframe', 'embed', 'object',
                'link', 'base', 'svg', 'path', 'g', 'circle', 'rect',
                'polygon', 'line', 'ellipse', 'defs', 'pattern', 'clipPath', 'mask',
                'use', 'image', 'canvas', 'video', 'audio', 'source', 'track', 'map', 'area'
            ]
        if not keep_scripts:
            for tag_name in remove_tags:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

        if not aggressive:
            HTMLCleaner._keep_only_useful_meta_tags(soup)
        
        # 3. 불필요한 속성 제거 (이벤트 핸들러 등)
        for tag in soup.find_all():
            # 대부분의 속성 제거 (텍스트와 기본 구조만 유지)
            attrs_to_remove = []
            for attr in tag.attrs:
                # 유지할 속성: id, class (일부), href, src, alt, title
                keep_attrs = ['id', 'class', 'href', 'src', 'alt', 'title', 'name', 'value', 'type']
                if attr not in keep_attrs:
                    attrs_to_remove.append(attr)
                # 이벤트 핸들러와 트래킹 관련 속성은 무조건 제거
                elif attr.startswith('on') or (attr.startswith('data-') and 'track' in attr.lower()):
                    attrs_to_remove.append(attr)
            
            for attr in attrs_to_remove:
                try:
                    del tag[attr]
                except:
                    pass
        
        # 4. 상품 정보와 관련 없는 요소 제거 (공격적 모드일 때만)
        if aggressive:
            HTMLCleaner._remove_unrelated_elements(soup)
        
        # 5. 빈 태그 제거 (공격적 모드일 때만)
        if aggressive:
            HTMLCleaner._remove_empty_tags(soup)
        else:
            # 덜 공격적: 텍스트나 의미 있는 속성이 없는 래퍼만 제거
            HTMLCleaner._remove_truly_empty_tags(soup)
        
        # 6. HTML 정리
        cleaned_html = str(soup)
        
        # 7. 추가 정리 (정규식) - 공격적 모드일 때만
        if aggressive:
            cleaned_html = HTMLCleaner._post_process(cleaned_html)
        else:
            # 덜 공격적: 기본 정리만
            cleaned_html = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_html)
            cleaned_html = re.sub(r' +', ' ', cleaned_html)
        
        logger.info(f"HTML 정리 완료: {len(cleaned_html)} 문자 ({len(html) - len(cleaned_html)} 문자 제거)")
        
        return cleaned_html
    
    @staticmethod
    def _remove_unrelated_elements(soup: BeautifulSoup):
        """상품 정보와 관련 없는 요소 제거 - 더 보수적으로."""
        # 패턴 매칭으로 제거할 요소 찾기
        elements_to_remove = []
        
        for tag in soup.find_all():
            # 클래스와 ID 확인
            classes = ' '.join(tag.get('class', [])).lower()
            tag_id = tag.get('id', '').lower()
            combined = f"{classes} {tag_id}"
            
            # 텍스트가 충분히 있는 요소는 유지 (중요한 정보일 수 있음)
            text = tag.get_text(strip=True)
            if HTMLCleaner._contains_critical_product_text(text):
                continue
            if len(text) > 20:  # 충분한 텍스트가 있으면 유지
                continue
            
            # 제거 패턴 매칭 (더 엄격하게)
            should_remove = False
            for pattern in HTMLCleaner.REMOVE_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    # 하지만 유지 패턴도 있으면 유지
                    should_keep = False
                    for keep_pattern in HTMLCleaner.KEEP_PATTERNS:
                        if re.search(keep_pattern, combined, re.IGNORECASE):
                            should_keep = True
                            break
                    
                    if not should_keep:
                        # 텍스트가 거의 없을 때만 제거
                        if len(text) < 10:
                            should_remove = True
                            break
            
            if should_remove:
                elements_to_remove.append(tag)
        
        # 제거 실행
        for tag in elements_to_remove:
            try:
                tag.decompose()
            except:
                pass
    
    @staticmethod
    def _remove_empty_tags(soup: BeautifulSoup):
        """빈 태그 제거 (텍스트가 없는 div, span 등) - 공격적 버전."""
        empty_tags = []
        
        # 더 많은 태그 타입에 대해 빈 태그 제거
        for tag in soup.find_all(['div', 'span', 'p', 'li', 'td', 'th', 'section', 'article', 'aside', 'header', 'footer']):
            # 텍스트가 없고 자식도 없으면 제거
            text = tag.get_text(strip=True)
            children = tag.find_all()
            if HTMLCleaner._contains_critical_product_text(text):
                continue
            if not text and not children:
                empty_tags.append(tag)
            # 매우 짧은 텍스트만 있고 의미 없는 경우도 제거
            elif len(text) < 3 and not any(child.name in ['img', 'a', 'button'] for child in children):
                empty_tags.append(tag)
        
        for tag in empty_tags:
            try:
                tag.decompose()
            except:
                pass
    
    @staticmethod
    def _remove_truly_empty_tags(soup: BeautifulSoup):
        """정말 빈 태그만 제거 (덜 공격적 버전)."""
        empty_tags = []
        
        candidate_tags = ['div', 'span', 'section', 'article', 'aside', 'li', 'ul']
        meaningful_child_tags = {'img', 'a', 'input', 'button', 'select', 'option', 'textarea', 'label'}
        meaningful_attrs = {'src', 'href', 'value', 'alt', 'title'}
        
        for tag in soup.find_all(candidate_tags):
            text = tag.get_text(strip=True)
            children = tag.find_all()
            has_meaningful_child = any(child.name in meaningful_child_tags for child in children)
            has_meaningful_attr = any(tag.get(attr) for attr in meaningful_attrs)
            if HTMLCleaner._contains_critical_product_text(text):
                continue
            
            # 텍스트도 없고, 의미 있는 자식/속성도 없는 래퍼만 제거
            if not text and not children:
                empty_tags.append(tag)
            elif not text and not has_meaningful_child and not has_meaningful_attr:
                empty_tags.append(tag)
        
        for tag in empty_tags:
            try:
                tag.decompose()
            except:
                pass
    
    @staticmethod
    def _post_process(html: str) -> str:
        """후처리: 정규식으로 추가 정리."""
        # 연속된 공백/줄바꿈 정리
        html = re.sub(r'\n\s*\n\s*\n+', '\n\n', html)
        html = re.sub(r' +', ' ', html)
        
        # 빈 속성 제거
        html = re.sub(r'\s+class=""', '', html)
        html = re.sub(r'\s+id=""', '', html)
        
        # 긴 클래스명 줄이기 (첫 번째 클래스만 유지)
        html = re.sub(r'class="([^"]+)"', lambda m: f'class="{m.group(1).split()[0]}"' if len(m.group(1)) > 50 else m.group(0), html)
        
        # 중복된 텍스트 패턴 제거 (예: "상품 상품 상품" -> "상품")
        html = re.sub(r'(\S+)\s+\1\s+\1+', r'\1', html)
        
        # 매우 긴 텍스트 노드 줄이기 (100자 이상이면 앞부분만)
        def truncate_long_text(match):
            text = match.group(1)
            if len(text) > 100:
                return text[:100] + '...'
            return text
        
        html = re.sub(r'>([^<]{100,})<', truncate_long_text, html)
        
        return html

    @staticmethod
    def _keep_only_useful_meta_tags(soup: BeautifulSoup):
        """가격/제목/이미지 관련 메타만 남기고 나머지는 제거."""
        useful_patterns = [
            r'og:',
            r'twitter:',
            r'price',
            r'product',
            r'discount',
            r'kakao:commerce',
            r'title',
            r'description',
            r'image',
        ]

        for meta in soup.find_all('meta'):
            combined = " ".join(
                str(meta.get(attr, ""))
                for attr in ("property", "name", "content", "itemprop")
            ).lower()
            if any(re.search(pattern, combined, re.IGNORECASE) for pattern in useful_patterns):
                continue
            meta.decompose()

    @staticmethod
    def _contains_critical_product_text(text: str) -> bool:
        """가격/배송/무게 같은 핵심 정보가 있으면 보존."""
        if not text:
            return False
        normalized = re.sub(r'\s+', ' ', text).strip()
        if not normalized:
            return False

        for pattern in HTMLCleaner.CRITICAL_TEXT_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def _basic_clean(html: str) -> str:
        """BeautifulSoup 없이 기본 정리만 수행."""
        # 스크립트 태그 제거
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # 스타일 태그 제거
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # 주석 제거
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        
        # 연속된 공백 정리
        html = re.sub(r'\s+', ' ', html)
        
        return html
    
    @staticmethod
    def extract_product_section(html: str) -> str:
        """
        상품 정보가 있는 섹션만 추출 (더 공격적으로).
        
        Args:
            html: 원본 HTML
            
        Returns:
            상품 정보 섹션 HTML
        """
        logger.info("상품 정보 섹션 추출 중...")
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except:
            return HTMLCleaner._basic_clean(html)
        
        # 상품 정보가 있을 가능성이 높은 요소 찾기
        product_sections = []
        
        # 1. data-shp-contents-id가 있는 요소 찾기 (네이버 스마트스토어)
        product_element = soup.find(attrs={'data-shp-contents-id': True})
        if product_element:
            container = product_element.find_parent(['div', 'section', 'article', 'main'])
            if container:
                product_sections.append(container)
        
        # 2. 상품 관련 클래스/ID가 있는 요소 찾기 (더 엄격하게)
        priority_patterns = [r'product', r'상품', r'price', r'가격', r'option', r'옵션']
        for pattern in priority_patterns:
            elements = soup.find_all(class_=re.compile(pattern, re.I))
            # 텍스트가 있는 요소만 선택
            elements = [e for e in elements if e.get_text(strip=True)]
            product_sections.extend(elements[:3])  # 최대 3개만
        
        # 3. 메인 콘텐츠 영역 찾기
        main_content = soup.find('main') or soup.find(id=re.compile(r'main|content|product', re.I))
        if main_content:
            product_sections.append(main_content)
        
        # 4. body에서 직접 상품 정보 찾기
        body = soup.find('body')
        if body:
            # body의 직접 자식 중 텍스트가 많은 것 찾기
            for child in body.find_all(['div', 'section', 'article'], recursive=False, limit=10):  # 더 많이 찾기
                text = child.get_text(strip=True)
                if len(text) > 50:  # 기준 완화 (100 -> 50)
                    product_sections.append(child)
        
        if product_sections:
            # 가장 큰 섹션 선택하되, 너무 크면 텍스트만 추출
            largest = max(product_sections, key=lambda x: len(str(x)))
            largest_str = str(largest)
            
            # 너무 크면 텍스트만 추출 (하지만 더 많이 유지)
            if len(largest_str) > 200000:  # 기준 완화 (100000 -> 200000)
                logger.info("섹션이 너무 커서 텍스트만 추출합니다.")
                text_only = largest.get_text(separator='\n', strip=True)
                # 텍스트를 간단한 HTML로 변환
                lines = text_only.split('\n')
                cleaned_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 1]  # 기준 완화 (2 -> 1)
                cleaned = '\n'.join(cleaned_lines[:2000])  # 더 많이 유지 (500 -> 2000)
                logger.info(f"텍스트 추출 완료: {len(cleaned)} 문자")
                return cleaned
            
            # 섹션을 찾았으면 정리하되, 너무 공격적으로 하지 않음
            cleaned = HTMLCleaner.clean_html(largest_str, aggressive=False)  # 공격적 정리 비활성화
            logger.info(f"상품 섹션 추출 완료: {len(cleaned)} 문자")
            return cleaned
        
        # 섹션을 찾지 못하면 전체 HTML을 정리하되, 덜 공격적으로
        logger.warning("상품 섹션을 찾지 못해 전체 HTML을 정리합니다.")
        # 전체 HTML을 정리하되, 덜 공격적으로
        cleaned = HTMLCleaner.clean_html(str(soup), aggressive=False)
        # 여전히 너무 작으면 텍스트만 추출
        if len(cleaned) < 100:
            text_only = soup.get_text(separator='\n', strip=True)
            lines = text_only.split('\n')
            cleaned_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 1]  # 기준 완화
            cleaned = '\n'.join(cleaned_lines[:2000])  # 더 많이 유지
        return cleaned


def clean_html_for_parsing(html: str, extract_section: bool = False) -> str:
    """
    편의 함수: 파싱을 위한 HTML 정리.
    
    Args:
        html: 원본 HTML
        extract_section: 상품 섹션만 추출할지 여부 (기본: False - 덜 공격적으로)
        
    Returns:
        정리된 HTML
    """
    if extract_section:
        return HTMLCleaner.extract_product_section(html)
    else:
        # 덜 공격적으로 정리 (aggressive=False)
        return HTMLCleaner.clean_html(html, aggressive=False)


def extract_structured_data(html: str) -> dict:
    """
    HTML에서 구조화된 상품 데이터 추출.
    - JSON-LD (Product 스키마) : 가장 신뢰할 수 있는 소스
    - OpenGraph / product meta 태그
    - window.__PRELOADED_STATE__ (네이버 SSR 데이터)
    반환: {"jsonld": [...], "meta": {...}, "preloaded": {...}}
    """
    import json

    result = {"jsonld": [], "meta": {}, "preloaded": {}}

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return result

    # 1. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                result["jsonld"].extend(data)
            elif isinstance(data, dict):
                result["jsonld"].append(data)
        except Exception:
            pass

    # 2. OpenGraph / product meta
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name") or ""
        content = meta.get("content") or ""
        if not prop or not content:
            continue
        prop_lower = prop.lower()
        if any(k in prop_lower for k in ("og:", "product:", "price", "title", "description", "image")):
            result["meta"][prop] = content

    # 3. __PRELOADED_STATE__ (네이버 SSR 상태)
    for script in soup.find_all("script"):
        text = script.string or ""
        if "__PRELOADED_STATE__" in text:
            m = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.+?\});?\s*(?:window|$)", text, re.DOTALL)
            if not m:
                m = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.+)", text, re.DOTALL)
            if m:
                try:
                    result["preloaded"] = json.loads(m.group(1))
                    break
                except Exception:
                    pass

    return result


def clean_html_for_llm_context(html: str) -> str:
    """
    LLM에 전달할 HTML을 가볍게 정리.

    구조와 텍스트는 최대한 유지하고, 스타일/스크립트/장식성 요소만 제거한다.
    """
    logger.info(f"LLM용 HTML 경량 정리 시작: {len(html)} 문자")

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.warning(f"LLM용 HTML 파싱 실패, 기본 정리만 수행: {exc}")
        return HTMLCleaner._basic_clean(html)

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    removable_tags = [
        "script", "style", "noscript", "iframe", "canvas", "svg",
        "path", "g", "defs", "clipPath", "mask", "source", "track"
    ]
    for tag_name in removable_tags:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    low_signal_patterns = [
        r"font[_-]?face",
        r"icon",
        r"\bico\b",
        r"spinner",
        r"loader",
        r"loading",
        r"skeleton",
        r"placeholder",
        r"tooltip",
        r"toast",
    ]

    tags_to_decompose = []
    for tag in soup.find_all():
        if tag is None or tag.parent is None:
            continue
        classes = " ".join(tag.get("class") or [])
        tag_id = tag.get("id") or ""
        combined = f"{classes} {tag_id}".strip().lower()

        if combined and any(re.search(pattern, combined, re.IGNORECASE) for pattern in low_signal_patterns):
            text = tag.get_text(strip=True)
            if not text:
                tags_to_decompose.append(tag)
                continue

        attrs_to_remove = []
        for attr in list(tag.attrs):
            if attr == "style" or attr.startswith("on"):
                attrs_to_remove.append(attr)
                continue
            if attr.startswith("data-") and any(token in attr.lower() for token in ("track", "analytics", "gtm")):
                attrs_to_remove.append(attr)

        for attr in attrs_to_remove:
            try:
                del tag[attr]
            except Exception:
                pass

    for tag in tags_to_decompose:
        try:
            tag.decompose()
        except Exception:
            pass

    cleaned_html = str(soup)
    cleaned_html = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_html)
    cleaned_html = re.sub(r" +", " ", cleaned_html)

    logger.info(
        f"LLM용 HTML 경량 정리 완료: {len(cleaned_html)} 문자 ({len(html) - len(cleaned_html)} 문자 제거)"
    )
    return cleaned_html
