// Stealth injection — ports techniques from coupang_collector.py & naver_collector.py
// Applied via BrowserContext.addInitScript so it runs on every page before any JS
import { BrowserContext, Page } from "playwright";
import path from "path";
import fs from "fs";
import os from "os";

// ─── Per-domain persistent profile directories ────────────────────────────────

const PROFILES_DIR = path.resolve(__dirname, "../../.profiles");

export function getProfileDir(domain: string): string {
  const dir = path.join(PROFILES_DIR, domain.replace(/[^a-z0-9.-]/gi, "_"));
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// ─── CDP stealth init script (runs before page JS) ───────────────────────────

const STEALTH_SCRIPT = `
(function () {
  // 1. Hide webdriver flag
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

  // 2. Add chrome object (missing in headless)
  if (!window.chrome) {
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
  }

  // 3. Fix navigator.plugins (headless has 0 plugins)
  if (!navigator.plugins || navigator.plugins.length === 0) {
    const fakePlugin = { description: '', filename: 'internal-pdf-viewer', length: 1, name: 'Chrome PDF Plugin' };
    Object.defineProperty(navigator, 'plugins', { get: () => [fakePlugin, fakePlugin, fakePlugin] });
  }

  // 4. Languages
  Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });

  // 5. WebGL vendor (from coupang_collector.py _apply_stealth_techniques)
  try {
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
      if (p === 37445) return 'Intel Inc.';
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return getParam.call(this, p);
    };
  } catch(e) {}

  // 6. Permissions — avoid navigator.permissions.query throwing for 'notifications'
  try {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) =>
      params.name === 'notifications'
        ? Promise.resolve({ state: 'denied', onchange: null })
        : origQuery(params);
  } catch(e) {}

  // 7. Fix hairline feature detect used by some anti-bot scripts
  const orig = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    if (type === 'image/png') return orig.apply(this, arguments);
    return orig.apply(this, arguments);
  };
})();
`;

// ─── Apply stealth to a context (call after creating context) ─────────────────

export async function applyStealthToContext(context: BrowserContext): Promise<void> {
  await context.addInitScript(STEALTH_SCRIPT);
}

// ─── Set request headers that make requests look like real browser traffic ────

export function getStealthHeaders(refererDomain?: string): Record<string, string> {
  return {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": refererDomain ? "cross-site" : "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    ...(refererDomain ? { "Referer": `https://www.google.com/search?q=${refererDomain}` } : {}),
  };
}

// ─── Navigate like a human (mirrors naver_collector _load_page) ──────────────
// Uses window.location.href instead of CDP navigation — harder to fingerprint

export async function stealthNavigate(page: Page, url: string, timeout = 30_000): Promise<void> {
  const currentUrl = page.url();

  if (!currentUrl || currentUrl === "about:blank") {
    // First navigation must use goto
    await page.goto(url, { waitUntil: "domcontentloaded", timeout });
  } else {
    // Subsequent navigations: use JS (avoids CDP-level navigation detection)
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded", timeout }).catch(() => {}),
      page.evaluate((u) => { window.location.href = u; }, url),
    ]);
  }

  // Wait for real content (not just DOM) — mirrors naver_collector logic
  await page.waitForFunction(
    () => document.body && (document.body.innerText.length > 500 || document.title.length > 0),
    { timeout: 15_000 }
  ).catch(() => {}); // timeout OK — we'll detect empty page downstream
}

// ─── Detect bot-blocked page ─────────────────────────────────────────────────

export async function isBotBlocked(page: Page): Promise<boolean> {
  const html = await page.content();
  const title = await page.title();
  const url = page.url();

  if (html.length < 3_000) return true; // suspiciously small

  const blockedSignals = [
    "access denied", "access-denied",
    "robot check", "captcha",
    "비정상적인 접근", "자동화된 요청",
    "보안 확인", "bot detection",
    "cf-browser-verification", // Cloudflare
    "challenge-platform",
  ];

  const haystack = (html.slice(0, 20_000) + title + url).toLowerCase();
  return blockedSignals.some((s) => haystack.includes(s));
}
