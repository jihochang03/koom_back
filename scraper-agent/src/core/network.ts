// Network tab recorder — mirrors Intuned's .intuned-agent/tab_*/network/ output
import { Page } from "playwright";
import fs from "fs";
import path from "path";

export interface NetworkEntry {
  timestamp: string;
  id: string;
  method: string;
  url: string;
  status: number;
  size: number;
  contentType: string;
  resourceType: string;
  requestHeaders?: Record<string, string>;
  requestBody?: string;
  responseBody?: string;
}

export class NetworkRecorder {
  private entries: NetworkEntry[] = [];
  private outputDir: string;

  constructor(outputDir: string) {
    this.outputDir = outputDir;
    fs.mkdirSync(path.join(outputDir, "request_bodies"), { recursive: true });
  }

  attach(page: Page): void {
    page.on("response", async (response) => {
      try {
        const request = response.request();
        const resourceType = request.resourceType();

        // Skip assets that don't carry product data
        if (["image", "font", "stylesheet", "media"].includes(resourceType)) return;

        const id = Math.random().toString(36).slice(2, 8);
        const contentType = response.headers()["content-type"] ?? "";

        let responseBody: string | undefined;
        if (contentType.includes("json") || contentType.includes("text")) {
          try {
            responseBody = await response.text();
            fs.writeFileSync(
              path.join(this.outputDir, "request_bodies", `${id}.body`),
              responseBody
            );
          } catch {
            // Body already consumed — skip
          }
        }

        let requestBody: string | undefined;
        const method = request.method();
        if (method === "POST" || method === "PUT" || method === "PATCH") {
          requestBody = request.postData() ?? undefined;
          if (requestBody) {
            fs.writeFileSync(
              path.join(this.outputDir, "request_bodies", `${id}.request`),
              requestBody
            );
          }
        }

        // Capture headers that hint at API keys / auth patterns (skip sensitive values)
        const rawHeaders = request.headers();
        const requestHeaders: Record<string, string> = {};
        for (const [k, v] of Object.entries(rawHeaders)) {
          const lower = k.toLowerCase();
          if (lower === "cookie" || lower === "authorization") {
            requestHeaders[k] = v.slice(0, 20) + "…[redacted]";
          } else if (!["accept-encoding", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"].includes(lower)) {
            requestHeaders[k] = v;
          }
        }

        const bodyLen = responseBody?.length ?? 0;
        const entry: NetworkEntry = {
          timestamp: new Date().toISOString(),
          id,
          method,
          url: response.url(),
          status: response.status(),
          size: bodyLen,
          contentType,
          resourceType,
          requestHeaders,
          requestBody,
          responseBody,
        };

        this.entries.push(entry);
        this.appendLog(entry);
      } catch {
        // Ignore individual entry errors
      }
    });
  }

  private appendLog(e: NetworkEntry): void {
    const bodyRef = e.responseBody ? ` → ${e.id}.body` : "";
    const line = `[${e.timestamp}] #${e.id} ${e.method} ${e.url} ${e.status} | ${e.size} | ${e.contentType} | ${e.resourceType}${bodyRef}\n`;
    fs.appendFileSync(path.join(this.outputDir, "requests.txt"), line);
  }

  // Returns only JSON API / GraphQL responses — highest signal for product data
  getApiEntries(): NetworkEntry[] {
    return this.entries.filter(
      (e) =>
        (e.contentType.includes("json") || e.url.includes("graphql")) &&
        e.status >= 200 &&
        e.status < 300 &&
        e.responseBody
    );
  }

  getAllEntries(): NetworkEntry[] {
    return [...this.entries];
  }
}
