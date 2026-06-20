from django.urls import path
from . import views

urlpatterns = [
    path('upload/',                      views.FileUploadView.as_view()),
    path('files/',                       views.FileListView.as_view()),
    path('files/<int:pk>/',              views.FileDeleteView.as_view()),
    path('files/<int:pk>/presigned/',    views.PresignedUrlView.as_view()),
]
