/**
 * Template Builder Agent
 * URL을 받아 tools로 페이지를 탐색하고, Python 스크레이퍼 코드를 생성·실행·저장.
 * 사용자 피드백을 받아 반복 개선하는 다중 턴 대화 지원.
 */
import Anthropic from "@anthropic-ai/sdk";
import path from "path";
import fs from "fs";
import { spawn } from "child_process";
import { collectHTML } from "../core/local-collector";
import { getCategory } from "../categories";

/** Windows CP949 깨짐 방지 — spawn으로 raw Buffer 수집 후 UTF-8 디코딩 */
function runPythonUtf8(
  exe: string,
  args: string[],
  opts: { timeout: number; cwd: string }
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(exe, args, {
      cwd: opts.cwd,
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
    });

    const chunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    child.stdout.on("data", (d: Buffer) => chunks.push(d));
    child.stderr.on("data", (d: Buffer) => errChunks.push(d));

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("Python 실행 시간 초과"));
    }, opts.timeout);

    child.on("close", () => {
      clearTimeout(timer);
      resolve({
        stdout: Buffer.concat(chunks).toString("utf-8"),
        stderr: Buffer.concat(errChunks).toString("utf-8"),
      });
    });
    child.on("error", (err) => { clearTimeout(timer); reject(err); });
  });
}

let _client: Anthropic | null = null;
const client = () => {
  if (!_client) _client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return _client;
};

export const TEMPLATES_DIR = path.resolve(__dirname, "../../templates");

// ── Session state (HTML + network log 세션별 보관) ────────────────────────────

interface SessionState {
  html: string;
  networkLog: Array<{ url: string; body: string; ct?: string }>;
  pageUrl: string;
  lastCode: string;
  updatedAt: number;
}
const _sessions = new Map<string, SessionState>();

export function getSession(id: string): SessionState | undefined {
  return _sessions.get(id);
}

export function setSession(id: string, state: SessionState) {
  _sessions.set(id, state);
  // 1시간 이상 된 세션 정리
  const now = Date.now();
  for (const [k, v] of _sessions) {
    if (now - v.updatedAt > 3_600_000) _sessions.delete(k);
  }
}

// ── Tools ─────────────────────────────────────────────────────────────────────

const TOOL_DEFS: Anthropic.Messages.Tool[] = [
  {
    name: "collect_page",
    description:
      "로컬 수집 서버로 페이지를 수집합니다. HTML과 네트워크 로그를 반환합니다.\n" +
      "mode 선택:\n" +
      "- simple: 브라우저 없이 plain requests (가장 빠름). blocked=true면 chrome으로 재시도\n" +
      "- chrome: undetected_chromedriver Chrome (봇 우회, 대부분 통함)\n" +
      "- naver: 네이버/스마트스토어 전용 Chrome 프로필\n" +
      "첫 방문 사이트는 반드시 simple 먼저 시도. 실패 시 chrome, 네이버 계열이면 naver.",
    input_schema: {
      type: "object" as const,
      properties: {
        url:  { type: "string", description: "수집할 페이지 URL" },
        mode: {
          type: "string",
          enum: ["simple", "chrome", "naver"],
          description: "수집 방식. 생략 시 simple",
        },
      },
      required: ["url"],
    },
  },
  {
    name: "grep_html",
    description:
      "수집된 HTML에서 정규식 패턴을 검색합니다. 옵션·가격·제목 관련 HTML 구조 파악에 사용하세요.",
    input_schema: {
      type: "object" as const,
      properties: {
        pattern: { type: "string", description: "검색할 정규식 패턴" },
        context_lines: { type: "number", description: "매칭 전후 컨텍스트 줄 수 (기본 2)" },
        max_results: { type: "number", description: "최대 결과 수 (기본 20)" },
      },
      required: ["pattern"],
    },
  },
  {
    name: "get_html_section",
    description:
      "CSS 셀렉터로 HTML의 특정 섹션을 추출합니다. 옵션 컨테이너, 가격 영역 등 확인에 사용하세요.",
    input_schema: {
      type: "object" as const,
      properties: {
        selector: { type: "string", description: "CSS 셀렉터 (예: '.option_wrap', '#product-price')" },
        max_chars: { type: "number", description: "반환할 최대 문자 수 (기본 3000)" },
      },
      required: ["selector"],
    },
  },
  {
    name: "inspect_network",
    description:
      "캡처된 fetch/XHR 응답 목록을 조회합니다. 옵션·가격 API 엔드포인트 탐색에 사용하세요.",
    input_schema: {
      type: "object" as const,
      properties: {
        url_filter: { type: "string", description: "URL에 포함된 문자열로 필터링 (예: 'product', 'option')" },
        max_body_chars: { type: "number", description: "응답 본문 최대 표시 문자 수 (기본 2000)" },
        max_entries: { type: "number", description: "최대 표시 항목 수 (기본 10)" },
      },
    },
  },
  {
    name: "run_code",
    description:
      "Python 스크레이퍼 코드를 실제로 실행해 결과를 반환합니다. 코드는 반드시 scrape(url) 함수를 포함해야 합니다.",
    input_schema: {
      type: "object" as const,
      properties: {
        code: { type: "string", description: "실행할 Python 스크레이퍼 코드" },
        url: { type: "string", description: "테스트할 URL" },
      },
      required: ["code", "url"],
    },
  },
  {
    name: "save_template",
    description:
      "검증된 스크레이퍼 코드를 templates/ 폴더에 저장합니다. run_code로 성공 확인 후 호출하세요.",
    input_schema: {
      type: "object" as const,
      properties: {
        domain: { type: "string", description: "사이트 도메인 (예: smartstore.naver.com)" },
        page_type: { type: "string", enum: ["detail", "list", "both"], description: "페이지 유형" },
        code: { type: "string", description: "저장할 Python 코드" },
        notes: { type: "string", description: "템플릿 설명 (옵셔널)" },
      },
      required: ["domain", "page_type", "code"],
    },
  },
  {
    name: "click_and_capture",
    description:
      "지정한 CSS 셀렉터들을 순서대로 클릭한 뒤 HTML과 네트워크 로그를 반환합니다. " +
      "셀렉터는 배열 순서대로 실행되며 각 클릭 사이에 wait_ms만큼 대기합니다. " +
      "2단계 아코디언(선택1 항목 클릭 → 선택2 열기)은 [선택1_sel, 선택2_accordion_sel] 처럼 배열에 순서대로 넣으세요. " +
      "network_log에 클릭으로 트리거된 XHR/fetch 요청이 포함됩니다 — 옵션 API URL이 있으면 Python에서 직접 활용하세요. " +
      "new_signals > 0 이면 DOM에 새 옵션이 나타났다는 의미입니다. " +
      "성공한 셀렉터는 save_site_knowledge의 extra_clicks에 저장하세요.",
    input_schema: {
      type: "object" as const,
      properties: {
        url:       { type: "string",  description: "현재 수집 중인 페이지 URL" },
        selectors: { type: "array",   items: { type: "string" }, description: "클릭할 CSS 셀렉터 목록 (한 번에 최대 10개)" },
        wait_ms:   { type: "number",  description: "클릭 후 대기 시간 ms (기본 600)" },
      },
      required: ["url", "selectors"],
    },
  },
  {
    name: "save_site_knowledge",
    description:
      "사이트별 수집 힌트를 수집 서버에 저장합니다. 다음에 같은 사이트 방문 시 자동 재사용됩니다.\n" +
      "반드시 access_method를 포함하세요: 이 사이트에 어떤 수집 방식이 통했는지 기록합니다.\n" +
      "- simple: requests.get 직접 통함\n" +
      "- chrome: undetected_chromedriver 필요\n" +
      "- naver: 네이버 전용 Chrome 프로필 필요",
    input_schema: {
      type: "object" as const,
      properties: {
        domain: { type: "string", description: "사이트 도메인 (예: smartstore.naver.com)" },
        collection_info: {
          type: "object",
          description: "수집 힌트 객체",
          properties: {
            access_method: {
              type: "string",
              enum: ["simple", "chrome", "naver"],
              description: "이 사이트에 통한 수집 방식 (필수)",
            },
            notes: { type: "string" },
            extra_clicks: { type: "array", items: { type: "string" }, description: "클릭해야 할 CSS 셀렉터 목록" },
            wait_for_selector: { type: "string", description: "페이지 로드 후 대기할 셀렉터" },
            network_patterns: { type: "array", items: { type: "string" }, description: "옵션/가격 API URL 패턴" },
          },
          required: ["access_method"],
        },
      },
      required: ["domain", "collection_info"],
    },
  },
];

