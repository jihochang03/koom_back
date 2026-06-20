from django.urls import path
from . import views

urlpatterns = [
    path('', views.MallListView.as_view()),
    path('featured-categories/', views.FeaturedCategoryListView.as_view()),
    path('featured-categories/<int:pk>/', views.FeaturedCategoryDetailView.as_view()),
    path('<slug:slug>/', views.MallDetailView.as_view()),
    path('<slug:slug>/products/', views.MallProductListView.as_view()),
    path('<slug:slug>/recommended/', views.MallRecommendedView.as_view()),
    path('<slug:slug>/jobs/', views.MallCrawlJobListView.as_view()),
    path('<slug:slug>/jobs/<int:job_id>/crawl/', views.MallCrawlJobTriggerView.as_view()),
]
