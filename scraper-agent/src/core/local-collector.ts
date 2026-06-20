// Calls the local collector server (collector/server.py)
// which uses undetected_chromedriver for proper bot evasion.
// Auto-starts the Python server if not already running.
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const COLLECTOR_PORT = 18080;
const HEALTH_TIMEOUT_MS = 2_000;
const COLLECT_TIMEOUT_MS = 180_000;
const START_TIMEOUT_MS = 90_000;  // Chrome startup can take a while

const SERVER_SCRIPT = path.resolve(__dirname, "../../collector/server.py");
const COLLECTOR_DIR = path.resolve(__dirname, "../../collector");

// dk project venv — reuse its packages so we don't need a separate install
const DK_VENV_PYTHON = "D:\\문서\\4-2\\볼트랩\\dk\\.venv\\Scripts\\python.exe";

export interface NetworkLogEntry {
  url: string;
  body: string;
  ct: string;
}

export interface ProductOption {
  option_type: string;
  available_values: string[];
  selected_value?: string;
  option_prices?: Record<string, number>;
  soldout_values?: string[];
  option_images?: Record<string, string>;
  option_titles?: Record<string, string>;
}

export interface ParsedProductInfo {
  title?: string;
  original_price?: number;
  discounted_price?: number;
  discount_rate?: number;
  main_image_url?: string;
  shipping_fee?: number;
  shipping_period?: string;
  product_options?: ProductOption[];
  sold_out?: boolean;
  [key: string]: unknown;
}

export interface CollectResult {
  html: string;
  page_title: string;
  final_url: string;
  source_port: number;
  network_log: NetworkLogEntry[];
  product_info?: ParsedProductInfo;
}

let _serverProcess: ChildProcess | null = null;

async function fetchJSON(url: string, options: RequestInit, timeoutMs: number): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (res.status === 503) {
      const body = await res.json().catch(() => ({})) as { busy?: boolean };
      const err = new Error("HTTP 503") as Error & { busy: boolean };
      err.busy = body.busy === true;
      throw err;
    }
    if (res.status === 504) {
      throw new Error("수집 타임아웃 (90초 초과) — 페이지가 너무 복잡하거나 봇 차단 중입니다.");
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// Find a usable Python executable that has the required packages
function findPython(): string | null {
  // 1st: dk project venv (already has undetected_chromedriver installed)
  if (fs.existsSync(DK_VENV_PYTHON)) return DK_VENV_PYTHON;

  // 2nd: system python3 / python
  const candidates = ["python", "python3"];
  const { execSync } = require("child_process");
  for (const cmd of candidates) {
    try {
      execSync(`${cmd} --version`, { stdio: "ignore" });
      return cmd;
    } catch {}
  }
  return null;
}

// Check if the local server is alive
export async function isServerAlive(): Promise<boolean> {
  try {
    await fetchJSON(`http://127.0.0.1:${COLLECTOR_PORT}/health`, {}, HEALTH_TIMEOUT_MS);
    return true;
  } catch {
    return false;
  }
}

// Wait for the server to become healthy (polls every 2s up to timeoutMs)
async function waitForServer(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isServerAlive()) return true;
    await new Promise((r) => setTimeout(r, 2_000));
  }
  return false;
}

// Start collector/server.py as a background subprocess.
// No-op if already running. Returns true if server is ready.
export async function startCollectorServer(): Promise<boolean> {
  if (await isServerAlive()) {
    console.info(`  ✓ 수집 서버 이미 실행 중 (포트 ${COLLECTOR_PORT})`);
    return true;
  }

  const python = findPython();
  if (!python) {
    console.warn("  ⚠  Python을 찾을 수 없습니다. 수집 서버를 시작할 수 없습니다.");
    return false;
  }

  if (!fs.existsSync(SERVER_SCRIPT)) {
    console.warn(`  ⚠  ${SERVER_SCRIPT} 없음. 수집 서버를 시작할 수 없습니다.`);
    return false;
  }

  console.info(`  → Python 수집 서버 시작 중... (${python})`);
  console.info(`  → Chrome 창이 열립니다. 잠시 기다려주세요...`);

  _serverProcess = spawn(python, [SERVER_SCRIPT], {
    cwd: COLLECTOR_DIR,
    env: { ...process.env, COLLECTOR_PORT: String(COLLECTOR_PORT), COLLECTOR_MAX_WORKERS: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });

  _serverProcess.stdout?.on("data", (d: Buffer) => {
    const line = d.toString().trim();
    if (line) process.stdout.write(`  [collector] ${line}\n`);
  });
  _serverProcess.stderr?.on("data", (d: Buffer) => {
    const line = d.toString().trim();
    if (line) process.stderr.write(`  [collector] ${line}\n`);
  });
  _serverProcess.on("exit", (code) => {
    if (code !== null && code !== 0) {
      console.error(`  ✗ 수집 서버 종료 (코드 ${code})`);
    }
    _serverProcess = null;
  });

  const ready = await waitForServer(START_TIMEOUT_MS);
  if (ready) {
    console.info(`  ✓ 수집 서버 준비 완료 (포트 ${COLLECTOR_PORT})`);
  } else {
    console.error(`  ✗ 수집 서버 시작 시간 초과 (${START_TIMEOUT_MS / 1000}초)`);
  }
  return ready;
}

// Stop the collector server if we started it
export function stopCollectorServer(): void {
  if (!_serverProcess) return;
  console.info("  → 수집 서버 종료 중...");
  try {
    _serverProcess.kill();
  } catch {}
  _serverProcess = null;
}

// Collect rendered HTML from the local server.
// Returns null if no server is available.
export async function collectHTML(url: string): Promise<CollectResult | null> {
  if (!(await isServerAlive())) {
    // Try once more with a slightly longer wait (server may be mid-startup)
    await new Promise((r) => setTimeout(r, 3_000));
    if (!(await isServerAlive())) return null;
  }

  // Retry up to 4 times when server is busy (Chrome slot occupied)
  const BUSY_RETRIES = 4;
  const BUSY_WAIT_MS = 8_000;

  for (let attempt = 0; attempt <= BUSY_RETRIES; attempt++) {
    try {
      const data = await fetchJSON(
        `http://127.0.0.1:${COLLECTOR_PORT}/collect/general`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        },
        COLLECT_TIMEOUT_MS
      ) as { success: boolean; html?: string; page_title?: string; final_url?: string; error?: string; network_log?: NetworkLogEntry[]; product_info?: ParsedProductInfo };

      if (data.success && data.html && data.html.length > 3_000) {
        return {
          html: data.html,
          page_title: data.page_title ?? "",
          final_url: data.final_url ?? url,
          source_port: COLLECTOR_PORT,
          network_log: data.network_log ?? [],
          product_info: data.product_info,
        };
      }

      if (!data.success) {
        console.warn(`  ⚠  수집 서버 실패: ${data.error}`);
      }
      break;
    } catch (e) {
      const isBusy = (e as { busy?: boolean }).busy === true;
      if (isBusy && attempt < BUSY_RETRIES) {
        console.warn(`  ⏳ 수집 서버 사용 중 — ${BUSY_WAIT_MS / 1000}초 후 재시도 (${attempt + 1}/${BUSY_RETRIES})`);
        await new Promise((r) => setTimeout(r, BUSY_WAIT_MS));
        continue;
      }
      console.warn(`  ⚠  수집 서버 오류: ${e instanceof Error ? e.message : e}`);
      break;
    }
  }

  return null;
}