// ── Tool implementations ──────────────────────────────────────────────────────

async function toolCollectPage(
  { url, mode = "simple" }: { url: string; mode?: "simple" | "chrome" | "naver" },
  sessionId: string
): Promise<string> {
  const COLLECTOR_URL = process.env.COLLECTOR_URL ?? "http://localhost:18080";

  type SimpleCollectResult = {
    success: boolean;
    blocked?: boolean;
    html?: string;
    status_code?: number;
    product_info?: unknown;
    network_log?: unknown[];
  };

  // simple 모드: /collect/simple (브라우저 없음)
  if (mode === "simple") {
    let simpleResult: SimpleCollectResult | null = null;
    try {
      const resp = await fetch(`${COLLECTOR_URL}/collect/simple`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, raw: true }),  // 스크립트 포함 원본 HTML (grep 정확도 향상)
      });
      simpleResult = await resp.json() as SimpleCollectResult;
    } catch (e) {
      return `[심플 수집 실패] 수집 서버 연결 오류: ${e}\n→ chrome 모드로 재시도하세요.`;
    }

    if (!simpleResult?.success || simpleResult.blocked) {
      const reason = simpleResult?.status_code
        ? `HTTP ${simpleResult.status_code}`
        : "차단 감지";
      return (
        `[심플 차단] ${reason} — chrome 모드로 재시도 필요\n` +
        `collect_page(url="${url}", mode="chrome") 를 다음에 호출하세요.`
      );
    }

    // simple 성공 — 세션 저장 후 요약 반환
    const state = {
      html: simpleResult.html ?? "",
      networkLog: [] as Array<{ url: string; body: string; ct?: string }>,
      pageUrl: url,
      lastCode: _sessions.get(sessionId)?.lastCode ?? "",
      updatedAt: Date.now(),
    };
    setSession(sessionId, state);

    const info = simpleResult.product_info as Record<string, unknown> | null;
    return [
      `[심플 수집 성공] HTML ${Math.round((simpleResult.html?.length ?? 0) / 1024)}KB (script 포함)`,
      info ? `▶ HTML파서 선추출:\n${JSON.stringify(info, null, 2).slice(0, 1500)}` : "",
    ].filter(Boolean).join("\n");
  }

  // chrome / naver 모드: /collect/general (브라우저, raw=true로 스크립트 포함)
  let result: import("../core/local-collector").CollectResult | null = null;
  let optionTriggers: string[] = [];
  try {
    const resp = await fetch(`${COLLECTOR_URL}/collect/general`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, raw: true }),
      signal: AbortSignal.timeout(180_000),
    });
    if (resp.ok) {
      const data = await resp.json() as { success: boolean; html?: string; page_title?: string; final_url?: string; network_log?: Array<{ url: string; body: string; ct: string }>; option_triggers?: string[]; product_info?: unknown };
      if (data.success && data.html && data.html.length > 3_000) {
        result = { html: data.html, page_title: data.page_title ?? "", final_url: data.final_url ?? url, source_port: 18080, network_log: data.network_log ?? [], product_info: data.product_info as import("../core/local-collector").ParsedProductInfo | undefined };
        optionTriggers = data.option_triggers ?? [];
      }
    }
  } catch {}
  if (!result) return `[Chrome 수집 실패] 로컬 수집 서버에서 수집 실패 (URL: ${url})`;

  const state: SessionState = {
    html: result.html,
    networkLog: result.network_log ?? [],
    pageUrl: url,
    lastCode: _sessions.get(sessionId)?.lastCode ?? "",
    updatedAt: Date.now(),
  };
  setSession(sessionId, state);

  const netLen = state.networkLog.length;

  // 네트워크 로그 — 옵션/가격 관련 URL 우선, 최대 12개, 본문 일부 포함
  const OPTION_KEYS = ["option", "variant", "item", "sku", "quantity", "price", "product"];
  const prioritized = [
    ...state.networkLog.filter(e => OPTION_KEYS.some(k => e.url.toLowerCase().includes(k))),
    ...state.networkLog.filter(e => !OPTION_KEYS.some(k => e.url.toLowerCase().includes(k))),
  ].slice(0, 12);

  const netSummary = prioritized.map((e, i) =>
    `[${i + 1}] ${e.url}\n     CT:${e.ct ?? "?"} body(${e.body.length}): ${e.body.slice(0, 300)}`
  ).join("\n\n---\n");

  // HTML에서 주요 셀렉터 힌트 자동 감지
  const html = result.html;
  const selectorHints: string[] = [];
  const optionPatterns = [
    /class="([^"]*option[^"]*)"/i,
    /class="([^"]*variant[^"]*)"/i,
    /class="([^"]*swatch[^"]*)"/i,
    /class="([^"]*color[^"]*)"/i,
    /class="([^"]*size[^"]*)"/i,
  ];
  const seen = new Set<string>();
  for (const pat of optionPatterns) {
    const m = html.match(pat);
    if (m && !seen.has(m[1])) { seen.add(m[1]); selectorHints.push(`.${m[1].trim().split(" ")[0]}`); }
    if (selectorHints.length >= 4) break;
  }

  const iframeNote = html.includes("<!-- IFRAME ")
    ? "\n▶ iframe 콘텐츠 병합됨 (상세·리뷰가 iframe 안에 있던 경우 — HTML 하단 <!-- IFRAME ... --> 이후 참고)"
    : "";

  return [
    `수집 완료: HTML ${Math.round(html.length / 1024)}KB, 네트워크 ${netLen}개`,
    result.product_info ? `\n▶ HTML파서 선추출:\n${JSON.stringify(result.product_info, null, 2).slice(0, 1500)}` : "",
    selectorHints.length > 0 ? `\n▶ 옵션 관련 CSS 힌트: ${selectorHints.join(", ")}` : "",
    optionTriggers.length > 0 ? `\n▶ 클릭형 옵션 트리거 후보(셀렉터): ${optionTriggers.join(", ")}\n   → 옵션이 비어 보이면 click_and_capture로 이 셀렉터를 클릭해 펼친 뒤 추출하고, 템플릿에는 /collect/click 호출로 templatize` : "",
    iframeNote,
    netLen > 0 ? `\n▶ 네트워크 로그 (옵션/가격 우선):\n${netSummary}` : "",
  ].filter(Boolean).join("\n");
}

