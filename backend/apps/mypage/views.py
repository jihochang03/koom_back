from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import UserAddress, UserCoupon, PointLog, NotificationSetting
from .serializers import (
    UserAddressSerializer, UserAddressWriteSerializer,
    UserCouponSerializer, PointLogSerializer, NotificationSettingSerializer,
)


# ── Address ───────────────────────────────────────────────────────────────────

class AddressListView(APIView):
    def get(self, request, customer_id):
        addrs = UserAddress.objects.filter(customer_id=customer_id)
        return Response(UserAddressSerializer(addrs, many=True).data)

    def post(self, request, customer_id):
        ser = UserAddressWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d.get('is_default'):
            UserAddress.objects.filter(customer_id=customer_id).update(is_default=False)
        addr = UserAddress.objects.create(customer_id=customer_id, **d)
        return Response(UserAddressSerializer(addr).data, status=http_status.HTTP_201_CREATED)


class AddressDetailView(APIView):
    def patch(self, request, customer_id, addr_id):
        addr = get_object_or_404(UserAddress, id=addr_id, customer_id=customer_id)
        ser = UserAddressWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d.get('is_default'):
            UserAddress.objects.filter(customer_id=customer_id).update(is_default=False)
        for k, v in d.items():
            setattr(addr, k, v)
        addr.save()
        return Response(UserAddressSerializer(addr).data)

    def delete(self, request, customer_id, addr_id):
        addr = get_object_or_404(UserAddress, id=addr_id, customer_id=customer_id)
        addr.delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


# ── Coupons ───────────────────────────────────────────────────────────────────

class UserCouponListView(APIView):
    def get(self, request, customer_id):
        qs = UserCoupon.objects.filter(customer_id=customer_id).select_related('coupon')
        used = request.query_params.get('used')
        if used == 'true':
            qs = qs.exclude(used_at=None)
        elif used == 'false':
            qs = qs.filter(used_at=None)
        return Response(UserCouponSerializer(qs, many=True).data)


# ── Points ────────────────────────────────────────────────────────────────────

class PointLogListView(APIView):
    def get(self, request, customer_id):
        logs = PointLog.objects.filter(customer_id=customer_id)
        balance = logs.first().balance_after if logs.exists() else 0
        return Response({
            'balance': balance,
            'logs': PointLogSerializer(logs, many=True).data,
        })


# ── Notification settings ─────────────────────────────────────────────────────

class NotificationSettingView(APIView):
    def get(self, request, customer_id):
        obj, _ = NotificationSetting.objects.get_or_create(customer_id=customer_id)
        return Response(NotificationSettingSerializer(obj).data)

    def patch(self, request, customer_id):
        obj, _ = NotificationSetting.objects.get_or_create(customer_id=customer_id)
        ser = NotificationSettingSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


# ── Admin: Coupon management ──────────────────────────────────────────────────

class CouponAdminListView(APIView):
    """어드민: 쿠폰 전체 목록 조회 및 쿠폰 생성"""

    def get(self, request):
        from .models import Coupon
        qs = Coupon.objects.all()
        is_active = request.query_params.get('is_active')
        if is_active == 'true':
            qs = qs.filter(is_active=True)
        elif is_active == 'false':
            qs = qs.filter(is_active=False)
        from .serializers import CouponSerializer
        return Response(CouponSerializer(qs, many=True).data)

    def post(self, request):
        from .models import Coupon
        from .serializers import CouponSerializer
        ser = CouponSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(CouponSerializer(obj).data, status=201)


class CouponAdminDetailView(APIView):
    """어드민: 쿠폰 수정 및 삭제"""

    def get(self, request, coupon_id):
        from .models import Coupon
        from .serializers import CouponSerializer
        coupon = get_object_or_404(Coupon, pk=coupon_id)
        return Response(CouponSerializer(coupon).data)

    def patch(self, request, coupon_id):
        from .models import Coupon
        from .serializers import CouponSerializer
        coupon = get_object_or_404(Coupon, pk=coupon_id)
        ser = CouponSerializer(coupon, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CouponSerializer(coupon).data)

    def delete(self, request, coupon_id):
        from .models import Coupon
        coupon = get_object_or_404(Coupon, pk=coupon_id)
        coupon.is_active = False
        coupon.save()
        return Response(status=204)


class UserCouponIssueView(APIView):
    """어드민: 특정 쿠폰을 고객에게 발급"""

    def post(self, request, coupon_id):
        from .models import Coupon, UserCoupon
        from .serializers import UserCouponSerializer
        coupon = get_object_or_404(Coupon, pk=coupon_id, is_active=True)
        customer_ids = request.data.get('customer_ids', [])
        if not customer_ids:
            customer_id = request.data.get('customer_id')
            if customer_id:
                customer_ids = [customer_id]

        if not customer_ids:
            return Response({'error': 'customer_id or customer_ids required'}, status=400)

        issued = []
        for cid in customer_ids:
            uc, created = UserCoupon.objects.get_or_create(customer_id=cid, coupon=coupon)
            if created:
                issued.append(cid)

        return Response({'issued_to': issued, 'skipped_already_issued': len(customer_ids) - len(issued)}, status=201)
