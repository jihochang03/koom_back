/**
 * CAPTCHA Solver Library — extensible handler-based CAPTCHA detection and solving.
 *
 * Usage:
 *   const solver = new CaptchaSolver();
 *   solver.register(myCustomHandler);  // optional: add site-specific handlers
 *   const tool = solver.createTool(askUserFn);
 *   // inject tool into runAgentLoop
 *
 * Built-in handlers (tried in order):
 *   NaverCaptchaHandler  — Naver image CAPTCHA (known selectors)
 *   VisionCaptchaHandler — Generic fallback via Claude Vision
 */
import Anthropic from "@anthropic-ai/sdk";
import { Page } from "playwright";
import fs from "fs";
import os from "os";
import path from "path";
import type { AgentTool } from "./agent-core";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface CaptchaAnalysis {
  handlerName: string;
  captchaType: string;        // "math" | "image_text" | "naver" | "checkbox" | "unknown"
  interpretation: string;     // 사람이 읽을 수 있는 설명: "수학 문제: 3 + 4 = ?"
  answer: string;             // 제안된 정답
  inputSelector: string;      // 입력 필드 CSS selector
  submitSelector?: string;    // 제출 버튼 CSS selector (없으면 Enter)
  screenshotBase64: string;
  screenshotPath: string;     // 임시 저장된 스크린샷 경로
}

/**
 * Implement this interface to add a new CAPTCHA type.
 * Register with solver.register(handler) — higher priority handlers should be registered last.
 */
export interface CaptchaHandler {
  name: string;
  /** Returns true if this handler thinks a CAPTCHA is present. */
  detect(html: string): boolean;
  /**
   * Analyze the CAPTCHA and return a proposed solution.
   * Return null if this handler cannot handle this specific CAPTCHA.
   */
  analyze(
    page: Page,
    screenshotBase64: string,
    client: Anthropic
  ): Promise<CaptchaAnalysis | null>;
  /**
   * Execute the solution (fill input, click submit).
   * Returns true if submission succeeded (CAPTCHA element gone after submit).
   */
  solve(page: Page, analysis: CaptchaAnalysis): Promise<boolean>;
}

/** Return "confirm" to proceed, "reject" to try a different handler. */
export type AskUserFn = (analysis: CaptchaAnalysis) => Promise<"confirm" | "reject">;

// ── Claude Vision CAPTCHA analysis ────────────────────────────────────────────

const CAPTCHA_ANALYSIS_SYSTEM = `You are a CAPTCHA analysis expert.
Given a screenshot, determine if a CAPTCHA is present and how to solve it.
Respond with ONLY a JSON object, no markdown fences.`;

interface VisionResponse {
  has_captcha: boolean;
  captcha_type: "math" | "image_text" | "checkbox" | "slider" | "naver" | "unknown";
  interpretation: string;   // Korean description: "수학 문제: 3 + 4 = ? → 답: 7"
  answer: string;
  input_selector: string;   // Best CSS selector guess for the answer input field
  submit_selector: string;  // Best CSS selector guess for the submit button (or "")
  confidence: "high" | "medium" | "low";
}

async function analyzeWithClaude(
  screenshotBase64: string,
  html: string,
  client: Anthropic
): Promise<VisionResponse | null> {
  try {
    const response = await client.messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 1_000,
      system: CAPTCHA_ANALYSIS_SYSTEM,
      messages: [
        {
          role: "user",
          content: [
            { type: "image", source: { type: "base64", media_type: "image/png", data: screenshotBase64 } },
            {
              type: "text",
              text: `HTML snippet (first 3000 chars):\n${html.slice(0, 3000)}\n\nReturn JSON with fields:
{
  "has_captcha": boolean,
  "captcha_type": "math|image_text|checkbox|slider|naver|unknown",
  "interpretation": "한국어로 캡차 설명 및 답",
  "answer": "정답 문자열",
  "input_selector": "CSS selector for the answer input",
  "submit_selector": "CSS selector for submit button (empty string if Enter works)",
  "confidence": "high|medium|low"
}`,
            },
          ],
        },
      ],
    });

    const text = response.content[0].type === "text" ? response.content[0].text : "";
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;
    return JSON.parse(jsonMatch[0]) as VisionResponse;
  } catch {
    return null;
  }
}