function toolGrepHtml(
  { pattern, context_lines = 3, max_results = 20 }: { pattern: string; context_lines?: number; max_results?: number },
  sessionId: string
): string {
  const state = _sessions.get(sessionId);
  if (!state?.html) return "[오류] 먼저 collect_page를 호출하세요.";

  const lines = state.html.split("\n");
  let re: RegExp;
  try { re = new RegExp(pattern, "i"); } catch { return `[오류] 잘못된 정규식: ${pattern}`; }

  // minified HTML은 한 줄이 수십 KB일 수 있어 줄당 길이를 제한 (컨텍스트 폭발 방지)
  const LINE_CAP = 600;
  const clip = (s: string) => (s.length > LINE_CAP ? s.slice(0, LINE_CAP) + "…" : s);
  const matches: string[] = [];
  for (let i = 0; i < lines.length && matches.length < max_results; i++) {
    if (re.test(lines[i])) {
      const start = Math.max(0, i - context_lines);
      const end   = Math.min(lines.length - 1, i + context_lines);
      matches.push(`--- 줄 ${i + 1} ---`);
      matches.push(lines.slice(start, end + 1).map(clip).join("\n"));
    }
  }
  return matches.length > 0
    ? matches.join("\n\n")
    : `패턴 '${pattern}'에 매칭되는 내용 없음`;
}

