# Prohibited Items API

수입 금지·제한 품목 키워드 관리 (Section 17.3).

Base URL: `/api/prohibited/`

## 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/prohibited/` | 키워드 목록 (`?risk_level=`, `?category=`) |
| POST | `/api/prohibited/` | 키워드 등록 (어드민) |
| GET | `/api/prohibited/{id}/` | 키워드 상세 |
| PATCH | `/api/prohibited/{id}/` | 키워드 수정 |
| DELETE | `/api/prohibited/{id}/` | 키워드 비활성화 (soft delete) |
| POST | `/api/prohibited/check/` | 상품명 금지 품목 매칭 확인 |

## POST `/api/prohibited/check/`

```json
{ "title": "화이트 라이터 세트" }
```

Response:
```json
{
  "matches": [{ "keyword": "라이터", "risk_level": "restricted", ... }],
  "risk_level": "restricted",
  "title_checked": "화이트 라이터 세트"
}
```

## risk_level 허용값

| 값 | 설명 |
|----|------|
| `prohibited` | 수입 금지 |
| `restricted` | 수입 제한 |
| `warning` | 주의 |

## DB 모델

`keyword`(unique), `category`, `risk_level`, `description`, `customs_reference`, `is_active`
