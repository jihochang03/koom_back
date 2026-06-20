// get-item — single product detail scraper
// Mirrors the Intuned get-item.ts pattern exactly
import { BrowserContext, Page } from "playwright";
import { goToUrl, validateDataUsingSchema } from "../../../core/browser";
import { extendTimeout } from "../../../core/runtime";
import { NetworkRecorder } from "../../../core/network";
import { extractProductDetail, ProductItem } from "../ai/claude";
import path from "path";

// ─── Schema ──────────────────────────────────────────────────────────────────

const DATA_SCHEMA: Record<string, unknown> = {
  type: "object",
  properties: {
    id: { type: "string" },
    title: { type: "string" },
    url: { type: "string" },
    description: { type: ["string", "null"] },
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
    options: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          values: { type: "array", items: { type: "string" } },
        },
        required: ["name", "values"],
      },
    },
    specifications: { type: "object" },
    seller: { type: ["string", "null"] },
    shipping_info: { type: ["string", "null"] },
  },
  required: ["id", "title", "url"],
};

// ─── Handler (exact Intuned signature) ───────────────────────────────────────

export default async function handler(
  params: Record<string, unknown>,
  page: Page,
  context: BrowserContext
): Promise<ProductItem> {
  extendTimeout();

  const itemUrl = params.url as string;
  const outputDir = (params.output_dir as string | undefined) ?? ".agent-output";

  const networkDir = path.join(outputDir, "network", "detail");
  const recorder = new NetworkRecorder(networkDir);
  recorder.attach(page);

  await goToUrl({ page, url: itemUrl });
  await page.waitForTimeout(1_000);

  const html = await page.content();

  const freshApiData = recorder
    .getApiEntries()
    .slice(0, 5)
    .map((e) => e.responseBody)
    .filter(Boolean)
    .join("\n\n---\n\n");

  const detail = await extractProductDetail({
    html,
    url: itemUrl,
    networkApiData: freshApiData || undefined,
  });

  // Merge any pre-known fields from list-items params
  const merged: ProductItem = {
    ...(params as Partial<ProductItem>),
    ...detail,
    id: detail.id !== "unknown" ? detail.id : (params.id as string) ?? "unknown",
    url: itemUrl,
  };

  validateDataUsingSchema({ data: merged, schema: DATA_SCHEMA });

  return merged;
}
