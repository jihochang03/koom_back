import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type Msg =
  | { kind: 'user';       id: string; text: string }
  | { kind: 'assistant';  id: string; text: string; streaming: boolean }
  | { kind: 'tool_call';  id: string; name: string; preview: string }
  | { kind: 'tool_result';id: string; name: string; preview: string }
  | { kind: 'code';       id: string; code: string }
  | { kind: 'extraction'; id: string; data: Record<string, unknown> }
  | { kind: 'status';     id: string; text: string; done: boolean }

const EXAMPLE_URLS = [
  'coupang.com/vp/products/...',
  'smartstore.naver.com/...',
  'musinsa.com/products/...',
  'gmarket.co.kr/...',
]

const CATEGORIES = [
  { value: 'shopping',     label: '쇼핑' },
  { value: 'news',         label: '뉴스/블로그' },
  { value: 'real_estate',  label: '부동산' },
  { value: 'jobs',         label: '채용/구인' },
  { value: 'general',      label: '일반' },
]

const PAGE_TYPES = [
  { value: 'detail', label: '상세 페이지' },
  { value: 'list',   label: '목록 페이지' },
  { value: 'both',   label: '목록 + 상세' },
]

// ── Status pill ───────────────────────────────────────────────────────────────

function StatusPill({ text, done }: { text: string; done: boolean }) {
  return (
    <div className={`status-pill${done ? ' done' : ' spinning'}`}>
      <span className="status-icon">{done ? '✓' : '↻'}</span>
      {text}
    </div>
  )
}

// ── Tool card ─────────────────────────────────────────────────────────────────

function ToolCard({ name, preview, isCall }: { name: string; preview: string; isCall: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="tool-card">
      <div className="tool-card-header" onClick={() => setOpen(o => !o)}>
        <span className={`tool-icon ${isCall ? 'call' : 'result'}`}>
          {isCall ? '⚙' : '↳'}
        </span>
        <span className="tool-name">{name}</span>
        {!open && <span className="tool-preview-text">{preview.slice(0, 80)}</span>}
        <span className={`tool-chevron${open ? ' open' : ''}`}>▾</span>
      </div>
      {open && <div className="tool-card-body">{preview}</div>}
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
        <span className="code-lang">
          <span className="code-lang-dot" />
          Python
        </span>
        <div className="code-actions">
          <button className={`copy-btn${copied ? ' copied' : ''}`} onClick={copy}>
            {copied ? '✓ 복사됨' : '복사'}
          </button>
        </div>
      </div>
      <pre className="code-pre"><code>{code}</code></pre>
    </div>
  )
}

// ── Extraction card ───────────────────────────────────────────────────────────

