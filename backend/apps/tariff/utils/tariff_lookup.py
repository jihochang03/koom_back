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
        "candidates_found": candidates_found,
    }


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

        # 5차: LIKE 부분 문자열
        if len(results) < 5:
            by_len = sorted(
                (k for k in keywords if len(k) >= 3),
                key=len,
                reverse=True,
            )
            for kw in by_len[:5]:
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
        "candidates_found": candidates_found,
        "selection_method": selection_method,
    }


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

    # ── 벡터 검색 우선 시도 ──────────────────────────────────────────────────
    vec_candidates = search_candidates_vec(product_title, db_path, limit=limit, api_key=openai_key)
    search_expansion: Optional[str] = None

    if vec_candidates:
        logger.info("벡터 검색 사용: '%s' → %d건", product_title[:40], len(vec_candidates))
        candidates = vec_candidates
    else:
        # vec 없으면 1차 Claude 호출(쿼리 확장) + FTS fallback
        if anthropic_key:
            search_expansion = _expand_title_for_tariff_db(product_title, anthropic_key)
            if search_expansion == _NON_PHYSICAL_SENTINEL:
                return {"non_physical": True, **_empty_tariff_lookup()}
            if search_expansion:
                logger.info(
                    "관세 DB 검색 확장(FTS): 원문=%r → hs_search=%r",
                    (product_title or "")[:80],
                    search_expansion[:160],
                )
        candidates = search_candidates(product_title, db_path, limit=limit, search_hint=search_expansion)

    def _with_expansion(out: dict) -> dict:
        if search_expansion and search_expansion != _NON_PHYSICAL_SENTINEL:
            out = dict(out)
            out["search_expansion"] = search_expansion
        return out

    if not candidates:
        return _with_expansion(_empty_tariff_lookup())

    n = len(candidates)

    # 부모 컨텍스트 조회 (후보 행 직전의 부모 섹션 헤더들)
    ctx_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        def _get_parent_ctx(rowid: int, limit: int = 3) -> str:
            rows = ctx_conn.execute(
                "SELECT 한글품명 FROM tariff WHERE rowid < ? AND 한글품명 IS NOT NULL "
                "AND (기본세율 IS NULL OR 기본세율 = '') "
                "ORDER BY rowid DESC LIMIT ?",
                (rowid, limit),
            ).fetchall()
            parts = [r[0].strip() for r in reversed(rows) if r[0] and r[0].strip()]
            # 너무 길면 뒤에서 2개만
            if parts:
                return " > ".join(parts[-2:])
            return ""
    except Exception:
        def _get_parent_ctx(rowid: int, limit: int = 3) -> str:  # type: ignore
            return ""

    lines = []
    for i, row in enumerate(candidates, 1):
        rid, 순번, 품명, 기본, 잠정, wto, rcep = row[:7]
        ctx = _get_parent_ctx(rid)
        ctx_note = f"\n   분류: {ctx}" if ctx else ""
        lines.append(
            f"{i}. [{순번}] {품명} | 기본:{기본} | 잠정:{잠정} | WTO:{wto} | RCEP:{rcep}{ctx_note}"
        )
    ctx_conn.close()
    candidates_text = "\n".join(lines)

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
