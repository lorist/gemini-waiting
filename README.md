Django Patient Waiting Room App
This is a Django-based web application that provides a real-time patient waiting room system for doctors, featuring a patient-facing queue joining page and a doctor's dashboard with live updates.

Features
Doctor Management: Doctors can be added and managed via the Django Admin panel.

Patient Queueing: Patients can select a doctor from a dynamic list and join their waiting room queue.

Real-time Status Updates: Utilizes Django Channels and WebSockets to provide live updates of patient statuses on the doctor's dashboard and the patient's view.

Patient Status Management: Doctors can change a patient's status (Waiting, In Progress, Done, Cancelled) from their dashboard.

Patient Removal: Doctors can remove patients from the active queue, which also moves them to a history view.

Patient History: A dedicated page for doctors to view a history of patients whose appointments are 'Done' or 'Cancelled'.

Patient Notifications & Redirection: When a patient's status is marked 'Done' or 'Cancelled', they are informed via a dialogue and redirected back to the join queue page.

Responsive Design: Frontend utilizes Tailwind CSS for a mobile-first, responsive layout.

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

class Doctor(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class Patient(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class WaitingRoomEntry(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='waiting_patients')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, default='Waiting') # e.g., 'Waiting', 'In Progress', 'Done', 'Cancelled'
    arrived_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['arrived_at']
    def __str__(self):
        return f"{self.patient.name} for Dr. {self.doctor.name} - {self.status}"

8. Define App Views
Ensure your waitingroom/views.py contains the necessary views:

# waitingroom/views.py
from django.shortcuts import render, get_object_or_404
from .models import Doctor, WaitingRoomEntry

def patient_waiting_room_view(request):
    doctors = Doctor.objects.all().order_by('name')
    context = {'doctors': doctors}
    return render(request, 'waitingroom/patient_waiting_room.html', context)

def doctor_dashboard_view(request, doctor_id):
    doctor = get_object_or_404(Doctor, pk=doctor_id)
    context = {'doctor': doctor}
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
Create or update waitingroom/admin.py to register your models for admin access:

# waitingroom/admin.py
from django.contrib import admin
from .models import Doctor, Patient, WaitingRoomEntry

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(WaitingRoomEntry)
class WaitingRoomEntryAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'patient', 'status', 'arrived_at')
    list_filter = ('status', 'doctor')
    search_fields = ('patient__name', 'doctor__name')
    raw_id_fields = ('doctor', 'patient')

11. Create Templates
Ensure you have the following HTML templates:

templates/base.html (for the base layout)

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

Doctor History: From the doctor dashboard, click "View Patient History" or navigate directly to http://127.0.0.1:8000/doctor-history/<doctor_id>/ to see completed or cancelled appointments.

Contributing
Feel free to fork this repository, make improvements, and submit pull requests.

License
[Specify your license here, e.g., MIT, Apache 2.0, etc.]