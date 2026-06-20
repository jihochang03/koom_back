from django.urls import path
from . import views, views_paypay

urlpatterns = [
    # 카드 결제 (GMO idPass)
    path('entry/',                        views.PaymentEntryView.as_view()),
    path('execute/',                      views.PaymentExecuteView.as_view()),
    path('capture/',                      views.PaymentCaptureView.as_view()),
    path('cancel/',                       views.PaymentCancelView.as_view()),
    path('refund/',                       views.PaymentRefundView.as_view()),
    path('status/<str:order_id>/',        views.PaymentStatusView.as_view()),
    # PayPay QR 결제
    path('paypay/entry/',                 views_paypay.PayPayEntryView.as_view()),
    path('paypay/execute/',               views_paypay.PayPayExecuteView.as_view()),
    path('paypay/status/<str:order_id>/', views_paypay.PayPayStatusView.as_view()),
]
