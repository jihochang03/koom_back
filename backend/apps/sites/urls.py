from django.urls import path
from . import views

urlpatterns = [
    path('', views.SiteListView.as_view(), name='site-list'),
    path('classify/', views.URLClassifyView.as_view(), name='url-classify'),
]
