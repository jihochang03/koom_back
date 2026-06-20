/**
 * scraper-agent CLI
 *
 * scrape   — URL로 상품 데이터 직접 수집
 *   npx ts-node src/index.ts scrape <url> [max_pages] [--headless] [--no-details]
 *
 * agent    — 자연어 요청으로 새 API 핸들러 생성·테스트
 *   npx ts-node src/index.ts agent "<task>"
 *
 * template — 처음 보는 사이트 URL 분석 → templates/<domain>.json 생성
 *   npx ts-node src/index.ts template <url>
 */
import { chromium, BrowserContext, Page } from "playwright";
import path from "path";
import fs from "fs";
import { clearPayloadQueue, getPayloadQueue } from "./core/runtime";
import listItemsHandler from "./modules/shopping/apis/list-items";
import getItemHandler from "./modules/shopping/apis/get-item";
import { runAgent } from "./agent/agent";
import { generateTemplate } from "./agent/template-agent";
import { runMarketAgent } from "./modules/shopping/agent/market-agent";

// ── .env ─────────────────────────────────────────────────────────────────────
try {
  const envPath = path.resolve(__dirname, "../.env");
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, "utf-8").split("\n")) {
      const eq = line.indexOf("=");
      if (eq > 0) {
        const k = line.slice(0, eq).trim();
        const v = line.slice(eq + 1).trim();
        if (k && !process.env[k]) process.env[k] = v;
      }
    }
  }
} catch {}

// ── Args ──────────────────────────────────────────────────────────────────────
const [, , mode, ...rest] = process.argv;

function printHelp(): void {
  console.log(`
Usage:
  chat      npx ts-node src/index.ts chat
  scrape    npx ts-node src/index.ts scrape <url> [max_pages] [--headless] [--no-details]
  agent     npx ts-node src/index.ts agent "<task>"
  template  npx ts-node src/index.ts template <url>

Examples:
  npx ts-node src/index.ts chat
  npx ts-node src/index.ts scrape https://www.coupang.com/np/search?q=노트북 3 --headless
  npx ts-node src/index.ts agent "쿠팡 검색 스크래퍼 API 만들어줘"
  npx ts-node src/index.ts template https://www.rakuten.co.jp/search?q=shoes
`);
}

// ════════════════════════════════════════════════════════════════════════════
// AGENT MODE
// ════════════════════════════════════════════════════════════════════════════
if (mode === "chat") {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("[error] ANTHROPIC_API_KEY not set. Add it to .env");
    process.exit(1);
  }
  runMarketAgent().catch((err) => { console.error("[fatal]", err); process.exit(1); });

} else if (mode === "agent") {
  const task = rest.join(" ").trim();
  if (!task) { printHelp(); process.exit(1); }

  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("[error] ANTHROPIC_API_KEY not set. Add it to .env");
    process.exit(1);
  }

  console.log(`
╔══════════════════════════════════════════════════════════╗
║              scraper-agent  [agent mode]                 ║
╠══════════════════════════════════════════════════════════╣
║  Task: ${task.slice(0, 56).padEnd(56)} ║
╚══════════════════════════════════════════════════════════╝
`);

  runAgent(task).catch((err) => { console.error("[fatal]", err); process.exit(1); });

// ════════════════════════════════════════════════════════════════════════════
// SCRAPE MODE
// ════════════════════════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════════════════════════
// TEMPLATE MODE  (처음 보는 사이트 → templates/<domain>.json 생성)
// ════════════════════════════════════════════════════════════════════════════
} else if (mode === "template") {
  const url = rest.find((a) => a.startsWith("http"));
  if (!url) { printHelp(); process.exit(1); }

  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("[error] ANTHROPIC_API_KEY not set.");
    process.exit(1);
  }

  generateTemplate(url)
    .then((t) => {
      // stdout에 JSON 출력 → Python subprocess가 읽을 수 있음
      console.log("__TEMPLATE__" + JSON.stringify(t));
      process.exit(0);
    })
    .catch((err) => {
      console.error("[template] Fatal:", err);
      process.exit(1);
    });

} else if (mode === "scrape") {
  const url = rest.find((a) => a.startsWith("http"));
  const maxPages = parseInt(rest.find((a) => /^\d+$/.test(a)) ?? "3", 10);
  const headless = rest.includes("--headless");
  const noDetails = rest.includes("--no-details");

  if (!url) { printHelp(); process.exit(1); }

  const runId = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const outputDir = path.resolve(__dirname, `../output/${runId}`);
  fs.mkdirSync(outputDir, { recursive: true });

  console.log(`
╔══════════════════════════════════════════════════════════╗
║              scraper-agent  [scrape mode]                ║
╠══════════════════════════════════════════════════════════╣
║  URL      : ${url.slice(0, 54).padEnd(54)} ║
║  Pages    : ${String(maxPages).padEnd(54)} ║
║  Details  : ${String(!noDetails).padEnd(54)} ║
║  Headless : ${String(headless).padEnd(54)} ║
║  Output   : ${outputDir.slice(-54).padEnd(54)} ║
╚══════════════════════════════════════════════════════════╝
`);

  (async () => {
    const browser = await chromium.launch({
      headless,
      args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    });
    const context: BrowserContext = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      viewport: { width: 1280, height: 800 },
      locale: "ko-KR",
    });
    const page: Page = await context.newPage();

    try {
      console.info("\n[scrape] ═══ Step 1: list-items ══════════════════════════");
      const listResult = await listItemsHandler(
        { url, max_pages: maxPages, output_dir: outputDir, fetch_details: !noDetails },
        page,
        context
      );
      const listFile = path.join(outputDir, "products.json");
      fs.writeFileSync(listFile, JSON.stringify(listResult, null, 2));
      console.info(`\n[scrape] ✓ ${(listResult.items as unknown[]).length} products → ${listFile}`);

      const queue = getPayloadQueue();
      clearPayloadQueue();

      if (!noDetails && queue.length > 0) {
        console.info(`\n[scrape] ═══ Step 2: get-item (${queue.length} products) ═══════`);
        const details: unknown[] = [];
        let ok = 0, fail = 0;

        for (let i = 0; i < queue.length; i++) {
          const { parameters } = queue[i];
          const productUrl = parameters.url as string;
          process.stdout.write(`[scrape] ${i + 1}/${queue.length}  ${productUrl.slice(0, 60)}\r`);
          try {
            details.push(await getItemHandler({ ...parameters, output_dir: outputDir }, page, context));
            ok++;
          } catch (err) {
            console.error(`\n[scrape] ✗ ${productUrl}\n  ${err}`);
            fail++;
          }
          await page.waitForTimeout(400);
        }

        const detailFile = path.join(outputDir, "product_details.json");
        fs.writeFileSync(detailFile, JSON.stringify(details, null, 2));
        console.info(`\n[scrape] ✓ ${ok} details saved, ${fail} failed → ${detailFile}`);
      }
    } finally {
      await browser.close();
    }

    console.info(`\n[scrape] Done. Output: ${outputDir}\n`);
  })().catch((err) => { console.error("[fatal]", err); process.exit(1); });

} else {
  printHelp();
  process.exit(1);
}
