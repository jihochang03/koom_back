// Shopping product analysis page — URL input → SSE stream → ProductCard
import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import ProductCard from './ProductCard'
import type { ProductData } from './ProductCard'

type Msg =
  | { kind: 'user';      id: string; url: string }
  | { kind: 'status';    id: string; text: string; done: boolean }
  | { kind: 'assistant'; id: string; text: string; streaming: boolean }
  | { kind: 'product';   id: string; data: ProductData }

export default function AnalyzePage() {
  const [msgs, setMsgs]       = useState<Msg[]>([])
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef             = useRef<HTMLDivElement>(null)
  const abortRef              = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const analyze = useCallback(async () => {
    const url = input.trim()
    if (!url || loading) return
    if (!url.startsWith('http')) {
      alert('http(s)://로 시작하는 URL을 입력해주세요.')
      return
    }

    setInput('')
    setLoading(true)

    const uid = Date.now().toString()
    const assistId = uid + '_a'
    let assistantAdded = false

    setMsgs(prev => [...prev,
      { kind: 'user', id: uid + '_u', url },
    ])

    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
        signal: abortRef.current.signal,
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
          let event = 'message', data = ''
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) event = line.slice(7).trim()
            else if (line.startsWith('data: ')) data = line.slice(6).trim()
          }
          if (!data) continue

          let parsed: Record<string, unknown>
          try { parsed = JSON.parse(data) } catch { continue }

          if (event === 'status') {
            const text = String(parsed.message ?? '')
            setMsgs(prev => [...prev,
              { kind: 'status', id: uid + '_s' + Date.now(), text, done: false }
            ])

          } else if (event === 'text') {
            const chunk = String(parsed.chunk ?? '')
            if (!assistantAdded) {
              assistantAdded = true
              setMsgs(prev => {
                const updated = prev.map(m =>
                  m.kind === 'status' ? { ...m, done: true } : m
                )
                return [...updated, { kind: 'assistant', id: assistId, text: chunk, streaming: true }]
              })
            } else {
              setMsgs(prev => prev.map(m =>
                m.kind === 'assistant' && m.id === assistId
                  ? { ...m, text: m.text + chunk }
                  : m
              ))
            }

          } else if (event === 'result') {
            setMsgs(prev => [
              ...prev.map(m =>
                m.kind === 'assistant' && m.id === assistId
                  ? { ...m, streaming: false }
                  : m
              ),
              { kind: 'product', id: uid + '_p', data: parsed as unknown as ProductData },
            ])

          } else if (event === 'error') {
            const errMsg = String(parsed.message ?? '알 수 없는 오류')
            if (!assistantAdded) {
              setMsgs(prev => [...prev,
                { kind: 'assistant', id: assistId, text: `❌ ${errMsg}`, streaming: false }
              ])
            } else {
              setMsgs(prev => prev.map(m =>
                m.kind === 'assistant' && m.id === assistId
                  ? { ...m, text: m.text + `\n\n❌ ${errMsg}`, streaming: false }
                  : m
              ))
            }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setMsgs(prev => [...prev,
          { kind: 'assistant', id: assistId, text: `❌ 연결 오류: ${err}`, streaming: false }
        ])
      }
    }

    setLoading(false)
    abortRef.current = null
  }, [input, loading])

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); analyze() }
  }

  return (
    <>
      <div className="messages">
        {msgs.length === 0 && (
          <div className="empty">
            <div className="empty-icon">🛒</div>
            <div className="empty-title">URL을 입력해주세요</div>
            <div className="empty-sub">
              쿠팡, 네이버, G마켓, 무신사 등<br />
              상품 페이지 URL을 붙여넣으면<br />
              Claude가 실시간으로 읽어드립니다
            </div>
          </div>
        )}

        {msgs.map(m => {
          if (m.kind === 'user') return (
            <div className="msg-row user" key={m.id}>
              <div className="bubble-user">{m.url}</div>
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

          if (m.kind === 'assistant') return (
            <div className="msg-row assistant" key={m.id}>
              <div className="bubble-assistant">
                {m.text}
                {m.streaming && <span className="cursor" />}
              </div>
            </div>
          )

          if (m.kind === 'product') return (
            <div className="msg-row product" key={m.id}>
              <ProductCard data={m.data} />
            </div>
          )

          return null
        })}

        <div ref={bottomRef} />
      </div>

      <div className="input-bar">
        <input
          className="url-input"
          type="url"
          placeholder="https://www.coupang.com/vp/products/..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={loading}
          autoFocus
        />
        <button
          className={`analyze-btn${loading ? ' loading' : ''}`}
          onClick={analyze}
          disabled={loading}
        >
          {loading ? '분석 중' : '분석'}
        </button>
      </div>
    </>
  )
}
