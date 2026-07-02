// Claude API integration — AI-powered page analysis and data extraction
import Anthropic from "@anthropic-ai/sdk";
import { NetworkEntry } from "../../../core/network";
import { getCategory, isShoppingCategory } from "../../../categories";

let _client: Anthropic | null = null;
const client = () => {
  if (!_client) _client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return _client;
};

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PageAnalysis {
  hasProductList: boolean;
  productContainerSelector: string;
  paginationSelector: string | null;
  extractionStrategy: "dom" | "api" | "hybrid";
  apiEndpoint: string | null;
  notes: string;
}

export interface ProductItem {
  id: string;
  title: string;
  url: string;
  price?: {
    original: number | null;
    discounted: number | null;
    currency: string;
  };
  images?: string[];
  category?: string | null;
  brand?: string | null;
  rating?: number | null;
  review_count?: number | null;
  availability?: "in_stock" | "out_of_stock" | "unknown";
  options?: string[];
  description?: string | null;
  seller?: string | null;
  shipping_info?: string | null;
  specifications?: Record<string, string>;
}

// ─── Page structure analysis ─────────────────────────────────────────────────

const ANALYSIS_SYSTEM = `You are a web scraping expert specializing in e-commerce product extraction.
Analyze a webpage screenshot and its HTML to identify product listing structure.
Respond with ONLY a JSON object — no markdown fences, no explanation.`;

const ANALYSIS_SCHEMA = `{
  "hasProductList": boolean,
  "productContainerSelector": "CSS selector for individual product cards",
  "paginationSelector": "CSS selector for next-page button, or null",
  "extractionStrategy": "dom" | "api" | "hybrid",
  "apiEndpoint": "if network API was detected, the URL pattern, else null",
  "notes": "brief observations"
}`;

export async function analyzePageStructure({
  screenshotBase64,
  htmlSample,
  url,
  networkApiSample,
}: {
  screenshotBase64: string;
  htmlSample: string;
  url: string;
  networkApiSample?: string;
}): Promise<PageAnalysis> {
  const textParts: string[] = [
    `URL: ${url}`,
    `\nHTML (first 8 000 chars):\n\`\`\`html\n${htmlSample.slice(0, 8_000)}\n\`\`\``,
  ];

  if (networkApiSample) {
    textParts.push(
      `\nNetwork API responses detected:\n\`\`\`json\n${networkApiSample.slice(0, 3_000)}\n\`\`\``
    );
  }

  textParts.push(`\nReturn JSON matching this schema:\n${ANALYSIS_SCHEMA}`);

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1_024,
    system: ANALYSIS_SYSTEM,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image",
            source: { type: "base64", media_type: "image/png", data: screenshotBase64 },
          },
          { type: "text", text: textParts.join("") },
        ],
      },
    ],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "";
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error(`analyzePageStructure: no JSON in response:\n${text}`);

  return JSON.parse(jsonMatch[0]) as PageAnalysis;
}

// ─── Product list extraction ──────────────────────────────────────────────────

const LIST_SYSTEM = `You are a product data extraction expert.
Extract all product items from the provided HTML or API JSON and return them as a JSON array.
Return ONLY the JSON array — no markdown fences, no explanation.
Each item must have at minimum: id (string), title (string), url (string).`;

export async function extractProductList({
  html,
  networkApiData,
  url,
  containerSelector,
}: {
  html: string;
  networkApiData?: string;
  url: string;
  containerSelector: string;
}): Promise<ProductItem[]> {
  const parts: string[] = [`Page URL: ${url}\nProduct container selector: "${containerSelector}"\n`];

  if (networkApiData) {
    parts.push(`\nNetwork API data (prefer this if it contains product arrays):\n\`\`\`json\n${networkApiData.slice(0, 6_000)}\n\`\`\`\n`);
  }

  parts.push(`\nPage HTML:\n\`\`\`html\n${html.slice(0, 10_000)}\n\`\`\``);

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 8_000,
    system: LIST_SYSTEM,
    messages: [{ role: "user", content: parts.join("") }],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "[]";
  const jsonMatch = text.match(/\[[\s\S]*\]/);
  if (!jsonMatch) {
    console.warn("[claude] extractProductList: no JSON array, returning []");
    return [];
  }
  return JSON.parse(jsonMatch[0]) as ProductItem[];
}

