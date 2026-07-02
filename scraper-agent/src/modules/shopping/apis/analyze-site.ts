// analyze-site — template-first, then Claude fallback
import { BrowserContext, Page } from "playwright";
import { NetworkRecorder } from "../../../core/network";
import { narrateAndExtract, extractSizeInfo, ProductData, SizeInfo } from "../ai/claude";
import { stealthNavigate, isBotBlocked, getStealthHeaders } from "../../../core/stealth";
import { collectHTML } from "../../../core/local-collector";
import { findTemplate, runTemplate, runTemplateCode, mapToProductData } from "../../../core/template-runner";
import { isShoppingCategory } from "../../../categories";
import path from "path";
import fs from "fs";

const TMP_BASE = path.resolve(__dirname, "../../../../templates");

// ── 자가치유(self-healing) ──────────────────────────────────────────────────
// 템플릿이 실행됐으나 결과가 불충분(사이트 리뉴얼 등)하면, 백그라운드로 빌더 에이전트를
// 호출해 템플릿을 증분 재빌드한다. 유료(Claude) 동작이므로 기본 OFF + 도메인별 쿨다운.
//   활성화: SELF_HEAL=1   쿨다운: SELF_HEAL_COOLDOWN_MS (기본 6시간)
const _healCooldown = new Map<string, number>();
function maybeSelfHeal(
  domain: string, url: string, category: string | null, log: (m: string) => void
): void {
  if (process.env.SELF_HEAL !== "1") return;
  const now = Date.now();
  const cooldownMs = Number(process.env.SELF_HEAL_COOLDOWN_MS ?? 6 * 3600 * 1000);
  if (now - (_healCooldown.get(domain) ?? 0) < cooldownMs) return;
  _healCooldown.set(domain, now);
  log(`↻ 자가치유 트리거: ${domain} 템플릿 불충분 → 백그라운드 재빌드`);
  // fire-and-forget (응답을 막지 않음). 동적 import로 순환참조 회피.
  import("../../../agent/template-builder-agent")
    .then(({ runTemplateBuilder }) =>
      runTemplateBuilder(`heal-${now}`, [{ role: "user", content: url }], {}, category, "detail")
    )
    .then(() => log(`✓ 자가치유 완료: ${domain}`))
    .catch((e) => log(`⚠ 자가치유 실패(${domain}): ${e instanceof Error ? e.message : e}`));
}

const OPTION_TRIGGER_SELECTORS = [
  '[class*="option"]', '[class*="variant"]', '[class*="color"]',
  '[class*="size"]',   '[class*="package"]', '[class*="plan"]',
  '[class*="tab"]',    '[role="tab"]',        'select',
  '[class*="choice"]', '[class*="grade"]',
];

// ─── Capture via Playwright (fallback) ───────────────────────────────────────

async function captureViaPlaywright(
  url: string,
  page: Page,
  tmpDir: string
): Promise<{ html: string; networkEntries: ReturnType<NetworkRecorder["getApiEntries"]> }> {
  const recorder = new NetworkRecorder(tmpDir);
  recorder.attach(page);

  await page.setExtraHTTPHeaders(getStealthHeaders(new URL(url).hostname));
  await stealthNavigate(page, url);

  if (await isBotBlocked(page)) {
    console.warn(`  ⚠  봇 차단 감지 — 헤더 초기화 후 재시도`);
    await page.setExtraHTTPHeaders({});
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(3_000);
  }

  await page.waitForTimeout(2_000);
  await page.evaluate(() => window.scrollTo(0, Math.floor(document.body.scrollHeight * 0.4)));
  await page.waitForTimeout(500);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(800);
  await page.evaluate(() => window.scrollTo(0, 0));

  // 쇼핑 페이지: 옵션 클릭 트리거
  for (const sel of OPTION_TRIGGER_SELECTORS) {
    try {
      for (const el of (await page.$$(sel)).slice(0, 3)) {
        try { await el.scrollIntoViewIfNeeded(); await el.click({ timeout: 800 }); await page.waitForTimeout(250); } catch {}
      }
    } catch {}
  }
  await page.waitForTimeout(1_000);

  const html = await page.content();
  const networkEntries = recorder.getApiEntries();
  try { fs.rmSync(tmpDir, { recursive: true }); } catch {}

  return { html, networkEntries };
}

// ─── Handler ─────────────────────────────────────────────────────────────────