function toolGetHtmlSection(
  { selector, max_chars = 4000 }: { selector: string; max_chars?: number },
  sessionId: string
): string {
  const state = _sessions.get(sessionId);
  if (!state?.html) return "[오류] 먼저 collect_page를 호출하세요.";

  // 간단한 패턴 매칭 (class/id 기반)
  const classMatch = selector.match(/\.([a-zA-Z0-9_-]+)/);
  const idMatch    = selector.match(/#([a-zA-Z0-9_-]+)/);
  const tagMatch   = selector.match(/^([a-zA-Z][a-zA-Z0-9]*)/);

  let searchStr = classMatch
    ? `class="${classMatch[1]}`
    : idMatch
    ? `id="${idMatch[1]}"`
    : tagMatch
    ? `<${tagMatch[1]}`
    : selector;

  const idx = state.html.indexOf(searchStr);
  if (idx === -1) return `셀렉터 '${selector}'에 해당하는 요소를 찾지 못했습니다.`;

  const snippet = state.html.slice(Math.max(0, idx - 100), idx + max_chars);
  return `셀렉터 '${selector}' 주변 HTML:\n${snippet}`;
}

function toolInspectNetwork(
  { url_filter, max_body_chars = 2000, max_entries = 12 }: {
    url_filter?: string; max_body_chars?: number; max_entries?: number;
  },
  sessionId: string
): string {
  const state = _sessions.get(sessionId);
  if (!state) return "[오류] 먼저 collect_page를 호출하세요.";

  let entries = state.networkLog;
  if (url_filter) entries = entries.filter(e => e.url.includes(url_filter));
  entries = entries.slice(0, max_entries);

  if (entries.length === 0) return url_filter ? `'${url_filter}' 포함 URL 없음` : "네트워크 로그 없음";

  return entries.map((e, i) => [
    `[${i + 1}] ${e.url}`,
    `  Content-Type: ${e.ct ?? "unknown"}`,
    `  응답 (${e.body.length}자): ${e.body.slice(0, max_body_chars)}`,
  ].join("\n")).join("\n\n---\n\n");
}

async function toolRunCode(
  { code, url }: { code: string; url: string },
  sessionId: string
): Promise<string> {
  const tmpFile = path.join(TEMPLATES_DIR, `.tmp_run_${sessionId.slice(-8)}.py`);
  fs.mkdirSync(TEMPLATES_DIR, { recursive: true });

  // UTF-8 헤더 + main 실행 블록 주입
  const utf8Header = "import sys; sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')\n";
  const hasMain = code.includes("if __name__");
  const codeWithMain = hasMain
    ? code
    : code + `\n\nif __name__ == "__main__":\n    _url = sys.argv[1] if len(sys.argv) > 1 else ""\n    _r = scrape(_url)\n    print(__import__("json").dumps(_r, ensure_ascii=False, indent=2))\n`;
  const fullCode = utf8Header + codeWithMain;

  fs.writeFileSync(tmpFile, fullCode, "utf-8");

  // 세션에 마지막 코드 저장
  const state = _sessions.get(sessionId);
  if (state) { state.lastCode = code; state.updatedAt = Date.now(); }

  try {
    const pythonExe = process.env.PYTHON_EXE ?? "python";
    const { stdout, stderr } = await runPythonUtf8(
      pythonExe,
      [tmpFile, url],
      { timeout: 60_000, cwd: path.resolve(__dirname, "../../") }
    );
    fs.unlinkSync(tmpFile);

    const output = stdout.trim();
    const errOut = stderr.trim();

    // TODO(token): run_code 출력 3000→1500자, 오류 1500→800자 축소
    if (!output && errOut) return `[실행 오류]\n${errOut.slice(0, 800)}`;

    return [
      output ? `[실행 결과]\n${output.slice(0, 1500)}` : "",
      errOut ? `[경고/로그]\n${errOut.slice(0, 300)}` : "",
    ].filter(Boolean).join("\n\n");
  } catch (err: unknown) {
    try { fs.unlinkSync(tmpFile); } catch {}
    const detail = err instanceof Error ? err.message : String(err);
    return `[실행 실패]\n${detail.slice(0, 800)}`;
  }
}

async function toolClickAndCapture(
  { url, selectors, wait_ms = 600 }: { url: string; selectors: string[]; wait_ms?: number },
  sessionId: string
): Promise<string> {
  const COLLECTOR_URL = process.env.COLLECTOR_URL ?? "http://localhost:18080";
  try {
    const resp = await fetch(`${COLLECTOR_URL}/collect/click`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, selectors, wait_ms }),
    });
    if (!resp.ok) return `[click_and_capture] 서버 오류: ${resp.status}`;
    const d = await resp.json() as {
      clicked: string[]; option_signals_before: number; option_signals_after: number;
      new_signals: number; html: string;
      network_log?: Array<{ url: string; body: string; ct?: string }>;
    };

    // 세션 HTML + 네트워크 로그 업데이트
    const state = _sessions.get(sessionId);
    if (state) {
      if (d.html) { state.html = d.html; }
      if (d.network_log?.length) {
        state.networkLog = [...state.networkLog, ...d.network_log].slice(-60);
      }
      state.updatedAt = Date.now();
    }

    // 클릭 후 발생한 네트워크 요청 요약
    const netLog = d.network_log ?? [];
    const optionApis = netLog
      .filter(e => /option|variant|sku|item|combination|product/i.test(e.url))
      .slice(0, 5)
      .map(e => `  ${e.url}  →  ${e.body.slice(0, 200)}`);

    const summary = [
      `클릭 성공: ${d.clicked.join(", ") || "없음"}`,
      `옵션 신호: ${d.option_signals_before} → ${d.option_signals_after} (+${d.new_signals})`,
      d.new_signals > 0 ? "✓ 새 옵션 발견됨 — grep_html로 확인 후 save_site_knowledge에 extra_clicks 저장하세요" : "DOM 변화 없음",
      netLog.length > 0
        ? `클릭 후 네트워크 요청 ${netLog.length}개:\n` +
          (optionApis.length > 0
            ? `▶ 옵션 관련 API:\n${optionApis.join("\n")}`
            : netLog.slice(0, 3).map(e => `  ${e.url}`).join("\n"))
        : "클릭 후 네트워크 요청 없음 (동적 로드 없음)",
    ].join("\n");
    return summary;
  } catch (e) {
    return `[click_and_capture] 실패: ${e}`;
  }
}

