from django.urls import path
from . import views

urlpatterns = [
    path('', views.ProhibitedKeywordListView.as_view(), name='prohibited-list'),
    path('<int:pk>/', views.ProhibitedKeywordDetailView.as_view(), name='prohibited-detail'),
    path('check/', views.ProhibitedCheckView.as_view(), name='prohibited-check'),
]