export default async function handler(
  params: Record<string, unknown>,
  page: Page | null,
  _context: BrowserContext | null,
  callbacks?: { onStatus?: (msg: string) => void; onText?: (chunk: string) => void }
): Promise<Record<string, unknown> | ProductData> {
  const url = params.url as string;
  const category = (params.category as string | undefined) ?? null;
  const domain = new URL(url).hostname.replace(/^www\./, "");
  const log = (msg: string) => { console.info(msg); callbacks?.onStatus?.(msg); };

  // 템플릿 결과가 유효한지 판단 (제목 또는 가격 중 하나는 있어야 함)
  function isValidRaw(raw: Record<string, unknown>): boolean {
    if (Array.isArray(raw.items) && raw.items.length > 0) return true;
    const hasTitle = typeof raw.title === "string" && raw.title.trim().length > 0;
    const hasPrice = raw.price_original != null || raw.price_discounted != null;
    return hasTitle || hasPrice;
  }

  // ── 0순위: 호출자(고객사 Django)가 전달한 템플릿 코드 ─────────────────────
  const providedCode = params.template as string | undefined;
  if (providedCode) {
    const name = (params.templateName as string | undefined) ?? domain;
    const raw = await runTemplateCode(providedCode, name, url, log);
    if (raw && isValidRaw(raw)) {
      if (Array.isArray(raw.items)) return raw;
      return isShoppingCategory(category) ? mapToProductData(raw) : raw;
    }
    if (raw) log(`⚠  전달된 템플릿 결과 불충분 (제목·가격 없음) — Claude 분석으로 fallback`);
    else log(`⚠  전달된 템플릿 실행 실패 — Claude 분석으로 fallback`);
    maybeSelfHeal(domain, url, category, log);
  }

  // ── 1순위: 우리 서버 로컬 캐시 (직접 사용 시 폴백) ──────────────────────
  const templatePath = findTemplate(domain);
  if (templatePath) {
    const raw = await runTemplate(templatePath, url, log);
    if (raw && isValidRaw(raw)) {
      if (Array.isArray(raw.items)) return raw;
      return isShoppingCategory(category) ? mapToProductData(raw) : raw;
    }
    if (raw) log(`⚠  템플릿 결과 불충분 (제목·가격 없음) — Claude 분석으로 fallback`);
    else log(`⚠  템플릿 실행 실패 — Claude 분석으로 fallback`);
    maybeSelfHeal(domain, url, category, log);
  }

  let html: string;
  let networkEntries: ReturnType<NetworkRecorder["getApiEntries"]> = [];
  let networkLog: Array<{ url: string; body: string; ct?: string }> = [];

  // ── 1순위: 로컬 수집 서버 ──────────────────────────────────────────────────
  log(`→ 페이지 수집 중... (${domain})`);
  log(`  Chrome이 페이지를 방문합니다. 봇 감지 우회로 30초~2분 소요될 수 있습니다.`);
  const localResult = await collectHTML(url);

  if (localResult) {
    const netCount = localResult.network_log.length;
    const optCount = localResult.product_info?.product_options?.length ?? 0;
    log(`✓ HTML ${Math.round(localResult.html.length / 1024)}KB 수집 완료${netCount > 0 ? ` | fetch/XHR ${netCount}개 캡처` : ""}${optCount > 0 ? ` | HTML파서 옵션 ${optCount}그룹 선추출` : ""}`);
    html = localResult.html;
    networkLog = localResult.network_log;
  } else {
    // ── 2순위: Playwright ──────────────────────────────────────────────────
    log(`⚠  로컬 서버 없음 — Playwright로 시도`);
    if (!page) throw new Error(
      "Python 수집 서버가 응답하지 않습니다. 서버가 아직 시작 중이면 잠시 후 다시 시도하세요. (python collector/server.py)"
    );
    const tmpDir = path.join(TMP_BASE, `.tmp_${domain}_${Date.now()}`);
    const pw = await captureViaPlaywright(url, page, tmpDir);
    html = pw.html;
    networkEntries = pw.networkEntries;

    if (html.length < 3_000) {
      throw new Error(`페이지 수집 실패 (${html.length}B) — 봇 차단으로 보입니다.`);
    }
  }

  log(`→ Claude가 페이지를 읽고 있어요... (카테고리: ${category ?? "shopping"})`);
  const result = await narrateAndExtract({
    url, html, networkEntries, networkLog,
    productInfo: localResult?.product_info as Record<string, unknown> | undefined,
    onText: callbacks?.onText,
    category,
  }) as unknown as ProductData;

  // 국제배송 크기/무게가 없으면 상세 이미지 OCR 폴백
  const sz = result.size;
  const sizeEmpty = !sz || (sz.weight_g == null && sz.width_cm == null && sz.length_cm == null && sz.height_cm == null);
  if (sizeEmpty) {
    log(`→ 크기 정보 없음 — 상세 이미지 OCR 시도`);
    const extracted: SizeInfo = await extractSizeInfo({
      html,
      specifications: result.specifications ?? null,
      productUrl: url,
    });
    if (extracted.source !== "none") {
      result.size = extracted;
      log(`✓ 크기 추출 완료 (source: ${extracted.source}, confidence: ${extracted.confidence})`);
    }
  }

  return result;
}
