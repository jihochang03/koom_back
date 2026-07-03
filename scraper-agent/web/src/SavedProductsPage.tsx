import { useState, useEffect, useCallback, type ChangeEvent } from 'react'
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

interface ProductsResponse {
  items: StoredProduct[]
  total: number
  domains: string[]
}

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      month: 'numeric', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function SavedProductsPage() {
  const [data, setData]       = useState<ProductsResponse | null>(null)
  const [domain, setDomain]   = useState('')
  const [q, setQ]             = useState('')
  const [loading, setLoading] = useState(false)
  const [clearing, setClearing] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (domain) params.set('domain', domain)
      if (q) params.set('q', q)
      params.set('limit', '200')
      const res = await fetch(`/api/local-products?${params}`)
      if (res.ok) setData(await res.json() as ProductsResponse)
    } catch { /* ignore */ }
    setLoading(false)
  }, [domain, q])

  useEffect(() => { void load() }, [load])

  const deleteProduct = async (id: string) => {
    await fetch(`/api/local-products/${id}`, { method: 'DELETE' })
    setData(prev => prev ? {
      ...prev,
      items: prev.items.filter(p => p.id !== id),
      total: prev.total - 1,
    } : prev)
  }

  const clearAll = async () => {
    if (!confirm(`저장된 상품 ${data?.total ?? 0}개를 모두 삭제하시겠습니까?`)) return
    setClearing(true)
    await fetch('/api/local-products', { method: 'DELETE' })
    setData(prev => prev ? { ...prev, items: [], total: 0 } : prev)
    setClearing(false)
  }

  const onSearch = (e: ChangeEvent<HTMLInputElement>) => setQ(e.target.value)

  const items = data?.items ?? []
  const domains = data?.domains ?? []
  const total = data?.total ?? 0

  return (
    <div className="sp-layout">
      {/* ── Filter bar ── */}
      <div className="sp-toolbar">
        <div className="sp-toolbar-left">
          <span className="sp-count">{total}개 상품</span>

          {/* Domain chips */}
          <div className="sp-domain-chips">
            <button
              className={`chip${!domain ? ' active' : ''}`}
              onClick={() => setDomain('')}
            >
              전체
            </button>
            {domains.map(d => (
              <button
                key={d}
                className={`chip${domain === d ? ' active' : ''}`}
                onClick={() => setDomain(d === domain ? '' : d)}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <div className="sp-toolbar-right">
          <div className="sp-search-box">
            <input
              type="text"
              placeholder="제목, 브랜드, 판매자 검색..."
              value={q}
              onChange={onSearch}
            />
          </div>
          <button
            className="sp-refresh-btn"
            onClick={() => void load()}
            disabled={loading}
          >
            {loading ? '↻' : '새로고침'}
          </button>
          {total > 0 && (
            <button
              className="sp-clear-btn"
              onClick={() => void clearAll()}
              disabled={clearing}
            >
              {clearing ? '삭제 중...' : '전체 삭제'}
            </button>
          )}
        </div>
      </div>

      {/* ── Product grid ── */}
      <div className="sp-content">
        {items.length === 0 ? (
          <div className="empty-state" style={{ minHeight: '50vh' }}>
            <div className="empty-logo">📦</div>
            <div className="empty-title">
              {loading ? '불러오는 중...' : q || domain ? '검색 결과 없음' : '저장된 상품 없음'}
            </div>
            <div className="empty-sub">
              {!loading && !q && !domain &&
                '목록 수집 탭에서 상품을 수집하면 여기에 저장됩니다'
              }
            </div>
          </div>
        ) : (
          <div className="sp-grid">
            {items.map(p => (
              <div key={p.id} className="sp-grid-cell">
                <div className="sp-card-meta">
                  <span className="sp-card-domain">{p.domain}</span>
                  <span className="sp-card-date">{fmtDate(p.crawled_at)}</span>
                  <div className="sp-card-actions">
                    <a
                      className="sp-card-btn"
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="상품 페이지 열기"
                    >
                      ↗
                    </a>
                    <button
                      className="sp-card-btn del"
                      onClick={() => void deleteProduct(p.id)}
                      title="삭제"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <ProductCard data={p.data} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
