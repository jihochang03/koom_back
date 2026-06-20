/**
 * CLI Agent — wires up browser tools, file tools, captcha solver,
 * and runs the agentic loop for code generation tasks.
 *
 * Uses runAgentLoop from core/agent-core for the actual loop logic.
 */
import * as readline from "readline";
import { allFileTools, PROJECT_ROOT } from "./tools/file-tools";
import { allBrowserTools, closeBrowser, getActivePage } from "./tools/browser-tools";
import { allRunTools } from "./tools/run-tools";
import { runAgentLoop, AgentTool } from "../core/agent-core";
import { CaptchaSolver, createCliAskUser } from "../core/captcha-solver";

// ── readline helper ────────────────────────────────────────────────────────────

function prompt(q: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((res) => rl.question(q, (a) => { rl.close(); res(a); }));
}

// ── ask_user tool ──────────────────────────────────────────────────────────────

const askUserTool: AgentTool = {
  name: "ask_user",
  description: "Ask the user a yes/no question. Call this BEFORE write_file to confirm the plan.",
  input_schema: {
    type: "object" as const,
    properties: {
      question: { type: "string" },
      summary:  { type: "string" },
    },
    required: ["question", "summary"],
  },
  execute: async ({ question, summary }: Record<string, unknown>) => {
    console.log("\n" + "═".repeat(62));
    console.log("📋  " + summary);
    console.log("═".repeat(62));
    const ans = await prompt(`\n🤔  ${question} [y/n] > `);
    return ans.toLowerCase().startsWith("y") ? "yes" : "no";
  },
};

// ── CAPTCHA solver wired to readline + browser ─────────────────────────────────

const captchaSolver = new CaptchaSolver();
const captchaTool = captchaSolver.createBoundTool(getActivePage, createCliAskUser(prompt));

// ── System prompt ──────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are an expert web scraping development assistant.

Project root: ${PROJECT_ROOT}

## Workflow
1. list_files("src/modules/shopping/apis/*.ts") then read_file each to learn code style
2. navigate_browser to the target page, then take_screenshot + grep_html to map the DOM
3. If you see a CAPTCHA, call solve_captcha immediately — do NOT skip it
4. ask_user with a clear summary of what you'll build — WAIT for "yes" before writing
5. write_file the new handler in src/modules/shopping/apis/<name>.ts
6. run_api to test, fix if needed, then print a short PR-style summary

## CAPTCHA handling
- Call solve_captcha whenever you see a CAPTCHA challenge in the screenshot
- If solve_captcha reports failure, tell the user what type of CAPTCHA appeared
- Ask the user: "어떤 종류의 캡차인지 설명해주세요" — then document it and try again

## Code style rules
- imports from ../../../core/browser and ../../../core/runtime
- export default async function handler(params, page, context) { ... }
- Never write code before ask_user confirms`;

// ── Tool list ──────────────────────────────────────────────────────────────────

const ALL_TOOLS: AgentTool[] = [
  ...allFileTools,
  ...allBrowserTools,
  ...allRunTools,
  askUserTool,
  captchaTool,
];

// ── Public API ─────────────────────────────────────────────────────────────────

export async function runAgent(request: string): Promise<void> {
  console.log("\n🤖  Agent starting...\n");

  await runAgentLoop(
    [{ role: "user", content: request }],
    {
      systemPrompt: SYSTEM_PROMPT,
      tools: ALL_TOOLS,
      onText:       (t)    => console.log("\n💬  " + t),
      onToolCall:   (n, i) => console.log(`\n🔧  ${n}(${briefInput(i)})`),
      onToolResult: (n, r) => console.log(`   ↳  ${r.replace(/\n/g, " ").slice(0, 180)}${r.length > 180 ? "…" : ""}`),
      onDone:       ()     => console.log("\n✅  Agent done.\n"),
    }
  );

  await closeBrowser();
}

function briefInput(input: Record<string, unknown>): string {
  return Object.entries(input)
    .filter(([k]) => !["content", "code"].includes(k))
    .map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 60)}`)
    .join(", ");
}
