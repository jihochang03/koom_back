import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type TMsg =
  | { kind: 'user';        id: string; text: string }
  | { kind: 'assistant';   id: string; text: string; streaming: boolean }
  | { kind: 'tool_call';   id: string; name: string; preview: string }
  | { kind: 'tool_result'; id: string; name: string; preview: string }
  | { kind: 'code';        id: string; code: string }
  | { kind: 'extraction';  id: string; data: Record<string, unknown> }
  | { kind: 'status';      id: string; text: string }

// ── Extraction preview ────────────────────────────────────────────────────────

function ExtractionCard({ data }: { data: Record<string, unknown> }) {
  const opts = data.options as Array<{ name: string; values: string[] }> | undefined
  const price_d = data.price_discounted as number | null | undefined
  const price_o = data.price_original  as number | null | undefined
  const imgs    = data.images as string[] | undefined
  const img     = imgs?.[0]

  return (
    <div className="extraction-card">
      <div className="ex-header">📦 추출 결과</div>
      {img && <img className="ex-img" src={img} alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />}
      {!!data.title && <div className="ex-title">{String(data.title)}</div>}
      {(price_d != null || price_o != null) && (
        <div className="ex-price">
          {price_d != null && <span className="price-d">₩{Number(price_d).toLocaleString()}</span>}
          {price_o != null && price_o !== price_d && <span className="price-o">₩{Number(price_o).toLocaleString()}</span>}
        </div>
      )}
      {opts && opts.length > 0 && (
        <div className="ex-options">
          {opts.map((g, i) => (
            <div key={i} className="ex-opt-group">
              <span className="ex-opt-name">{g.name}</span>
              <div className="ex-opt-tags">
                {(g.values ?? []).slice(0, 10).map((v, j) => (
                  <span key={j} className="ex-tag">{v}</span>
                ))}
                {(g.values?.length ?? 0) > 10 && <span className="ex-tag more">+{(g.values?.length ?? 0) - 10}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      {!!data.availability && <div className="ex-avail">{String(data.availability)}</div>}
    </div>
  )
}

// ── Code block ────────────────────────────────────────────────────────────────

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <div className="code-block">
      <div className="code-header">
        <span>Python 스크레이퍼</span>
        <button className="copy-btn" onClick={copy}>{copied ? '✓ 복사됨' : '복사'}</button>
      </div>
      <pre className="code-pre"><code>{code}</code></pre>
    </div>
  )
}

// ── Tool event ────────────────────────────────────────────────────────────────

function ToolLine({ name, preview, isCall }: { name: string; preview: string; isCall: boolean }) {
  const [open, setOpen] = useState(false)
  const icon = isCall ? '🔧' : '↳'
  return (
    <div className="tool-line" onClick={() => setOpen(o => !o)}>
      <span className="tool-icon">{icon}</span>
      <span className="tool-name">{name}</span>
      <span className="tool-preview">{open ? '' : preview.slice(0, 80)}</span>
      {open && <div className="tool-full">{preview}</div>}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function TemplatePage() {
  const [msgs, setMsgs]           = useState<TMsg[]>([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [history, setHistory]     = useState<unknown[]>([])
  const bottomRef                 = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setLoading(true)

    const uid   = Date.now().toString()
    const aId   = uid + '_a'
    let aAdded  = false

    setMsgs(prev => [...prev, { kind: 'user', id: uid + '_u', text }])

    try {
      const res = await fetch('/api/template/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message:    text,
          messages:   history,
          session_id: sessionId ?? undefined,
        }),
      })
      if (!res.ok || !res.body) throw new Error(`서버 오류: ${res.status}`)

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const block of parts) {
          let event = '', data = ''
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) event = line.slice(7).trim()
            else if (line.startsWith('data: ')) data = line.slice(6).trim()
          }
          if (!data || !event) continue

          let p: Record<string, unknown>
          try { p = JSON.parse(data) } catch { continue }

          if (event === 'session') {
            setSessionId(String(p.session_id))

          } else if (event === 'status') {
            setMsgs(prev => [...prev, { kind: 'status', id: uid + '_st' + Date.now(), text: String(p.message) }])

          } else if (event === 'text') {
            const chunk = String(p.chunk ?? '')
            if (!aAdded) {
              aAdded = true
              setMsgs(prev => [...prev, { kind: 'assistant', id: aId, text: chunk, streaming: true }])
            } else {
              setMsgs(prev => prev.map(m =>
                m.kind === 'assistant' && m.id === aId ? { ...m, text: m.text + chunk } : m
              ))
            }

          } else if (event === 'tool_call') {
            setMsgs(prev => [...prev, {
              kind: 'tool_call', id: uid + '_tc' + Date.now(),
              name: String(p.name), preview: JSON.stringify(p.input ?? '').slice(0, 200),
            }])

          } else if (event === 'tool_result') {
            setMsgs(prev => [...prev, {
              kind: 'tool_result', id: uid + '_tr' + Date.now(),
              name: String(p.name), preview: String(p.preview ?? ''),
            }])

          } else if (event === 'code') {
            setMsgs(prev => {
              // 같은 코드가 이미 있으면 교체, 없으면 추가
              const last = [...prev].reverse().find(m => m.kind === 'code')
              if (last) {
                return prev.map(m => m.id === last.id ? { ...m, code: String(p.code) } : m)
              }
              return [...prev, { kind: 'code', id: uid + '_co' + Date.now(), code: String(p.code) }]
            })

          } else if (event === 'extraction') {
            setMsgs(prev => {
              // 마지막 extraction 카드 교체
              const last = [...prev].reverse().find(m => m.kind === 'extraction')
              if (last) {
                return prev.map(m => m.id === last.id ? { ...m, data: p } : m)
              }
              return [...prev, { kind: 'extraction', id: uid + '_ex' + Date.now(), data: p }]
            })

          } else if (event === 'messages') {
            setHistory((p.messages as unknown[]) ?? [])

          } else if (event === 'done') {
            setMsgs(prev => prev.map(m =>
              m.kind === 'assistant' && m.id === aId ? { ...m, streaming: false } : m
            ))
          }
        }
      }
    } catch (err) {
      setMsgs(prev => [...prev, { kind: 'assistant', id: aId, text: `❌ ${err}`, streaming: false }])
    }

    setLoading(false)
  }, [input, loading, sessionId, history])

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const reset = () => {
    setMsgs([])
    setSessionId(null)
    setHistory([])
    setInput('')
  }

  return (
    <div className="tpl-page">
      <div className="tpl-toolbar">
        <span className="tpl-label">🛠 템플릿 빌더</span>
        {sessionId && <span className="tpl-session">세션 {sessionId.slice(-8)}</span>}
        <button className="tpl-reset" onClick={reset} disabled={loading}>초기화</button>
      </div>

      <div className="tpl-messages">
        {msgs.length === 0 && (
          <div className="empty">
            <div className="empty-icon">🛠</div>
            <div className="empty-title">URL을 입력하세요</div>
            <div className="empty-sub">
              상품 페이지 URL을 입력하면<br/>
              Claude가 페이지를 분석해<br/>
              Python 스크레이퍼 코드를 만들어드립니다
            </div>
          </div>
        )}

        {msgs.map(m => {
          if (m.kind === 'user') return (
            <div className="msg-row user" key={m.id}>
              <div className="bubble-user">{m.text}</div>
            </div>
          )
          if (m.kind === 'status') return (
            <div className="msg-row status" key={m.id}>
              <div className="status-line loading"><span className="status-icon">⟳</span>{m.text}</div>
            </div>
          )
          if (m.kind === 'assistant') return (
            <div className="msg-row assistant" key={m.id}>
              <div className="bubble-assistant">
                {m.text}
                {m.streaming && <span className="cursor" />}
              </div>
            </div>
          )
          if (m.kind === 'tool_call') return (
            <div className="msg-row tool" key={m.id}>
              <ToolLine name={m.name} preview={m.preview} isCall={true} />
            </div>
          )
          if (m.kind === 'tool_result') return (
            <div className="msg-row tool" key={m.id}>
              <ToolLine name={m.name} preview={m.preview} isCall={false} />
            </div>
          )
          if (m.kind === 'code') return (
            <div className="msg-row code" key={m.id}>
              <CodeBlock code={m.code} />
            </div>
          )
          if (m.kind === 'extraction') return (
            <div className="msg-row product" key={m.id}>
              <ExtractionCard data={m.data} />
            </div>
          )
          return null
        })}
        <div ref={bottomRef} />
      </div>

      <div className="input-bar">
        <input
          className="url-input"
          type="text"
          placeholder={msgs.length === 0 ? 'https://... URL을 입력하세요' : '피드백을 입력하세요 (예: 옵션 2가 빠졌어요)'}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          disabled={loading}
          autoFocus
        />
        <button
          className={`analyze-btn${loading ? ' loading' : ''}`}
          onClick={send}
          disabled={loading}
        >
          {loading ? '분석 중' : msgs.length === 0 ? '시작' : '전송'}
        </button>
      </div>
    </div>
  )
}