function ExtractionCard({ data }: { data: Record<string, unknown> }) {
  const [imgIdx, setImgIdx] = useState(0)

  type RawOpt = { name: string; values: string[]; soldout_values?: string[] }
  const opts    = data.options as RawOpt[] | undefined
  const price_d = data.price_discounted as number | null | undefined
  const price_o = data.price_original  as number | null | undefined
  const imgs    = (data.images as string[] | undefined ?? []).filter(Boolean)
  const img     = imgs[Math.min(imgIdx, imgs.length - 1)]
  const hasDisc = price_o != null && price_d != null && price_o > price_d
  const rate    = hasDisc ? Math.round((1 - price_d! / price_o!) * 100) : null
  const isOut   = data.availability === 'out_of_stock'
  const specs   = Object.entries((data.specifications as Record<string, string>) ?? {}).filter(([, v]) => v).slice(0, 8)

  return (
    <div className="extraction-card">
      <div className="ex-header">
        <span>📦</span>
        추출 결과
        {!!data.availability && (
          <span className={`ex-avail-badge${isOut ? ' out' : ''}`}>
            {isOut ? '품절' : '판매중'}
          </span>
        )}
      </div>

      <div className="ex-top">
        {imgs.length > 0 && (
          <div className="ex-gallery">
            <img
              className="ex-img"
              src={img}
              alt=""
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            {imgs.length > 1 && (
              <div className="ex-thumbs">
                {imgs.slice(0, 5).map((src, i) => (
                  <button
                    key={i}
                    className={`ex-thumb${i === imgIdx ? ' active' : ''}`}
                    onClick={() => setImgIdx(i)}
                  >
                    <img src={src} alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  </button>
                ))}
                {imgs.length > 5 && <span className="ex-thumb-more">+{imgs.length - 5}</span>}
              </div>
            )}
          </div>
        )}

        <div className="ex-info">
          {!!data.title && <div className="ex-title">{String(data.title)}</div>}

          {(price_d != null || price_o != null) && (
            <div className="ex-price">
              {price_d != null && <span className="price-d">₩{Number(price_d).toLocaleString()}</span>}
              {hasDisc && price_o != null && <span className="price-o">₩{Number(price_o).toLocaleString()}</span>}
              {rate != null && <span className="ex-rate">-{rate}%</span>}
            </div>
          )}

          <div className="ex-meta">
            {!!data.seller && (
              <div className="ex-meta-row">
                <span className="meta-lbl">판매자</span>
                <span>{String(data.seller)}</span>
              </div>
            )}
            {!!data.brand && (
              <div className="ex-meta-row">
                <span className="meta-lbl">브랜드</span>
                <span>{String(data.brand)}</span>
              </div>
            )}
            {data.rating != null && (
              <div className="ex-meta-row">
                <span className="meta-lbl">평점</span>
                <span>
                  ⭐ {String(data.rating)}
                  {data.review_count != null && ` (${Number(data.review_count).toLocaleString()})`}
                </span>
              </div>
            )}
          </div>

          {(data.shipping_fee_text != null || data.delivery_date != null) && (
            <div className="ex-shipping">
              <span className="ship-icon">🚚</span>
              {data.shipping_fee_text != null && (
                <span className={data.shipping_fee === 0 ? 'free-ship' : 'ship-fee'}>
                  {String(data.shipping_fee_text)}
                </span>
              )}
              {data.delivery_date != null && (
                <>
                  {data.shipping_fee_text != null && <span className="ship-sep">·</span>}
                  <span className="ship-date">{String(data.delivery_date)}</span>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {opts && opts.length > 0 && (
        <div className="ex-options">
          {opts.map((g, i) => {
            const soSet = new Set(g.soldout_values ?? [])
            return (
              <div key={i} className="ex-opt-group">
                <span className="ex-opt-name">{g.name}</span>
                <div className="ex-opt-tags">
                  {(g.values ?? []).map((v, j) => (
                    <span key={j} className={`ex-tag${soSet.has(v) ? ' soldout' : ''}`}>{v}</span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {specs.length > 0 && (
        <div className="ex-specs">
          <div className="ex-opt-name" style={{ marginBottom: 6 }}>스펙</div>
          <table className="spec-table">
            <tbody>
              {specs.map(([k, v]) => (
                <tr key={k}>
                  <td className="spec-key">{k}</td>
                  <td className="spec-val">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── AgentPage ─────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const [msgs, setMsgs]           = useState<Msg[]>([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [history, setHistory]     = useState<unknown[]>([])
  const [category, setCategory]   = useState('shopping')
  const [pageType, setPageType]   = useState('detail')
  const bottomRef                 = useRef<HTMLDivElement>(null)
  const inputRef                  = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const send = useCallback(async (overrideText?: string) => {
    const text = (overrideText ?? input).trim()
    if (!text || loading) return
    setInput('')
    setLoading(true)

    const uid  = Date.now().toString()
    const aId  = uid + '_a'
    let aAdded = false

    setMsgs(prev => [...prev, { kind: 'user', id: uid + '_u', text }])

    try {
      const res = await fetch('/api/template/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message:    text,
          messages:   history,
          session_id: sessionId ?? undefined,
          category,
          page_type:  pageType,
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
            else if (line.startsWith('data: ')) data  = line.slice(6).trim()
          }
          if (!data || !event) continue

          let p: Record<string, unknown>
          try { p = JSON.parse(data) } catch { continue }

          if (event === 'session') {
            setSessionId(String(p.session_id))

          } else if (event === 'status') {
            setMsgs(prev => [...prev, {
              kind: 'status',
              id: uid + '_st' + Date.now(),
              text: String(p.message),
              done: false,
            }])

          } else if (event === 'text') {
            const chunk = String(p.chunk ?? '')
            if (!aAdded) {
              aAdded = true
              setMsgs(prev => [
                ...prev.map(m => m.kind === 'status' ? { ...m, done: true } : m),
                { kind: 'assistant', id: aId, text: chunk, streaming: true },
              ])
            } else {
              setMsgs(prev => prev.map(m =>
                m.kind === 'assistant' && m.id === aId
                  ? { ...m, text: m.text + chunk }
                  : m
              ))
            }

          } else if (event === 'tool_call') {
            setMsgs(prev => [...prev, {
              kind: 'tool_call',
              id: uid + '_tc' + Date.now(),
              name: String(p.name),
              preview: JSON.stringify(p.input ?? '').slice(0, 500),
            }])

          } else if (event === 'tool_result') {
            setMsgs(prev => [...prev, {
              kind: 'tool_result',
              id: uid + '_tr' + Date.now(),
              name: String(p.name),
              preview: String(p.preview ?? ''),
            }])

          } else if (event === 'code') {
            setMsgs(prev => {
              const last = [...prev].reverse().find(m => m.kind === 'code')
              if (last) {
                return prev.map(m => m.id === last.id ? { ...m, code: String(p.code) } : m)
              }
              return [...prev, { kind: 'code', id: uid + '_co' + Date.now(), code: String(p.code) }]
            })

          } else if (event === 'extraction') {
            setMsgs(prev => {
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
      setMsgs(prev => [...prev, {
        kind: 'assistant',
        id: aId,
        text: `오류가 발생했습니다: ${err}`,
        streaming: false,
      }])
    }

    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [input, loading, sessionId, history])

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const reset = () => {
    setMsgs([])
    setSessionId(null)
    setHistory([])
    setInput('')
    setCategory('shopping')
    setPageType('detail')
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const isEmpty = msgs.length === 0

  const placeholder = isEmpty
    ? 'https://... 상품 URL을 입력하세요'
    : '피드백을 입력하세요 (예: 옵션이 빠졌어요)'

  const btnLabel = loading ? '분석 중...' : isEmpty ? '분석 시작' : '전송'

  return (
    <div className="main">
      <div className="messages">
        <div className="messages-inner">

          {/* Empty state */}
          {isEmpty && (
            <div className="empty-state">
              <div className="empty-logo">◈</div>
              <div className="empty-title">URL을 분석해드립니다</div>
              <div className="empty-sub">
                URL을 입력하면 Claude가 페이지를 분석해<br />
                Python 스크레이퍼 코드를 만들고<br />
                실제로 데이터를 추출해 검증합니다
              </div>

              <div className="empty-selectors">
                <div className="selector-group">
                  <label className="selector-label">카테고리</label>
                  <div className="selector-chips">
                    {CATEGORIES.map(c => (
                      <button
                        key={c.value}
                        className={`chip${category === c.value ? ' active' : ''}`}
                        onClick={() => setCategory(c.value)}
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="selector-group">
                  <label className="selector-label">페이지 유형</label>
                  <div className="selector-chips">
                    {PAGE_TYPES.map(p => (
                      <button
                        key={p.value}
                        className={`chip${pageType === p.value ? ' active' : ''}`}
                        onClick={() => setPageType(p.value)}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="empty-chips">
                {EXAMPLE_URLS.map((url, i) => (
                  <button key={i} className="chip" onClick={() => {
                    setInput('https://www.' + url)
                    inputRef.current?.focus()
                  }}>
                    {url.split('/')[0]}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          {msgs.map(m => {
            if (m.kind === 'user') return (
              <div className="msg-row" key={m.id}>
                <div className="bubble-user">{m.text}</div>
              </div>
            )

            if (m.kind === 'status') return (
              <div className="msg-row" key={m.id}>
                <StatusPill text={m.text} done={m.done} />
              </div>
            )

            if (m.kind === 'assistant') return (
              <div className="msg-row msg-row-assistant" key={m.id}>
                <div className="agent-avatar">◈</div>
                <div className="bubble-assistant">
                  {m.text}
                  {m.streaming && <span className="cursor" />}
                </div>
              </div>
            )

            if (m.kind === 'tool_call') return (
              <div className="msg-row" key={m.id}>
                <ToolCard name={m.name} preview={m.preview} isCall={true} />
              </div>
            )

            if (m.kind === 'tool_result') return (
              <div className="msg-row" key={m.id}>
                <ToolCard name={m.name} preview={m.preview} isCall={false} />
              </div>
            )

            if (m.kind === 'code') return (
              <div className="msg-row" key={m.id}>
                <CodeBlock code={m.code} />
              </div>
            )

            if (m.kind === 'extraction') return (
              <div className="msg-row" key={m.id}>
                <ExtractionCard data={m.data} />
              </div>
            )

            return null
          })}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input bar */}
      <div className="input-area">
        <div className="input-wrap">
          <div className="input-box">
            <input
              ref={inputRef}
              type="text"
              placeholder={placeholder}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              disabled={loading}
              autoFocus
            />
          </div>
          <button
            className={`send-btn${loading ? ' loading' : ''}`}
            onClick={() => send()}
            disabled={loading}
          >
            {btnLabel}
          </button>
          {!isEmpty && (
            <button
              className="header-btn"
              onClick={reset}
              disabled={loading}
              style={{ height: 46, padding: '0 14px' }}
            >
              초기화
            </button>
          )}
        </div>
        <div className="input-hint">
          {isEmpty
            ? 'Enter로 전송 · 분석 후 채팅으로 템플릿 수정 가능'
            : `${CATEGORIES.find(c => c.value === category)?.label ?? category} · ${PAGE_TYPES.find(p => p.value === pageType)?.label ?? pageType}`
          }
        </div>
      </div>
    </div>
  )
}
