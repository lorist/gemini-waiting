Django Patient Waiting Room App
This is a Django-based web application that provides a real-time patient waiting room system for doctors, featuring a patient-facing queue joining page and a doctor's dashboard with live updates.

Features
Doctor Management: Doctors can be added and managed via the Django Admin panel.

Patient Queueing: Patients can select a doctor from a dynamic list and join their waiting room queue.

Real-time Status Updates: Utilizes Django Channels and WebSockets to provide live updates of patient statuses on the doctor's dashboard and the patient's view.

Patient Status Management: Doctors can change a patient's status ('Waiting', 'In Progress', 'In Call', 'Done', 'Cancelled', 'Left Call') from their dashboard.

Unique Patient Identification: Patients are assigned a unique UUID for consistent identification across sessions.

Secure Virtual Room Access: Each patient entry has unique host_pin (for doctor) and guest_pin (for patient) for joining virtual meeting rooms (e.g., Pexip).

Patient Removal: Doctors can remove patients from the active queue, which also moves them to a history view.

Patient History: A dedicated page for doctors to view a history of patients whose appointments are 'Done' or 'Cancelled'.

Patient Notifications & Redirection: When a patient's status is marked 'Done' or 'Cancelled', they are informed via a dialogue and redirected back to the join queue page.

Real-time Chat: Both doctors and patients can send and receive chat messages in real-time.

Doctor's Dashboard: Chat is accessed via a dedicated "Chat" button per patient, with unread message badges.

Patient's Page: Chat is accessed via a "Chat" button, which automatically opens if the doctor sends the first message, and shows unread message badges.

Shared Whiteboard: A collaborative drawing whiteboard is available for doctors and patients.

Activation: The whiteboard is activated by the doctor when the patient's status is 'In Progress' or 'In Call'.

Real-time Drawing: Drawing actions are synchronized between the doctor and patient.

Drawing History: When the whiteboard is opened, previous drawings are loaded.

Color Selection & Clear: Users can select drawing colors and clear the canvas.

Pexip Integration: Direct links are provided for doctors and patients to join Pexip virtual meeting rooms based on their unique pins and patient UUIDs.

Responsive Design: Frontend utilizes Tailwind CSS for a mobile-first, responsive layout, with common styles centralized in base.html.

Technologies Used
Backend: Django (Python Web Framework)

Real-time: Django Channels (for WebSockets)

Database: SQLite (default, configurable for PostgreSQL, MySQL etc.)

Frontend: HTML, CSS (Tailwind CSS), JavaScript

ASGI Server: Daphne

Setup and Installation
Follow these steps to get the project up and running on your local machine.

1. Clone the Repository
git clone <your-repository-url>
cd <your-project-directory-name> # e.g., cd gemini-waiting

2. Create a Virtual Environment
It's highly recommended to use a virtual environment to manage dependencies.

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

3. Install Dependencies
Install Django, Channels, and any other necessary packages.

pip install Django channels daphne

4. Configure Django Settings
Ensure your waitingproj/settings.py file has the following crucial configurations:

# waitingproj/settings.py

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ... other settings ...

INSTALLED_APPS = [
    # ...
    'channels',
    'waitingroom', # Your app name
]

ASGI_APPLICATION = 'waitingproj.asgi.application' # IMPORTANT: Ensure this is correct

# Channels Layer (for development, use InMemoryChannelLayer)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Pexip Configuration (Add these lines)
PEXIP_ADDRESS = 'your_pexip_domain.com' # Replace with your Pexip domain
PEXIP_PATH = 'webapp' # Replace with your Pexip webapp path, e.g., 'webapp' or 'webrtc'

# Template Configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')], # Add this for project-level templates like base.html
        'APP_DIRS': True, # Crucial for finding templates in app/templates/app/
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ... rest of your settings ...

5. Configure ASGI Application
Ensure your waitingproj/asgi.py file is correctly set up to handle both HTTP and WebSocket protocols:

# waitingproj/asgi.py
import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import waitingroom.routing # Import your app's routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'waitingproj.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            waitingroom.routing.websocket_urlpatterns
        )
    ),
})

6. Define App Routing
Create waitingroom/routing.py to define your WebSocket URL patterns:

# waitingroom/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/waiting_room/(?P<doctor_id>\d+)/$', consumers.WaitingRoomConsumer.as_asgi()),
]

7. Define App Models
Ensure your waitingroom/models.py defines the Doctor, Patient, and WaitingRoomEntry models:

# waitingroom/models.py
from django.db import models
import uuid

