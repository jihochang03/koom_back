import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import ProductCard from './shopping/ProductCard'
import type { ProductData } from './shopping/ProductCard'

interface StoredProduct {
  id: string
  url: string
  domain: string
  crawled_at: string
  list_url?: string
  data: ProductData
}

type ProgressMsg =
  | { kind: 'status'; text: string }
  | { kind: 'urls_found'; count: number; urls: string[] }
  | { kind: 'template'; domain: string; reused: boolean }
  | { kind: 'progress'; done: number; total: number }
  | { kind: 'error'; text: string }

export default function ListCrawlPage() {
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [msgs, setMsgs]           = useState<ProgressMsg[]>([])
  const [products, setProducts]   = useState<StoredProduct[]>([])
  const [urlCount, setUrlCount]   = useState<number | null>(null)
  const [progress, setProgress]   = useState<{ done: number; total: number } | null>(null)
  const [templateDomain, setTemplateDomain] = useState<string | null>(null)
  const bottomRef                 = useRef<HTMLDivElement>(null)
  const inputRef                  = useRef<HTMLInputElement>(null)
  const logRef                    = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [msgs])

  const addMsg = (msg: ProgressMsg) => setMsgs(prev => [...prev, msg])

  const start = useCallback(async () => {
    const url = input.trim()
    if (!url || loading) return
    if (!url.startsWith('http')) { alert('http(s)://로 시작하는 URL을 입력하세요'); return }

    setLoading(true)
    setMsgs([])
    setProducts([])
    setUrlCount(null)
    setProgress(null)
    setTemplateDomain(null)

    try {
      const res = await fetch('/api/crawl-list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, category: 'shopping' }),
      })
      if (!res.ok) throw new Error(`서버 오류: ${res.status} — 백엔드 서버를 재시작하세요 (npm run web)`)
      if (!res.body) throw new Error('스트림 없음')
      const ct = res.headers.get('content-type') ?? ''
      if (!ct.includes('text/event-stream')) throw new Error(`잘못된 응답 타입: ${ct} — 백엔드 서버를 재시작하세요 (npm run web)`)

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
          if (!event || !data) continue

          let p: Record<string, unknown>
          try { p = JSON.parse(data) } catch { continue }

          if (event === 'status') {
            addMsg({ kind: 'status', text: String(p.message ?? '') })
          } else if (event === 'urls_found') {
            const cnt = Number(p.count ?? 0)
            setUrlCount(cnt)
            addMsg({ kind: 'urls_found', count: cnt, urls: (p.urls as string[]) ?? [] })
          } else if (event === 'template_done') {
            const domain = String(p.domain ?? '')
            const reused = Boolean(p.reused)
            setTemplateDomain(domain)
            addMsg({ kind: 'template', domain, reused })
          } else if (event === 'progress') {
            const prog = { done: Number(p.done ?? 0), total: Number(p.total ?? 0) }
            setProgress(prog)
          } else if (event === 'product') {
            setProducts(prev => [p as unknown as StoredProduct, ...prev])
          } else if (event === 'error') {
            addMsg({ kind: 'error', text: String(p.message ?? '오류 발생') })
          }
        }
      }
    } catch (err) {
      addMsg({ kind: 'error', text: String(err) })
    }

    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [input, loading])

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); start() }
  }

  const isEmpty = msgs.length === 0 && products.length === 0

  return (
    <div className="lc-layout">
      {/* ── Left: log + controls ── */}
      <div className="lc-left">
        {/* Input */}
        <div className="lc-input-area">
          <div className="input-box" style={{ flex: 1 }}>
            <input
              ref={inputRef}
              type="url"
              placeholder="https://... 목록 페이지 URL (카테고리, 검색결과 등)"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              disabled={loading}
              autoFocus
            />
          </div>
          <button
            className={`send-btn${loading ? ' loading' : ''}`}
            onClick={start}
            disabled={loading}
          >
            {loading ? '수집 중...' : '수집 시작'}
          </button>
        </div>

        {/* Stats row */}
        {(urlCount !== null || templateDomain || progress) && (
          <div className="lc-stats">
            {urlCount !== null && (
              <span className="lc-stat-chip">
                🔗 {urlCount}개 URL 발견
              </span>
            )}
            {templateDomain && (
              <span className="lc-stat-chip green">
                {templateDomain} 템플릿 {products.length > 0 ? '✓' : '빌드 중...'}
              </span>
            )}
            {progress && (
              <span className="lc-stat-chip">
                {progress.done}/{progress.total} 수집
              </span>
            )}
          </div>
        )}

        {/* Progress bar */}
        {progress && progress.total > 0 && (
          <div className="lc-progress-bar">
            <div
              className="lc-progress-fill"
              style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
            />
          </div>
        )}

        {/* Log */}
        {isEmpty ? (
          <div className="empty-state" style={{ minHeight: '40vh' }}>
            <div className="empty-logo">📋</div>
            <div className="empty-title">목록 페이지 대량 수집</div>
            <div className="empty-sub">
              목록 페이지 URL을 입력하면<br />
              상품 URL을 자동으로 찾고<br />
              템플릿을 빌드해 전체 상품을 수집합니다
            </div>
          </div>
        ) : (
          <div className="lc-log" ref={logRef}>
            {msgs.map((m, i) => {
              if (m.kind === 'status') return (
                <div key={i} className="lc-log-line">{m.text}</div>
              )
              if (m.kind === 'urls_found') return (
                <div key={i} className="lc-log-line highlight">
                  🔗 상품 URL {m.count}개 발견
                </div>
              )
              if (m.kind === 'template') return (
                <div key={i} className="lc-log-line highlight green">
                  {m.reused ? '⚡' : '✓'} 템플릿 {m.reused ? '재사용' : '생성'}: {m.domain}
                </div>
              )
              if (m.kind === 'progress') return null
              if (m.kind === 'error') return (
                <div key={i} className="lc-log-line error">❌ {m.text}</div>
              )
              return null
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* ── Right: product grid ── */}
      <div className="lc-right">
        {products.length === 0 ? (
          loading ? (
            <div className="lc-empty-right">
              <div className="lc-spinner">↻</div>
              <div className="lc-empty-label">상품 수집 대기 중...</div>
            </div>
          ) : (
            <div className="lc-empty-right">
              <div className="lc-empty-label">수집된 상품이 여기에 표시됩니다</div>
            </div>
          )
        ) : (
          <div className="lc-product-list">
            <div className="lc-product-header">
              <span className="lc-product-count">{products.length}개 수집됨</span>
            </div>
            {products.map(p => (
              <div key={p.id} className="lc-product-item">
                <ProductCard data={p.data} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