// ─── Product detail extraction ────────────────────────────────────────────────

const DETAIL_SYSTEM = `You are a product detail extraction expert.
Extract full product details from the HTML and return a single JSON object.
Return ONLY the JSON object — no markdown fences, no explanation.
Fields: id, title, url, description, price (original/discounted/currency), images (array),
category, brand, rating, review_count, availability, options (array of {name, values:[]}),
specifications (object), seller, shipping_info.`;

export async function extractProductDetail({
  html,
  url,
  networkApiData,
}: {
  html: string;
  url: string;
  networkApiData?: string;
}): Promise<ProductItem> {
  const parts: string[] = [`Product URL: ${url}\n`];

  if (networkApiData) {
    parts.push(`\nNetwork API data:\n\`\`\`json\n${networkApiData.slice(0, 4_000)}\n\`\`\`\n`);
  }

  parts.push(`\nHTML:\n\`\`\`html\n${html.slice(0, 12_000)}\n\`\`\``);

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 4_000,
    system: DETAIL_SYSTEM,
    messages: [{ role: "user", content: parts.join("") }],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "{}";
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    console.warn("[claude] extractProductDetail: no JSON object, returning stub");
    return { id: "unknown", title: "", url };
  }
  return JSON.parse(jsonMatch[0]) as ProductItem;
}

// ─── Site options analysis ────────────────────────────────────────────────────

export interface OptionGroup {
  name: string;
  values: string[];
}

export interface ApiStrategy {
  url_pattern: string;
  method: "GET" | "POST";
  headers?: Record<string, string>;
  body_template?: string | null;
  id_extraction: {
    from: "url" | "dom" | "network";
    pattern: string;
    group?: number;
  };
  response_options_path: string;
  option_name_field: string;
  option_values_field: string;
}

export interface DomStrategy {
  option_groups: Array<{
    name: string;
    container_selector: string;
    value_selector: string;
    attr: string;
  }>;
}

export interface SizeInfo {
  weight_g: number | null;
  width_cm: number | null;
  length_cm: number | null;
  height_cm: number | null;
  girth_sum_cm?: number | null;     // 세 변의 합 (국제배송 부피 기준)
  longest_side_cm?: number | null;
  source: "text" | "image_ocr" | "none" | "written" | "title_guess" | "mixed";
  confidence: "high" | "medium" | "low" | "HIGH" | "MEDIUM" | "LOW";
  note?: string;
}

export interface ProductData {
  title: string;
  description?: string | null;
  price?: { original: number | null; discounted: number | null; currency: string } | null;
  options: OptionGroup[];
  images?: string[];
  brand?: string | null;
  availability?: "in_stock" | "out_of_stock" | "unknown";
  shipping_fee?: number | null;
  shipping_fee_text?: string | null;
  delivery_date?: string | null;
  rating?: number | null;
  review_count?: number | null;
  seller?: string | null;
  specifications?: Record<string, string>;
  size?: SizeInfo | null;
}

export interface SiteRecipe {
  domain: string;
  source_url: string;
  created_at: string;
  strategy: "api" | "dom" | "hybrid";
  confidence: "high" | "medium" | "low";
  api?: ApiStrategy | null;
  dom?: DomStrategy | null;
  detected_product?: ProductData | null;
  notes: string;
}

const SITE_ANALYSIS_SYSTEM = `You are a reverse engineering expert specializing in e-commerce APIs and web scraping.
Analyze network traffic and HTML from a product page to discover how the site serves product options/variants (색상, 사이즈, 패키지, etc.).
Return ONLY valid JSON — no markdown fences, no explanation.`;

