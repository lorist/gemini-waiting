# pexip_events/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('events', views.pexip_event_sink_view, name='pexip_event_sink'),
]
