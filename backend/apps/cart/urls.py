from django.urls import path
from . import views

urlpatterns = [
    path('<str:customer_id>/', views.CartView.as_view()),
    path('<str:customer_id>/page/', views.CartPageView.as_view()),
    path('<str:customer_id>/checkout/', views.CartCheckoutView.as_view()),
    path('<str:customer_id>/items/', views.CartItemListView.as_view()),
    path('<str:customer_id>/items/<int:item_id>/', views.CartItemDetailView.as_view()),
]