const SITE_ANALYSIS_SCHEMA = `{
  "strategy": "api" | "dom" | "hybrid",
  "confidence": "high" | "medium" | "low",
  "api": {
    "url_pattern": "API URL with {product_id} placeholder — null if no API found",
    "method": "GET" | "POST",
    "headers": { "important-header": "value" },
    "body_template": "POST body template or null",
    "id_extraction": {
      "from": "url",
      "pattern": "regex to extract product ID from page URL",
      "group": 1
    },
    "response_options_path": "dot.notation.path to options array",
    "option_name_field": "field name for option group name",
    "option_values_field": "field name for option values"
  },
  "dom": {
    "option_groups": [
      {
        "name": "옵션명 (e.g. 색상)",
        "container_selector": "CSS selector for the option group",
        "value_selector": "CSS selector for individual option values",
        "attr": "innerText | value | data-xxx"
      }
    ]
  },
  "detected_product": {
    "title": "상품명",
    "description": "상품 설명",
    "price": { "original": 480000, "discounted": null, "currency": "KRW" },
    "options": [{ "name": "패키지", "values": ["BASIC", "STANDARD", "PREMIUM"] }],
    "images": ["이미지 URL"],
    "brand": null,
    "availability": "in_stock",
    "rating": 4.8,
    "review_count": 123,
    "seller": "판매자명",
    "specifications": { "key": "value" }
  },
  "notes": "brief explanation"
}
Set api to null if no API found. Set dom to null if API covers everything.
detected_product = ALL product data extractable from the network responses and HTML right now.
Extract every field you can find — title, price, ALL options with values, images, rating, seller, specs, etc.`;

export async function analyzeSiteForOptions({
  url,
  screenshotBase64,
  html,
  networkEntries,
}: {
  url: string;
  screenshotBase64: string;
  html: string;
  networkEntries: NetworkEntry[];
}): Promise<SiteRecipe> {
  const domain = new URL(url).hostname.replace(/^www\./, "");

  const networkSummary = networkEntries
    .slice(0, 25)
    .map((e, i) => {
      const lines: string[] = [
        `[${i + 1}] ${e.method} ${e.url}  →  ${e.status}  (${e.contentType})`,
      ];
      if (e.requestHeaders) {
        const notable = Object.entries(e.requestHeaders)
          .filter(([k]) => ["x-api-key", "x-auth-token", "x-naver-", "referer", "origin", "accept"].some(p => k.toLowerCase().startsWith(p)))
          .map(([k, v]) => `  ${k}: ${v}`)
          .join("\n");
        if (notable) lines.push(`  Notable headers:\n${notable}`);
      }
      if (e.requestBody) lines.push(`  Request body: ${e.requestBody.slice(0, 400)}`);
      if (e.responseBody) lines.push(`  Response: ${e.responseBody.slice(0, 800)}`);
      return lines.join("\n");
    })
    .join("\n\n─────\n\n");

  const textContent = [
    `Domain: ${domain}`,
    `Product page URL: ${url}`,
    `\n${"─".repeat(60)}\nNETWORK REQUESTS (${networkEntries.length} total, showing top 25):\n${"─".repeat(60)}\n${networkSummary || "(none captured)"}`,
    `\n${"─".repeat(60)}\nHTML (first 40000 chars):\n${"─".repeat(60)}\n${html.slice(0, 40_000)}`,
    `\n${"─".repeat(60)}\nReturn JSON matching this schema:\n${SITE_ANALYSIS_SCHEMA}`,
  ].join("\n");

  const userContent: Anthropic.MessageParam["content"] = screenshotBase64
    ? [
        { type: "image" as const, source: { type: "base64" as const, media_type: "image/png" as const, data: screenshotBase64 } },
        { type: "text" as const, text: textContent },
      ]
    : [{ type: "text" as const, text: textContent }];

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 4_000,
    system: SITE_ANALYSIS_SYSTEM,
    messages: [{ role: "user", content: userContent }],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "{}";
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error(`analyzeSiteForOptions: no JSON in response:\n${text}`);

  const partial = JSON.parse(jsonMatch[0]);

  return {
    domain,
    source_url: url,
    created_at: new Date().toISOString(),
    strategy: partial.strategy ?? "dom",
    confidence: partial.confidence ?? "low",
    api: partial.api ?? null,
    dom: partial.dom ?? null,
    detected_product: partial.detected_product ?? null,
    notes: partial.notes ?? "",
  };
}

