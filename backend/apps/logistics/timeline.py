"""
배송 추적 이벤트 적재 + 고객 화면용 타임라인 구성.

- ingest_tracking_events: 원천 이벤트(세관/택배 등) → TrackingEvent 저장 + 5단계 분류 +
  ShippingTracking의 current_stage / delivered_at / delivery_region 재계산.
- build_timeline: 진행 바 5단계 상태 + 날짜별 이벤트 로그 + 최종 배송정보 페이로드.
"""
from __future__ import annotations

import re
from datetime import datetime

from django.utils import timezone

from .models import ShippingTracking, TrackingEvent
from .stages import (
    TRACKING_STAGE_CHOICES, TRACKING_STAGE_ORDER, STAGE_LABELS,
    classify_tracking_stage, stage_index, max_stage,
)

# 이벤트 dict에서 값을 뽑을 때 허용하는 키 (원천 API마다 다름)
_TIME_KEYS = ['occurred_at', 'datetime', 'date_time', 'event_time', 'reg_date',
              'trans_time', 'status_date', 'time', 'date', 'timestamp']
_DESC_KEYS = ['description', 'desc', 'status_name', 'status', 'text', 'message',
              'trace_desc', 'event', 'detail']
_LOC_KEYS = ['location', 'place', 'where', 'branch', 'trans_place', 'area', 'region']
_CODE_KEYS = ['raw_code', 'status_code', 'code', 'scan_code']

_DT_FORMATS = [
    '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
    '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y%m%d%H%M%S', '%Y-%m-%d',
]


def _first(d: dict, keys: list):
    for k in keys:
        v = d.get(k)
        if v not in (None, ''):
            return v
    return None


