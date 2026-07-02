/**
 * 저장된 Python 템플릿으로 페이지 정보를 추출.
 * templates/<domain>_detail.py 또는 _both.py 가 있으면 실행하고 결과를 반환.
 * 반환 타입은 카테고리에 따라 형태가 다르므로 Record<string, unknown> 으로 처리.
 * 쇼핑 카테고리용 ProductData 변환이 필요한 경우 mapToProductData() 를 별도 호출.
 */
import path from "path";
import fs from "fs";
import os from "os";
import { spawn } from "child_process";
import { ProductData } from "../modules/shopping/ai/claude";
import { TEMPLATES_DIR } from "../agent/template-builder-agent";

/**
 * 호출자(고객사 Django)가 전달한 템플릿 코드를 임시 파일로 실행.
 * 완료 후 임시 파일은 삭제.
 */
export async function runTemplateCode(
  code: string,
  name: string,
  url: string,
  onStatus?: (msg: string) => void,
): Promise<Record<string, unknown> | null> {
  const tmpFile = path.join(os.tmpdir(), `koom_tpl_${Date.now()}_${Math.random().toString(36).slice(2)}.py`);
  try {
    fs.writeFileSync(tmpFile, code, "utf-8");
    onStatus?.(`→ 전달된 템플릿 실행 중... (${name})`);
    return await runTemplate(tmpFile, url, onStatus);
  } finally {
    try { fs.unlinkSync(tmpFile); } catch {}
  }
}

// 도메인에 매칭되는 템플릿 파일 경로 반환 (없으면 null)
export function findTemplate(domain: string): string | null {
  const candidates = [
    `${domain}_detail.py`,
    `${domain}_both.py`,
    // www. 없는 버전
    `${domain.replace(/^www\./, "")}_detail.py`,
    `${domain.replace(/^www\./, "")}_both.py`,
  ];
  for (const name of candidates) {
    const p = path.join(TEMPLATES_DIR, name);
    if (fs.existsSync(p)) return p;
  }
  return null;
}

// Python 출력(dict) → ProductData 변환 (쇼핑 카테고리 전용)
export function mapToProductData(raw: Record<string, unknown>): ProductData {
  const priceO = raw.price_original as number | null | undefined;
  const priceD = raw.price_discounted as number | null | undefined;

  type RawOpt = { name?: string; values?: string[] };
  const options = ((raw.options as RawOpt[]) ?? [])
    .filter(o => Array.isArray(o.values) && o.values.length > 0)
    .map(o => ({ name: o.name ?? "옵션", values: o.values! }));

  return {
    title:             (raw.title as string) ?? "",
    description:       (raw.description as string) ?? null,
    price:             (priceO != null || priceD != null)
      ? { original: priceO ?? null, discounted: priceD ?? null, currency: "KRW" }
      : null,
    options,
    images:            (raw.images as string[]) ?? [],
    brand:             (raw.brand as string) ?? null,
    availability:      (raw.availability as ProductData["availability"]) ?? "unknown",
    shipping_fee:      (raw.shipping_fee as number) ?? null,
    shipping_fee_text: (raw.shipping_fee_text as string) ?? null,
    delivery_date:     (raw.delivery_date as string) ?? null,
    rating:            (raw.rating as number) ?? null,
    review_count:      (raw.review_count as number) ?? null,
    seller:            (raw.seller as string) ?? null,
    specifications:    (raw.specifications as Record<string, string>) ?? {},
    size:              (raw.size as ProductData["size"]) ?? null,
  };
}

/** scrape(url) 함수만 있고 __main__ 블록이 없는 템플릿에 실행 진입점을 추가 */
function ensureMainBlock(code: string): string {
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

// 템플릿 실행 → 원시 dict (실패 시 null)
export async function runTemplate(
  templatePath: string,
  url: string,
  onStatus?: (msg: string) => void,
): Promise<Record<string, unknown> | null> {
  const pythonExe = process.env.PYTHON_EXE ?? "python";
  onStatus?.(`→ 저장된 템플릿 실행 중... (${path.basename(templatePath)})`);

  // __main__ 블록 없는 템플릿은 래퍼 파일로 실행
  let runFile = templatePath;
  let tmpWrap: string | null = null;
  try {
    const code = fs.readFileSync(templatePath, "utf-8");
    const wrapped = ensureMainBlock(code);
    if (wrapped !== code) {
      tmpWrap = path.join(os.tmpdir(), `koom_wrap_${Date.now()}_${Math.random().toString(36).slice(2)}.py`);
      fs.writeFileSync(tmpWrap, wrapped, "utf-8");
      runFile = tmpWrap;
    }
  } catch (err) {
    console.warn(`[template-runner] 템플릿 읽기 실패: ${err}`);
    return null;
  }

  return new Promise((resolve) => {
    const cleanup = () => { if (tmpWrap) try { fs.unlinkSync(tmpWrap!); } catch {} };

    const proc = spawn(pythonExe, [runFile, url], {
      cwd: path.resolve(TEMPLATES_DIR, ".."),
      env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      proc.kill();
      console.warn("[template-runner] 타임아웃 (90초)");
      resolve(null);
    }, 90_000);

    proc.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      for (const line of text.split("\n")) {
        const trimmed = line.trim();
        if (trimmed.startsWith("[STATUS]")) {
          onStatus?.(`  ${trimmed.replace("[STATUS]", "").trim()}`);
        }
      }
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      for (const line of text.split("\n")) {
        const trimmed = line.trim();
        if (trimmed) console.warn(`[template-runner] ${trimmed}`);
      }
    });

    proc.on("close", (code) => {
      clearTimeout(timer);
      cleanup();
      if (code !== 0) {
        const errSummary = stderr.split("\n").filter(Boolean).slice(-4).join(" | ");
        console.warn(`[template-runner] 종료코드 ${code}: ${errSummary}`);
        onStatus?.(`⚠ 템플릿 오류 (코드 ${code}): ${errSummary.slice(0, 300)}`);
        resolve(null);
        return;
      }
      const out = stdout.trim();
      if (!out) {
        console.warn("[template-runner] stdout 없음");
        onStatus?.("⚠ 템플릿 출력 없음");
        resolve(null);
        return;
      }

      const jsonMatch = out.match(/```json\s*([\s\S]*?)```/) ?? out.match(/(\{[\s\S]*\})/);
      if (!jsonMatch) {
        console.warn(`[template-runner] JSON 없음, 출력 앞부분: ${out.slice(0, 200)}`);
        onStatus?.("⚠ 템플릿이 JSON을 출력하지 않음");
        resolve(null);
        return;
      }

      try {
        const raw = JSON.parse(jsonMatch[1]) as Record<string, unknown>;
        const itemCount = Array.isArray(raw.items) ? raw.items.length : 1;
        onStatus?.(`✓ 템플릿 추출 완료 (항목 ${itemCount}개)`);
        resolve(raw);
      } catch (err) {
        console.warn(`[template-runner] JSON 파싱 실패: ${err}`);
        onStatus?.(`⚠ JSON 파싱 실패: ${err}`);
        resolve(null);
      }
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      cleanup();
      console.warn(`[template-runner] 실행 실패: ${err.message}`);
      onStatus?.(`⚠ 템플릿 실행 실패: ${err.message}`);
      resolve(null);
    });
  });
}
