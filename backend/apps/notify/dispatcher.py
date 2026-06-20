"""
알림 디스패처.

각 채널 서비스를 호출하고 NotificationLog에 기록.
orders 앱의 status 변경 시 호출 진입점.

사용 예:
    from apps.notify.dispatcher import notify_order_event
    notify_order_event(
        customer_id='user@email.com',
        event='payment_complete',
        channels=['line', 'email'],
        recipients={'line': 'Uxxxxxxxxx', 'email': 'user@email.com'},
        context={'order_number': 'ORD-20260609-ABC', 'amount_jpy': 1200},
        order_number='ORD-20260609-ABC',
    )
"""
import logging
from django.utils import timezone

from .models import NotificationLog
from .services import line_messaging, email_sender, sms

logger = logging.getLogger(__name__)

_SENDERS = {
    'line':  line_messaging.send,
    'email': email_sender.send,
    'sms':   sms.send,
}


def notify_order_event(
    customer_id: str,
    event: str,
    channels: list[str],
    recipients: dict[str, str],   # {'line': userId, 'email': '...', 'sms': '+81...'}
    context: dict | None = None,
    order_number: str = '',
) -> dict[str, bool]:
    """지정 채널로 이벤트 알림 발송. 결과 dict 반환."""
    ctx = context or {}
    results = {}

    for channel in channels:
        recipient = recipients.get(channel, '')
        if not recipient:
            continue

        sender = _SENDERS.get(channel)
        if not sender:
            logger.warning("Unknown notify channel: %s", channel)
            continue

        log = NotificationLog.objects.create(
            customer_id=customer_id,
            channel=channel,
            event=event,
            recipient=recipient,
            order_number=order_number,
            send_status='pending',
        )

        ok = sender(recipient, event, ctx)
        log.send_status = 'sent' if ok else 'failed'
        log.sent_at = timezone.now() if ok else None
        log.save(update_fields=['send_status', 'sent_at'])

        results[channel] = ok

    return results
