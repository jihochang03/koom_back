import { Browser, BrowserContext, Page, chromium } from "playwright";
import type { AgentTool } from "../../core/agent-core";

let browser: Browser | null = null;
let context: BrowserContext | null = null;
let page: Page | null = null;
let launching = false;

function _resetBrowser() {
  browser = null;
  context = null;
  page = null;
}

async function getPage(): Promise<Page> {
  // 이미 살아있는 페이지 반환
  if (browser && page) {
    try { await page.evaluate('1'); return page; } catch { _resetBrowser(); }
  }

  // 동시 launch 방지 — 다른 caller가 launch 중이면 완료까지 대기
  if (launching) {
    await new Promise<void>(resolve => {
      const id = setInterval(() => { if (!launching) { clearInterval(id); resolve(); } }, 100);
    });
    if (browser && page) return page;
  }

  launching = true;
  try {
    browser = await chromium.launch({
      headless: false,
      args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    });
    browser.on('disconnected', _resetBrowser);
    context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      viewport: { width: 1280, height: 800 },
    });
    page = await context.newPage();
    page.on('crash', _resetBrowser);
  } finally {
    launching = false;
  }
  return page!;
}

export async function closeBrowser(): Promise<void> {
  const b = browser;
  _resetBrowser();
  if (b) {
    try { await b.close(); } catch { /* already closed */ }
  }
}

/** Returns the currently active page (launches browser if not started). */
export async function getActivePage(): Promise<Page> {
  return getPage();
}

export const navigateBrowserTool: AgentTool = {
  name: "navigate_browser",
  description: "Open the browser and navigate to a URL to inspect the live page.",
  input_schema: {
    type: "object" as const,
    properties: { url: { type: "string" } },
    required: ["url"],
  },
  execute: async ({ url }: Record<string, unknown>): Promise<string> => {
    const p = await getPage();
    await p.goto(url as string, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await p.waitForTimeout(1_000);
    return `[navigate_browser] ${url}\nTitle: "${await p.title()}"`;
  },
};

export const takeScreenshotTool: AgentTool = {
  name: "take_screenshot",
  description: "Take a screenshot of the current browser page so you can see its layout.",
  input_schema: { type: "object" as const, properties: {} },
  execute: async (_: Record<string, unknown>) => {
    const p = await getPage();
    const buf = await p.screenshot({ type: "png", fullPage: false });
    return { __screenshot: true as const, base64: buf.toString("base64"), url: p.url() };
  },
};

export const getPageHtmlTool: AgentTool = {
  name: "get_page_html",
  description: "Get the current page HTML, optionally scoped to a CSS selector.",
  input_schema: {
    type: "object" as const,
    properties: { selector: { type: "string" } },
  },
  execute: async ({ selector }: Record<string, unknown>): Promise<string> => {
    const p = await getPage();
    let html = selector
      ? (await (await p.$(selector as string))?.innerHTML()) ?? `[not found: ${selector}]`
      : await p.content();
    if (html.length > 15_000) html = html.slice(0, 15_000) + "\n... (truncated)";
    return html;
  },
};

export const grepHtmlTool: AgentTool = {
  name: "grep_html",
  description: "Search the current page HTML for a pattern and return matching lines with context.",
  input_schema: {
    type: "object" as const,
    properties: {
      pattern: { type: "string" },
      context_lines: { type: "number" },
    },
    required: ["pattern"],
  },
  execute: async ({ pattern, context_lines = 3 }: Record<string, unknown>): Promise<string> => {
    const p = await getPage();
    const lines = (await p.content()).split("\n");
    const regex = new RegExp(pattern as string, "gi");
    const ctx = context_lines as number;
    const matches: string[] = [];
    const seen = new Set<number>();

    lines.forEach((line, i) => {
      if (regex.test(line)) {
        for (let j = Math.max(0, i - ctx); j <= Math.min(lines.length - 1, i + ctx); j++) {
          if (!seen.has(j)) { matches.push(`${j + 1}: ${lines[j]}`); seen.add(j); }
        }
        matches.push("---");
      }
    });

    if (matches.length === 0) return `[grep_html] No matches: ${pattern}`;
    const out = matches.join("\n");
    return out.length > 8_000 ? out.slice(0, 8_000) + "\n... (truncated)" : out;
  },
};

export const allBrowserTools: AgentTool[] = [
  navigateBrowserTool,
  takeScreenshotTool,
  getPageHtmlTool,
  grepHtmlTool,
];