def _parse_dt(value):
    """문자열/epoch → aware datetime. 실패 시 None."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value))
        except (ValueError, OSError, OverflowError):
            return None
    else:
        s = str(value).strip()
        dt = None
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in _DT_FORMATS:
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _extract_region(location: str, description: str) -> str:
    """배송 지역 추출: location 우선, 없으면 설명의 '○○ 배송 완료'에서 지역 추출."""
    if location:
        return location.strip()
    m = re.search(r'([가-힣A-Za-z]+)\s*배[송달]\s*(?:완료|출발|예정)', description or '')
    if m:
        return m.group(1)
    return ''


def normalize_event(item, default_source='carrier') -> dict | None:
    """원천 이벤트 dict → TrackingEvent 필드 dict. 시각·설명 없으면 None."""
    if not isinstance(item, dict):
        return None
    occurred_at = _parse_dt(_first(item, _TIME_KEYS))
    description = _first(item, _DESC_KEYS)
    if occurred_at is None or not description:
        return None
    description = str(description).strip()[:500]
    location = (_first(item, _LOC_KEYS) or '')
    raw_code = (_first(item, _CODE_KEYS) or '')
    stage = item.get('stage') or classify_tracking_stage(description, str(raw_code))
    return {
        'occurred_at': occurred_at,
        'description': description,
        'location': str(location).strip()[:255],
        'raw_code': str(raw_code).strip()[:50],
        'source': item.get('source') or default_source,
        'stage': stage,
        'raw': item,
    }


def ingest_tracking_events(order_number: str, events, default_source='carrier') -> dict:
    """
    원천 이벤트 목록 → TrackingEvent 저장(중복 제거) + ShippingTracking 단계 재계산.

    반환: {created, total, current_stage, delivered_at, delivery_region}
    """
    normalized = [n for n in (normalize_event(e, default_source) for e in (events or [])) if n]

    created = 0
    for n in normalized:
        _, was_created = TrackingEvent.objects.update_or_create(
            order_number=order_number,
            occurred_at=n['occurred_at'],
            description=n['description'],
            defaults={
                'stage': n['stage'],
                'location': n['location'],
                'raw_code': n['raw_code'],
                'source': n['source'],
                'raw': n['raw'],
            },
        )
        if was_created:
            created += 1

    return recompute_tracking_stage(order_number)


def recompute_tracking_stage(order_number: str) -> dict:
    """저장된 TrackingEvent 전체로 current_stage / delivered_at / delivery_region 재계산."""
    qs = list(TrackingEvent.objects.filter(order_number=order_number).order_by('occurred_at', 'id'))
    tracking, _ = ShippingTracking.objects.get_or_create(order_number=order_number)

    if not qs:
        return {
            'created': 0, 'total': 0,
            'current_stage': tracking.current_stage,
            'delivered_at': tracking.delivered_at,
            'delivery_region': tracking.delivery_region,
        }

    current = max_stage([e.stage for e in qs])
    tracking.current_stage = current

    delivered_event = next((e for e in reversed(qs) if e.stage == 'delivered'), None)
    if delivered_event:
        tracking.delivered_at = delivered_event.occurred_at
        region = _extract_region(delivered_event.location, delivered_event.description)
        if region:
            tracking.delivery_region = region

    tracking.save(update_fields=[
        'current_stage', 'delivered_at', 'delivery_region', 'updated_at',
    ])

    return {
        'total': len(qs),
        'current_stage': current,
        'delivered_at': tracking.delivered_at,
        'delivery_region': tracking.delivery_region,
    }


def build_timeline(order_number: str) -> dict:
    """
    고객 배송추적 화면 페이로드.

    {
      order_number, current_stage, current_stage_index,
      stages: [{key,label,status,reached_at}],     # status: completed|current|pending
      events_by_date: [{date, items:[{occurred_at, time, stage, stage_label, description, location, source}]}],
      delivery: {delivered_at, region, carrier, tracking_number, delivery_type}
    }
    """
    tracking = ShippingTracking.objects.filter(order_number=order_number).first()
    events = list(TrackingEvent.objects.filter(order_number=order_number).order_by('occurred_at', 'id'))

    current_stage = tracking.current_stage if tracking else (
        max_stage([e.stage for e in events]) if events else 'shipment_sent'
    )
    cur_idx = stage_index(current_stage)

    # 단계별 최초 도달 시각
    reached = {}
    for e in events:
        if e.stage not in reached:
            reached[e.stage] = e.occurred_at

    stages = []
    for i, (key, label) in enumerate(TRACKING_STAGE_CHOICES):
        if i < cur_idx:
            status = 'completed'
        elif i == cur_idx:
            status = 'current'
        else:
            status = 'pending'
        stages.append({
            'key': key,
            'label': label,
            'status': status,
            'reached_at': reached.get(key),
        })

    # 날짜별 그룹 (occurred_at 로컬 날짜 기준)
    groups = []
    by_date = {}
    for e in events:
        local = timezone.localtime(e.occurred_at)
        dkey = local.strftime('%Y-%m-%d')
        if dkey not in by_date:
            by_date[dkey] = []
            groups.append(dkey)
        by_date[dkey].append({
            'occurred_at': e.occurred_at,
            'time': local.strftime('%H:%M:%S'),
            'stage': e.stage,
            'stage_label': STAGE_LABELS.get(e.stage, e.stage),
            'description': e.description,
            'location': e.location,
            'source': e.source,
        })
    events_by_date = [{'date': d, 'items': by_date[d]} for d in groups]

    delivery = {
        'delivered_at': tracking.delivered_at if tracking else None,
        'region': tracking.delivery_region if tracking else '',
        'carrier': tracking.carrier if tracking else '',
        'tracking_number': tracking.tracking_number if tracking else '',
        'delivery_type': tracking.dhub_delivery_type if tracking else '',
    }

    return {
        'order_number': order_number,
        'current_stage': current_stage,
        'current_stage_index': cur_idx,
        'stages': stages,
        'events_by_date': events_by_date,
        'delivery': delivery,
    }
