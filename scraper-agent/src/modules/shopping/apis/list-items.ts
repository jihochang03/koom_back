// list-items — generic paginated product list scraper
// Mirrors the Intuned list-items.ts pattern exactly
import { BrowserContext, Page } from "playwright";
import { goToUrl, validateDataUsingSchema } from "../../../core/browser";
import { extendTimeout, extendPayload } from "../../../core/runtime";
import { NetworkRecorder } from "../../../core/network";
import { analyzePageStructure, extractProductList, ProductItem } from "../ai/claude";
import path from "path";

// ─── Schema (same pattern as Intuned's DATA_SCHEMA) ──────────────────────────

const DATA_SCHEMA: Record<string, unknown> = {
  type: "array",
  items: {
    type: "object",
    properties: {
      id: { type: "string" },
      title: { type: "string" },
      url: { type: "string" },
      price: {
        type: "object",
        properties: {
          original: { type: ["number", "null"] },
          discounted: { type: ["number", "null"] },
          currency: { type: "string" },
        },
      },
      images: { type: "array", items: { type: "string" } },
      category: { type: ["string", "null"] },
      brand: { type: ["string", "null"] },
      rating: { type: ["number", "null"] },
      review_count: { type: ["number", "null"] },
      availability: { type: "string" },
      options: { type: "array", items: { type: "string" } },
    },
    required: ["id", "title", "url"],
  },
};

// ─── DOM-only fast-path extraction ───────────────────────────────────────────

async function tryDomExtract(
  page: Page,
  containerSelector: string
): Promise<ProductItem[]> {
  return page.evaluate((sel: string) => {
    const containers = Array.from(document.querySelectorAll(sel));
    const BASE = window.location.origin;

    return containers
      .map((el, idx) => {
        const anchor = el.querySelector("a") as HTMLAnchorElement | null;
        const title =
          el.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name'],[class*='product-name']")
            ?.textContent?.trim() ??
          anchor?.textContent?.trim() ??
          "";

        const href = anchor?.getAttribute("href") ?? "";
        const url = href.startsWith("http") ? href : href ? `${BASE}${href}` : "";

        const img = el.querySelector("img") as HTMLImageElement | null;
        const imgSrc = img?.src || (img?.dataset?.src ?? "");

        // Price: look for discounted first, then original
        const priceEls = el.querySelectorAll("[class*='price'],[class*='cost'],[data-price]");
        let discounted: number | null = null;
        let original: number | null = null;

        priceEls.forEach((p) => {
          const raw = p.textContent?.replace(/[^0-9.]/g, "") ?? "";
          const num = parseFloat(raw);
          if (!isNaN(num)) {
            if (discounted === null) discounted = num;
            else if (original === null) original = num;
          }
        });

        const id =
          (el as HTMLElement).dataset?.productId ??
          anchor?.href?.match(/[?&]id=([^&]+)/)?.[1] ??
          `item_${idx}`;

        return title || url
          ? {
              id,
              title,
              url,
              price: { original, discounted, currency: "KRW" },
              images: imgSrc ? [imgSrc] : [],
              availability: "unknown" as const,
            }
          : null;
      })
      .filter(Boolean) as ProductItem[];
  }, containerSelector);
}

// ─── Pagination ───────────────────────────────────────────────────────────────

async function isNextPageAvailable(page: Page, selector: string | null): Promise<boolean> {
  if (!selector) return false;
  const el = await page.$(selector);
  return el !== null;
}

async function goToNextPage(page: Page, selector: string): Promise<void> {
  const el = await page.$(selector);
  if (!el) return;

  const href = await el.getAttribute("href");
  if (href) {
    const next = href.startsWith("http") ? href : `${new URL(page.url()).origin}${href}`;
    await goToUrl({ page, url: next });
  } else {
    await el.click();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(800);
  }
}

// ─── Handler (exact Intuned signature) ───────────────────────────────────────

export default async function handler(
  params: Record<string, unknown>,
  page: Page,
  context: BrowserContext
): Promise<Record<string, unknown>> {
  const targetUrl = params.url as string;
  const maxPages = (params.max_pages as number | undefined) ?? 3;
  const outputDir = (params.output_dir as string | undefined) ?? ".agent-output";
  const fetchDetails = (params.fetch_details as boolean | undefined) ?? true;

  // ── Network recording ──
  const networkDir = path.join(outputDir, "network");
  const recorder = new NetworkRecorder(networkDir);
  recorder.attach(page);

  // ── Navigate ──
  await goToUrl({ page, url: targetUrl });

  // Give the network recorder time to capture initial XHR/fetch calls
  await page.waitForTimeout(1_500);

  // ── AI page analysis ──
  const screenshotBuf = await page.screenshot({ type: "png", fullPage: false });
  const screenshotBase64 = screenshotBuf.toString("base64");
  const html = await page.content();

  const apiEntries = recorder.getApiEntries();
  const networkApiSample = apiEntries
    .slice(0, 5)
    .map((e) => e.responseBody)
    .filter(Boolean)
    .join("\n\n---\n\n");

  console.info("[list-items] Analyzing page structure with Claude...");
  const analysis = await analyzePageStructure({
    screenshotBase64,
    htmlSample: html,
    url: targetUrl,
    networkApiSample: networkApiSample || undefined,
  });

  console.info("[list-items] Analysis:", JSON.stringify(analysis, null, 2));

  if (!analysis.hasProductList) {
    console.warn("[list-items] No product list detected on this page.");
    return { items: [], totalPages: 0, analysis };
  }

  // ── Paginated extraction loop (same pattern as Intuned list-items.ts) ──
  const allItems: ProductItem[] = [];
  let pageCount = 0;

  while (pageCount < maxPages) {
    extendTimeout();

    const currentHtml = await page.content();
    const freshApiData = recorder
      .getApiEntries()
      .slice(-8)
      .map((e) => e.responseBody)
      .filter(Boolean)
      .join("\n\n---\n\n");

    // Try fast DOM-only extraction first; fall back to AI if it yields nothing
    let items = await tryDomExtract(page, analysis.productContainerSelector);

    if (items.length === 0) {
      console.info(
        "[list-items] DOM extraction yielded 0 items — falling back to Claude extraction"
      );
      items = await extractProductList({
        html: currentHtml,
        networkApiData: freshApiData || undefined,
        url: page.url(),
        containerSelector: analysis.productContainerSelector,
      });
    }

    validateDataUsingSchema({ data: items, schema: DATA_SCHEMA });
    allItems.push(...items);
    console.info(
      `[list-items] Page ${pageCount + 1}: extracted ${items.length} items (total ${allItems.length})`
    );

    // ── extendPayload: chain to get-item for each product ──
    if (fetchDetails) {
      for (const item of items) {
        if (item.url) {
          extendPayload({
            api: "get-item",
            parameters: {
              url: item.url,
              id: item.id,
              title: item.title,
            },
          });
        }
      }
    }

    pageCount += 1;

    if (!(await isNextPageAvailable(page, analysis.paginationSelector))) break;
    await goToNextPage(page, analysis.paginationSelector!);
  }

  return { items: allItems, totalPages: pageCount, analysis };
}