// ─── Parse product data from a raw API response using a saved recipe ──────────

const PARSE_SYSTEM = `You are a product data extraction expert.
Given a raw API JSON response and context about the product page, extract ALL product information.
Return ONLY valid JSON — no markdown fences, no explanation.`;

const PARSE_SCHEMA = `{
  "title": "상품명",
  "description": "설명",
  "price": { "original": 480000, "discounted": 380000, "currency": "KRW" },
  "options": [{ "name": "옵션그룹명", "values": ["값1", "값2"] }],
  "images": ["url1"],
  "brand": "브랜드명 or null",
  "availability": "in_stock | out_of_stock | unknown",
  "rating": 4.8,
  "review_count": 123,
  "seller": "판매자명 or null",
  "specifications": { "key": "value" }
}`;

// ─── Streaming narration + extraction ────────────────────────────────────────

const NARRATE_SYSTEM = `당신은 사용자 대신 쇼핑 페이지를 읽어주는 도우미입니다.
HTML 내용을 보고 발견한 상품 정보를 자연스러운 한국어 대화체로 설명해주세요.
상품명·가격·할인·옵션(색상·사이즈·패키지 등)·재고·판매자·평점·브랜드·스펙·무게·크기 등을 찾아서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.
"HTML 파서 선추출 데이터" 섹션이 있으면 그 내용을 가장 우선적으로 활용하고, 해당 옵션/가격 정보를 JSON에 그대로 포함하세요.
설명이 끝나면 반드시 아래 형식의 JSON 코드 블록을 출력하세요:
\`\`\`json
{
  "title": "상품명",
  "price": { "original": 숫자, "discounted": 숫자또는null, "currency": "KRW" },
  "options": [{ "name": "옵션명", "values": ["값1", "값2"] }],
  "images": ["url"],
  "brand": null,
  "availability": "in_stock",
  "rating": null,
  "review_count": null,
  "seller": null,
  "specifications": {},
  "size": { "weight_g": 숫자또는null, "width_cm": 숫자또는null, "length_cm": 숫자또는null, "height_cm": 숫자또는null }
}
\`\`\`
size 필드: 상품 스펙/상세정보/배송정보에서 무게(g 또는 kg→g 변환)와 크기(mm→cm 변환)를 추출. 없으면 null.`;

// 옵션 관련 HTML 섹션 추출 (select, 옵션 컨테이너 등)
function extractOptionSections(html: string): string {
  const chunks: string[] = [];

  // <select> 요소 전체
  const selectRe = /<select[\s\S]{0,4000}?<\/select>/gi;
  let m: RegExpExecArray | null;
  while ((m = selectRe.exec(html)) !== null && chunks.length < 6) {
    chunks.push(m[0]);
  }

  // option/variant/choice/package/plan/color/size 포함 컨테이너
  const containerRe = /<(?:div|ul|ol|fieldset|section)[^>]*(?:class|id)="[^"]*(?:option|variant|choice|package|plan|color|size|grade|type)[^"]*"[\s\S]{0,5000}?<\/(?:div|ul|ol|fieldset|section)>/gi;
  while ((m = containerRe.exec(html)) !== null && chunks.length < 12) {
    chunks.push(m[0]);
  }

  if (chunks.length === 0) return "";
  return `\n${"─".repeat(50)}\n옵션 관련 HTML 섹션 (${chunks.length}개 추출):\n${"─".repeat(50)}\n` +
    chunks.map((c, i) => `[섹션${i + 1}]\n${c.slice(0, 2_000)}`).join("\n\n");
}

// Convert BeautifulSoup productInfo options to ProductData options format
function productInfoToOptions(opts: Array<{ option_type?: string; available_values?: string[]; [k: string]: unknown }>): OptionGroup[] {
  return opts
    .filter(o => o.available_values && o.available_values.length > 0)
    .map(o => ({ name: o.option_type ?? "옵션", values: o.available_values ?? [] }));
}

