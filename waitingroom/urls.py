# waitingroom/urls.py
from django.urls import path, re_path
from . import views
from . import consumers # Import consumers for WebSocket routing

urlpatterns = [
    # URL for the patient-facing page to join a queue
    path('join-queue/', views.patient_waiting_room_view, name='patient_join_queue'),

    # URL for the doctor's dashboard.
    # We'll assume a doctor_id is part of the URL for simplicity.
    # In a real app, this might be protected by authentication and not directly expose ID.
    path('doctor/<int:doctor_id>/', views.doctor_dashboard_view, name='doctor_dashboard'),

    # You might also need a URL for an API endpoint to fetch doctor data for the patient page
    # path('api/doctors/', views.doctor_list_api_view, name='api_doctor_list'),
    path('doctor-history/<int:doctor_id>/', views.doctor_history_view, name='doctor_history'),
]
