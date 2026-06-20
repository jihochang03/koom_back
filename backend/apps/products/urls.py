from django.urls import path
from . import views

urlpatterns = [
    path('', views.ProductListView.as_view()),
    path('batch/', views.ProductBatchCreateView.as_view()),
    path('categories/', views.ProductCategoryListView.as_view()),
    path('arrival-photos/<int:photo_id>/', views.ArrivalPhotoDeleteView.as_view()),
    path('<int:pk>/category/', views.ProductCategoryUpdateView.as_view()),
    path('<int:pk>/badges/', views.ProductBadgeUpdateView.as_view()),
    path('<int:pk>/detail/', views.ProductDetailUpdateView.as_view()),
    path('<int:pk>/refresh/', views.ProductRefreshView.as_view()),
    path('<int:pk>/page/', views.ProductDetailPageView.as_view()),
    path('<int:pk>/inbound/', views.ProductInboundUpdateView.as_view()),
    path('<int:pk>/arrival-photos/', views.ArrivalPhotoListCreateView.as_view()),
]
