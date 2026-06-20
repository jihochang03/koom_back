import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

_SUBJECTS: dict[str, str] = {
    'order_confirmed':  '【koom】ご注文を受け付けました',
    'payment_complete': '【koom】お支払い完了のお知らせ',
    'purchase_started': '【koom】商品購入のお知らせ',
    'inspection_done':  '【koom】検品完了のお知らせ',
    'shipping_kr':      '【koom】韓国発送のお知らせ',
    'shipping_intl':    '【koom】国際配送中のお知らせ',
    'shipping_jp':      '【koom】日本国内配送中のお知らせ',
    'delivered':        '【koom】配達完了のお知らせ',
    'cancel_complete':  '【koom】キャンセル完了のお知らせ',
    'refund_complete':  '【koom】返金完了のお知らせ',
}

_BODIES: dict[str, str] = {
    'order_confirmed':  'ご注文ありがとうございます。\n注文番号: {order_number} を受け付けました。',
    'payment_complete': 'お支払いが完了しました。\n注文番号: {order_number}\n決済金額: ¥{amount_jpy}',
    'inspection_done':  '商品の検品が完了しました。まもなく発送します。\n注文番号: {order_number}',
    'shipping_intl':    '商品が国際配送中です。\n注文番号: {order_number}\n追跡番号: {tracking_number}',
    'delivered':        'お荷物が届きました！ご利用ありがとうございます。\n注文番号: {order_number}',
    'cancel_complete':  'ご注文をキャンセルしました。\n注文番号: {order_number}',
    'refund_complete':  '返金処理が完了しました。\n注文番号: {order_number}\n返金額: ¥{amount_jpy}',
}


def send(to_email: str, event: str, context: dict | None = None) -> bool:
    """SendGrid 이메일 발송."""
    api_key = getattr(settings, 'SENDGRID_API_KEY', '') or os.environ.get('SENDGRID_API_KEY', '')
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set — skipping email notify")
        return False

    ctx = context or {}
    subject = _SUBJECTS.get(event, ctx.get('subject', 'koom お知らせ'))
    body_tmpl = _BODIES.get(event, ctx.get('body', ''))
    try:
        body = body_tmpl.format_map({k: v for k, v in ctx.items()})
    except KeyError:
        body = body_tmpl

    from_email = getattr(settings, 'SENDGRID_FROM_EMAIL', 'noreply@koom.jp')
    from_name  = getattr(settings, 'SENDGRID_FROM_NAME', 'koom')

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, From, To, Content

        message = Mail(
            from_email=From(from_email, from_name),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=Content('text/plain', body),
        )
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        return True
    except Exception as e:
        logger.error("SendGrid failed to=%s event=%s err=%s", to_email, event, e)
        return False
