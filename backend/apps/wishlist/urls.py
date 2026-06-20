from django.urls import path
from . import views

urlpatterns = [
    path('<str:customer_id>/', views.WishlistView.as_view(), name='wishlist'),
    path('<str:customer_id>/items/', views.WishlistItemAddView.as_view(), name='wishlist-add'),
    path('<str:customer_id>/items/<int:item_id>/', views.WishlistItemDeleteView.as_view(), name='wishlist-delete'),
]