export async function narrateAndExtract({
  url,
  html,
  networkEntries,
  networkLog = [],
  productInfo,
  onText,
  category,
}: {
  url: string;
  html: string;
  networkEntries: NetworkEntry[];
  networkLog?: Array<{ url: string; body: string; ct?: string }>;
  productInfo?: Record<string, unknown>;
  onText?: (chunk: string) => void;
  /** 카테고리 ID. 미지정 또는 'shopping' 이면 기존 쇼핑 로직 그대로 동작 */
  category?: string | null;
}): Promise<Record<string, unknown>> {
  const isShopping = isShoppingCategory(category);
  const categoryDef = getCategory(category);

  // 시스템 프롬프트 결정 (쇼핑: 기존 상수 / 그 외: 카테고리 정의 사용)
  const systemPrompt = isShopping
    ? NARRATE_SYSTEM
    : `${categoryDef.narrateSystem}
설명이 끝나면 반드시 아래 형식의 JSON 코드 블록을 출력하세요:
\`\`\`json
${categoryDef.schemaExample}
\`\`\``;

  // Playwright 캡처 네트워크
  const playwrightNet = networkEntries
    .slice(0, 15)
    .map((e, i) => {
      const lines = [`[${i + 1}] ${e.method} ${e.url} → ${e.status} (${e.contentType})`];
      if (e.requestBody) lines.push(`  요청: ${e.requestBody.slice(0, 200)}`);
      if (e.responseBody) lines.push(`  응답: ${e.responseBody.slice(0, 800)}`);
      return lines.join("\n");
    })
    .join("\n\n");

  // JS 인터셉트 네트워크 (fetch/XHR)
  const jsNet = networkLog
    .slice(0, 30)
    .map((e, i) => `[${i + 1}] ${e.url}\n  응답: ${e.body.slice(0, 1_200)}`)
    .join("\n\n");

  // 쇼핑 카테고리일 때만 옵션 HTML 섹션 추출
  const optionSections = isShopping ? extractOptionSections(html) : "";

  // HTML 파서 선추출 데이터 (쇼핑 전용: BeautifulSoup 결과)
  const parsedSection = (isShopping && productInfo)
    ? `\n${"─".repeat(50)}\nHTML 파서 선추출 데이터 (BeautifulSoup — 가장 우선):\n${"─".repeat(50)}\n${JSON.stringify(productInfo, null, 2)}`
    : "";

  const pageLabel = isShopping ? "상품 페이지 URL" : "페이지 URL";

  const content = [
    `${pageLabel}: ${url}`,
    parsedSection,
    playwrightNet
      ? `\n${"─".repeat(50)}\n네트워크 요청 (Playwright, ${networkEntries.length}개):\n${"─".repeat(50)}\n${playwrightNet}`
      : "",
    jsNet
      ? `\n${"─".repeat(50)}\nfetch/XHR 인터셉트 (${networkLog.length}개):\n${"─".repeat(50)}\n${jsNet}`
      : "",
    optionSections,
    `\n${"─".repeat(50)}\nHTML (앞 30000자):\n${"─".repeat(50)}\n${html.slice(0, 30_000)}`,
  ].filter(Boolean).join("\n");

  const stream = client().messages.stream({
    model: "claude-sonnet-4-6",
    max_tokens: 4_000,
    system: systemPrompt,
    messages: [{ role: "user", content }],
  });

  let fullText = "";
  stream.on("text", (text: string) => {
    process.stdout.write(text);
    onText?.(text);
    fullText += text;
  });

  await stream.finalMessage();
  process.stdout.write("\n\n");

  // JSON 코드 블록 파싱
  let parsed: Record<string, unknown> | null = null;
  const fenceMatch = fullText.match(/```json\s*([\s\S]*?)\s*```/);
  if (fenceMatch) {
    try { parsed = JSON.parse(fenceMatch[1]); } catch {}
  }
  if (!parsed) {
    const rawMatch = fullText.match(/\{[\s\S]*\}/);
    if (rawMatch) {
      try { parsed = JSON.parse(rawMatch[0]); } catch {}
    }
  }
  if (!parsed) {
    console.warn("[claude] narrateAndExtract: JSON 파싱 실패 — 빈 결과 반환");
    parsed = isShopping ? { title: "", options: [] } : { title: "", page_type: "unknown", data: {} };
  }

  // 쇼핑 전용: BeautifulSoup 옵션 우선 병합
  if (isShopping && productInfo) {
    const rawOpts = productInfo.product_options;
    if (Array.isArray(rawOpts) && rawOpts.length > 0) {
      const htmlOptions = productInfoToOptions(rawOpts as Array<{ option_type?: string; available_values?: string[] }>);
      const opts = parsed.options as OptionGroup[] | undefined;
      if (htmlOptions.length > 0 && (!opts || opts.length === 0)) {
        parsed.options = htmlOptions;
      }
    }
    if (!parsed.price && (productInfo.discounted_price || productInfo.original_price)) {
      parsed.price = {
        original: (productInfo.original_price as number) ?? null,
        discounted: (productInfo.discounted_price as number) ?? null,
        currency: "KRW",
      };
    }
  }

  return parsed;
}

