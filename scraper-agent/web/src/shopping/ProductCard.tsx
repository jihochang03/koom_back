import { useState } from 'react'

export interface OptionGroup {
  name: string
  values: string[]
  soldout_values?: string[]
}

export interface SizeInfo {
  weight_kg?: number | null
  girth_sum_cm?: number | null
  confidence?: string
  source?: string
}

export interface ProductData {
  title?: string
  description?: string | null
  price?: { original: number | null; discounted: number | null; currency: string } | null
  options?: OptionGroup[]
  images?: string[]
  brand?: string | null
  availability?: string
  rating?: number | null
  review_count?: number | null
  seller?: string | null
  shipping_fee?: number | null
  shipping_fee_text?: string | null
  delivery_date?: string | null
  specifications?: Record<string, string>
  size?: SizeInfo | null
}

function fmt(n: number | null | undefined) {
  if (n == null) return null
  return '₩' + n.toLocaleString('ko-KR')
}

export default function ProductCard({ data }: { data: ProductData }) {
  const [imgIdx, setImgIdx] = useState(0)
  const [specsOpen, setSpecsOpen] = useState(false)

  const discounted = data.price?.discounted ?? data.price?.original
  const original   = data.price?.original
  const hasDiscount = original != null && discounted != null && original > discounted
  const rate = hasDiscount ? Math.round((1 - discounted! / original!) * 100) : null
  const images = (data.images ?? []).filter(Boolean)
  const img = images[Math.min(imgIdx, images.length - 1)]
  const isOut = data.availability === 'out_of_stock'
  const options = (data.options ?? []).filter(o => o.values?.length > 0)
  const specs = Object.entries(data.specifications ?? {}).filter(([, v]) => v)
  const visibleSpecs = specsOpen ? specs : specs.slice(0, 6)

  return (
    <div className="product-card">

      {/* ── Top: gallery + info ── */}
      <div className="card-top">
        <div className="card-gallery">
          <div className="card-img-main">
            {img
              ? <img src={img} alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              : <span className="card-img-ph">📦</span>
            }
          </div>
          {images.length > 1 && (
            <div className="card-thumbs">
              {images.slice(0, 8).map((src, i) => (
                <button
                  key={i}
                  className={`card-thumb${i === imgIdx ? ' active' : ''}`}
                  onClick={() => setImgIdx(i)}
                >
                  <img src={src} alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </button>
              ))}
              {images.length > 8 && (
                <span className="card-thumb-more">+{images.length - 8}</span>
              )}
            </div>
          )}
        </div>

        <div className="card-info">
          {data.title && <div className="card-title">{data.title}</div>}

          {(discounted != null || original != null) && (
            <div className="card-price">
              {discounted != null && <span className="price-main">{fmt(discounted)}</span>}
              {hasDiscount && <span className="price-orig">{fmt(original)}</span>}
              {rate != null && <span className="price-badge">-{rate}%</span>}
            </div>
          )}

          {data.availability && (
            <span className={`avail-badge${isOut ? ' out' : ''}`}>
              <span className="avail-dot" />
              {isOut ? '품절' : '판매중'}
            </span>
          )}

          <div className="card-meta">
            {data.seller && (
              <div className="meta-row">
                <span className="meta-lbl">판매자</span>
                <span className="meta-val">{data.seller}</span>
              </div>
            )}
            {data.brand && (
              <div className="meta-row">
                <span className="meta-lbl">브랜드</span>
                <span className="meta-val">{data.brand}</span>
              </div>
            )}
            {data.rating != null && (
              <div className="meta-row">
                <span className="meta-lbl">평점</span>
                <span className="meta-val">
                  ⭐ {data.rating}
                  {data.review_count != null && (
                    <span className="meta-sub"> ({data.review_count.toLocaleString()}개)</span>
                  )}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Shipping ── */}
      {(data.shipping_fee_text || data.delivery_date) && (
        <div className="card-shipping">
          <span className="ship-icon">🚚</span>
          {data.shipping_fee_text && (
            <span className={data.shipping_fee === 0 ? 'free-ship' : 'ship-fee'}>
              {data.shipping_fee_text}
            </span>
          )}
          {data.delivery_date && (
            <>
              {data.shipping_fee_text && <span className="ship-sep">·</span>}
              <span className="ship-date">{data.delivery_date}</span>
            </>
          )}
        </div>
      )}

      {/* ── Options ── */}
      {options.length > 0 && (
        <div className="card-section">
          <div className="section-label">옵션</div>
          <div className="options-list">
            {options.map((g, i) => {
              const soSet = new Set(g.soldout_values ?? [])
              return (
                <div className="opt-group" key={i}>
                  <span className="opt-group-name">{g.name}</span>
                  <div className="opt-tags">
                    {g.values.map((v, j) => (
                      <span key={j} className={`opt-tag${soSet.has(v) ? ' soldout' : ''}`}>
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Specifications ── */}
      {specs.length > 0 && (
        <div className="card-section">
          <div className="section-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            스펙
            {specs.length > 6 && (
              <button className="spec-toggle" onClick={() => setSpecsOpen(o => !o)}>
                {specsOpen ? '접기' : `+${specs.length - 6}개 더보기`}
              </button>
            )}
          </div>
          <table className="spec-table">
            <tbody>
              {visibleSpecs.map(([k, v]) => (
                <tr key={k}>
                  <td className="spec-key">{k}</td>
                  <td className="spec-val">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Size ── */}
      {data.size && (data.size.weight_kg != null || data.size.girth_sum_cm != null) && (
        <div className="card-section">
          <div className="section-label">크기/무게</div>
          <div className="size-row">
            {data.size.weight_kg != null && (
              <span className="size-chip">
                <span className="meta-lbl">무게</span> {data.size.weight_kg}kg
              </span>
            )}
            {data.size.girth_sum_cm != null && (
              <span className="size-chip">
                <span className="meta-lbl">둘레합</span> {data.size.girth_sum_cm}cm
              </span>
            )}
            {data.size.confidence && (
              <span className={`conf-badge conf-${data.size.confidence.toLowerCase()}`}>
                {data.size.confidence}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
