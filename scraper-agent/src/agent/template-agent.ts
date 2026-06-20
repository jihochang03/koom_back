/**
 * Template Agent
 * 처음 보는 사이트 URL을 받아 Claude가 페이지를 분석한 뒤
 * templates/<domain>.json 파일을 생성한다.
 *
 * Python 템플릿 실행기(template_scraper.py)가 이 JSON을 읽어
 * Playwright로 실제 스크랩을 수행한다.
 */
import Anthropic from "@anthropic-ai/sdk";
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { NetworkRecorder } from "../core/network";

let _client: Anthropic | null = null;
const client = () => {
  if (!_client) _client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return _client;
};

const TEMPLATES_DIR = path.resolve(__dirname, "../../templates");

// ─── JSON 템플릿 스키마 ──────────────────────────────────────────────────────

export interface FieldDef {
  selector?: string;    // CSS selector
  attr?: string;        // "innerText" | "src" | "href" | attribute name
  parse?: "number" | "text";
  value?: string;       // static value (e.g. currency: "JPY")
  absolute?: boolean;   // relative URL → absolute
}

export interface SiteTemplate {
  domain: string;
  source_url: string;
  created_at: string;
  product_container: string;
  fields: Record<string, FieldDef>;
  pagination: {
    selector: string | null;
    type: "link" | "click";
  };
  wait_for?: string;
  scroll_to_bottom?: boolean;
  extraction_strategy: "dom" | "api";
  api_endpoint?: string | null;
  notes: string;
}

// ─── System prompt ────────────────────────────────────────────────────────────

const SYSTEM = `You are an expert web scraping analyst.
Given a webpage screenshot and its HTML, generate a JSON template that describes
how to extract product data from this page.

Return ONLY valid JSON matching this exact structure (no markdown fences, no explanation):
{
  "product_container": "CSS selector for each product card/row",
  "fields": {
    "title":            { "selector": "...", "attr": "innerText" },
    "price_original":   { "selector": "...", "attr": "innerText", "parse": "number" },
    "price_discounted": { "selector": "...", "attr": "innerText", "parse": "number" },
    "currency":         { "value": "KRW" },
    "image":            { "selector": "img", "attr": "src", "absolute": true },
    "url":              { "selector": "a", "attr": "href", "absolute": true },
    "availability":     { "selector": "...", "attr": "innerText" }
  },
  "pagination": {
    "selector": "CSS selector for next-page button or null",
    "type": "link"
  },
  "wait_for": "CSS selector to wait for before extracting (or null)",
  "scroll_to_bottom": false,
  "extraction_strategy": "dom",
  "api_endpoint": null,
  "notes": "brief description of the site structure"
}

Rules:
- product_container must select INDIVIDUAL product cards (not the whole grid)
- If no next-page button exists, set pagination.selector to null
- If network API data is provided and it contains product arrays, set extraction_strategy to "api" and api_endpoint to the URL
- currency: use "KRW" for Korean sites, "JPY" for Japanese, etc.
- For missing fields, omit them from fields rather than using null selectors`;

// ─── Main function ────────────────────────────────────────────────────────────

export async function generateTemplate(url: string): Promise<SiteTemplate> {
  const domain = new URL(url).hostname.replace(/^www\./, "");
  const outputPath = path.join(TEMPLATES_DIR, `${domain}.json`);

  console.info(`[template-agent] Analyzing: ${url}`);
  console.info(`[template-agent] Domain: ${domain}`);

  // ── Launch browser + record network ──
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
  });
  const context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    viewport: { width: 1280, height: 800 },
  });
  const page = await context.newPage();

  const tmpNetworkDir = path.join(TEMPLATES_DIR, `.tmp_${domain}`);
  const recorder = new NetworkRecorder(tmpNetworkDir);
  recorder.attach(page);

  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForTimeout(2_000); // let dynamic content settle

  // ── Capture page state ──
  const screenshotBuf = await page.screenshot({ type: "png", fullPage: false });
  const screenshotBase64 = screenshotBuf.toString("base64");
  const html = await page.content();
  await browser.close();

  // ── Collect API data from network ──
  const apiEntries = recorder.getApiEntries();
  const networkApiSample = apiEntries
    .slice(0, 4)
    .map((e) => `/* ${e.url} */\n${e.responseBody}`)
    .filter(Boolean)
    .join("\n\n---\n\n")
    .slice(0, 4_000);

  // Clean up temp network dir
  try { fs.rmSync(tmpNetworkDir, { recursive: true }); } catch {}

  // ── Ask Claude ──
  console.info("[template-agent] Asking Claude to analyze page structure...");

  const textParts = [
    `URL: ${url}\nDomain: ${domain}`,
    `\nHTML (first 10 000 chars):\n${html.slice(0, 10_000)}`,
    networkApiSample
      ? `\n\nNetwork API responses:\n${networkApiSample}`
      : "",
  ].join("");

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 2_000,
    system: SYSTEM,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image",
            source: { type: "base64", media_type: "image/png", data: screenshotBase64 },
          },
          { type: "text", text: textParts },
        ],
      },
    ],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "";
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    throw new Error(`Claude returned no JSON:\n${text}`);
  }

  const partial = JSON.parse(jsonMatch[0]);

  const template: SiteTemplate = {
    domain,
    source_url: url,
    created_at: new Date().toISOString(),
    product_container: partial.product_container ?? "",
    fields: partial.fields ?? {},
    pagination: partial.pagination ?? { selector: null, type: "link" },
    wait_for: partial.wait_for ?? undefined,
    scroll_to_bottom: partial.scroll_to_bottom ?? false,
    extraction_strategy: partial.extraction_strategy ?? "dom",
    api_endpoint: partial.api_endpoint ?? null,
    notes: partial.notes ?? "",
  };

  // ── Save ──
  fs.mkdirSync(TEMPLATES_DIR, { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(template, null, 2), "utf-8");
  console.info(`[template-agent] ✓ Template saved → ${outputPath}`);

  return template;
}
