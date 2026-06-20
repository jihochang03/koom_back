import "dotenv/config";
import express, { Request, Response } from "express";
import cors from "cors";
import path from "path";
import crypto from "crypto";
import { startCollectorServer, stopCollectorServer } from "./core/local-collector";
import analyzeSiteHandler from "./modules/shopping/apis/analyze-site";
import { runTemplateBuilder } from "./agent/template-builder-agent";
import { enqueuePrefetch } from "./products/prefetch-queue";
import type Anthropic from "@anthropic-ai/sdk";

const DJANGO_BASE = process.env.DJANGO_BASE_URL ?? "http://localhost:8000";

const app = express();
app.use(cors());
app.use(express.json({ limit: "50mb" }));

// ── SSE helper ────────────────────────────────────────────────────────────────

function sseWriter(res: Response) {
  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();

  return {
    send(event: string, data: unknown) {
      res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    },
    end() { res.end(); },
  };
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.post("/api/analyze", async (req: Request, res: Response) => {
  const { url, category, template, templateName } = req.body as {
    url?: string;
    category?: string;
    template?: string;        // 고객사 DB에서 전달받은 템플릿 코드
    templateName?: string;    // 로깅용 템플릿 식별자
  };
  if (!url || !url.startsWith("http")) {
    res.status(400).json({ error: "유효한 URL이 필요합니다" });
    return;
  }

  const sse = sseWriter(res);

  try {
    const result = await analyzeSiteHandler(
      { url, category: category ?? "shopping", template, templateName },
      null,
      null,
      {
        onStatus: (msg) => sse.send("status", { message: msg.trim() }),
        onText:   (chunk) => sse.send("text", { chunk }),
      }
    );

    // 목록 결과: items 배열의 각 URL을 개별 상세 스크랩
    const rawResult = result as Record<string, unknown>;
    const listItems = rawResult.items;
    if (Array.isArray(listItems) && listItems.length > 0 && !rawResult.title) {
      sse.send("status", { message: `→ 목록 ${listItems.length}개 상품 상세 수집 시작` });
      const enriched: unknown[] = [];
      for (let i = 0; i < listItems.length; i++) {
        const item = listItems[i] as Record<string, unknown>;
        const itemUrl = typeof item.url === "string" ? item.url : null;
        if (!itemUrl) { enriched.push(item); continue; }

        sse.send("status", { message: `→ [${i + 1}/${listItems.length}] ${itemUrl}` });
        try {
          const detail = await analyzeSiteHandler(
            { url: itemUrl, category: category ?? "shopping" },
            null,
            null,
            { onStatus: (msg) => sse.send("status", { message: `  ${msg.trim()}` }) }
          );
          enriched.push(detail);
        } catch (err) {
          console.warn(`[list-detail] 실패 ${itemUrl}:`, err);
          enriched.push(item);
        }
      }
      sse.send("result", { ...rawResult, items: enriched });
    } else {
      sse.send("result", result);
    }
  } catch (err) {
    sse.send("error", { message: err instanceof Error ? err.message : String(err) });
  }

  sse.send("done", {});
  sse.end();
});

// ── Template builder (multi-turn) ────────────────────────────────────────────

app.post("/api/template/build", async (req: Request, res: Response) => {
  const { message, messages: history, session_id, category, page_type } = req.body as {
    message?: string;
    messages?: Anthropic.Messages.MessageParam[];
    session_id?: string;
    category?: string;
    page_type?: string;
  };

  if (!message) {
    res.status(400).json({ error: "message가 필요합니다" });
    return;
  }

  const sessionId = session_id ?? crypto.randomUUID();
  const sse = sseWriter(res);
  sse.send("session", { session_id: sessionId });

  // tool_result 내용이 너무 길면 잘라내기 (히스토리 크기 제한)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const trimmedHistory = (history ?? []).map((msg: any) => {
    if (msg.role !== "user" || !Array.isArray(msg.content)) return msg;
    const content = msg.content.map((block: any) => {
      // TODO(token): 클라이언트→서버 전송 시 tool_result 4000→800자 트리밍
      if (block.type === "tool_result" && typeof block.content === "string" && block.content.length > 800) {
        return { ...block, content: block.content.slice(0, 800) + "\n...(truncated)" };
      }
      return block;
    });
    return { ...msg, content };
  }) as Anthropic.Messages.MessageParam[];

  const messages: Anthropic.Messages.MessageParam[] = [
    ...trimmedHistory,
    { role: "user", content: message },
  ];

  try {
    const finalMessages = await runTemplateBuilder(sessionId, messages, {
      onStatus:    (msg)       => sse.send("status",     { message: msg }),
      onText:      (chunk)     => sse.send("text",       { chunk }),
      onToolCall:  (name, inp) => sse.send("tool_call",  { name, input: inp }),
      onToolResult:(name, pre) => sse.send("tool_result",{ name, preview: pre }),
      onCode:      (code)      => sse.send("code",       { code }),
      onExtraction:(data)      => sse.send("extraction", data),
    }, category, page_type);
    sse.send("messages", { messages: finalMessages });
  } catch (err) {
    sse.send("error", { message: err instanceof Error ? err.message : String(err) });
  }

  sse.send("done", {});
  sse.end();
});