async function toolSaveSiteKnowledge(
  { domain, collection_info }: { domain: string; collection_info: Record<string, unknown> }
): Promise<string> {
  const COLLECTOR_URL = process.env.COLLECTOR_URL ?? "http://localhost:18080";
  try {
    const resp = await fetch(`${COLLECTOR_URL}/api/knowledge/${encodeURIComponent(domain)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ collection: collection_info }),
    });
    if (!resp.ok) return `[save_site_knowledge] 서버 오류: ${resp.status}`;
    const data = await resp.json() as Record<string, unknown>;
    return `[save_site_knowledge] 저장 완료: ${domain}\n${JSON.stringify(data.data, null, 2).slice(0, 400)}`;
  } catch (e) {
    return `[save_site_knowledge] 연결 실패 (수집 서버가 실행 중인지 확인): ${e}`;
  }
}

function addMainBlockIfMissing(code: string): string {
  const hasJsonMain =
    /if\s+__name__\s*==\s*['"]__main__['"]/m.test(code) &&
    /json\.dumps/m.test(code);
  if (hasJsonMain) return code;
  return (
    code +
    `\n\nif __name__ == "__main__":\n` +
    `    import sys as _sys, json as _json\n` +
    `    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""\n` +
    `    _result = scrape(_url)\n` +
    `    print(_json.dumps(_result, ensure_ascii=False))\n`
  );
}

function toolSaveTemplate(
  { domain, page_type, code, notes }: { domain: string; page_type: string; code: string; notes?: string },
): string {
  fs.mkdirSync(TEMPLATES_DIR, { recursive: true });
  const filename = `${domain.replace(/[^a-zA-Z0-9._-]/g, "_")}_${page_type}.py`;
  const outPath = path.join(TEMPLATES_DIR, filename);

  const notesLines = notes
    ? notes.split("\n").map((l, i) => (i === 0 ? `# Notes: ${l}` : `# ${l}`)).join("\n")
    : "";
  const header = [
    `# Template: ${domain} (${page_type})`,
    `# Generated: ${new Date().toISOString()}`,
    notesLines,
    "",
  ].filter(Boolean).join("\n") + "\n";

  const finalCode = addMainBlockIfMissing(code);
  fs.writeFileSync(outPath, header + finalCode, "utf-8");
  return `템플릿 저장 완료: ${outPath}`;
}

// ── System prompt (카테고리별 동적 생성) ─────────────────────────────────────

function buildSystemPrompt(category?: string | null, pageType?: string | null): string {
  const cat = getCategory(category);

  const pageTypeLabel = pageType === 'list' ? '목록 페이지'
    : pageType === 'detail' ? '상세(단일 상품) 페이지'
    : pageType === 'both' ? '목록 + 상세 페이지 모두'
    : null;

  return `당신은 Python 웹 스크레이퍼 코드 생성 전문가입니다.
주어진 URL의 페이지를 분석해 재사용 가능한 Python 스크레이퍼 코드를 만드세요.
현재 카테고리: **${cat.name}**${pageTypeLabel ? `\n대상 페이지 유형: **${pageTypeLabel}**` : ''}

## 탐색 원칙
가능한 많은 정보를 수집해야 정확한 템플릿을 만들 수 있습니다. 필요한 만큼 탐색하세요.
- collect_page 반환값의 선추출 결과, 네트워크 로그, CSS 힌트를 먼저 확인하세요.
- 구조가 불분명하면 grep_html로 찾고, 컨텍스트가 더 필요하면 get_html_section으로 상세 확인하세요.
- **script 태그 안 JSON 데이터도 grep으로 찾을 수 있습니다** (raw HTML 반환 됨).
- inspect_network로 옵션/가격 API를 찾아 정확한 데이터 소스를 파악하세요.
- run_code 결과에서 None/빈값이 있으면 해당 필드에 집중해 추가 탐색하세요.

## 접근 방식 선택 — 반드시 이 순서로

사이트마다 필요한 수집 방식이 다릅니다. 3단계 순서로 시도하고, 성공한 방식을 기억하세요.

| mode | 방식 | Python 코드 패턴 |
|------|------|-----------------|
| simple | requests.get 직접 (브라우저 없음) | \`requests.get(url, headers={...})\` |
| chrome | undetected_chromedriver Chrome | \`requests.post("http://localhost:18080/collect/general", ...)\` |
| naver | 네이버 전용 Chrome 프로필 | \`requests.post("http://localhost:18080/collect/general", ...)\` |

**선택 기준:**
1. 항상 **simple 먼저** — collect_page(url, mode="simple")
   - 결과에 "[심플 차단]"이 있으면 → chrome으로 재시도
   - 네이버 계열(smartstore.naver.com, shopping.naver.com 등) → 바로 naver
2. simple 차단 → **chrome** — collect_page(url, mode="chrome")
3. chrome도 실패 + 네이버 계열 → **naver** — collect_page(url, mode="naver")

**save_site_knowledge에 반드시 access_method 저장:**
\`\`\`
save_site_knowledge(domain, { access_method: "simple" | "chrome" | "naver", ... })
\`\`\`

## 워크플로우 — ★ 절대 규칙: "저장 먼저(SAVE-FIRST), 보강은 나중"
당신의 예산은 약 18스텝. **저장(save_template) 없이 끝나면 무조건 실패**입니다. 과탐색이 가장 흔한 실패 원인.

**절대 규칙 (어기지 말 것):**
- **탐색(grep/section/inspect)은 첫 run_code 전까지 최대 3회.** 3회를 쓰면 무조건 코드를 쓰고 run_code.
- run_code에서 [A](title·가격·shipping_fee_text)가 나오면 **바로 그 다음 스텝에서 save_template + save_site_knowledge** (= 핵심부터 확보). 보강은 그 뒤에.
- **title 검증**: title에 판매자명·카테고리·사이트명이 들어가면 잘못된 것 → 상품명 셀렉터를 고쳐라(예: og:title, JSON-LD name, h1 상품명). 판매자명이 title이 되지 않게 주의.
- 같은 필드를 여러 번 grep 금지. 한 필드 막히면 비워두고 진행.

1. collect_page(url, mode="simple") — 우선 브라우저 없이 시도
   - "[심플 차단]" → collect_page(url, mode="chrome") 재시도 · 네이버 계열 → mode="naver"
2. **선추출(product_info)** 먼저 확인. 핵심이 있으면 탐색 없이 바로 3번. (탐색은 위 절대규칙대로 최대 3회)
3. **Python 코드 작성 → run_code** (가진 정보로 일단. 완벽하지 않아도 됨)
4. **[A] 나오면 즉시 save_template + save_site_knowledge** (보강 전에 먼저 저장!)
5. 저장 후 남는 예산으로만 [B] 보강: 비어 있는 [B] 필드 **하나당 grep/section/inspect_network 1회** → 코드 수정 → run_code → **다시 save_template로 갱신**.
   - 옵션이 클릭으로만 나타나면 click_and_capture 사용.
   - 예산이 부족하면 [B] 일부는 비운 채 저장해도 된다. **저장 못 하는 것보다 핵심만이라도 저장이 낫다.**

## 추출 목표 — "보이는 건 다 뽑는다" (단, 4번 저장 이후 보강 단계에서)
[A] 항상 필수 (없으면 실패): title / (price_original 또는 price_discounted) / shipping_fee_text

## 가격 추출 — 가장 중요. HTML에서 반드시 찾아낼 것
두 가격(할인가 + 정가)이 있으면 둘 다 추출. 하나뿐이면 price_discounted에 저장.
한국 쇼핑몰 공통 패턴 (이 중 하나는 반드시 해당됨):
- .price01 / .price02 — 보통 price01=할인가(낮은 숫자), price02=정가(높은 숫자)
- .sale-price / .original-price / .regular-price / .normal-price
- .selling-price / .consumer-price / .market-price / .real-price / .final-price
- .dc-price / .discount-price / [class*="sale"] + [class*="price"]
- del 또는 s 태그 — 거의 항상 정가(취소선 가격)
- .salePercent / [class*="discount"] / "% 할인" 텍스트 근처에 항상 가격 쌍이 있음
- data-sale-price / data-price / data-original-price 속성
- JSON-LD ("offers": {"price": ...}) — script[type="application/ld+json"] 에서 추출
- 두 숫자 중 큰 것 = 정가, 작은 것 = 할인가. 확신 없으면 grep_html로 price 클래스 주변 HTML 확인.
[B] 페이지에 보이면 채운다 (저장 후 보강, 예산 내에서):
- options: 옵션 선택 UI(드롭다운·색상·사이즈·수량)가 있으면 **모든 그룹·값**. JSON-LD로 가격을 얻더라도 **옵션은 HTML/네트워크에서 별도 추출**(JSON-LD엔 옵션이 없는 경우가 많음).
- images: **og:image 1장에서 끝내지 말 것** — 썸네일·갤러리·상세 이미지까지 최대 10장. 중복 제거, 썸네일은 고해상도로 보정, // → https: 보정.
- brand / rating(0~5 실수)·review_count(정수) / delivery_date(도착·발송 안내) / seller / specifications(필수표기정보 표 dict)
- 선추출(product_info)에 값이 있으면(shipping_period·brand·rating 등) **그대로 사용**하고 직접 파싱과 병합.
- ★ **HTML/product_info에 없으면 = 네트워크 API에서 온 것.** inspect_network로 해당 API 응답을 찾고, **템플릿 코드에서 \`data["network_log"]\`(=[{url,body,ct}])를 url 패턴으로 찾아 json.loads(body)로 파싱**한다. (리뷰·평점·이미지 갤러리·옵션·재고가 대표적). 브라우저가 이미 호출·캡처했으니 별도 인증 불필요 — 이 방식까지 **반드시 템플릿화**할 것.

## 탐색 결정 기준 (엄격히 — 과탐색이 가장 흔한 실패 원인)
- 선추출(product_info)에 핵심이 있으면 → **탐색 0회**, 바로 코드 작성
- 네트워크 API가 보이면 → inspect_network 1회
- 구조 불분명 → grep_html은 **필드당 1회**, 같은 목적으로 반복 금지
- **코드를 한 번도 안 썼는데 탐색 4회를 넘기지 말 것** — 즉시 run_code로 전환
${cat.templateHints}

## 생성할 Python 코드 규칙
- 필수 함수: scrape(url: str) -> dict
- 반환 dict 키: ${cat.templateKeys}
- requests + BeautifulSoup 사용${pageType === 'list' ? '\n- 목록 페이지: 반드시 items 배열 반환 (각 항목 title, url 포함), 페이지네이션 처리 포함' : pageType === 'detail' ? '\n- 상세 페이지: 단일 상품 정보 dict 반환' : pageType === 'both' ? '\n- URL이 목록이면 items 배열, 상세이면 단일 상품 dict 반환하도록 분기 처리' : ''}

### access_method별 HTML 수집 코드
**simple** (access_method="simple"):
\`\`\`python
import requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}
resp = requests.get(url, headers=HEADERS, timeout=15)
html = resp.text
\`\`\`

**chrome / naver** (access_method="chrome" or "naver"):
\`\`\`python
import requests
data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
html = data.get("html", "")
net_log = data.get("network_log", [])   # 브라우저가 캡처한 fetch/XHR 응답 [{url, body, ct}]
\`\`\`
- 수집 서버는 페이지를 **끝까지 스크롤**해 지연로딩(갤러리·리뷰·평점)을 트리거하고, 그때 발생한 API 응답을 \`network_log\`로 함께 돌려준다. **HTML에 없는 데이터는 거의 다 여기 있다.**

- 클릭 필요 시: POST http://localhost:18080/collect/click {"url": url, "selectors": [...]}
- 성공한 access_method에 맞는 패턴을 코드에 사용할 것

## 사용자 피드백 처리
- 피드백이 들어오면 해당 부분만 수정 후 run_code 1회 재검증
- 일반 피드백(정보 틀렸어, 빠졌어): 탐색 없이 코드만 수정
- 구조 피드백(클릭해야 해, 2단계야 등): click_and_capture 1회 허용 후 코드 재작성

## 설명 방식
- 발견한 내용을 한국어로 1-2줄 간략히 설명
- 코드 블록은 \`\`\`python 으로 감싸서 표시`;
}

// ── Agentic loop ──────────────────────────────────────────────────────────────

export interface TemplateBuilderCallbacks {
  onStatus?: (msg: string) => void;
  onText?: (chunk: string) => void;
  onToolCall?: (name: string, input: Record<string, unknown>) => void;
  onToolResult?: (name: string, preview: string) => void;
  onCode?: (code: string) => void;
  onExtraction?: (data: Record<string, unknown>) => void;
  onDone?: (messages: Anthropic.Messages.MessageParam[]) => void;
}

// TODO(token): 오래된 tool_result를 요약으로 압축 — 히스토리 크기 제한
function pruneHistory(messages: Anthropic.Messages.MessageParam[]): Anthropic.Messages.MessageParam[] {
  const KEEP_RECENT = 8; // 최근 N개 메시지는 원본 유지
  if (messages.length <= KEEP_RECENT) return messages;

  const old    = messages.slice(0, messages.length - KEEP_RECENT);
  const recent = messages.slice(messages.length - KEEP_RECENT);

  const pruned = old.map(msg => {
    if (msg.role !== "user" || !Array.isArray(msg.content)) return msg;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const content = (msg.content as any[]).map(block => {
      if (
        block.type === "tool_result" &&
        typeof block.content === "string" &&
        block.content.length > 400
      ) {
        return { ...block, content: `[${block.content.length}자 결과 — 이전 턴 처리됨]` };
      }
      return block;
    });
    return { ...msg, content };
  });

  return [...pruned, ...recent];
}

/** 첫 번째 유저 메시지에서 URL을 추출해 기존 템플릿 코드를 반환 (없으면 null) */
function loadExistingTemplateForMessages(
  messages: Anthropic.Messages.MessageParam[],
): { domain: string; code: string; filename: string } | null {
  const firstUser = messages.find(m => m.role === "user");
  if (!firstUser) return null;
  const text = typeof firstUser.content === "string"
    ? firstUser.content
    : (firstUser.content as Array<{ type: string; text?: string }>)
        .filter(b => b.type === "text").map(b => b.text ?? "").join(" ");
  const urlMatch = text.match(/https?:\/\/[^\s]+/);
  if (!urlMatch) return null;
  try {
    const domain = new URL(urlMatch[0]).hostname.replace(/^www\./, "");
    const candidates = [`${domain}_detail.py`, `${domain}_both.py`, `${domain}_list.py`];
    const templatePath = candidates.map(n => path.join(TEMPLATES_DIR, n)).find(p => fs.existsSync(p)) ?? null;
    if (!templatePath) return null;
    const code = fs.readFileSync(templatePath, "utf-8");
    return { domain, code, filename: path.basename(templatePath) };
  } catch {
    return null;
  }
}

export async function runTemplateBuilder(
  sessionId: string,
  messages: Anthropic.Messages.MessageParam[],
  callbacks: TemplateBuilderCallbacks = {},
  category?: string | null,
  pageType?: string | null,
): Promise<Anthropic.Messages.MessageParam[]> {
  const { onStatus, onText, onToolCall, onToolResult, onCode, onExtraction, onDone } = callbacks;
  const systemPrompt = buildSystemPrompt(category, pageType);

  // 첫 대화(히스토리 없음)일 때만 기존 템플릿을 주입
  const isFirstTurn = messages.length === 1;
  if (isFirstTurn) {
    const existing = loadExistingTemplateForMessages(messages);
    if (existing) {
      onStatus?.(`→ 기존 템플릿 발견: ${existing.filename} — 기존 동작 보존 + 누락된 신규 필드 추가(업그레이드)`);
      const inject = `\n\n[기존 템플릿 (${existing.filename})]:\n\`\`\`python\n${existing.code}\n\`\`\`\n` +
        `이 템플릿을 **증분 업그레이드**하세요 (처음부터 다시 만들지 말 것):\n` +
        `1. 먼저 run_code로 실행해 현재 출력에서 **비어 있거나 누락된 출력 키**를 확인합니다.\n` +
        `2. 위 시스템 지침의 [A]·[B] 필드 중 빠진 것을 **기존 코드에 추가**합니다. 특히 최근 추가된: ` +
        `size(/extract/size 호출), delivery_date, 이미지 갤러리(여러 장), brand·rating·review_count, specifications, ` +
        `그리고 HTML에 없으면 network_log API 파싱·iframe 콘텐츠. **이미 잘 나오는 필드의 셀렉터·로직은 그대로 보존**합니다.\n` +
        `3. 수정 후 run_code로 재검증 → save_template로 저장(+ 클릭형 옵션 발견 시 save_site_knowledge의 extra_clicks).\n` +
        `핵심: 기존 동작 유지 + 새 필드만 더하는 증분 업그레이드. 이미 모든 필드가 채워져 있으면 그대로 두고 저장만.`;
      const first = messages[0];
      const firstText = typeof first.content === "string" ? first.content : (first.content as Array<{type:string;text?:string}>).filter(b=>b.type==="text").map(b=>b.text??"").join("");
      messages = [{ role: "user", content: firstText + inject }];
    }
  }

  let iterations = 0;
  const maxIter = 18;
  let savedTemplate = false;

  while (iterations++ < maxIter) {
    const response = await client().messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 6_000,
      system: [{ type: "text", text: systemPrompt, cache_control: { type: "ephemeral" } }] as Anthropic.Messages.TextBlockParam[],
      tools: [
        ...TOOL_DEFS.slice(0, -1),
        { ...TOOL_DEFS[TOOL_DEFS.length - 1], cache_control: { type: "ephemeral" } },
      ] as Anthropic.Messages.Tool[],
      // TODO(token): 매 턴 히스토리 프루닝으로 컨텍스트 크기 제한
      messages: pruneHistory(messages),
    });

    const assistantContent: Anthropic.Messages.ContentBlock[] = [];
    const toolUses: Anthropic.Messages.ToolUseBlock[] = [];

    for (const block of response.content) {
      assistantContent.push(block);
      if (block.type === "text" && block.text.trim()) {
        onText?.(block.text);

        // 코드 블록 감지
        const codeMatch = block.text.match(/```python\s*([\s\S]*?)```/);
        if (codeMatch) onCode?.(codeMatch[1].trim());
      }
      if (block.type === "tool_use") toolUses.push(block);
    }

    messages = [...messages, { role: "assistant", content: assistantContent }];

    if (response.stop_reason === "end_turn" || toolUses.length === 0) break;

    const toolResults: Anthropic.Messages.ToolResultBlockParam[] = [];

    for (const tu of toolUses) {
      const input = tu.input as Record<string, unknown>;
      onToolCall?.(tu.name, input);
      onStatus?.(`🔧 ${tu.name}(${briefInput(input)})`);

      let result = "";
      try {
        switch (tu.name) {
          case "collect_page":
            result = await toolCollectPage(
              { url: input.url as string, mode: (input.mode as "simple" | "chrome" | "naver") ?? "simple" },
              sessionId
            );
            break;
          case "grep_html":
            result = toolGrepHtml(input as Parameters<typeof toolGrepHtml>[0], sessionId);
            break;
          case "get_html_section":
            result = toolGetHtmlSection(input as Parameters<typeof toolGetHtmlSection>[0], sessionId);
            break;
          case "inspect_network":
            result = toolInspectNetwork(input as Parameters<typeof toolInspectNetwork>[0], sessionId);
            break;
          case "run_code": {
            result = await toolRunCode(
              { code: input.code as string, url: input.url as string },
              sessionId
            );
            // 실행 결과가 JSON이면 onExtraction 발행
            const jsonMatch = result.match(/\[실행 결과\]\s*([\s\S]*)/);
            if (jsonMatch) {
              try {
                const parsed = JSON.parse(jsonMatch[1].trim());
                onExtraction?.(parsed);
              } catch {}
            }
            break;
          }
          case "save_template": {
            const saveInput = { ...(input as Parameters<typeof toolSaveTemplate>[0]) };
            if (pageType && ["detail", "list", "both"].includes(pageType)) {
              saveInput.page_type = pageType as "detail" | "list" | "both";
            }
            result = toolSaveTemplate(saveInput);
            savedTemplate = true;
            break;
          }
          case "click_and_capture":
            result = await toolClickAndCapture(
              input as Parameters<typeof toolClickAndCapture>[0],
              sessionId
            );
            break;
          case "save_site_knowledge":
            result = await toolSaveSiteKnowledge(
              input as Parameters<typeof toolSaveSiteKnowledge>[0]
            );
            break;
          default:
            result = `Unknown tool: ${tu.name}`;
        }
      } catch (err) {
        result = `[tool error] ${err instanceof Error ? err.message : String(err)}`;
      }

      onToolResult?.(tu.name, result.slice(0, 200));
      // 컨텍스트 폭발 방지: 단일 tool_result 상한 (iframe 병합/minified HTML grep 등이 거대해질 수 있음)
      const MAX_RESULT_CHARS = 16_000;
      const capped = result.length > MAX_RESULT_CHARS
        ? result.slice(0, MAX_RESULT_CHARS) + `\n…(결과 ${result.length}자 중 앞 ${MAX_RESULT_CHARS}자만 표시 — 더 좁은 패턴/셀렉터로 재시도)`
        : result;
      toolResults.push({ type: "tool_result", tool_use_id: tu.id, content: capped });
    }

    messages = [...messages, { role: "user", content: toolResults }];

    // 수렴 안전망: 예산 임박했는데 아직 저장 안 했으면 "지금 저장" 강제 넛지
    if (!savedTemplate && iterations >= maxIter - 3) {
      messages = [...messages, {
        role: "user",
        content:
          "⏰ 남은 스텝이 거의 없습니다. 추가 탐색을 멈추고, 지금까지 확인한 정보만으로 " +
          "scrape() 코드를 완성해 run_code로 한 번 검증한 뒤 **즉시 save_template + save_site_knowledge로 저장**하세요. " +
          "title·가격이 비면 og:title / JSON-LD / 메타태그로라도 채우고, 나머지는 비워둔 채 저장해도 됩니다.",
      }];
    }
  }

  onDone?.(messages);
  return messages;
}

function briefInput(input: Record<string, unknown>): string {
  return Object.entries(input)
    .filter(([k]) => k !== "code")
    .map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 50)}`)
    .join(", ");
}
