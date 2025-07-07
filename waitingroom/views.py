# waitingroom/views.py
#https://gemini.google.com/app/f8d063d46c0e1969
# daphne -p 8000 --verbosity 2 waitingproj.asgi:application

from django.shortcuts import render, get_object_or_404
from .models import Doctor, WaitingRoomEntry # Import WaitingRoomEntry

def patient_waiting_room_view(request):
    """
    Renders the patient-facing HTML page for joining a doctor's waiting room.
    Fetches all doctors from the database to populate the dropdown.
    """
    doctors = Doctor.objects.all().order_by('name') # Fetch all doctors, ordered by name
    context = {
        'doctors': doctors,
    }
    return render(request, 'waitingroom/patient_waiting_room.html', context)

def doctor_dashboard_view(request, doctor_id):
    """
    Renders the doctor's dashboard HTML page.
    It fetches the specific doctor based on the doctor_id from the URL.
    """
    doctor = get_object_or_404(Doctor, pk=doctor_id)
    context = {
        'doctor': doctor,
    }
    return render(request, 'waitingroom/doctor_dashboard.html', context)

def doctor_history_view(request, doctor_id):
    """
    Renders the doctor's patient history page.
    Shows patients with 'Done' or 'Cancelled' status for the specific doctor.
    """
    doctor = get_object_or_404(Doctor, pk=doctor_id)
    historical_entries = WaitingRoomEntry.objects.filter(
        doctor=doctor,
        status__in=['Done', 'Cancelled'] # Filter for historical statuses
    ).select_related('patient').order_by('-arrived_at') # Order by most recent first

    context = {
        'doctor': doctor,
        'historical_entries': historical_entries,
    }
    return render(request, 'waitingroom/doctor_history.html', context)

