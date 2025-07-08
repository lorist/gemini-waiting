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
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='waiting_patients')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, default='Waiting') # e.g., 'Waiting', 'In Progress', 'Done', 'Cancelled'
    arrived_at = models.DateTimeField(auto_now_add=True)
    host_pin = models.CharField(max_length=6, unique=True, null=True, blank=True) # 6-digit PIN for doctor
    guest_pin = models.CharField(max_length=6, unique=True, null=True, blank=True) # 6-digit PIN for patient
    added_by_doctor = models.BooleanField(default=False) # NEW: Flag to indicate if added by doctor

    class Meta:
        ordering = ['arrived_at']

    def __str__(self):
        return f"{self.patient.name} for Dr. {self.doctor.name} - {self.status}"

