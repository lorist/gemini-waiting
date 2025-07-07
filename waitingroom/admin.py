# waitingroom/admin.py
from django.contrib import admin
from .models import Doctor, Patient, WaitingRoomEntry

# Register your models here.

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name',) # Customize what fields are shown in the list view
    search_fields = ('name',) # Add a search bar for the name field

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(WaitingRoomEntry)
class WaitingRoomEntryAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'patient', 'status', 'arrived_at')
    list_filter = ('status', 'doctor') # Allow filtering by status and doctor
    search_fields = ('patient__name', 'doctor__name') # Search by patient or doctor name
    raw_id_fields = ('doctor', 'patient') # Use raw ID input for FKs for better performance with many objects