// ── Products API ─────────────────────────────────────────────────────────────
// Proxy reads/writes to Django; crawl endpoints handled here.

async function djangoProxy(
  req: Request,
  res: Response,
  djangoPath: string,
  method: string,
  body?: unknown
): Promise<void> {
  try {
    const r = await fetch(`${DJANGO_BASE}${djangoPath}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const json = await r.json();
    res.status(r.status).json(json);
  } catch {
    res.status(503).json({ error: "Django 백엔드에 연결할 수 없습니다." });
  }
}

// List products (with optional ?category= and ?page= filters)
app.get("/api/products", async (req: Request, res: Response) => {
  const qs = new URLSearchParams(req.query as Record<string, string>).toString();
  const path = qs ? `/api/products/?${qs}` : "/api/products/";
  await djangoProxy(req, res, path, "GET");
});

// Batch save products from a list crawl result
app.post("/api/products/batch", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${DJANGO_BASE}/api/products/batch/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    const saved = await r.json() as Array<{ id: number; url: string }>;
    res.status(r.status).json(saved);

    // Enqueue background prefetch for each saved product
    if (r.ok && Array.isArray(saved)) {
      for (const p of saved) {
        enqueuePrefetch(p.id, p.url, DJANGO_BASE);
      }
    }
  } catch {
    res.status(503).json({ error: "Django 백엔드에 연결할 수 없습니다." });
  }
});

// Get distinct categories in use
app.get("/api/products/categories", async (req: Request, res: Response) => {
  await djangoProxy(req, res, "/api/products/categories/", "GET");
});

// Update category label on a product
app.patch("/api/products/:id/category", async (req: Request, res: Response) => {
  await djangoProxy(req, res, `/api/products/${req.params.id}/category/`, "PATCH", req.body);
});

// Reset detail_status to pending (re-queues prefetch)
app.post("/api/products/:id/refresh", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${DJANGO_BASE}/api/products/${req.params.id}/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const product = await r.json() as { id: number; url: string };
    res.status(r.status).json(product);

    if (r.ok && product?.id) {
      enqueuePrefetch(product.id, product.url, DJANGO_BASE);
    }
  } catch {
    res.status(503).json({ error: "Django 백엔드에 연결할 수 없습니다." });
  }
});

// Live detail crawl (SSE) — fresh crawl on user click, saves result to Django
app.post("/api/products/detail", async (req: Request, res: Response) => {
  const { id, url } = req.body as { id?: number; url?: string };
  if (!url || !url.startsWith("http")) {
    res.status(400).json({ error: "유효한 URL이 필요합니다" });
    return;
  }

  const sse = sseWriter(res);

  try {
    if (id) {
      await fetch(`${DJANGO_BASE}/api/products/${id}/detail/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detail_status: "prefetching", detail_data: {} }),
      });
    }

    const result = await analyzeSiteHandler(
      { url, category: "shopping" },
      null,
      null,
      {
        onStatus: (msg) => sse.send("status", { message: msg.trim() }),
        onText:   (chunk) => sse.send("text",   { chunk }),
      }
    );

    sse.send("result", result);

    if (id) {
      await fetch(`${DJANGO_BASE}/api/products/${id}/detail/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detail_status: "ready", detail_data: result }),
      });
    }
  } catch (err) {
    sse.send("error", { message: err instanceof Error ? err.message : String(err) });
    if (id) {
      await fetch(`${DJANGO_BASE}/api/products/${id}/detail/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ detail_status: "failed", detail_data: {} }),
      }).catch(() => {});
    }
  }

  sse.send("done", {});
  sse.end();
});

// ── Click-and-capture proxy ───────────────────────────────────────────────────

