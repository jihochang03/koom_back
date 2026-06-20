from django.urls import path
from . import views

urlpatterns = [
    path('analyze/', views.AnalyzeView.as_view(), name='scraping-analyze'),
    path('requests/', views.ScrapeRequestListView.as_view(), name='scraping-request-list'),
    path('requests/<int:pk>/', views.ScrapeRequestDetailView.as_view(), name='scraping-request-detail'),
    path('visits/recent/', views.UrlVisitRecentView.as_view(), name='url-visits-recent'),
    path('visits/popular/', views.UrlPopularView.as_view(), name='url-visits-popular'),
]
