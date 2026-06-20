// @intuned/browser equivalent — Playwright wrapper + schema validation
import { Page } from "playwright";
import Ajv from "ajv";

const ajv = new Ajv({ strict: false, allErrors: false });

export async function goToUrl({
  page,
  url,
  waitUntil = "domcontentloaded",
  timeout = 30_000,
}: {
  page: Page;
  url: string;
  waitUntil?: "domcontentloaded" | "load" | "networkidle";
  timeout?: number;
}): Promise<void> {
  await page.goto(url, { waitUntil, timeout });
  // Let dynamic content (JS-rendered) settle
  await page.waitForTimeout(800);
}

export function validateDataUsingSchema({
  data,
  schema,
}: {
  data: unknown;
  schema: Record<string, unknown>;
}): void {
  const validate = ajv.compile(schema);
  const valid = validate(data);
  if (!valid) {
    const errors = ajv.errorsText(validate.errors);
    console.warn("[browser] Schema validation warnings:", errors);
  }
}
