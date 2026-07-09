import Anthropic from "@anthropic-ai/sdk";
import crypto from "crypto";
import { findTemplate, runTemplate, mapToProductData } from "../../../core/template-runner";
import { runTemplateBuilder } from "../../../agent/template-builder-agent";
import { productStore } from "../../../products/product-store";

const COLLECTOR_URL = process.env.COLLECTOR_URL ?? "http://localhost:18080";

let _claude: Anthropic | null = null;
const claude = () => (_claude ??= new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY }));

async function collectPage(url: string): Promise<{ html: string; networkLog?: unknown[] } | null> {
  try {
    const resp = await fetch(`${COLLECTOR_URL}/collect/general`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!resp.ok) return null;
    const data = await resp.json() as { success?: boolean; html?: string; network_log?: unknown[] };
    if (!data.success || !data.html) return null;
    return { html: data.html, networkLog: data.network_log };
  } catch {
    return null;
  }
}

// CSS/JS/이미지 등 명백히 상품이 아닌 URL 제거
const SKIP_EXT_RE = /\.(js|css|png|jpg|jpeg|gif|webp|ico|svg|woff2?|ttf|eot|mp4|mp3|json)(\?|$)/i;
const SKIP_PATH_RE = /^\/(?:assets|static|cdn|fonts|images?|img|favicon)\//i;
// 상품 상세 URL 패턴
const PRODUCT_PATH_RE = /\/(?:goods|item|product|detail|vp\/products?|store\/[^/?#]+)\/\d{4,}/i;
const PRODUCT_QS_RE = /[?&](?:goodsNo|goodsCd|itemId|itemNo|prdNo|productNo|goodsCode|product_id)=(\d{4,}|[A-Z]{2}\d{8,})/i;

function isProductUrl(urlStr: string): boolean {
  try {
    const u = new URL(urlStr);
    return PRODUCT_PATH_RE.test(u.pathname) || PRODUCT_QS_RE.test(u.search);
  } catch { return false; }
}

function isAssetUrl(urlStr: string): boolean {
  try {
    const u = new URL(urlStr);
    return SKIP_EXT_RE.test(u.pathname) || SKIP_PATH_RE.test(u.pathname) || u.pathname === '/' || u.pathname === '';
  } catch { return false; }
}

async function extractProductUrls(html: string, baseUrl: string, networkLog?: unknown[]): Promise<string[]> {
  const base = new URL(baseUrl);
  const baseDomain = base.hostname.split('.').slice(-2).join('.');
  const seen = new Set<string>();

  function addUrl(raw: string) {
    try {
      const abs = new URL(raw, base.origin).href;
      const u = new URL(abs);
      // 동일 도메인 + 서브도메인 허용
      if (u.hostname === base.hostname || u.hostname.endsWith('.' + baseDomain)) {
        seen.add(abs);
      }
    } catch { /* skip */ }
  }

  // 1) href 속성
  const hrefRe = /href\s*=\s*["']([^"'\s]+)["']/g;
  let m: RegExpExecArray | null;
  while ((m = hrefRe.exec(html)) !== null) addUrl(m[1]);

  // 2) data-href / data-url / data-path / data-link 속성
  const dataRe = /data-(?:href|url|path|link)\s*=\s*["']([^"'\s]+)["']/g;
  while ((m = dataRe.exec(html)) !== null) addUrl(m[1]);

  // 3) gate/redirect URL의 target 파라미터 → 실제 경로 추출
  const targetRe = /[?&]target=([^&"'\s>]+)/g;
  while ((m = targetRe.exec(html)) !== null) {
    try { addUrl(decodeURIComponent(m[1])); } catch { addUrl(m[1]); }
  }

  // 4) 스크립트 태그 안 경로 패턴
  const scriptBlocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(s => s[1]).join(" ");
  const pathRe = /["'`](\/(?:goods|item|product|detail|vp\/products|store\/[^/?#"'`]+)\/\d{4,}[^"'`\s?#]{0,80})["'`]/g;
  while ((m = pathRe.exec(scriptBlocks)) !== null) addUrl(m[1]);

  // 5) network_log에서 상품 ID 추출 → URL 구성
  if (networkLog && networkLog.length > 0) {
    for (const entry of networkLog) {
      const e = entry as { url?: string; responseBody?: string };
      if (!e.responseBody) continue;
      try {
        const json = JSON.parse(e.responseBody);
        // 배열이거나 data/list/items 같은 키 안의 배열 탐색
        const items: unknown[] = Array.isArray(json)
          ? json
          : (json?.data?.list ?? json?.data?.items ?? json?.result?.list ?? json?.list ?? json?.items ?? []);
        if (!Array.isArray(items)) continue;
        for (const item of items.slice(0, 200)) {
          const it = item as Record<string, unknown>;
          // 상품 ID 필드 이름들
          const idFields = ['goodsCd', 'goodsNo', 'itemId', 'productNo', 'prdNo', 'goodsCode', 'goodsId'];
          for (const field of idFields) {
            const val = it[field];
            if (val && String(val).length >= 4) {
              // goodsCd는 보통 GD000000XXXXXXXX 형식
              const id = String(val);
              // 상품 상세 URL 후보 구성
              if (/^\d{4,}$/.test(id)) {
                addUrl(`/goods/goodsDetail?goodsCd=${id}`);
              } else if (/^[A-Z]{2}\d{8,}$/.test(id)) {
                addUrl(`/goods/goodsDetail?goodsCd=${id}`);
              }
            }
          }
          // URL 필드 직접 포함된 경우
          const urlFields = ['goodsUrl', 'itemUrl', 'productUrl', 'detailUrl', 'linkUrl'];
          for (const field of urlFields) {
            const val = it[field];
            if (typeof val === 'string' && val.startsWith('/')) addUrl(val);
          }
        }
      } catch { /* JSON parse 실패는 무시 */ }
    }
  }

  // 6) 명백한 product URL 즉시 반환 (Claude 불필요)
  const obvious = [...seen].filter(isProductUrl);
  if (obvious.length > 0) {
    console.log(`[crawl-list] 명확한 상품 URL ${obvious.length}개 발견 (Claude 없이)`);
    return obvious;
  }

  // gate URL에서 target이 product 패턴인 경우도 반환
  const gateProducts: string[] = [];
  for (const urlStr of seen) {
    try {
      const u = new URL(urlStr);
      const target = u.searchParams.get('target') ?? '';
      if (target && (PRODUCT_PATH_RE.test(target) || /\/\d{6,}$/.test(target))) {
        gateProducts.push(new URL(target, base.origin).href);
      }
    } catch { /* skip */ }
  }
  if (gateProducts.length > 0) {
    console.log(`[crawl-list] gate target에서 상품 URL ${gateProducts.length}개 추출`);
    return [...new Set(gateProducts)];
  }

  // 7) assets 제거 후 Claude에 넘기기
  const candidates = [...seen].filter(u => !isAssetUrl(u)).slice(0, 300);
  if (candidates.length === 0) return [];

  console.log(`[crawl-list] Claude에 ${candidates.length}개 URL 분류 요청`);
  const resp = await claude().messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 4096,
    messages: [{
      role: "user",
      content: `다음 URL 목록에서 상품 상세 페이지 URL만 골라 JSON 배열로 반환하세요.

상품 상세 페이지 판단 기준:
- 단일 상품을 보여주는 URL: /goods/숫자, /item/숫자, /products/숫자, /vp/products/xxx, /store/브랜드/숫자 등
- 게이트/리다이렉트 URL: 경로가 /gate 이고 target 파라미터 끝이 숫자(ID)면 상품 URL
- 파라미터에 상품 ID가 있는 경우 (예: ?goodsNo=123, ?goodsCd=GD123)도 포함

제외: 홈(/), 카테고리 목록(/category, /list), 검색, 마이페이지, 장바구니, 로그인, 리뷰, 공지

사이트: ${base.hostname}
URL 목록:
${candidates.join("\n")}

JSON 배열만 반환 (설명 없이):`,
    }],
  });

  const text = resp.content[0].type === "text" ? resp.content[0].text : "[]";
  const match = text.match(/\[[\s\S]*\]/);
  if (!match) return [];
  try {
    return (JSON.parse(match[0]) as string[]).filter(u => {
      try { new URL(u); return true; } catch { return false; }
    });
  } catch { return []; }
}

export async function crawlList(
  listUrl: string,
  category: string,
  onEvent: (event: string, data: unknown) => void
): Promise<void> {
  const domain = new URL(listUrl).hostname.replace(/^www\./, "");
  const emit = (event: string, data: unknown) => onEvent(event, data);

  // ─ Step 1: Collect listing page ───────────────────────────────────────────
  emit("status", { message: "목록 페이지 수집 중..." });
  const page = await collectPage(listUrl);
  if (!page) throw new Error("목록 페이지 수집 실패 — 수집 서버를 확인하세요");

  // ─ Step 2: Extract product URLs ───────────────────────────────────────────
  emit("status", { message: "상품 상세 URL 추출 중..." });
  const productUrls = await extractProductUrls(page.html, listUrl, page.networkLog);
  if (productUrls.length === 0) throw new Error("상품 URL을 찾지 못했습니다 — 수동으로 확인하세요");

  emit("urls_found", { urls: productUrls, count: productUrls.length });
  emit("status", { message: `→ ${productUrls.length}개 상품 URL 발견` });

  // ─ Step 3: Find or build template ─────────────────────────────────────────
  let templatePath = findTemplate(domain);
  if (templatePath) {
    emit("status", { message: `→ 기존 템플릿 사용: ${domain}` });
    emit("template_done", { domain, reused: true });
  } else {
    emit("status", { message: "템플릿 없음 — 샘플 2개로 빌드 시작..." });
    const samples = productUrls.slice(0, 2);

    for (let i = 0; i < samples.length; i++) {
      emit("status", { message: `→ 샘플 [${i + 1}/${samples.length}] 빌드 중: ${samples[i].slice(0, 60)}` });
      try {
        await runTemplateBuilder(
          crypto.randomUUID(),
          [{ role: "user" as const, content: samples[i] }],
          {
            onStatus: (msg: string) => emit("status", { message: `  ${msg}` }),
            onText: () => {},
            onToolCall: () => {},
            onToolResult: () => {},
            onCode: () => {},
            onExtraction: () => {},
          },
          category,
          "detail"
        );
        templatePath = findTemplate(domain);
        if (templatePath) break;
      } catch (err) {
        emit("status", { message: `  ⚠ 빌드 오류: ${String(err).slice(0, 100)}` });
      }
    }

    if (templatePath) {
      emit("template_done", { domain, reused: false });
      emit("status", { message: `✓ 템플릿 저장 완료: ${domain}` });
    } else {
      throw new Error("템플릿 생성 실패 — Agent 탭에서 직접 빌드하세요");
    }
  }

  // ─ Step 4: Run template on all product URLs ────────────────────────────────
  const total = productUrls.length;
  let done = 0;

  for (const productUrl of productUrls) {
    emit("status", { message: `→ [${done + 1}/${total}] ${productUrl.slice(0, 70)}` });
    try {
      const raw = await runTemplate(templatePath!, productUrl);
      if (raw) {
        const data = mapToProductData(raw);
        const saved = productStore.upsert(productUrl, domain, data, listUrl);
        emit("product", saved);
      } else {
        emit("status", { message: `  ⚠ 결과 없음: ${productUrl.slice(0, 50)}` });
      }
    } catch (err) {
      emit("status", { message: `  ⚠ 실패: ${String(err).slice(0, 100)}` });
    }
    done++;
    emit("progress", { done, total });
  }
}
