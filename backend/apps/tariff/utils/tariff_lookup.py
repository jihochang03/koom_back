"""
일본 관세율표 SQLite 조회 + Claude 최적 항목 선택.

세율 적용 우선순위 (일본 관세법):
  RCEP(FTA) → 잠정세율 → WTO협정 → 기본세율
  최종 = 파싱 가능한 것 중 가장 낮은 값

세율 유형:
  free      : "Free" / "(Free)"          → advalorem 0%
  advalorem : "8.5%"                     → 종가세
  specific  : "3,400,000 yen/each"       → 종량세  (advalorem 없음)
  compound  : "25% + 63 yen/kg"          → 혼합세  (advalorem + specific 둘 다)
  unknown   : 파싱 불가

흐름:
  0. Claude로 제목 → 관세 관점 한국어 검색어 확장 (선택)
  1. 확장어·원제목 키워드 FTS5 검색 → 후보 최대 20건
  2. Claude → 최적 항목 번호 선택
  3. 선택된 행의 세율 파싱 → 우선순위·최솟값 선택 후 반환
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tariff.db")


def _empty_tariff_lookup(candidates_found: int = 0) -> dict:
    """조회 실패·무후보 시 공통 구조 (호출마다 새 dict — 공유 dict 변이 방지)."""
    return {
        "rate": None,
        "rate_source": "none",
        "duty_type": None,
        "specific_yen_per_unit": None,
        "specific_unit": None,
        "matched_item": None,
        "순번": None,
        "full_path": None,
        "depth_path": [],
        "candidates_found": candidates_found,
    }


def _depth_from_full_path(full_path: Optional[str]) -> list[str]:
    """
    관세율표 full_path("대분류 > 중분류 > ... > 품목")를 depth 배열로 분해.

    관세 분류는 "이것 중에 → 이것 중에" 식 트리이므로, 검수 담당자가
    어떤 경로로 이 품목에 도달했는지 단계별로 보여 주는 데 사용한다.
    """
    if not full_path or not str(full_path).strip():
        return []
    return [seg.strip() for seg in str(full_path).split(">") if seg.strip()]


def _parse_llm_selected_index(text: str) -> Optional[int]:
    """Claude가 JSON 외 설명을 섞어도 selected 정수만 뽑기."""
    if not text or not str(text).strip():
        return None
    t = str(text).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if fence and fence.group(1).strip():
        t = fence.group(1).strip()
    m = re.search(r'["\']selected["\']\s*:\s*(\d+)', t)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    lo, hi = t.find("{"), t.rfind("}")
    if lo != -1 and hi > lo:
        frag = t[lo : hi + 1]
        try:
            data = json.loads(frag)
            v = data.get("selected", 0)
            return int(v)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # 마지막 수단: 응답이 숫자로만 구성됐거나 첫 번째 단독 숫자 추출
    m = re.match(r"^\s*(\d+)\s*$", t)
    if m:
        return int(m.group(1))
    return None


# ── 세율 파싱 ─────────────────────────────────────────────────────────────────

def _parse_duty(s: Optional[str]) -> dict:
    """
    세율 문자열 → duty 정보 dict.

    반환 키: type, advalorem (float|None), specific_yen (float|None), unit (str|None)
    """
    empty: dict = {"type": None, "advalorem": None, "specific_yen": None, "unit": None}
    if not s or str(s).strip() in ("", "None", "-"):
        return empty

    raw = str(s).strip()
    # 전처리: 쉼표·공백·괄호·# 제거
    cleaned = raw.replace(",", "").replace(" ", "").replace("(", "").replace(")", "").replace("#", "")
    cl = cleaned.lower()

    if cl == "free":
        return {"type": "free", "advalorem": 0.0, "specific_yen": None, "unit": None}

    # 혼합세: 25%+63yen/kg
    m = re.match(r"^([\d.]+)%\+([\d.]+)yen/([a-z]+)$", cl)
    if m:
        return {
            "type": "compound",
            "advalorem": float(m.group(1)) / 100.0,
            "specific_yen": float(m.group(2)),
            "unit": m.group(3),
        }

    # 종량세: 4000000yen/each
    m = re.match(r"^([\d.]+)yen/([a-z]+)$", cl)
    if m:
        return {
            "type": "specific",
            "advalorem": None,
            "specific_yen": float(m.group(1)),
            "unit": m.group(2),
        }

    # 종가세: 8.5%
    m = re.match(r"^([\d.]+)%$", cleaned)
    if m:
        return {
            "type": "advalorem",
            "advalorem": float(m.group(1)) / 100.0,
            "specific_yen": None,
            "unit": None,
        }

    # 소수점만 (예: "0.085")
    m = re.match(r"^([\d.]+)$", cleaned)
    if m:
        v = float(m.group(1))
        return {
            "type": "advalorem",
            "advalorem": v / 100.0 if v > 1.0 else v,
            "specific_yen": None,
            "unit": None,
        }

    return {"type": "unknown", "advalorem": None, "specific_yen": None, "unit": None}


def _parse_rate(s: Optional[str]) -> Optional[float]:
    """advalorem/free/compound → float. specific/unknown → None. (하위 호환용)"""
    d = _parse_duty(s)
    if d["type"] in ("free", "advalorem"):
        return d["advalorem"]
    if d["type"] == "compound":
        return d["advalorem"]  # compound의 종가 부분
    return None


def _best_duty(
    rcep: Optional[str],
    temp: Optional[str],
    wto: Optional[str],
    basic: Optional[str],
) -> tuple[Optional[float], str, dict]:
    """
    RCEP → 잠정 → WTO → 기본 순서로 파싱.
    advalorem 비교 가능한 것 중 최솟값(가장 유리) 선택.
    advalorem이 하나도 없으면 specific 중 우선순위 첫 번째 반환.

    반환: (advalorem_rate_or_None, source, duty_dict)
    """
    av_candidates: list[tuple[float, str, dict]] = []
    specific_fallback: Optional[tuple[str, dict]] = None

    for raw, source in [(rcep, "rcep"), (temp, "temp"), (wto, "wto"), (basic, "basic")]:
        d = _parse_duty(raw)
        t = d["type"]
        if t in ("free", "advalorem"):
            av_candidates.append((d["advalorem"], source, d))
        elif t == "compound":
            # compound: advalorem 부분으로 비교, specific 정보도 보존
            av_candidates.append((d["advalorem"], source, d))
        elif t == "specific" and specific_fallback is None:
            specific_fallback = (source, d)

    if av_candidates:
        # 최솟값; 동률이면 list 앞쪽(RCEP > 잠정 > WTO > 기본) — min은 stable
        best = min(av_candidates, key=lambda x: x[0])
        return best[0], best[1], best[2]

    if specific_fallback:
        source, d = specific_fallback
        return None, source, d

    return None, "unparseable", {"type": "unknown", "advalorem": None, "specific_yen": None, "unit": None}


# ── 벡터 검색 ────────────────────────────────────────────────────────────────

def _embed_dims(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT value FROM tariff_meta WHERE key='embed_dims'"
        ).fetchone()
        return int(row[0]) if row else 512
    except Exception:
        return 512


def _vec_table_exists(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM tariff_vec LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def _embed_text(text: str, api_key: str, dims: int = 512) -> Optional[list]:
    model = os.getenv("TARIFF_EMBED_MODEL", "text-embedding-3-small")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=model, input=[text[:2000]], dimensions=dims)
        return resp.data[0].embedding
    except Exception as e:
        logger.warning("임베딩 생성 실패 (무시): %s", e)
        return None


def search_candidates_vec(
    product_title: str,
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 20,
    api_key: Optional[str] = None,
) -> list[tuple]:
    """
    sqlite-vec 코사인 유사도로 후보 검색.
    tariff_vec 테이블이 없거나 openai 키 없으면 빈 리스트 반환.
    """
    if not os.path.exists(db_path):
        return []
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return []
    try:
        import sqlite_vec
        import struct
    except ImportError:
        logger.debug("sqlite-vec 미설치 — 벡터 검색 건너뜀")
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        try:
            conn.enable_load_extension(True)
        except AttributeError:
            logger.debug("SQLite 확장 로드 미지원 — 벡터 검색 건너뜀")
            return []
        try:
            sqlite_vec.load(conn)
        except Exception as e:
            logger.warning("sqlite-vec 로드 실패: %s", e)
            return []
        conn.enable_load_extension(False)

        if not _vec_table_exists(conn):
            return []
        dims = _embed_dims(conn)
        embedding = _embed_text(product_title, key, dims)
        if not embedding:
            return []
        query_vec = struct.pack(f"{dims}f", *embedding)
        rows = conn.execute(
            """
            SELECT t.rowid, t.순번, t.한글품명, t.기본세율, t.잠정세율, t.WTO협정, t.RCEP대한민국,
                   COALESCE(t.full_path, '')
            FROM tariff_vec v
            JOIN tariff t ON t.rowid = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (query_vec, limit),
        ).fetchall()
        return rows
    except Exception as e:
        logger.warning("벡터 검색 실패 (무시): %s", e)
        return []
    finally:
        conn.close()


