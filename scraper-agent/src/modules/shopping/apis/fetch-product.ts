// fetch-product — use saved template to fetch product data
// Falls back to full page navigation when template variables can't be resolved
import { BrowserContext, Page } from "playwright";
import { SiteRecipe, ProductData, parseProductFromResponse } from "../ai/claude";
import { NetworkRecorder } from "../../../core/network";
import { stealthNavigate, getStealthHeaders } from "../../../core/stealth";
import { collectHTML } from "../../../core/local-collector";
import fs from "fs";
import path from "path";

const TEMPLATES_DIR = path.resolve(__dirname, "../../templates");

export function loadTemplate(domain: string): SiteRecipe | null {
  const p = path.join(TEMPLATES_DIR, `${domain}.json`);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf-8")) as SiteRecipe;
  } catch {
    return null;
  }
}

function extractId(pageUrl: string, recipe: SiteRecipe): string | null {
  if (!recipe.api?.id_extraction) return null;
  const { pattern, group = 1 } = recipe.api.id_extraction;
  try {
    const match = pageUrl.match(new RegExp(pattern));
    return match?.[group] ?? null;
  } catch {
    return null;
  }
}

function buildApiUrl(recipe: SiteRecipe, productId: string): string {
  return recipe.api!.url_pattern.replace(/\{product_id\}/g, productId);
}

function hasUnfilledVars(url: string): boolean {
  return /\{[^}]+\}/.test(url);
}

// ─── Page-based extraction (navigate → capture HTML + network → Claude) ────────

async function extractViaPage(
  url: string,
  recipe: SiteRecipe,
  page: Page | null
): Promise<ProductData> {
  const domain = new URL(url).hostname.replace(/^www\./, "");

  // ── 1순위: dk local server ──
  const localResult = await collectHTML(url);
  if (localResult) {
    console.info(`  ✓ 로컬 서버(포트 ${localResult.source_port}) HTML: ${Math.round(localResult.html.length / 1024)}KB`);
    return parseProductFromResponse({ url, responseBody: localResult.html.slice(0, 20_000), recipe });
  }

  // ── 2순위: Playwright ──
  if (!page) throw new Error("Playwright 브라우저가 초기화되지 않았습니다 (로컬 서버도 없음).");
  console.info(`  → Playwright로 페이지 탐색`);
  const tmpDir = path.join(TEMPLATES_DIR, `.tmp_fetch_${domain}_${Date.now()}`);
  const recorder = new NetworkRecorder(tmpDir);
  recorder.attach(page);

  await page.setExtraHTTPHeaders(getStealthHeaders(domain));
  await stealthNavigate(page, url);
  await page.waitForTimeout(2_000);
  await page.evaluate(() => window.scrollTo(0, Math.floor(document.body.scrollHeight * 0.5)));
  await page.waitForTimeout(800);
  await page.evaluate(() => window.scrollTo(0, 0));

  const html = await page.content();
  const networkEntries = recorder.getApiEntries();
  try { fs.rmSync(tmpDir, { recursive: true }); } catch {}

  const apiData = networkEntries.slice(0, 10)
    .map((e) => `/* ${e.url} */\n${e.responseBody}`).filter(Boolean).join("\n\n---\n\n");
  const responseBody = apiData
    ? `API RESPONSES:\n${apiData.slice(0, 8_000)}\n\nHTML:\n${html.slice(0, 8_000)}`
    : html.slice(0, 15_000);

  console.info(`  → 파싱: API ${networkEntries.length}개 | HTML ${Math.round(html.length / 1024)}KB`);
  return parseProductFromResponse({ url, responseBody, recipe });
}

// ─── Handler ─────────────────────────────────────────────────────────────────

export default async function handler(
  params: Record<string, unknown>,
  page: Page | null,
  _context: BrowserContext | null
): Promise<ProductData> {
  const url = params.url as string;
  const recipe = params.recipe as SiteRecipe;

  // ── Try API strategy first ──
  if (recipe.strategy !== "dom" && recipe.api) {
    const productId = extractId(url, recipe);

    if (productId) {
      const apiUrl = buildApiUrl(recipe, productId);

      if (hasUnfilledVars(apiUrl)) {
        console.info(`  → 보조 ID 필요 (${apiUrl}) — 페이지 탐색으로 전환`);
        return extractViaPage(url, recipe, page);
      }

      console.info(`  → API 호출: ${apiUrl}`);
      try {
        const headers: Record<string, string> = { "Accept": "application/json", ...(recipe.api.headers ?? {}) };

        let responseBody: string;
        if (page) {
          // Playwright request (shares browser cookies)
          const res = await page.request.get(apiUrl, { headers, timeout: 15_000 });
          if (!res.ok()) {
            console.warn(`  ⚠ API ${res.status()} — 페이지 탐색으로 전환`);
            return extractViaPage(url, recipe, page);
          }
          responseBody = await res.text();
        } else {
          // Plain fetch (no browser cookies)
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 15_000);
          try {
            const res = await fetch(apiUrl, { headers, signal: controller.signal });
            if (!res.ok) {
              console.warn(`  ⚠ API ${res.status} — 페이지 탐색으로 전환`);
              return extractViaPage(url, recipe, null);
            }
            responseBody = await res.text();
          } finally {
            clearTimeout(timer);
          }
        }

        console.info(`  → 응답: ${Math.round(responseBody.length / 1024)}KB → Claude 파싱`);
        return parseProductFromResponse({ url, responseBody, recipe });
      } catch (e) {
        console.warn(`  ⚠ API 호출 실패 (${e instanceof Error ? e.message : e}) — 페이지 탐색으로 전환`);
      }
    }
  }

  // ── Fallback: navigate the page ──
  console.info(`  → 페이지 직접 탐색`);
  return extractViaPage(url, recipe, page);
}
