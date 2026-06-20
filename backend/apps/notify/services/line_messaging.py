import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

LINE_API = 'https://api.line.me/v2/bot/message/push'


def _token() -> str:
    return getattr(settings, 'LINE_CHANNEL_ACCESS_TOKEN', '') or os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')


# 이벤트별 메시지 템플릿
_TEMPLATES: dict[str, str] = {
    'order_confirmed':  '【koom】ご注文を受け付けました。\n注文番号: {order_number}',
    'payment_complete': '【koom】お支払いが完了しました。\n注文番号: {order_number}\n金額: ¥{amount_jpy}',
    'purchase_started': '【koom】商品の購入手続きを開始しました。\n注文番号: {order_number}',
    'inspection_done':  '【koom】検品が完了しました。まもなく発送します。\n注文番号: {order_number}',
    'shipping_kr':      '【koom】韓国から発送しました。\n注文番号: {order_number}',
    'shipping_intl':    '【koom】国際配送中です。\n注文番号: {order_number}\n追跡番号: {tracking_number}',
    'shipping_jp':      '【koom】日本国内で配送中です。\n注文番号: {order_number}\n追跡番号: {tracking_number}',
    'delivered':        '【koom】お荷物が届きました！\n注文番号: {order_number}\nご利用ありがとうございました。',
    'cancel_complete':  '【koom】ご注文をキャンセルしました。\n注文番号: {order_number}',
    'refund_complete':  '【koom】返金処理が完了しました。\n注文番号: {order_number}\n返金額: ¥{amount_jpy}',
}


def send(line_user_id: str, event: str, context: dict | None = None) -> bool:
    """LINE Messaging API — Push Message 발송."""
    token = _token()
    if not token:
        logger.warning("LINE_CHANNEL_ACCESS_TOKEN not set — skipping LINE notify")
        return False

    ctx = context or {}
    template = _TEMPLATES.get(event, ctx.get('message', ''))
    if not template:
        logger.warning("No LINE template for event=%s", event)
        return False

    try:
        text = template.format_map({k: v for k, v in ctx.items()})
    except KeyError:
        text = template

    payload = {
        'to': line_user_id,
        'messages': [{'type': 'text', 'text': text}],
    }
    try:
        resp = requests.post(
            LINE_API,
            json=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("LINE push failed user=%s event=%s err=%s", line_user_id, event, e)
        return False