// ── Shared solve helper ────────────────────────────────────────────────────────

async function performSolve(page: Page, analysis: CaptchaAnalysis): Promise<boolean> {
  try {
    // Find and fill input
    const input = await page.$(analysis.inputSelector);
    if (!input) {
      // Fallback: first visible text/number input
      const fallbackInput = await page.$('input[type="text"]:visible, input[type="number"]:visible, input:not([type]):visible');
      if (!fallbackInput) return false;
      await fallbackInput.fill(analysis.answer);
    } else {
      await input.fill(analysis.answer);
    }

    await page.waitForTimeout(300);

    // Submit
    if (analysis.submitSelector) {
      const btn = await page.$(analysis.submitSelector);
      if (btn) await btn.click();
      else await page.keyboard.press("Enter");
    } else {
      await page.keyboard.press("Enter");
    }

    await page.waitForTimeout(2_000);

    // Verify CAPTCHA is gone (simple heuristic: check if input selector still exists)
    const stillThere = await page.$(analysis.inputSelector);
    return !stillThere;
  } catch {
    return false;
  }
}

// ── Built-in: Naver CAPTCHA handler ───────────────────────────────────────────

export const NaverCaptchaHandler: CaptchaHandler = {
  name: "NaverCaptcha",

  detect(html: string): boolean {
    return /captcha|naver.*captcha|chk_captcha|captchaKey/i.test(html) &&
           /naver\.com/i.test(html);
  },

  async analyze(page, screenshotBase64, client): Promise<CaptchaAnalysis | null> {
    const html = await page.content();
    const vision = await analyzeWithClaude(screenshotBase64, html, client);
    if (!vision?.has_captcha) return null;

    // Naver-specific known selectors (override vision guess if found)
    const naverInputCandidates = [
      '#captcha_answer', 'input[name="captcha"]', 'input[name="chk_captcha"]',
      '.captcha_input input', '#captchaAnswer',
    ];
    let inputSelector = vision.input_selector || naverInputCandidates[0];
    for (const sel of naverInputCandidates) {
      if (await page.$(sel)) { inputSelector = sel; break; }
    }

    const screenshotPath = saveTempScreenshot(screenshotBase64);
    return {
      handlerName: "NaverCaptcha",
      captchaType: "naver",
      interpretation: vision.interpretation,
      answer: vision.answer,
      inputSelector,
      submitSelector: vision.submit_selector || undefined,
      screenshotBase64,
      screenshotPath,
    };
  },

  async solve(page, analysis): Promise<boolean> {
    return performSolve(page, analysis);
  },
};

// ── Built-in: Generic Vision CAPTCHA handler (catch-all) ──────────────────────