// ─── Size extraction (image OCR fallback) ────────────────────────────────────

/**
 * 상품 상세 HTML에서 이미지 URL을 추출한다.
 * 한국 쇼핑몰의 상품 상세 이미지(스펙 포함 JPG)는 페이지 하단부에 집중되어 있어
 * 문서 순서 기준 후반부 이미지를 우선한다.
 */
function extractDetailImageUrls(html: string, pageUrl: string): string[] {
  let origin: string;
  try { origin = new URL(pageUrl).origin; } catch { return []; }

  const seen = new Set<string>();
  const all: Array<{ url: string; pos: number }> = [];

  // src / data-src / data-original / data-lazy-src 등 모두 수집
  const imgRe = /<img\b[^>]+>/gi;
  const attrRe = /\b(?:data-src|data-original|data-lazy-src|data-lazy|src)\s*=\s*["']([^"']+)["']/i;
  let m: RegExpExecArray | null;

  while ((m = imgRe.exec(html)) !== null) {
    const tag = m[0];
    const am = tag.match(attrRe);
    if (!am) continue;

    let u = am[1].trim();
    if (!u || u.startsWith("data:")) continue;
    if (u.startsWith("//")) u = "https:" + u;
    else if (u.startsWith("/")) u = origin + u;
    else if (!u.startsWith("http")) continue;

    // 이미지 확장자 필터 (쿼리스트링 제거 후 판단)
    const path = u.split("?")[0].toLowerCase();
    if (!/\.(jpe?g|png|webp|gif)$/.test(path)) continue;

    // 명확한 썸네일 패턴 제외
    if (/[_-](?:thumb|tn|list|small|tiny|s\d{2,3})\b/i.test(u)) continue;

    if (!seen.has(u)) {
      seen.add(u);
      all.push({ url: u, pos: m.index });
    }
  }

  if (all.length === 0) return [];

  // 상세 섹션 키워드를 포함하는 URL을 우선
  const detailKw = /detail|desc|content|spec|info|body|prd_img|goods_img|product_img/i;
  const detailImgs = all.filter(({ url }) => detailKw.test(url));
  const others     = all.filter(({ url }) => !detailKw.test(url));

  // 그 외 이미지는 페이지 후반부(60% 이후)를 우선
  const htmlLen = html.length;
  const lateOthers  = others.filter(({ pos }) => pos > htmlLen * 0.6);
  const earlyOthers = others.filter(({ pos }) => pos <= htmlLen * 0.6);

  const ordered = [
    ...detailImgs.map(i => i.url),
    ...lateOthers.map(i => i.url),
    ...earlyOthers.map(i => i.url),
  ];

  return ordered.slice(0, 15); // 최대 15개 후보
}

