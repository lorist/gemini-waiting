# pexip_policy/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('service/configuration', views.pexip_policy_view, name='pexip_service_policy'),
]
