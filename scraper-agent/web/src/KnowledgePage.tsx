import { useEffect, useState, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

interface CaptchaInfo {
  type?: string;
  input_selector?: string;
  submit_selector?: string | null;
  solved_count?: number;
  last_solved?: string;
}

interface CollectionInfo {
  notes?: string;
  extra_clicks?: string[];
  wait_for_selector?: string;
  network_patterns?: string[];
}

interface DomainKnowledge {
  domain: string;
  created_at?: string;
  updated_at?: string;
  captcha?: CaptchaInfo;
  collection?: CollectionInfo;
}

interface TemplateFile {
  filename: string;
  domain: string;
  size: number;
  updated_at: string;
}

interface DomainEntry {
  domain: string;
  knowledge: DomainKnowledge | null;
  templates: TemplateFile[];
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function apiFetch(url: string, opts?: RequestInit) {
  const r = await fetch(url, opts);
  if (r.status === 204) return null;
  return r.json();
}

async function loadAllDomains(): Promise<DomainEntry[]> {
  const [kRes, tRes] = await Promise.all([
    apiFetch("/api/knowledge"),
    apiFetch("/api/templates"),
  ]) as [{ domains: string[] }, { files: TemplateFile[] }];

  const map = new Map<string, DomainEntry>();

  for (const d of kRes.domains ?? []) {
    map.set(d, { domain: d, knowledge: null, templates: [] });
  }
  for (const f of tRes.files ?? []) {
    if (!map.has(f.domain)) map.set(f.domain, { domain: f.domain, knowledge: null, templates: [] });
    map.get(f.domain)!.templates.push(f);
  }

  // Load knowledge details in parallel (small N, fine)
  await Promise.all(
    [...map.values()].filter(e => kRes.domains?.includes(e.domain)).map(async e => {
      try {
        e.knowledge = await apiFetch(`/api/knowledge/${encodeURIComponent(e.domain)}`);
      } catch {}
    })
  );

  return [...map.values()].sort((a, b) => a.domain.localeCompare(b.domain));
}

async function saveKnowledge(domain: string, body: Partial<DomainKnowledge>) {
  return apiFetch(`/api/knowledge/${encodeURIComponent(domain)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function deleteKnowledge(domain: string) {
  await apiFetch(`/api/knowledge/${encodeURIComponent(domain)}`, { method: "DELETE" });
}

async function loadTemplateContent(filename: string): Promise<string> {
  const d = await apiFetch(`/api/templates/${encodeURIComponent(filename)}`);
  return d.content as string;
}

async function deleteTemplate(filename: string) {
  await apiFetch(`/api/templates/${encodeURIComponent(filename)}`, { method: "DELETE" });
}

// ── Tiny components ───────────────────────────────────────────────────────────

function Badge({ children, color }: { children: React.ReactNode; color: "green" | "blue" | "purple" | "gray" }) {
  const palette = {
    green:  { bg: "#d1fae5", fg: "#065f46" },
    blue:   { bg: "#dbeafe", fg: "#1e40af" },
    purple: { bg: "#ede9fe", fg: "#5b21b6" },
    gray:   { bg: "#f3f4f6", fg: "#374151" },
  }[color];
  return (
    <span style={{ display: "inline-block", padding: "1px 8px", borderRadius: 10, fontSize: 11, fontWeight: 600, background: palette.bg, color: palette.fg }}>
      {children}
    </span>
  );
}

function IconBtn({ label, onClick, danger }: { label: string; onClick: (e: React.MouseEvent) => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      style={{ padding: "2px 8px", borderRadius: 4, border: `1px solid ${danger ? "#fca5a5" : "#d1d5db"}`, background: "transparent", color: danger ? "#ef4444" : "#6b7280", fontSize: 11, cursor: "pointer" }}
    >
      {label}
    </button>
  );
}

// ── JSON editor ───────────────────────────────────────────────────────────────

function JsonEditor({ label, value, onChange }: { label: string; value: object | null | undefined; onChange: (v: object | null) => void }) {
  const [text, setText] = useState(() => value ? JSON.stringify(value, null, 2) : "");
  const [err, setErr] = useState("");

  useEffect(() => { setText(value ? JSON.stringify(value, null, 2) : ""); setErr(""); }, [value]);

  function handleBlur() {
    if (!text.trim()) { onChange(null); return; }
    try { onChange(JSON.parse(text)); setErr(""); }
    catch { setErr("JSON 파싱 오류"); }
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        onBlur={handleBlur}
        rows={7}
        style={{ width: "100%", fontFamily: "monospace", fontSize: 12, padding: 8, border: `1px solid ${err ? "#ef4444" : "#e5e7eb"}`, borderRadius: 6, resize: "vertical", boxSizing: "border-box", lineHeight: 1.5, background: "#fafafa" }}
      />
      {err && <div style={{ color: "#ef4444", fontSize: 11 }}>{err}</div>}
    </div>
  );
}

// ── Template viewer ───────────────────────────────────────────────────────────

function TemplateViewer({ file, onDeleted }: { file: TemplateFile; onDeleted: () => void }) {
  const [content, setContent] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const isPy = file.filename.endsWith(".py");

  async function toggle() {
    if (!open && content === null) setContent(await loadTemplateContent(file.filename));
    setOpen(o => !o);
  }

  async function handleDelete() {
    if (!confirm(`${file.filename} 삭제할까요?`)) return;
    await deleteTemplate(file.filename);
    onDeleted();
  }

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, marginBottom: 8, overflow: "hidden" }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", cursor: "pointer", background: open ? "#f9fafb" : "#fff" }}
        onClick={toggle}
      >
        <span style={{ fontSize: 13 }}>{isPy ? "🐍" : "📋"}</span>
        <span style={{ flex: 1, fontSize: 13, fontFamily: "monospace", fontWeight: 500 }}>{file.filename}</span>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>{(file.size / 1024).toFixed(1)} KB</span>
        <IconBtn label="삭제" onClick={e => { e.stopPropagation(); handleDelete(); }} danger />
        <span style={{ color: "#9ca3af", fontSize: 12 }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && content !== null && (
        <div style={{ position: "relative" }}>
          <button
            onClick={() => navigator.clipboard.writeText(content)}
            style={{ position: "absolute", top: 6, right: 8, padding: "2px 8px", borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", fontSize: 11, cursor: "pointer", zIndex: 1 }}
          >
            복사
          </button>
          <pre style={{ margin: 0, padding: "10px 12px", fontSize: 11, fontFamily: "monospace", background: "#1e1e2e", color: "#cdd6f4", overflowX: "auto", maxHeight: 420, lineHeight: 1.5 }}>
            {content}
          </pre>
        </div>
      )}
    </div>
  );
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DetailPanel({ entry, onClose, onRefresh }: { entry: DomainEntry; onClose: () => void; onRefresh: () => void }) {
  const { domain, knowledge, templates } = entry;
  const [captcha, setCaptcha] = useState<object | null>(knowledge?.captcha ?? null);
  const [collection, setCollection] = useState<object | null>(knowledge?.collection ?? null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  async function handleSave() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = {};
      if (captcha) body.captcha = captcha;
      if (collection) body.collection = collection;
      await saveKnowledge(domain, body);
      setSavedMsg("저장됨");
      setTimeout(() => setSavedMsg(""), 2000);
    } catch { alert("저장 실패"); }
    finally { setSaving(false); }
  }

  async function handleDeleteKnowledge() {
    if (!confirm(`${domain} knowledge 삭제?`)) return;
    await deleteKnowledge(domain);
    onRefresh();
    onClose();
  }

  return (
    <div style={{ padding: "18px 20px", overflowY: "auto", height: "100%", boxSizing: "border-box" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#6b7280", padding: 0 }}>←</button>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, flex: 1 }}>{domain}</h3>
        {knowledge?.updated_at && <span style={{ fontSize: 11, color: "#9ca3af" }}>{knowledge.updated_at.slice(0, 16)}</span>}
      </div>

      {/* Knowledge section */}
      {knowledge ? (
        <section style={{ marginBottom: 24 }}>
          <SectionTitle>Site Knowledge</SectionTitle>
          <JsonEditor label="CAPTCHA 패턴" value={captcha} onChange={setCaptcha} />
          <JsonEditor label="수집 힌트 (collection)" value={collection} onChange={setCollection} />
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{ padding: "6px 16px", borderRadius: 6, border: "none", background: saving ? "#9ca3af" : "#3b82f6", color: "#fff", fontWeight: 600, fontSize: 13, cursor: saving ? "default" : "pointer" }}
            >
              {saving ? "저장 중…" : savedMsg || "저장"}
            </button>
            <button
              onClick={handleDeleteKnowledge}
              style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #fca5a5", background: "transparent", color: "#ef4444", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
            >
              Knowledge 삭제
            </button>
          </div>
        </section>
      ) : (
        <div style={{ color: "#9ca3af", fontSize: 13, marginBottom: 20 }}>저장된 site knowledge 없음</div>
      )}

      {/* Templates section */}
      {templates.length > 0 && (
        <section>
          <SectionTitle>템플릿 파일 ({templates.length})</SectionTitle>
          {templates.map(f => (
            <TemplateViewer key={f.filename} file={f} onDeleted={onRefresh} />
          ))}
        </section>
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10, paddingBottom: 5, borderBottom: "1px solid #f3f4f6" }}>
      {children}
    </div>
  );
}

// ── Domain row ────────────────────────────────────────────────────────────────

function DomainRow({ entry, onSelect }: { entry: DomainEntry; onSelect: () => void }) {
  const { domain, knowledge, templates } = entry;
  const pyCount = templates.filter(f => f.filename.endsWith(".py")).length;
  const jsonCount = templates.filter(f => f.filename.endsWith(".json")).length;

  return (
    <div
      onClick={onSelect}
      style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", borderRadius: 8, cursor: "pointer", background: "#fff", border: "1px solid #e5e7eb", marginBottom: 5 }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 1px 6px rgba(0,0,0,0.07)")}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = "none")}
    >
      <span style={{ flex: 1, fontWeight: 500, fontSize: 13 }}>{domain}</span>
      <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
        {knowledge?.captcha && <Badge color="green">캡차 {knowledge.captcha.solved_count ?? 0}회</Badge>}
        {knowledge?.collection && <Badge color="blue">수집힌트</Badge>}
        {pyCount > 0 && <Badge color="purple">🐍 ×{pyCount}</Badge>}
        {jsonCount > 0 && <Badge color="gray">JSON ×{jsonCount}</Badge>}
      </div>
      <span style={{ color: "#d1d5db", fontSize: 14 }}>›</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const [entries, setEntries] = useState<DomainEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    loadAllDomains()
      .then(d => { setEntries(d); setError(""); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectedEntry = entries.find(e => e.domain === selected) ?? null;

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)", fontFamily: "system-ui, sans-serif" }}>
      {/* List */}
      <div style={{ width: selectedEntry ? 300 : "100%", maxWidth: selectedEntry ? 300 : undefined, borderRight: selectedEntry ? "1px solid #e5e7eb" : "none", overflowY: "auto", padding: 16, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Knowledge & Templates</h2>
          <button onClick={load} style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "#6b7280" }} title="새로고침">⟳</button>
        </div>

        {loading && <div style={{ color: "#9ca3af", fontSize: 13 }}>로딩 중…</div>}
        {error && <div style={{ color: "#ef4444", fontSize: 13 }}>오류: {error}</div>}
        {!loading && !error && entries.length === 0 && (
          <div style={{ color: "#9ca3af", fontSize: 13 }}>아직 저장된 데이터가 없습니다.</div>
        )}

        {entries.map(e => (
          <DomainRow key={e.domain} entry={e} onSelect={() => setSelected(e.domain)} />
        ))}
      </div>

      {/* Detail */}
      {selectedEntry && (
        <div style={{ flex: 1, overflowY: "auto" }}>
          <DetailPanel
            entry={selectedEntry}
            onClose={() => setSelected(null)}
            onRefresh={() => { load(); setSelected(null); }}
          />
        </div>
      )}
    </div>
  );
}