/** URL에서 이미지를 fetch해 base64로 반환. 실패 시 null. */
async function fetchImageBase64(
  url: string,
): Promise<{ data: string; mediaType: "image/jpeg" | "image/png" | "image/webp" | "image/gif" } | null> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 12_000);
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { "User-Agent": "Mozilla/5.0 (compatible; ProductBot/1.0)" },
    });
    clearTimeout(t);

    if (!res.ok) return null;

    // 5MB 초과 이미지 스킵
    const len = parseInt(res.headers.get("content-length") ?? "0", 10);
    if (len > 5_000_000) return null;

    const buf = await res.arrayBuffer();
    if (buf.byteLength > 5_000_000) return null;

    const ct = (res.headers.get("content-type") ?? "").toLowerCase();
    const mediaType =
      ct.includes("png")  ? "image/png"  :
      ct.includes("webp") ? "image/webp" :
      ct.includes("gif")  ? "image/gif"  :
      "image/jpeg";

    return { data: Buffer.from(buf).toString("base64"), mediaType: mediaType as never };
  } catch {
    return null;
  }
}

const SIZE_OCR_SYSTEM = `당신은 상품 스펙 이미지에서 무게·크기 정보를 추출하는 전문가입니다.
이미지에 표시된 무게(중량)와 크기(가로/세로/높이/두께) 수치를 찾아 JSON으로 반환하세요.
단위 변환: g → 그대로, kg → ×1000하여 g로, mm → ÷10하여 cm로.
스펙 정보가 없는 이미지(제품 사진·디자인·배너)는 무시하세요.
JSON만 출력, 마크다운 불필요.`;

/**
 * 상품 상세 이미지에서 무게·크기를 Claude Vision으로 추출한다.
 * @param imageUrls  extractDetailImageUrls() 반환값
 * @param maxImages  실제로 Vision에 보낼 최대 이미지 수 (기본 5)
 */
export async function extractSizeFromImages(
  imageUrls: string[],
  maxImages = 5,
): Promise<SizeInfo> {
  const EMPTY: SizeInfo = {
    weight_g: null, width_cm: null, length_cm: null, height_cm: null,
    source: "none", confidence: "low",
  };

  if (imageUrls.length === 0) return EMPTY;

  // 후보 이미지를 순서대로 fetch, 성공한 것만 사용
  const imageParts: Anthropic.ImageBlockParam[] = [];
  for (const url of imageUrls) {
    if (imageParts.length >= maxImages) break;
    const img = await fetchImageBase64(url);
    if (!img) continue;
    imageParts.push({
      type: "image",
      source: { type: "base64", media_type: img.mediaType, data: img.data },
    });
  }

  if (imageParts.length === 0) return EMPTY;

  console.info(`[size-ocr] ${imageParts.length}장 이미지로 크기 추출 시도`);

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 512,
    system: SIZE_OCR_SYSTEM,
    messages: [{
      role: "user",
      content: [
        ...imageParts,
        {
          type: "text",
          text: [
            `위 이미지${imageParts.length > 1 ? "들" : ""}에서 무게와 크기 수치를 추출하세요.`,
            `{"weight_g": 숫자또는null, "width_cm": 숫자또는null, "length_cm": 숫자또는null, "height_cm": 숫자또는null}`,
          ].join("\n"),
        },
      ],
    }],
  });

  const raw = response.content[0].type === "text" ? response.content[0].text : "{}";
  const jsonMatch = raw.match(/\{[\s\S]*?\}/);
  if (!jsonMatch) return { ...EMPTY, source: "image_ocr" };

  try {
    const p = JSON.parse(jsonMatch[0]);
    const hasData = p.weight_g != null || p.width_cm != null || p.length_cm != null || p.height_cm != null;
    return {
      weight_g: p.weight_g ?? null,
      width_cm: p.width_cm ?? null,
      length_cm: p.length_cm ?? null,
      height_cm: p.height_cm ?? null,
      source: "image_ocr",
      confidence: hasData ? "medium" : "low",
    };
  } catch {
    return { ...EMPTY, source: "image_ocr" };
  }
}

/**
 * 텍스트(specifications / HTML)에서 크기·무게를 regex로 빠르게 추출.
 * API 호출 없이 비용 0.
 */
