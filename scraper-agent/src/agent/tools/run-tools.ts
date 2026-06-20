import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { PROJECT_ROOT } from "./file-tools";
import type { AgentTool } from "../../core/agent-core";

const RUNNER_TEMPLATE = `
import { chromium } from "playwright";
const handler = require("HANDLER_PATH").default;

(async () => {
  const params = PARAMS_JSON;
  const browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    const result = await handler(params, page, context);
    console.log("__RESULT__" + JSON.stringify(result, null, 2));
  } catch (err: any) {
    console.error("__ERROR__" + String(err?.message ?? err));
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
`;

export const runApiTool: AgentTool = {
  name: "run_api",
  description: "Execute a handler file with given params and return the scraped result. Use to test generated code.",
  input_schema: {
    type: "object" as const,
    properties: {
      file: { type: "string" },
      params: { type: "object" },
    },
    required: ["file", "params"],
  },
  execute: async ({ file, params }: Record<string, unknown>): Promise<string> => {
    const handlerPath = path.resolve(PROJECT_ROOT, file as string);
    if (!fs.existsSync(handlerPath)) return `[run_api] File not found: ${file}`;

    const runnerPath = path.join(PROJECT_ROOT, "__agent_runner__.ts");
    fs.writeFileSync(
      runnerPath,
      RUNNER_TEMPLATE
        .replace("HANDLER_PATH", handlerPath.replace(/\\/g, "/"))
        .replace("PARAMS_JSON", JSON.stringify(params ?? {})),
      "utf-8"
    );

    return new Promise((resolve) => {
      const proc = spawn(
        "npx",
        ["ts-node", "--project", path.join(PROJECT_ROOT, "tsconfig.json"), runnerPath],
        { cwd: PROJECT_ROOT, shell: true, timeout: 60_000 }
      );
      let stdout = "", stderr = "";
      proc.stdout.on("data", (d) => { stdout += d; });
      proc.stderr.on("data", (d) => { stderr += d; });
      proc.on("close", (code) => {
        try { fs.unlinkSync(runnerPath); } catch {}
        if (stdout.includes("__RESULT__")) {
          const result = stdout.slice(stdout.indexOf("__RESULT__") + 10);
          resolve(`[run_api] ✓ exit ${code}\n${result.slice(0, 4_000)}`);
        } else if (stdout.includes("__ERROR__")) {
          resolve(`[run_api] ✗ Error:\n${stdout.slice(stdout.indexOf("__ERROR__") + 9)}\n${stderr.slice(0, 500)}`);
        } else {
          resolve(`[run_api] exit ${code}\nstdout: ${stdout.slice(0, 2_000)}\nstderr: ${stderr.slice(0, 500)}`);
        }
      });
    });
  },
};

export const allRunTools: AgentTool[] = [runApiTool];
