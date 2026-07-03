import Anthropic from "@anthropic-ai/sdk";
import crypto from "crypto";
import { findTemplate, runTemplate, mapToProductData } from "../../../core/template-runner";
import { runTemplateBuilder } from "../../../agent/template-builder-agent";
import { productStore } from "../../../products/product-store";

const COLLECTOR_URL = process.env.COLLECTOR_URL ?? "http://localhost:18080";

let _claude: Anthropic | null = null;
const claude = () => (_claude ??= new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY }));

async function collectPage(url: string): Promise<{ html: string } | null> {
  try {
    const resp = await fetch(`${COLLECTOR_URL}/collect/general`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!resp.ok) return null;
    const data = await resp.json() as { success?: boolean; html?: string };
    if (!data.success || !data.html) return null;
    return { html: data.html };
  } catch {
    return null;
  }
}

async function extractProductUrls(html: string, baseUrl: string): Promise<string[]> {
  const base = new URL(baseUrl);

  // Extract all same-domain hrefs
  const seen = new Set<string>();
  const hrefRe = /href\s*=\s*["']([^"'\s]+)["']/g;
  let m: RegExpExecArray | null;
  while ((m = hrefRe.exec(html)) !== null) {
    try {
      const abs = new URL(m[1], base.origin).href;
      if (new URL(abs).hostname === base.hostname) seen.add(abs);
    } catch { /* skip invalid urls */ }
  }

  const urlList = [...seen].slice(0, 400).join("\n");
  if (!urlList) return [];

  const resp = await claude().messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 4096,
    messages: [{
      role: "user",
      content: `다음 URL 목록에서 상품 상세 페이지 URL만 골라 JSON 배열로 반환하세요.
상품 상세 페이지: 단일 상품을 보여주는 페이지 (/products/123, /item/456, /goods/789, /vp/products/xxx 등)
제외할 것: 카테고리 목록, 검색 결과, 마이페이지, 장바구니, 로그인, 리뷰, 공지사항, 브랜드관 등

사이트: ${base.hostname}
URL 목록:
${urlList}

JSON 배열만 반환 (설명 없이):`,
    }],
  });

  const text = resp.content[0].type === "text" ? resp.content[0].text : "[]";
  const match = text.match(/\[[\s\S]*\]/);
  if (!match) return [];
  try {
    return (JSON.parse(match[0]) as string[]).filter(u => {
      try { new URL(u); return true; } catch { return false; }
    });
  } catch { return []; }
}

export async function crawlList(
  listUrl: string,
  category: string,
  onEvent: (event: string, data: unknown) => void
): Promise<void> {
  const domain = new URL(listUrl).hostname.replace(/^www\./, "");
  const emit = (event: string, data: unknown) => onEvent(event, data);

  // ─ Step 1: Collect listing page ───────────────────────────────────────────
  emit("status", { message: "목록 페이지 수집 중..." });
  const page = await collectPage(listUrl);
  if (!page) throw new Error("목록 페이지 수집 실패 — 수집 서버를 확인하세요");

  // ─ Step 2: Extract product URLs ───────────────────────────────────────────
  emit("status", { message: "상품 상세 URL 추출 중..." });
  const productUrls = await extractProductUrls(page.html, listUrl);
  if (productUrls.length === 0) throw new Error("상품 URL을 찾지 못했습니다 — 수동으로 확인하세요");

  emit("urls_found", { urls: productUrls, count: productUrls.length });
  emit("status", { message: `→ ${productUrls.length}개 상품 URL 발견` });

  // ─ Step 3: Find or build template ─────────────────────────────────────────
  let templatePath = findTemplate(domain);
  if (templatePath) {
    emit("status", { message: `→ 기존 템플릿 사용: ${domain}` });
    emit("template_done", { domain, reused: true });
  } else {
    emit("status", { message: "템플릿 없음 — 샘플 2개로 빌드 시작..." });
    const samples = productUrls.slice(0, 2);

    for (let i = 0; i < samples.length; i++) {
      emit("status", { message: `→ 샘플 [${i + 1}/${samples.length}] 빌드 중: ${samples[i].slice(0, 60)}` });
      try {
        await runTemplateBuilder(
          crypto.randomUUID(),
          [{ role: "user" as const, content: samples[i] }],
          {
            onStatus: (msg: string) => emit("status", { message: `  ${msg}` }),
            onText: () => {},
            onToolCall: () => {},
            onToolResult: () => {},
            onCode: () => {},
            onExtraction: () => {},
          },
          category,
          "detail"
        );
        templatePath = findTemplate(domain);
        if (templatePath) break;
      } catch (err) {
        emit("status", { message: `  ⚠ 빌드 오류: ${String(err).slice(0, 100)}` });
      }
    }

    if (templatePath) {
      emit("template_done", { domain, reused: false });
      emit("status", { message: `✓ 템플릿 저장 완료: ${domain}` });
    } else {
      throw new Error("템플릿 생성 실패 — Agent 탭에서 직접 빌드하세요");
    }
  }

  // ─ Step 4: Run template on all product URLs ────────────────────────────────
  const total = productUrls.length;
  let done = 0;

  for (const productUrl of productUrls) {
    emit("status", { message: `→ [${done + 1}/${total}] ${productUrl.slice(0, 70)}` });
    try {
      const raw = await runTemplate(templatePath!, productUrl);
      if (raw) {
        const data = mapToProductData(raw);
        const saved = productStore.upsert(productUrl, domain, data, listUrl);
        emit("product", saved);
      } else {
        emit("status", { message: `  ⚠ 결과 없음: ${productUrl.slice(0, 50)}` });
      }
    } catch (err) {
      emit("status", { message: `  ⚠ 실패: ${String(err).slice(0, 100)}` });
    }
    done++;
    emit("progress", { done, total });
  }
}
