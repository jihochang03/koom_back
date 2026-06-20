// market-agent — chatbot REPL with real Chrome + persistent profiles + stealth
import * as readline from "readline";
import { chromium, BrowserContext, Page } from "playwright";
import analyzeSiteHandler from "../apis/analyze-site";
import { applyStealthToContext, getProfileDir } from "../../../core/stealth";
import { startCollectorServer, stopCollectorServer, isServerAlive } from "../../../core/local-collector";
import path from "path";
import fs from "fs";

// ─── Find real Chrome executable ─────────────────────────────────────────────

function findRealChrome(): string | undefined {
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    process.env.CHROME_PATH,
  ].filter(Boolean) as string[];

  return candidates.find((p) => fs.existsSync(p));
}

// ─── Launch persistent context (per domain) ───────────────────────────────────

async function launchContext(domain: string): Promise<{ context: BrowserContext; page: Page }> {
  const profileDir = getProfileDir(domain);
  const chromePath = findRealChrome();

  const launchOptions: Parameters<typeof chromium.launchPersistentContext>[1] = {
    headless: false,
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-blink-features=AutomationControlled",
      "--disable-infobars",
      "--disable-extensions",
      "--disable-popup-blocking",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-features=ChromeWhatsNewUI,Translate",
      "--window-size=1280,800",
      "--lang=ko-KR",
    ],
    executablePath: chromePath,
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    viewport: { width: 1280, height: 800 },
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    extraHTTPHeaders: { "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8" },
    ignoreDefaultArgs: ["--enable-automation"],
  };

  const context = await chromium.launchPersistentContext(profileDir, launchOptions);
  await applyStealthToContext(context);
  const page = await context.newPage();
  return { context, page };
}

function ask(rl: readline.Interface, prompt: string): Promise<string> {
  return new Promise((res) => rl.question(prompt, res));
}

// ─── Main REPL ────────────────────────────────────────────────────────────────

export async function runMarketAgent(): Promise<void> {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║          Market Analysis Agent  🤖                           ║
║  URL 입력 → Claude가 상품 페이지를 읽어드립니다             ║
║  실제 Chrome + 봇 탐지 우회 + 실시간 분석                   ║
╚══════════════════════════════════════════════════════════════╝
`);
  const chromePath = findRealChrome();
  if (chromePath) console.log(`  ✓ 실제 Chrome 사용: ${chromePath}\n`);
  else             console.log(`  ⚠ 실제 Chrome 없음 — Playwright 번들 Chromium 사용\n`);

  await startCollectorServer();

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  const contextCache = new Map<string, { context: BrowserContext; page: Page }>();

  async function getContextForDomain(domain: string): Promise<{ context: BrowserContext; page: Page }> {
    if (contextCache.has(domain)) {
      const cached = contextCache.get(domain)!;
      try { await cached.page.title(); return cached; } catch {}
      contextCache.delete(domain);
    }
    const fresh = await launchContext(domain);
    contextCache.set(domain, fresh);
    return fresh;
  }

  try {
    while (true) {
      const input = (await ask(rl, "\nURL 입력 (q 종료): ")).trim();
      if (!input || input.toLowerCase() === "q") break;
      if (!input.startsWith("http")) {
        console.log("  ⚠  http(s)://로 시작하는 URL을 입력해주세요.");
        continue;
      }

      let domain: string;
      try { domain = new URL(input).hostname.replace(/^www\./, ""); }
      catch { console.log("  ⚠  유효하지 않은 URL"); continue; }

      try {
        const localUp = await isServerAlive();
        let page: Page | null = null;
        let context: BrowserContext | null = null;

        if (!localUp) {
          const pw = await getContextForDomain(domain);
          page = pw.page;
          context = pw.context;
        }

        await analyzeSiteHandler({ url: input }, page, context);
        // narration streamed directly to stdout inside the handler

      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`\n  ✗ 오류: ${msg}\n`);
        try { await contextCache.get(domain)?.context.close(); } catch {}
        contextCache.delete(domain);
      }
    }
  } finally {
    rl.close();
    for (const { context } of contextCache.values()) {
      try { await context.close(); } catch {}
    }
    stopCollectorServer();
    console.log("\n  👋  종료\n");
  }
}
