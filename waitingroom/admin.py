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
    list_display = ('doctor', 'patient', 'status', 'arrived_at', 'host_pin', 'guest_pin') # Added PINs
    list_filter = ('status', 'doctor')
    search_fields = ('patient__name', 'doctor__name', 'patient__uuid', 'host_pin', 'guest_pin') # Search by PINs
    raw_id_fields = ('doctor', 'patient')

