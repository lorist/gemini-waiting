# waitingroom/models.py
from django.db import models
import uuid # Import the uuid module

class Doctor(models.Model):
    name = models.CharField(max_length=100)
    # Add other doctor-specific fields

    def __str__(self):
        return self.name

class Patient(models.Model):
    # UUID field with default and now non-nullable
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, null=False)
    name = models.CharField(max_length=100)
    # Add other patient-specific fields

    def __str__(self):
        return self.name

class WaitingRoomEntry(models.Model):
    # Define choices for status for better data integrity and clarity
    STATUS_CHOICES = [
        ('Waiting', 'Waiting'),
        ('In Progress', 'In Progress'),
        ('In Call', 'In Call'), # NEW: Status when patient is actively in the Pexip call
        ('Left Call', 'Left Call'), # NEW: Status when patient leaves the Pexip call
        ('Done', 'Done'),
        ('Cancelled', 'Cancelled'),
    ]

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='waiting_patients')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Waiting') # Use choices
    arrived_at = models.DateTimeField(auto_now_add=True)
    host_pin = models.CharField(max_length=6, unique=True, null=True, blank=True)
    guest_pin = models.CharField(max_length=6, unique=True, null=True, blank=True)
    added_by_doctor = models.BooleanField(default=False)
    # Whiteboard fields
    whiteboard_active = models.BooleanField(default=False) # True if whiteboard is currently open/active for this patient
    whiteboard_data = models.TextField(default='[]') # Stores JSON string of drawing commands

    class Meta:
        ordering = ['arrived_at']

    def __str__(self):
        return f"{self.patient.name} for Dr. {self.doctor.name} - {self.status}"