# ── FTS5 검색 ─────────────────────────────────────────────────────────────────

def _extract_keywords(title: str) -> list[str]:
    cleaned = re.sub(r"[()【】\[\]「」『』,，、；;]", " ", title)  # 쉼표 포함 제거
    cleaned = re.sub(r"\d+[cmgkglLpcs]+\b", " ", cleaned)
    tokens = cleaned.split()
    # 앞뒤 구두점 제거, 2자 이상, 숫자만 아닌 토큰
    tokens = [t.strip(".,·") for t in tokens]
    return [t for t in tokens if len(t) >= 2 and not re.match(r"^[\d.,]+$", t)]


def _keywords_for_search(product_title: str, search_hint: Optional[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    def add_from_text(text: str) -> None:
        if not text or not str(text).strip():
            return
        for t in _extract_keywords(str(text)):
            if t not in seen:
                seen.add(t)
                merged.append(t)

    if search_hint:
        hint = str(search_hint).strip()
        for seg in re.split(r"[,，、\n;；]\s*", hint):
            seg = seg.strip()
            if len(seg) >= 2:
                add_from_text(seg)
        # 전체 hint를 한 번 더 처리하면 "케이스," 같은 쓰레기 토큰 발생 → 생략
    add_from_text(product_title)
    return merged


def _tariff_expand_model() -> str:
    return os.getenv("TARIFF_EXPAND_MODEL") or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


def _tariff_select_model() -> str:
    return os.getenv("TARIFF_ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001"


_NON_PHYSICAL_SENTINEL = "__NON_PHYSICAL__"


def _expand_title_for_tariff_db(product_title: str, api_key: str) -> Optional[str]:
    if os.getenv("SKIP_CLAUDE", "").lower() in ("1", "true", "yes"):
        return None
    if not product_title or not product_title.strip():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        model = _tariff_expand_model()
        user_msg = (
            "역할: 일본 관세율표(HS 품목분류)의 **한글품명** 열과 매칭될 검색어를 생성한다.\n\n"
            "한글품명은 쇼핑몰 상품명이 아니라 행정·법령 문체의 품목 설명이다.\n"
            "예시처럼 대분류 명사 → 가공 형태 → 성분/재질/용도 순서로 압축한다.\n\n"
            "【변환 예시】\n"
            "  상품명: '포도향 무당 탄산음료 500ml'\n"
            "  → 탄산수, 비알코올성 음료, 기타 음료, 감미료, 무가당\n\n"
            "  상품명: '면 100% 반소매 티셔츠 남성'\n"
            "  → 면 편직물 의류, 티셔츠, 메리야스 상의, 면제\n\n"
            "  상품명: '블루투스 무선 이어폰 노이즈캔슬링'\n"
            "  → 헤드폰, 이어폰, 음향기기, 수신기, 마이크로폰\n\n"
            "  상품명: '소가죽 반지갑 카드지갑 남성용'\n"
            "  → 가죽제 지갑, 소 가죽, 핸드백 여행용품, 가죽 소품\n\n"
            "  상품명: '인스턴트 컵라면 닭고기맛'\n"
            "  → 국수류, 파스타, 조리된 면류, 인스턴트 국수, 밀가루 가공품\n\n"
            "  상품명: '화장수 스킨로션 히알루론산'\n"
            "  → 화장수, 스킨케어, 향장품, 피부용 화장품, 로션\n\n"
            "먼저 아래 제목이 **실물 수입 과세 대상**인지 판단한다.\n"
            "실물 수입 대상이 아닌 예: 공연·연극·콘서트 티켓/예매, 숙박/호텔 예약, "
            "투어·액티비티, 디지털 콘텐츠, 앱·소프트웨어, 멤버십, 상품권(실물 제외), "
            "음식점 이용권, 배달 음식, 인터넷 서비스 등.\n\n"
            "판단 결과:\n"
            "  A) 실물 수입 대상이 아니면 → {\"skip\": true}\n"
            "  B) 실물 수입 대상이면 → 브랜드·지역·행사명·할인 문구·배송 문구·용량·수량은 제거.\n"
            "     **관세율표 한글품명에 나올 법한** 품목 명사만 나열. 쉼표 구분, 10단어 이내.\n"
            "     재질(면·가죽·플라스틱), 가공 형태(조리된·건조·냉동), 용도(식용·공업용),\n"
            "     성분 분류(가당·무당·알코올함유), 대분류 품목명을 우선 포함.\n"
            '     → {"hs_search":"..."}\n\n'
            "JSON만 출력.\n\n"
            f'제목: "{product_title[:900]}"'
        )
        resp = client.messages.create(
            model=model,
            max_tokens=400,
            temperature=0,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group())
        if obj.get("skip"):
            logger.info("관세 DB 검색 건너뜀 (비실물 품목): '%s'", product_title[:60])
            return _NON_PHYSICAL_SENTINEL
        phrase = obj.get("hs_search") or obj.get("search") or obj.get("keywords")
        if phrase is None:
            return None
        s = str(phrase).strip()
        return s if s else None
    except Exception as e:
        logger.warning("관세 검색어 확장 실패 (무시): %s", e)
        return None


def _fts5_token(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if re.search(r'[\s"]', s):
        return '"' + s.replace('"', '""') + '"'
    return s


def _fts5_prefix_terms(keywords: list[str], max_terms: int) -> str:
    parts: list[str] = []
    for kw in keywords[:max_terms]:
        t = _fts5_token(kw)
        if not t:
            continue
        parts.append(f"{t}*")
    return " OR ".join(parts)


_SELECT_COLS = (
    "rowid, 순번, 한글품명, 기본세율, 잠정세율, WTO협정, RCEP대한민국, full_path"
)


def search_candidates(
    product_title: str,
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 20,
    search_hint: Optional[str] = None,
) -> list[tuple]:
    """
    FTS5로 한글품명 후보 검색.
    반환: [(rowid, 순번, 한글품명, 기본세율, 잠정세율, WTO협정, RCEP대한민국), ...]
    """
    if not os.path.exists(db_path):
        logger.warning("관세율 DB 없음: %s", db_path)
        return []

    keywords = _keywords_for_search(product_title, search_hint)
    if not keywords:
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        results: list[tuple] = []
        seen: set[int] = set()

        def _add(rows):
            for r in rows:
                if r[0] not in seen:
                    seen.add(r[0])
                    results.append(r)

        def _select_match(match_sql: str, lim: int):
            try:
                return conn.execute(
                    f"SELECT {_SELECT_COLS} FROM tariff_fts WHERE tariff_fts MATCH ? "
                    "ORDER BY bm25(tariff_fts) LIMIT ?",
                    (match_sql, lim),
                ).fetchall()
            except sqlite3.OperationalError:
                return conn.execute(
                    f"SELECT {_SELECT_COLS} FROM tariff_fts WHERE tariff_fts MATCH ? LIMIT ?",
                    (match_sql, lim),
                ).fetchall()

        # 1차: 개별 키워드 단독 검색 — bm25 OR 랭킹에서 밀리는 항목을 먼저 확보
        for kw in keywords[:8]:
            if len(results) >= limit:
                break
            t = _fts5_token(kw)
            if not t:
                continue
            try:
                _add(_select_match(t, limit))
            except sqlite3.OperationalError:
                pass

        # 2차: AND 검색 (처음 5개 키워드 — 여러 단어 동시 매칭 항목 보강)
        if len(results) < limit:
            and_parts = [_fts5_token(k) for k in keywords[:5] if _fts5_token(k)]
            and_query = " ".join(and_parts)
            if and_query:
                try:
                    _add(_select_match(and_query, limit))
                except sqlite3.OperationalError:
                    pass

        # 3차: OR 전체 (bm25 순위 기준, 다수 키워드 매칭 항목 보강)
        if len(results) < limit:
            or_exact = " OR ".join(_fts5_token(k) for k in keywords[:12] if _fts5_token(k))
            if or_exact:
                try:
                    _add(_select_match(or_exact, limit))
                except sqlite3.OperationalError:
                    pass

        # 4차: 접두어 OR
        if len(results) < limit:
            pref = _fts5_prefix_terms(keywords, 12)
            if pref:
                try:
                    _add(_select_match(pref, limit))
                except sqlite3.OperationalError:
                    pass

        # 5차: LIKE 부분 문자열 (후보가 부족할수록 더 적극적으로 — 오분류 방지)
        if len(results) < max(8, limit // 2):
            by_len = sorted(
                (k for k in keywords if len(k) >= 2),
                key=len,
                reverse=True,
            )
            for kw in by_len[:8]:
                if len(results) >= limit:
                    break
                try:
                    like_rows = conn.execute(
                        "SELECT rowid, 순번, 한글품명, 기본세율, 잠정세율, WTO협정, RCEP대한민국,"
                        " CASE WHEN full_path IS NOT NULL THEN full_path ELSE '' END"
                        " FROM tariff"
                        " WHERE 한글품명 IS NOT NULL AND 한글품명 LIKE ? LIMIT ?",
                        (f"%{kw}%", limit),
                    ).fetchall()
                    _add(like_rows)
                except sqlite3.OperationalError:
                    pass

        # 6차: 한글 bigram fallback — 키워드 추출이 모두 빗나가 후보가 거의 없을 때.
        #      긴 키워드를 2글자 조각으로 쪼개 부분 매칭, 완전 무후보 상황을 줄인다.
        if len(results) < 3:
            bigrams: list[str] = []
            seen_bg: set[str] = set()
            for kw in sorted((k for k in keywords if len(k) >= 3), key=len, reverse=True):
                for i in range(len(kw) - 1):
                    bg = kw[i : i + 2]
                    if re.search(r"[가-힣]", bg) and bg not in seen_bg:
                        seen_bg.add(bg)
                        bigrams.append(bg)
            for bg in bigrams[:10]:
                if len(results) >= limit:
                    break
                try:
                    like_rows = conn.execute(
                        "SELECT rowid, 순번, 한글품명, 기본세율, 잠정세율, WTO협정, RCEP대한민국,"
                        " CASE WHEN full_path IS NOT NULL THEN full_path ELSE '' END"
                        " FROM tariff"
                        " WHERE 한글품명 IS NOT NULL AND 한글품명 LIKE ? LIMIT ?",
                        (f"%{bg}%", limit),
                    ).fetchall()
                    _add(like_rows)
                except sqlite3.OperationalError:
                    pass

        return results[:limit]
    finally:
        conn.close()


# ── Claude 선택 ───────────────────────────────────────────────────────────────

def _row_to_lookup_dict(
    row: tuple,
    *,
    candidates_found: int,
    selection_method: str,
    product_title: str,
) -> dict:
    """
    DB 행 → lookup 결과 dict.
    세율·품명 텍스트는 DB 행에서만 해석. LLM은 후보 번호만 고름.
    """
    # full_path 컬럼이 없는 구버전 DB 호환
    if len(row) >= 8:
        _rowid, 순번_val, 품명_val, 기본_val, 잠정_val, wto_val, rcep_val, full_path_val = row[:8]
    else:
        _rowid, 순번_val, 품명_val, 기본_val, 잠정_val, wto_val, rcep_val = row[:7]
        full_path_val = None
    rate, source, duty = _best_duty(
        str(rcep_val)  if rcep_val  else None,
        str(잠정_val)  if 잠정_val  else None,
        str(wto_val)   if wto_val   else None,
        str(기본_val)  if 기본_val  else None,
    )

    duty_type = duty.get("type") or "unknown"

    logger.info(
        "관세율 조회 완료 (%s): '%s' → [%s] %s | %s(%s)=%s",
        selection_method,
        product_title[:40],
        순번_val,
        (품명_val or "?")[:30],
        source,
        duty_type,
        f"{rate*100:.1f}%" if rate is not None else (
            f"{duty.get('specific_yen')}yen/{duty.get('unit')}" if duty.get("specific_yen") else "N/A"
        ),
    )

    return {
        "rate": rate,                              # float|None (advalorem 부분)
        "rate_source": source,                     # rcep|temp|wto|basic|unparseable
        "duty_type": duty_type,                    # free|advalorem|specific|compound|unknown
        "specific_yen_per_unit": duty.get("specific_yen"),   # 종량세 단위 금액
        "specific_unit": duty.get("unit"),         # kg|each|...
        "matched_item": 품명_val,
        "순번": 순번_val,
        "full_path": full_path_val or None,        # "대분류 > ... > 품목" 전체 경로
        "depth_path": _depth_from_full_path(full_path_val),  # 단계별 분류 배열
        "candidates_found": candidates_found,
        "selection_method": selection_method,
    }


def _gather_candidates(
    product_title: str,
    db_path: str,
    limit: int,
    anthropic_key: Optional[str],
    openai_key: Optional[str],
) -> tuple[list[tuple], Optional[str], bool]:
    """
    벡터 검색 우선 → 실패 시 Claude 검색어 확장 + FTS5.

    반환: (candidates, search_expansion, non_physical)
      - non_physical=True 이면 후보 없이 비실물 품목으로 조기 종료
    """
    vec_candidates = search_candidates_vec(product_title, db_path, limit=limit, api_key=openai_key)
    if vec_candidates:
        logger.info("벡터 검색 사용: '%s' → %d건", product_title[:40], len(vec_candidates))
        return vec_candidates, None, False

    search_expansion: Optional[str] = None
    if anthropic_key:
        search_expansion = _expand_title_for_tariff_db(product_title, anthropic_key)
        if search_expansion == _NON_PHYSICAL_SENTINEL:
            return [], None, True
        if search_expansion:
            logger.info(
                "관세 DB 검색 확장(FTS): 원문=%r → hs_search=%r",
                (product_title or "")[:80],
                search_expansion[:160],
            )
    candidates = search_candidates(product_title, db_path, limit=limit, search_hint=search_expansion)
    return candidates, search_expansion, False


def _candidate_lines(candidates: list[tuple]) -> str:
    """
    후보 목록 → LLM 프롬프트용 텍스트. full_path를 분류 컨텍스트로 사용.

    구버전 rowid 역추적 대신 full_path 컬럼을 그대로 쓰므로 분류 경로가 정확하다.
    """
    lines = []
    for i, row in enumerate(candidates, 1):
        순번, 품명, 기본, 잠정, wto, rcep = row[1:7]
        full_path = row[7] if len(row) >= 8 else ""
        depth = _depth_from_full_path(full_path)
        cat = " > ".join(depth[:-1]) if len(depth) > 1 else ""
        ctx_note = f"\n   분류: {cat}" if cat else ""
        lines.append(
            f"{i}. [{순번}] {품명} | 기본:{기본} | 잠정:{잠정} | WTO:{wto} | RCEP:{rcep}{ctx_note}"
        )
    return "\n".join(lines)


def lookup_tariff_with_claude(
    product_title: str,
    db_path: str = _DEFAULT_DB_PATH,
    api_key: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """
    상품명으로 관세율표 조회 후, 후보가 여러 개일 때만 Claude로 행 번호 선택.

    반환 dict 키:
        rate                    float|None  (advalorem 세율)
        rate_source             str         (rcep|temp|wto|basic|unparseable)
        duty_type               str         (free|advalorem|specific|compound|unknown)
        specific_yen_per_unit   float|None  (종량세/혼합세 단위 금액)
        specific_unit           str|None    (kg|each|...)
        matched_item            str|None
        순번                    int|None
        candidates_found        int
        selection_method        str
        search_expansion        str         (Claude 확장 검색어, 있을 때만)
        non_physical            bool        (실물 아닌 품목이면 True)
    """
    anthropic_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    candidates, search_expansion, non_physical = _gather_candidates(
        product_title, db_path, limit, anthropic_key, openai_key
    )
    if non_physical:
        return {"non_physical": True, **_empty_tariff_lookup()}

    def _with_expansion(out: dict) -> dict:
        if search_expansion and search_expansion != _NON_PHYSICAL_SENTINEL:
            out = dict(out)
            out["search_expansion"] = search_expansion
        return out

    if not candidates:
        return _with_expansion(_empty_tariff_lookup())

    n = len(candidates)
    candidates_text = _candidate_lines(candidates)

    try:
        import anthropic
        if not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY 없음")
        client = anthropic.Anthropic(api_key=anthropic_key)

        prompt = (
            "역할: 아래 '후보'는 일본 관세율표의 **한글 품목 설명**이다. "
            "위 상품명은 쇼핑몰 등의 **판매 제목**이라, 한글품명과 문장이 같을 필요가 없다. "
            "글자 일치를 기대하지 말고, **같은 실물 품목**(재질·용도·종류·기능)에 해당하는 "
            "설명 줄을 고른다.\n\n"
            "규칙:\n"
            "- 후보 목록에 없는 품목명·세율·HS를 **새로 만들거나 추측하지 않는다**.\n"
            "- 표 밖의 관세율·분류 지식으로 줄을 고르지 않는다. **후보 번호만** 선택한다.\n"
            "- 후보 중에도 해당 실물에 맞는 설명이 없으면 selected를 0으로 한다.\n"
            "- 응답은 JSON 한 개, 키는 selected(정수)만.\n\n"
            f'상품명(판매 제목): "{product_title}"\n\n'
            f"후보(관세율표 한글 품목 설명):\n{candidates_text}\n\n"
            'JSON 예: {"selected": 3} 또는 {"selected": 0}'
        )

        if search_expansion:
            prompt = (
                f"품목 요약(일본 관세·HS 관점에서 정리한 검색용 문구, 참고만): {search_expansion}\n\n"
                + prompt
            )

        model = _tariff_select_model()
        sys_json = (
            "당신은 관세 품목 분류 도우미입니다. "
            "반드시 숫자 하나만 출력하세요. 설명·이유 금지. "
            "후보 중 맞는 항목이 없으면 0을 출력하세요."
        )
        resp = client.messages.create(
            model=model,
            max_tokens=10,
            temperature=0,
            system=sys_json,
            messages=[{"role": "user", "content": prompt + "\n\n위 후보 중 가장 적합한 번호(숫자만):"}],
        )
        text = resp.content[0].text.strip()
        selected_idx = _parse_llm_selected_index(text)
        retry_text = ""
        if selected_idx is None:
            logger.warning("관세율 조회: Claude 응답 파싱 실패 (%s)", text[:200])
            resp2 = client.messages.create(
                model=model,
                max_tokens=10,
                temperature=0,
                system="숫자 하나만 출력. 다른 글자 절대 금지.",
                messages=[
                    {"role": "user", "content": prompt + "\n\n번호(숫자만, 없으면 0):"},
                ],
            )
            retry_text = resp2.content[0].text.strip()
            selected_idx = _parse_llm_selected_index(retry_text)
        if selected_idx is None:
            logger.warning(
                "관세율 조회: 재시도 후에도 파싱 실패 first=%r retry=%r",
                text[:160],
                retry_text[:160],
            )
            return _with_expansion(_empty_tariff_lookup(n))

        if selected_idx <= 0 or selected_idx > len(candidates):
            return _with_expansion(_empty_tariff_lookup(n))

        return _with_expansion(
            _row_to_lookup_dict(
                candidates[selected_idx - 1],
                candidates_found=n,
                selection_method="llm",
                product_title=product_title,
            )
        )

    except Exception as e:
        logger.warning("관세율 조회 실패 (무시): %s", e)
        return _with_expansion(_empty_tariff_lookup(n))


# ── 검수 담당자용: 선정 사유 + 대안 후보 (fastbox 통관 분류 확인) ───────────────

def _parse_classification_json(text: str) -> dict:
    """Claude의 분류 응답에서 {selected, reason, alternatives} 추출 (잡설 섞여도 관용)."""
    fallback = {"selected": 0, "reason": "", "alternatives": []}
    if not text or not str(text).strip():
        return fallback
    t = str(text).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if fence and fence.group(1).strip():
        t = fence.group(1).strip()
    lo, hi = t.find("{"), t.rfind("}")
    if lo != -1 and hi > lo:
        try:
            data = json.loads(t[lo : hi + 1])
            sel = data.get("selected", 0)
            alts = data.get("alternatives", []) or []
            return {
                "selected": int(sel) if str(sel).strip().lstrip("-").isdigit() else 0,
                "reason": str(data.get("reason", "") or "").strip(),
                "alternatives": [int(a) for a in alts if str(a).strip().isdigit()],
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # 최소한 selected 번호라도 건진다
    idx = _parse_llm_selected_index(t)
    if idx is not None:
        return {"selected": idx, "reason": "", "alternatives": []}
    return fallback


def _select_with_reasoning(
    product_title: str,
    candidates: list[tuple],
    search_expansion: Optional[str],
    anthropic_key: Optional[str],
) -> dict:
    """
    후보 중 최적 항목 선택 + **선정 사유** + **대안 후보 순위**를 함께 받는다.

    검수 담당자가 AI 판단 근거를 보고, 다른 분류로 바꿀 수 있도록
    cheap한 번호-only 선택(lookup_tariff_with_claude) 대신 사유까지 생성.
    반환: {"selected": int, "reason": str, "alternatives": [int, ...]}
    """
    fallback = {"selected": 0, "reason": "", "alternatives": []}
    if not anthropic_key:
        return fallback
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=anthropic_key)
        candidates_text = _candidate_lines(candidates)
        prompt = (
            "역할: 아래 '후보'는 일본 관세율표(HS 품목분류)의 **한글 품목 설명**과 그 분류 경로다. "
            "위 상품명은 쇼핑몰 판매 제목이라 글자가 같을 필요는 없고, **같은 실물 품목**"
            "(재질·용도·종류·기능)에 해당하는 줄을 고른다.\n\n"
            "관세 분류는 대분류 → 중분류 → 세부품목으로 좁혀지는 트리다. 각 후보의 '분류' 경로가 "
            "상품과 맞는지도 함께 보고 판단한다.\n\n"
            "규칙:\n"
            "- 후보 목록에 없는 품목·세율·HS를 새로 만들지 않는다. **후보 번호만** 사용한다.\n"
            "- selected: 가장 적합한 후보 1개 번호. 맞는 것이 없으면 0.\n"
            "- reason: selected를 고른 이유를 한국어 1~3문장으로. 어떤 분류 경로·재질·용도 때문에 "
            "이 품목으로 봤는지 검수 담당자가 이해할 수 있게 설명한다.\n"
            "- alternatives: selected 외에 채택될 여지가 있는 후보 번호를 적합한 순서대로 최대 5개. "
            "헷갈릴 만한 다른 분류를 우선 포함한다. 없으면 빈 배열.\n"
            "- 출력은 JSON 하나만.\n\n"
            f'상품명(판매 제목): "{product_title}"\n\n'
            f"후보(관세율표 한글 품목 설명 / 분류 경로):\n{candidates_text}\n\n"
            '출력 예: {"selected": 3, "reason": "면 편직물 상의로 분류 경로가 의류>티셔츠와 일치한다.", '
            '"alternatives": [5, 2]}'
        )
        if search_expansion:
            prompt = (
                f"품목 요약(관세·HS 관점 정리, 참고용): {search_expansion}\n\n" + prompt
            )

        resp = client.messages.create(
            model=_tariff_select_model(),
            max_tokens=600,
            temperature=0,
            system=(
                "당신은 일본 수입 관세 품목분류(HS) 전문가입니다. "
                "반드시 JSON 하나만 출력하고, 후보 목록의 번호만 사용하세요."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_classification_json(resp.content[0].text.strip())
    except Exception as e:
        logger.warning("관세 분류 사유 생성 실패 (무시): %s", e)
        return fallback


def _candidate_summary(row: tuple, *, product_title: str) -> dict:
    """후보 행 → 검수자 화면용 요약 dict (세율·품명·분류 경로)."""
    d = _row_to_lookup_dict(
        row,
        candidates_found=0,
        selection_method="llm",
        product_title=product_title,
    )
    d.pop("candidates_found", None)
    d.pop("selection_method", None)
    return d


def classify_tariff(
    product_title: str,
    db_path: str = _DEFAULT_DB_PATH,
    api_key: Optional[str] = None,
    top_n: int = 5,
    limit: int = 30,
) -> dict:
    """
    검수 담당자용 관세 품목 분류. fastbox 통관 등록 전에:
      - selected     : AI가 고른 HS코드/품명/분류 경로 + **선정 사유(reason)**
      - alternatives : 채택될 여지가 있는 다른 후보들(각자 분류 경로·세율 포함)

    검수 담당자는 selected를 그대로 확정하거나, alternatives에서 다른 분류를
    선택하거나, 직접 입력해 수정·피드백할 수 있다.

    반환 dict:
      product_title, non_physical, search_expansion, candidates_found,
      selected: {hs_code, matched_item, full_path, depth_path, rate, rate_source,
                 duty_type, specific_yen_per_unit, specific_unit, reason} | None,
      alternatives: [{...같은 키..., rank}, ...]
    """
    anthropic_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    candidates, search_expansion, non_physical = _gather_candidates(
        product_title, db_path, limit, anthropic_key, openai_key
    )
    expansion = search_expansion if (search_expansion and search_expansion != _NON_PHYSICAL_SENTINEL) else None
    base = {
        "product_title": product_title,
        "non_physical": non_physical,
        "search_expansion": expansion,
        "candidates_found": len(candidates),
        "selected": None,
        "alternatives": [],
    }
    if non_physical or not candidates:
        return base

    sel = _select_with_reasoning(product_title, candidates, search_expansion, anthropic_key)
    selected_idx = sel.get("selected") or 0

    def _to_summary(idx: int) -> dict:
        return _candidate_summary(candidates[idx - 1], product_title=product_title)

    if 1 <= selected_idx <= len(candidates):
        chosen = _to_summary(selected_idx)
        chosen["reason"] = sel.get("reason", "")
        base["selected"] = chosen

    # 대안: LLM이 준 순위를 우선, 부족하면 검색 순서대로 채운다 (selected 제외)
    alt_indices: list[int] = []
    for i in sel.get("alternatives", []):
        if 1 <= i <= len(candidates) and i != selected_idx and i not in alt_indices:
            alt_indices.append(i)
    for i in range(1, len(candidates) + 1):
        if len(alt_indices) >= top_n:
            break
        if i != selected_idx and i not in alt_indices:
            alt_indices.append(i)

    alternatives = []
    for rank, i in enumerate(alt_indices[:top_n], 1):
        summary = _to_summary(i)
        summary["rank"] = rank
        alternatives.append(summary)
    base["alternatives"] = alternatives

    return base