export function parseSizeFromText(text: string): SizeInfo | null {
  // 무게: "500g", "1.2kg", "무게: 350g", "중량 200g"
  const wMatch = text.match(
    /(?:무게|중량|weight)[^\d]{0,10}([\d.]+)\s*(kg|g)\b/i
  ) ?? text.match(/\b([\d.]+)\s*(kg|g)\b(?=[^a-zA-Z]|$)/i);

  let weight_g: number | null = null;
  if (wMatch) {
    const v = parseFloat(wMatch[1]);
    weight_g = wMatch[2].toLowerCase() === "kg" ? Math.round(v * 1000) : v;
  }

  // 크기: "280×200×150mm", "28cm x 20cm x 15cm", "가로 28 세로 20 높이 15cm"
  const d3 = text.match(
    /([\d.]+)\s*[×xX*]\s*([\d.]+)\s*[×xX*]\s*([\d.]+)\s*(mm|cm)/i
  );
  let width_cm = null, length_cm = null, height_cm = null;
  if (d3) {
    const factor = d3[4].toLowerCase() === "mm" ? 0.1 : 1;
    [width_cm, length_cm, height_cm] = [d3[1], d3[2], d3[3]].map(v => Math.round(parseFloat(v) * factor * 10) / 10);
  }

  if (weight_g == null && width_cm == null) return null;

  return {
    weight_g, width_cm, length_cm, height_cm,
    source: "text",
    confidence: "high",
  };
}

/**
 * 크기 추출 메인 함수.
 *  1. specifications 텍스트 → regex (무료)
 *  2. HTML 전체 텍스트 → regex (무료)
 *  3. 상세 이미지 OCR → Claude Vision (폴백)
 */
export async function extractSizeInfo({
  html,
  specifications,
  productUrl,
}: {
  html: string;
  specifications?: Record<string, string> | null;
  productUrl: string;
}): Promise<SizeInfo> {
  const EMPTY: SizeInfo = {
    weight_g: null, width_cm: null, length_cm: null, height_cm: null,
    source: "none", confidence: "low",
  };

  // 1. specifications 텍스트에서 regex 추출
  if (specifications && Object.keys(specifications).length > 0) {
    const specText = Object.entries(specifications)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n");
    const result = parseSizeFromText(specText);
    if (result) {
      console.info("[size] 스펙 텍스트에서 크기 추출 성공");
      return result;
    }
  }

  // 2. HTML 텍스트에서 regex 추출 (태그 제거 후)
  const bodyText = html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ");
  const textResult = parseSizeFromText(bodyText);
  if (textResult) {
    console.info("[size] HTML 텍스트에서 크기 추출 성공");
    return { ...textResult, confidence: "medium" };
  }

  // 3. 이미지 OCR 폴백
  const imageUrls = extractDetailImageUrls(html, productUrl);
  if (imageUrls.length === 0) {
    console.info("[size] 상세 이미지 없음 — 크기 미추출");
    return EMPTY;
  }

  console.info(`[size] 텍스트에서 크기 없음 — 이미지 OCR 시도 (후보 ${imageUrls.length}개)`);
  return extractSizeFromImages(imageUrls);
}

export async function parseProductFromResponse({
  url,
  responseBody,
  recipe,
}: {
  url: string;
  responseBody: string;
  recipe: SiteRecipe;
}): Promise<ProductData> {
  const content = [
    `Product page URL: ${url}`,
    `Domain: ${recipe.domain}`,
    recipe.api
      ? `API options path: ${recipe.api.response_options_path} | name field: ${recipe.api.option_name_field} | values field: ${recipe.api.option_values_field}`
      : "",
    `\nRAW API RESPONSE:\n${responseBody.slice(0, 15_000)}`,
    `\nExtract ALL product info. Return JSON:\n${PARSE_SCHEMA}`,
  ].filter(Boolean).join("\n");

  const response = await client().messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 4_000,
    system: PARSE_SYSTEM,
    messages: [{ role: "user", content }],
  });

  const text = response.content[0].type === "text" ? response.content[0].text : "{}";
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    console.warn("[claude] parseProductFromResponse: no JSON, returning stub");
    return { title: "", options: [] };
  }
  return JSON.parse(jsonMatch[0]) as ProductData;
}
