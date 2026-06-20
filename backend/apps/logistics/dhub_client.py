import requests
from django.conf import settings


DHUB_STATUS_MAP = {
    'ORE':            {'customer_status': '주문 접수',          'stage': 'order_received'},
    'RPE':            {'customer_status': '국제 배송 준비',      'stage': 'preparing_dispatch'},
    'RFI':            {'customer_status': '일본 배송사 인계',    'stage': 'jp_carrier_handover'},
    'InTransit':      {'customer_status': '국제 배송 중',        'stage': 'intl_shipping'},
    'OutForDelivery': {'customer_status': '배달 예정',           'stage': 'intl_shipping'},
    'Delivered':      {'customer_status': '배송 완료',           'stage': 'delivered'},
    'AttemptFail':    {'customer_status': '배달 시도 실패',      'stage': 'intl_shipping'},
}


class DHubError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"DHubError {code}: {message}")


class DHubClient:
    def __init__(self):
        self.base_url = getattr(settings, 'DHUB_BASE_URL', 'https://dhub-api-qa.hanpda.com').rstrip('/')
        self.mall_id = getattr(settings, 'DHUB_MALL_ID', '')
        self.token = getattr(settings, 'DHUB_TOKEN', '')
        self.consumer_key = getattr(settings, 'DHUB_CONSUMER_KEY', '')
        self.seller_name = getattr(settings, 'DHUB_SELLER_NAME', 'Boltlab DK')

    def _headers(self):
        return {
            'consumerKey': self.consumer_key,
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    def _check(self, resp):
        data = resp.json()
        meta = data.get('meta', {})
        code = meta.get('code', resp.status_code)
        if code != 200:
            raise DHubError(code, meta.get('message', 'unknown'))
        return data.get('response')

    def register_order(self, order, address: dict) -> dict:
        """
        주문 등록 → FB 송장번호 채번.
        address 필수 키: receiver_name, receiver_cell, receiver_email,
                        receiver_zipcode, receiver_address1
        반환: {fb_invoice_no, ord_no, ord_bundle_no, result, delivery_type, ...}
        """
        item = {
            'seller_ord_code':      order.order_number,
            'seller_ord_item_code': order.order_number,
            'input_prd_name':       order.title[:500],
            'input_item_name':      order.title[:200],
            'ord_qty':              order.quantity,
            'selling_price':        float(order.price_product or 0),
            'hs_code':              address.get('hs_code', '621790'),
            'prd_category':         order.product_category or 'General',
            'prd_category_info':    order.product_category or 'General',
            'material':             address.get('material', ''),
            'cloth_material':       address.get('cloth_material', ''),
            'discount_price':       float(order.price_discount or 0),
        }
        bundle_no = order.order_number
        if order.group_id:
            try:
                bundle_no = order.group.group_number
            except Exception:
                pass

        payload = {
            'seller_name':            self.seller_name,
            'ord_date':               order.created_at.strftime('%Y-%m-%d'),
            'ord_bundle_no':          bundle_no,
            'currency_code':          'JPY',
            'country_domain':         'JP',
            'actual_payment':         float(order.price_actual or 0),
            'coupon_discount_price':  float(order.price_discount or 0),
            'points_spent_amount':    float(order.price_points_used or 0),
            'receiver_name':          address['receiver_name'],
            'receiver_name_voice':    address.get('receiver_name_voice', ''),
            'receiver_cell':          address['receiver_cell'],
            'receiver_email':         address['receiver_email'],
            'receiver_zipcode':       address['receiver_zipcode'],
            'receiver_address1':      address['receiver_address1'],
            'receiver_address2':      address.get('receiver_address2', ''),
            'receiver_address3':      address.get('receiver_address3', ''),
            'ship_fee':               float(order.price_intl_shipping or 0),
            'delivery_message':       address.get('delivery_message', ''),
            'item_list':              [item],
        }

        resp = requests.post(
            f'{self.base_url}/api/order/add',
            params={'mall_id': self.mall_id},
            headers=self._headers(),
            json=[payload],
            timeout=30,
        )
        results = self._check(resp)
        return results[0] if results else {}

    def instruct_delivery(self, fb_invoice_nos: list, requester_name: str,
                          requester_phone: str, arrival_due_date: str) -> dict:
        """배송지시: Fastbox 창고에서 국제 발송 지시."""
        payload = {
            'fb_invoice_no':        fb_invoice_nos,
            'instruction_requester': requester_name,
            'requester_phone':       requester_phone,
            'packing_status':        'O',
            'delivery_type':         'P',
            'arrival_due_date':      arrival_due_date,
        }
        resp = requests.post(
            f'{self.base_url}/api/delivery/instruction',
            params={'mall_id': self.mall_id},
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        return self._check(resp)

    def get_order_detail(self, fb_invoice_no: str) -> list:
        """주문 상세 조회."""
        resp = requests.get(
            f'{self.base_url}/api/order/detail',
            params={'mall_id': self.mall_id, 'fb_invoice_no': fb_invoice_no},
            headers=self._headers(),
            timeout=30,
        )
        return self._check(resp)

    def get_tracking(self, fb_invoice_no: str) -> dict:
        """배송추적 정보 조회."""
        resp = requests.get(
            f'{self.base_url}/api/Tracking',
            params={'mall_id': self.mall_id, 'fb_invoice_no': fb_invoice_no},
            headers=self._headers(),
            timeout=30,
        )
        return self._check(resp)

    def map_status(self, status_code: str) -> dict:
        """DHUB status_code → {customer_status, stage}"""
        return DHUB_STATUS_MAP.get(status_code, {
            'customer_status': status_code,
            'stage': 'intl_shipping',
        })