app.post("/api/collect/click", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${COLLECTOR_BASE}/collect/click`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    res.status(r.status).json(await r.json());
  } catch {
    res.status(503).json({ error: "수집 서버에 연결할 수 없습니다." });
  }
});

// ── Scrape with template (token-free when template exists) ───────────────────

app.get("/api/templates/db", async (_req: Request, res: Response) => {
  await djangoProxy(_req, res, "/api/templates/", "GET");
});

app.post("/api/scrape", async (req: Request, res: Response) => {
  const { url } = req.body as { url?: string };
  if (!url || !url.startsWith("http")) {
    res.status(400).json({ error: "유효한 URL이 필요합니다" });
    return;
  }

  const sse = sseWriter(res);

  // Django DB에서 해당 도메인 템플릿 조회
  let template: string | undefined;
  let templateDomain: string | undefined;
  try {
    const domain = new URL(url).hostname.replace(/^www\./, "");
    const tplRes = await fetch(`${DJANGO_BASE}/api/templates/${domain}/`);
    if (tplRes.ok) {
      const tpl = await tplRes.json() as { content?: string; domain?: string };
      if (tpl.content) {
        template = tpl.content;
        templateDomain = tpl.domain ?? domain;
        sse.send("template_found", { domain: templateDomain });
      }
    }
  } catch { /* no template — fall through to Claude */ }

  if (!template) {
    sse.send("template_not_found", {});
  }

  try {
    const result = await analyzeSiteHandler(
      { url, category: "shopping", template, templateName: templateDomain },
      null,
      null,
      {
        onStatus: (msg) => sse.send("status", { message: msg.trim() }),
        onText:   (chunk) => sse.send("text", { chunk }),
      }
    );
    sse.send("result", result);
  } catch (err) {
    sse.send("error", { message: err instanceof Error ? err.message : String(err) });
  }

  sse.send("done", {});
  sse.end();
});

// ── Templates API ─────────────────────────────────────────────────────────────

const TEMPLATES_DIR = path.resolve(__dirname, "../templates");

app.get("/api/templates", (_req: Request, res: Response) => {
  if (!fs.existsSync(TEMPLATES_DIR)) { res.json({ files: [] }); return; }
  const files = fs.readdirSync(TEMPLATES_DIR)
    .filter(f => f.endsWith(".py") || f.endsWith(".json"))
    .map(f => {
      const stat = fs.statSync(path.join(TEMPLATES_DIR, f));
      // Derive domain: strip trailing _detail / _list / _both + extension
      const base = f.replace(/\.(py|json)$/, "");
      const domain = base.replace(/_(detail|list|both)$/, "");
      return { filename: f, domain, size: stat.size, updated_at: stat.mtime.toISOString() };
    });
  res.json({ files });
});

app.get("/api/templates/:filename", (req: Request, res: Response) => {
  const filename = path.basename(String(req.params.filename));
  const full = path.join(TEMPLATES_DIR, filename);
  if (!fs.existsSync(full)) { res.status(404).json({ error: "없는 파일" }); return; }
  const content = fs.readFileSync(full, "utf-8");
  res.json({ filename, content });
});

app.delete("/api/templates/:filename", (req: Request, res: Response) => {
  const filename = path.basename(String(req.params.filename));
  const full = path.join(TEMPLATES_DIR, filename);
  if (!fs.existsSync(full)) { res.status(404).json({ error: "없는 파일" }); return; }
  fs.unlinkSync(full);
  res.json({ success: true });
});

// ── Site knowledge proxy → Flask collector ────────────────────────────────────

const COLLECTOR_BASE = `http://localhost:18080`;

app.get("/api/knowledge", async (_req: Request, res: Response) => {
  try {
    const r = await fetch(`${COLLECTOR_BASE}/api/knowledge`);
    res.json(await r.json());
  } catch {
    res.status(503).json({ error: "수집 서버에 연결할 수 없습니다." });
  }
});

app.get("/api/knowledge/:domain", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${COLLECTOR_BASE}/api/knowledge/${req.params.domain}`);
    res.status(r.status).json(await r.json());
  } catch {
    res.status(503).json({ error: "수집 서버에 연결할 수 없습니다." });
  }
});

app.post("/api/knowledge/:domain", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${COLLECTOR_BASE}/api/knowledge/${req.params.domain}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    res.status(r.status).json(await r.json());
  } catch {
    res.status(503).json({ error: "수집 서버에 연결할 수 없습니다." });
  }
});

app.delete("/api/knowledge/:domain", async (req: Request, res: Response) => {
  try {
    const r = await fetch(`${COLLECTOR_BASE}/api/knowledge/${req.params.domain}`, {
      method: "DELETE",
    });
    if (r.status === 204) {
      res.json({ success: true });
    } else {
      res.status(r.status).json(await r.json());
    }
  } catch {
    res.status(503).json({ error: "수집 서버에 연결할 수 없습니다." });
  }
});

// Serve built React app in production (only if dist exists)
import fs from "fs";
const WEB_DIST = path.resolve(__dirname, "../web/dist");
const WEB_INDEX = path.join(WEB_DIST, "index.html");
if (fs.existsSync(WEB_INDEX)) {
  app.use(express.static(WEB_DIST));
  app.use((_req: Request, res: Response) => {
    res.sendFile(WEB_INDEX);
  });
}

// ── Start ─────────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.WEB_PORT ?? "3000", 10);

async function main() {
  await startCollectorServer();

  app.listen(PORT, () => {
    const hasDist = fs.existsSync(WEB_INDEX);
    console.log(`\n  📡  API 서버: http://localhost:${PORT}/api/analyze`);
    if (hasDist) {
      console.log(`  🌐  웹 UI:    http://localhost:${PORT}`);
    } else {
      console.log(`  🌐  웹 UI:    http://localhost:5174  ← Vite dev 서버 (cd web && npm run dev)`);
    }
    console.log();
  });

  process.on("SIGINT", () => {
    stopCollectorServer();
    process.exit(0);
  });
}

main().catch(console.error);
