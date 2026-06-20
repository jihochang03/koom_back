from django.urls import path
from . import views

urlpatterns = [
    path('error-criteria/', views.ErrorCriteriaView.as_view(), name='error-criteria'),
    path('error-criteria/history/', views.ErrorCriteriaHistoryView.as_view(), name='error-criteria-history'),
    path('error-criteria/<int:pk>/log/', views.ErrorCriteriaLogView.as_view(), name='error-criteria-log'),
]
