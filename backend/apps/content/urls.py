from django.urls import path
from . import views

urlpatterns = [
    path('faq/', views.FAQListView.as_view(), name='faq-list'),
    path('faq/<int:pk>/', views.FAQDetailView.as_view(), name='faq-detail'),
    path('notices/', views.NoticeListView.as_view(), name='notice-list'),
    path('notices/<int:pk>/', views.NoticeDetailView.as_view(), name='notice-detail'),
    path('banners/', views.EventBannerListView.as_view(), name='banner-list'),
    path('banners/<int:pk>/', views.EventBannerDetailView.as_view(), name='banner-detail'),
    path('policies/', views.PolicyListView.as_view(), name='policy-list'),
    path('policies/<str:policy_type>/', views.PolicyDetailView.as_view(), name='policy-detail'),
]
