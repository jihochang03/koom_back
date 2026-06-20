from django.urls import path
from . import views

urlpatterns = [
    path('', views.TemplateListView.as_view(), name='template-list'),
    path('build/', views.TemplateBuildView.as_view(), name='template-build'),
    path('build-logs/', views.TemplateBuildLogListView.as_view(), name='template-build-log-list'),
    path('domain/<str:domain>/', views.TemplateByDomainView.as_view(), name='template-by-domain'),
    # filename은 확장자가 있어 domain 라우트 다음에 위치
    path('<str:filename>/', views.TemplateDetailView.as_view(), name='template-detail'),
]