export const VisionCaptchaHandler: CaptchaHandler = {
  name: "VisionCaptcha",

  detect(_html: string): boolean {
    // Always returns true — this is the fallback handler
    return true;
  },

  async analyze(page, screenshotBase64, client): Promise<CaptchaAnalysis | null> {
    const html = await page.content();
    const vision = await analyzeWithClaude(screenshotBase64, html, client);
    if (!vision?.has_captcha) return null;

    const screenshotPath = saveTempScreenshot(screenshotBase64);
    return {
      handlerName: "VisionCaptcha",
      captchaType: vision.captcha_type,
      interpretation: vision.interpretation,
      answer: vision.answer,
      inputSelector: vision.input_selector || 'input[type="text"]',
      submitSelector: vision.submit_selector || undefined,
      screenshotBase64,
      screenshotPath,
    };
  },

  async solve(page, analysis): Promise<boolean> {
    return performSolve(page, analysis);
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function saveTempScreenshot(base64: string): string {
  const p = path.join(os.tmpdir(), `captcha-${Date.now()}.png`);
  fs.writeFileSync(p, Buffer.from(base64, "base64"));
  return p;
}

// ── CaptchaSolver ─────────────────────────────────────────────────────────────

export class CaptchaSolver {
  private handlers: CaptchaHandler[] = [NaverCaptchaHandler, VisionCaptchaHandler];
  private client: Anthropic | null = null;

  private getClient(): Anthropic {
    if (!this.client) this.client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    return this.client;
  }

  /**
   * Register a custom CAPTCHA handler.
   * Handlers added later take priority over earlier ones.
   */
  register(handler: CaptchaHandler): this {
    // Insert before VisionCaptcha fallback (always last)
    this.handlers.splice(this.handlers.length - 1, 0, handler);
    return this;
  }

  /**
   * Main solve flow:
   * 1. Take screenshot
   * 2. Try each applicable handler → get analysis
   * 3. Call askUser for confirmation
   * 4. On confirm: solve + verify
   * 5. On reject: try next handler or give up
   */
  async solve(page: Page, askUser: AskUserFn): Promise<{ success: boolean; message: string }> {
    const buf = await page.screenshot({ type: "png", fullPage: false });
    const screenshotBase64 = buf.toString("base64");
    const html = await page.content();

    const applicableHandlers = this.handlers.filter(h => h.detect(html));

    for (const handler of applicableHandlers) {
      const analysis = await handler.analyze(page, screenshotBase64, this.getClient());
      if (!analysis) continue;

      const decision = await askUser(analysis);
      if (decision === "reject") continue;

      const success = await handler.solve(page, analysis);
      if (success) {
        return { success: true, message: `CAPTCHA solved via ${handler.name}` };
      }
      // solve failed — tell caller so agent can report to user
      return {
        success: false,
        message: `${handler.name}: 제출했지만 CAPTCHA가 해결되지 않았습니다. 다른 입력/방법이 필요할 수 있습니다.`,
      };
    }

    return { success: false, message: "적합한 CAPTCHA 핸들러를 찾을 수 없습니다." };
  }

  /**
   * Create a solve_captcha AgentTool bound to a specific Playwright Page getter.
   * Use this when the page may not exist at tool creation time.
   */
  createBoundTool(getPage: () => Promise<Page>, askUser: AskUserFn): AgentTool {
    const solver = this;
    return {
      name: "solve_captcha",
      description:
        "CAPTCHA가 현재 페이지에 있을 때 호출합니다. " +
        "스크린샷을 찍어 Claude Vision으로 분석하고, 사용자에게 해석을 확인한 뒤 자동으로 답을 입력합니다. " +
        "해결에 실패하면 그 이유를 반환합니다. " +
        "solve에 실패한 경우 사용자에게 캡차 종류를 물어보고 register_captcha_handler를 호출해 새 핸들러를 추가하세요.",
      input_schema: {
        type: "object" as const,
        properties: {
          hint: {
            type: "string",
            description: "CAPTCHA에 대한 힌트 (선택). 예: '수학 계산', '이미지 텍스트 입력'",
          },
        },
      },
      execute: async (_input: Record<string, unknown>): Promise<string> => {
        const p = await getPage();
        const result = await solver.solve(p, askUser);
        return result.message;
      },
    };
  }
}

// ── Convenience: build CLI-friendly askUser from readline ──────────────────────

export function createCliAskUser(
  promptFn: (q: string) => Promise<string>
): AskUserFn {
  return async (analysis: CaptchaAnalysis): Promise<"confirm" | "reject"> => {
    console.log("\n" + "═".repeat(64));
    console.log(`🔍  CAPTCHA 감지 — 핸들러: ${analysis.handlerName} (${analysis.captchaType})`);
    console.log(`📸  스크린샷 저장됨: ${analysis.screenshotPath}`);
    console.log(`💡  해석: ${analysis.interpretation}`);
    console.log(`✏️   입력할 답: "${analysis.answer}"  (입력란: ${analysis.inputSelector})`);
    console.log("═".repeat(64));
    const ans = await promptFn("이 해석이 맞나요? 맞으면 자동으로 답을 입력합니다. [y/n] > ");
    return ans.toLowerCase().startsWith("y") ? "confirm" : "reject";
  };
}
