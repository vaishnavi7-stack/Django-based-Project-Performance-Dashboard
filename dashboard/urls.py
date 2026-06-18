from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="dashboard"),
    path("api/dashboard/", views.dashboard_data, name="dashboard_data"),
]
