import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import ProductCard from './shopping/ProductCard'
import type { ProductData } from './shopping/ProductCard'

interface TemplateFile {
  filename: string
  domain: string
  size: number
  updated_at: string
}

const EXAMPLE_DOMAINS = [
  'coupang.com',
  'smartstore.naver.com',
  'musinsa.com',
  'gmarket.co.kr',
]

type Msg =
  | { kind: 'user';    id: string; url: string }
  | { kind: 'badge';   id: string; mode: 'template'; domain: string }
  | { kind: 'badge';   id: string; mode: 'claude' }
  | { kind: 'status';  id: string; text: string; done: boolean }
  | { kind: 'product'; id: string; data: ProductData }
  | { kind: 'error';   id: string; text: string }

export default function ScrapePage() {
  const [msgs, setMsgs]         = useState<Msg[]>([])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [templates, setTemplates] = useState<TemplateFile[]>([])
  const bottomRef               = useRef<HTMLDivElement>(null)
  const inputRef                = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  useEffect(() => {
    fetch('/api/templates')
      .then(r => r.ok ? r.json() : { files: [] })
      .then((d: { files?: TemplateFile[] }) => {
        // py 파일만, 도메인별 중복 제거
        const seen = new Set<string>()
        const uniq = (d.files ?? []).filter(f => {
          if (!f.filename.endsWith('.py')) return false
          if (seen.has(f.domain)) return false
          seen.add(f.domain)
          return true
        })
        setTemplates(uniq)
      })
      .catch(() => {})
  }, [])

  const scrape = useCallback(async () => {
    const url = input.trim()
    if (!url || loading) return
    if (!url.startsWith('http')) { alert('http(s)://로 시작하는 URL을 입력해주세요.'); return }

    setInput('')
    setLoading(true)
    const uid = Date.now().toString()
    setMsgs(prev => [...prev, { kind: 'user', id: uid + '_u', url }])

    // 도메인 추출 → Knowledge 템플릿 매칭
    let templateCode: string | undefined
    let matchedDomain: string | undefined
    try {
      const domain = new URL(url).hostname.replace(/^www\./, '')
      const match = templates.find(t => t.domain === domain || domain.endsWith('.' + t.domain))
      if (match) {
        const res = await fetch(`/api/templates/${encodeURIComponent(match.filename)}`)
        if (res.ok) {
          const d = await res.json() as { content?: string }
          templateCode = d.content
          matchedDomain = match.domain
        }
      }
    } catch { /* no match */ }

    if (templateCode && matchedDomain) {
      setMsgs(prev => [...prev, { kind: 'badge', id: uid + '_b', mode: 'template', domain: matchedDomain! }])
    } else {
      setMsgs(prev => [...prev, { kind: 'badge', id: uid + '_b', mode: 'claude' }])
    }

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          category: 'shopping',
          ...(templateCode ? { template: templateCode, templateName: matchedDomain } : {}),
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

          if (event === 'status') {
            setMsgs(prev => [...prev, { kind: 'status', id: uid + '_s' + Date.now(), text: String(p.message ?? ''), done: false }])
          } else if (event === 'result') {
            setMsgs(prev => [
              ...prev.map(m => m.kind === 'status' ? { ...m, done: true } : m),
              { kind: 'product', id: uid + '_p', data: p as unknown as ProductData },
            ])
          } else if (event === 'error') {
            setMsgs(prev => [...prev, { kind: 'error', id: uid + '_e', text: String(p.message ?? '오류') }])
          }
        }
      }
    } catch (err) {
      setMsgs(prev => [...prev, { kind: 'error', id: uid + '_e', text: String(err) }])
    }

    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [input, loading, templates])

  const exampleChips = templates.length > 0
    ? templates.slice(0, 6).map(t => t.domain)
    : EXAMPLE_DOMAINS

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); scrape() }
  }

  return (
    <div className="scrape-layout">
      {/* ── Sidebar ── */}
      <aside className="scrape-sidebar">
        <div className="sidebar-title">템플릿 사이트</div>
        {templates.length === 0
          ? <div className="sidebar-empty">Knowledge에 저장된 템플릿 없음</div>
          : templates.map(t => (
            <button
              key={t.domain}
              className="sidebar-item"
              onClick={() => setInput(`https://${t.domain}/`)}
            >
              <span className="sidebar-domain">{t.domain}</span>
            </button>
          ))
        }
      </aside>

      {/* ── Main ── */}
      <div className="scrape-main">
        <div className="messages">
          {msgs.length === 0 && (
            <div className="empty-state">
              <div className="empty-logo">⚡</div>
              <div className="empty-title">Knowledge 템플릿으로 즉시 수집</div>
              <div className="empty-sub">
                Knowledge에 템플릿이 있는 사이트는<br />
                Claude 없이 바로 데이터를 가져옵니다<br />
                없는 사이트는 Claude가 자동으로 처리합니다
              </div>
              <div className="empty-chips">
                {exampleChips.map(d => (
                  <button
                    key={d}
                    className="chip"
                    onClick={() => {
                      setInput(`https://${d}/`)
                      inputRef.current?.focus()
                    }}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          )}

          {msgs.map(m => {
            if (m.kind === 'user') return (
              <div className="msg-row user" key={m.id}>
                <div className="bubble-user">{m.url}</div>
              </div>
            )
            if (m.kind === 'badge') return (
              <div className="msg-row status" key={m.id}>
                {m.mode === 'template'
                  ? <div className="badge-template">⚡ {m.domain} 템플릿 사용 · 0토큰</div>
                  : <div className="badge-claude">✦ Claude 분석 · 템플릿 없음</div>
                }
              </div>
            )
            if (m.kind === 'status') return (
              <div className="msg-row status" key={m.id}>
                <div className={`status-line${m.done ? '' : ' loading'}`}>
                  <span className="status-icon">{m.done ? '✓' : '⟳'}</span>
                  {m.text}
                </div>
              </div>
            )
            if (m.kind === 'product') return (
              <div className="msg-row product" key={m.id}>
                <ProductCard data={m.data} />
              </div>
            )
            if (m.kind === 'error') return (
              <div className="msg-row assistant" key={m.id}>
                <div className="bubble-assistant">❌ {m.text}</div>
              </div>
            )
            return null
          })}

          <div ref={bottomRef} />
        </div>

        <div className="input-area">
          <div className="input-wrap">
            <div className="input-box">
              <input
                ref={inputRef}
                type="url"
                placeholder="https://... 상품 페이지 URL을 입력하세요"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                disabled={loading}
                autoFocus
              />
            </div>
            <button
              className={`send-btn${loading ? ' loading' : ''}`}
              onClick={scrape}
              disabled={loading}
            >
              {loading ? '수집 중...' : '수집'}
            </button>
          </div>
          <div className="input-hint">
            Enter로 수집 · Knowledge 템플릿 있으면 0토큰, 없으면 Claude 분석
          </div>
        </div>
      </div>
    </div>
  )
}
