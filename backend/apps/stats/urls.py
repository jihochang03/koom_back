from django.urls import path
from . import views

urlpatterns = [
    path('dk-burden/', views.DKBurdenStatsView.as_view(), name='stats-dk-burden'),
    path('error-rate/', views.ErrorRateStatsView.as_view(), name='stats-error-rate'),
    path('cs-conversion/', views.CSConversionStatsView.as_view(), name='stats-cs-conversion'),
    path('site-parsing/', views.SiteParsingStatsView.as_view(), name='stats-site-parsing'),
    path('monitoring/overview/', views.MonitoringOverviewView.as_view(), name='stats-monitoring-overview'),
]
