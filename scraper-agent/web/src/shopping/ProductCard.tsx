// Shopping product card display component
export interface OptionGroup {
  name: string
  values: string[]
}

export interface ProductData {
  title?: string
  price?: { original: number | null; discounted: number | null; currency: string } | null
  options?: OptionGroup[]
  images?: string[]
  brand?: string | null
  availability?: string
  rating?: number | null
  review_count?: number | null
  seller?: string | null
}

function fmt(n: number | null | undefined) {
  if (n == null) return null
  return '₩' + n.toLocaleString('ko-KR')
}

export default function ProductCard({ data }: { data: ProductData }) {
  const discounted = data.price?.discounted ?? data.price?.original
  const original   = data.price?.original
  const hasDiscount = original && discounted && original > discounted
  const rate = hasDiscount ? Math.round((1 - discounted! / original!) * 100) : null
  const img = data.images?.[0]
  const isOut = data.availability === 'out_of_stock'
  const options = (data.options ?? []).filter(o => o.values?.length > 0)

  return (
    <div className="product-card">
      <div className="card-inner">
        <div className="card-img">
          {img
            ? <img src={img} alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            : '📦'}
        </div>

        <div className="card-body">
          {data.title && <div className="card-title">{data.title}</div>}

          {discounted != null && (
            <div className="card-price">
              <span className="price-discounted">{fmt(discounted)}</span>
              {hasDiscount && <span className="price-original">{fmt(original)}</span>}
              {rate && <span className="price-badge">-{rate}%</span>}
            </div>
          )}

          <div className="card-meta">
            {data.availability && (
              <span className="meta-item">
                <span className={`avail-dot${isOut ? ' out' : ''}`} />
                {isOut ? '품절' : '판매중'}
              </span>
            )}
            {data.seller && <span className="meta-item">🏪 {data.seller}</span>}
            {data.rating != null && (
              <span className="meta-item">
                ⭐ {data.rating}
                {data.review_count != null && ` (${data.review_count.toLocaleString()})`}
              </span>
            )}
            {data.brand && <span className="meta-item">🏷 {data.brand}</span>}
          </div>
        </div>
      </div>

      {options.length > 0 && (
        <div className="card-options">
          <div className="options-label">옵션</div>
          {options.map((g, i) => {
            const show = g.values.slice(0, 12)
            const rest = g.values.length - show.length
            return (
              <div className="option-group" key={i}>
                <span className="option-group-name">{g.name}</span>
                <div className="option-tags">
                  {show.map((v, j) => <span className="tag" key={j}>{v}</span>)}
                  {rest > 0 && <span className="tag more">+{rest}</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