class Doctor(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class Patient(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, null=False)
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class WaitingRoomEntry(models.Model):
    STATUS_CHOICES = [
        ('Waiting', 'Waiting'),
        ('In Progress', 'In Progress'),
        ('In Call', 'In Call'),
        ('Left Call', 'Left Call'),
        ('Done', 'Done'),
        ('Cancelled', 'Cancelled'),
    ]

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='waiting_patients')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Waiting')
    arrived_at = models.DateTimeField(auto_now_add=True)
    host_pin = models.CharField(max_length=6, unique=True, null=True, blank=True)
    guest_pin = models.CharField(max_length=6, unique=True, null=True, blank=True)
    added_by_doctor = models.BooleanField(default=False)
    whiteboard_active = models.BooleanField(default=False)
    whiteboard_data = models.TextField(default='[]')

    class Meta:
        ordering = ['arrived_at']

    def __str__(self):
        return f"{self.patient.name} for Dr. {self.doctor.name} - {self.status}"

8. Define App Views
Ensure your waitingroom/views.py contains the necessary views and passes Pexip settings:

# waitingroom/views.py
from django.shortcuts import render, get_object_or_404
from .models import Doctor, WaitingRoomEntry
from django.conf import settings

def patient_waiting_room_view(request):
    doctors = Doctor.objects.all().order_by('name')
    context = {
        'doctors': doctors,
        'pexip_address': settings.PEXIP_ADDRESS,
        'pexip_path': settings.PEXIP_PATH,
    }
    return render(request, 'waitingroom/patient_waiting_room.html', context)

def doctor_dashboard_view(request, doctor_id):
    doctor = get_object_or_404(Doctor, pk=doctor_id)
    context = {
        'doctor': doctor,
        'pexip_address': settings.PEXIP_ADDRESS,
        'pexip_path': settings.PEXIP_PATH,
    }
    return render(request, 'waitingroom/doctor_dashboard.html', context)

def doctor_history_view(request, doctor_id):
    doctor = get_object_or_404(Doctor, pk=doctor_id)
    historical_entries = WaitingRoomEntry.objects.filter(
        doctor=doctor,
        status__in=['Done', 'Cancelled']
    ).select_related('patient').order_by('-arrived_at')
    context = {
        'doctor': doctor,
        'historical_entries': historical_entries,
    }
    return render(request, 'waitingroom/doctor_history.html', context)

9. Define App URLs
Ensure your waitingroom/urls.py defines the HTTP URL patterns:

# waitingroom/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('join-queue/', views.patient_waiting_room_view, name='patient_join_queue'),
    path('doctor/<int:doctor_id>/', views.doctor_dashboard_view, name='doctor_dashboard'),
    path('doctor-history/<int:doctor_id>/', views.doctor_history_view, name='doctor_history'),
]

And ensure your project's main waitingproj/urls.py includes these:

# waitingproj/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('waitingroom.urls')),
]

10. Register Models with Admin
Create or update waitingroom/admin.py to register your models for admin access, including UUID and PINs:

# waitingroom/admin.py
from django.contrib import admin
from .models import Doctor, Patient, WaitingRoomEntry

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'uuid',)
    search_fields = ('name', 'uuid',)
    readonly_fields = ('uuid',)

@admin.register(WaitingRoomEntry)
class WaitingRoomEntryAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'patient', 'status', 'arrived_at', 'host_pin', 'guest_pin', 'whiteboard_active') # Added PINs and whiteboard_active
    list_filter = ('status', 'doctor', 'whiteboard_active') # Filter by whiteboard active status
    search_fields = ('patient__name', 'doctor__name', 'patient__uuid', 'host_pin', 'guest_pin') # Search by PINs
    raw_id_fields = ('doctor', 'patient')


11. Create Templates
Ensure you have the following HTML templates:

templates/base.html (for the base layout, now containing common styles)

waitingroom/templates/waitingroom/patient_waiting_room.html

waitingroom/templates/waitingroom/doctor_dashboard.html

waitingroom/templates/waitingroom/doctor_history.html

12. Make Migrations and Migrate Database
python manage.py makemigrations
python manage.py migrate

13. Create a Superuser (for Admin Access)
python manage.py createsuperuser

Follow the prompts to create your admin login.

14. Run the Server
Start the Daphne ASGI server:

daphne -p 8000 --verbosity 2 waitingproj.asgi:application

The --verbosity 2 flag enables auto-reloading during development.

Usage
Access Admin: Go to http://127.0.0.1:8000/admin/ and log in with your superuser. Add some Doctor instances.

Patient View: Open http://127.00.1:8000/join-queue/ in your browser. Select a doctor and enter a patient name to join the queue. Observe your status update in real-time.

Doctor Dashboard: Open http://127.0.0.1:8000/doctor/<doctor_id>/ (replace <doctor_id> with the ID of a doctor you created, e.g., http://127.0.0.1:8000/doctor/1/). You'll see patients appear in real-time. Change their status or remove them.

Chat: Click the "Chat" button next to a patient to open the chat interface.

Whiteboard: For patients with 'In Progress' or 'In Call' status, click the "Whiteboard" button to open the shared whiteboard.

Doctor History: From the doctor dashboard, click "View Patient History" or navigate directly to http://127.0.0.1:8000/doctor-history/<doctor_id>/ to see completed or cancelled appointments.
