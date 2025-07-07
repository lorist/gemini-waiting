# myapp/models.py
from django.db import models

class Doctor(models.Model):
    name = models.CharField(max_length=100)
    # Add other doctor-specific fields

    def __str__(self):
        return self.name

class Patient(models.Model):
    name = models.CharField(max_length=100)
    # Add other patient-specific fields

    def __str__(self):
        return self.name

class WaitingRoomEntry(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='waiting_patients')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, default='Waiting') # e.g., 'Waiting', 'In Progress', 'Done'
    arrived_at = models.DateTimeField(auto_now_add=True)
    # Add other relevant fields like estimated_wait_time, etc.

    class Meta:
        ordering = ['arrived_at']

    def __str__(self):
        return f"{self.patient.name} for Dr. {self.doctor.name} - {self.status}"