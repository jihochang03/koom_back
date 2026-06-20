import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

_TEMPLATES: dict[str, str] = {
    'order_confirmed':  '【koom】注文番号{order_number}を受け付けました。',
    'payment_complete': '【koom】決済完了 注文:{order_number} ¥{amount_jpy}',
    'shipping_intl':    '【koom】国際発送 注文:{order_number} 追跡:{tracking_number}',
    'delivered':        '【koom】配達完了 注文:{order_number} ありがとうございました。',
    'refund_complete':  '【koom】返金完了 注文:{order_number} ¥{amount_jpy}',
}


def send(to_number: str, event: str, context: dict | None = None) -> bool:
    """Twilio SMS 발송. to_number는 E.164 형식 (+81XXXXXXXXXX)."""
    sid   = getattr(settings, 'TWILIO_ACCOUNT_SID', '') or os.environ.get('TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN',  '') or os.environ.get('TWILIO_AUTH_TOKEN', '')
    from_ = getattr(settings, 'TWILIO_FROM_NUMBER', '') or os.environ.get('TWILIO_FROM_NUMBER', '')

    if not all([sid, token, from_]):
        logger.warning("Twilio credentials not set — skipping SMS notify")
        return False

    ctx = context or {}
    template = _TEMPLATES.get(event, ctx.get('message', ''))
    if not template:
        logger.warning("No SMS template for event=%s", event)
        return False

    try:
        body = template.format_map({k: v for k, v in ctx.items()})
    except KeyError:
        body = template

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(to=to_number, from_=from_, body=body)
        return True
    except Exception as e:
        logger.error("Twilio failed to=%s event=%s err=%s", to_number, event, e)
        return False
