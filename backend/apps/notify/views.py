from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .dispatcher import notify_order_event
from .models import NotificationLog


class NotifySendView(APIView):
    """
    POST /api/notify/send/

    수동 알림 발송 (admin/서버 내부 호출용).

    Request:
    {
      "customer_id": "user@email.com",
      "event": "payment_complete",
      "channels": ["line", "email"],
      "recipients": { "line": "Uxxxx", "email": "user@email.com" },
      "context": { "order_number": "ORD-...", "amount_jpy": 1200 },
      "order_number": "ORD-..."
    }
    """

    def post(self, request):
        d = request.data
        customer_id  = d.get('customer_id', '')
        event        = d.get('event', '')
        channels     = d.get('channels', [])
        recipients   = d.get('recipients', {})
        context      = d.get('context', {})
        order_number = d.get('order_number', '')

        if not customer_id or not event or not channels:
            return Response({'error': 'customer_id, event, channels required'}, status=status.HTTP_400_BAD_REQUEST)

        results = notify_order_event(
            customer_id=customer_id,
            event=event,
            channels=channels,
            recipients=recipients,
            context=context,
            order_number=order_number,
        )
        return Response({'results': results})


class NotifyLogView(APIView):
    """
    GET /api/notify/logs/?customer_id=xxx&limit=20

    고객별 발송 이력 조회.
    """

    def get(self, request):
        customer_id = request.query_params.get('customer_id', '')
        limit = int(request.query_params.get('limit', 20))

        qs = NotificationLog.objects.all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        logs = list(qs.values(
            'id', 'customer_id', 'channel', 'event',
            'recipient', 'order_number', 'send_status',
            'error_detail', 'sent_at', 'created_at',
        )[:limit])
        return Response({'logs': logs})
