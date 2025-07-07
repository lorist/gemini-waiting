# myapp/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import WaitingRoomEntry, Doctor, Patient
import uuid

class WaitingRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.doctor_id = self.scope['url_route']['kwargs']['doctor_id']
        self.doctor_group_name = f'waiting_room_{self.doctor_id}'

        await self.channel_layer.group_add(
            self.doctor_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WebSocket connected for doctor {self.doctor_id}")

        # Send initial waiting list when a client connects (useful for doctor dashboard)
        await self.send_waiting_list()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.doctor_group_name,
            self.channel_name
        )
        print(f"WebSocket disconnected for doctor {self.doctor_id} with code {close_code}")

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'update_status':
            entry_id = text_data_json.get('entry_id')
            new_status = text_data_json.get('status')
            await self.update_waiting_entry_status(entry_id, new_status)
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'Waiting list updated'
                }
            )
        elif message_type == 'add_patient':
            patient_name = text_data_json.get('patient_name')
            patient_uuid = text_data_json.get('patient_uuid')
            await self.add_patient_to_waiting_room(patient_name, patient_uuid)
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'New patient added'
                }
            )
        elif message_type == 'remove_patient':
            entry_id = text_data_json.get('entry_id')
            await self.remove_waiting_entry(entry_id)
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'Patient removed'
                }
            )
        elif message_type == 'purge_history': # NEW: Handle purge history command
            # Ensure the command is for the correct doctor
            requested_doctor_id = text_data_json.get('doctor_id')
            if str(requested_doctor_id) == str(self.doctor_id): # Compare as strings for safety
                await self.purge_doctor_history()
                await self.channel_layer.group_send(
                    self.doctor_group_name,
                    {
                        'type': 'waiting_list_update', # Use existing update type to trigger refresh
                        'message': 'History purged'
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Unauthorized purge request.'
                }))


    async def waiting_list_update(self, event):
        await self.send_waiting_list()

    @sync_to_async
    def get_waiting_list_data(self):
        try:
            doctor = Doctor.objects.get(id=self.doctor_id)
            waiting_entries = WaitingRoomEntry.objects.filter(
                doctor=doctor
            ).exclude(
                status__in=['Done', 'Cancelled']
            ).select_related('patient').order_by('arrived_at')
            data = []
            for entry in waiting_entries:
                data.append({
                    'id': entry.id,
                    'patient_name': entry.patient.name,
                    'patient_uuid': str(entry.patient.uuid),
                    'status': entry.status,
                    'arrived_at': entry.arrived_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'doctor_id': entry.doctor.id
                })
            return data
        except Doctor.DoesNotExist:
            print(f"Doctor with ID {self.doctor_id} not found.")
            return []
        except Exception as e:
            print(f"Error fetching waiting list: {e}")
            return []

    async def send_waiting_list(self):
        waiting_list = await self.get_waiting_list_data()
        await self.send(text_data=json.dumps({
            'type': 'waiting_list',
            'data': waiting_list
        }))

    @sync_to_async
    def update_waiting_entry_status(self, entry_id, new_status):
        try:
            entry = WaitingRoomEntry.objects.get(id=entry_id, doctor_id=self.doctor_id)
            entry.status = new_status
            entry.save()
            print(f"Updated entry {entry_id} to status {new_status}")
        except WaitingRoomEntry.DoesNotExist:
            print(f"WaitingRoomEntry with ID {entry_id} not found for doctor {self.doctor_id}.")
        except Exception as e:
            print(f"Error updating status for entry {entry_id}: {e}")

    @sync_to_async
    def add_patient_to_waiting_room(self, patient_name, patient_uuid):
        try:
            doctor = Doctor.objects.get(id=self.doctor_id)
            if patient_uuid:
                patient, created = Patient.objects.get_or_create(
                    uuid=uuid.UUID(patient_uuid),
                    defaults={'name': patient_name}
                )
                if not created and patient.name != patient_name:
                    patient.name = patient_name
                    patient.save()
            else:
                patient, created = Patient.objects.get_or_create(name=patient_name)

            if not WaitingRoomEntry.objects.filter(doctor=doctor, patient=patient, status__in=['Waiting', 'In Progress']).exists():
                WaitingRoomEntry.objects.create(doctor=doctor, patient=patient, status='Waiting')
                print(f"Added patient {patient_name} (UUID: {patient.uuid}) to waiting room for doctor {self.doctor_id}")
            else:
                print(f"Patient {patient_name} (UUID: {patient.uuid}) is already in the active queue for doctor {self.doctor_id}.")

        except Doctor.DoesNotExist:
            print(f"Doctor with ID {self.doctor_id} not found.")
        except Exception as e:
            print(f"Error adding patient {patient_name}: {e}")

    @sync_to_async
    def remove_waiting_entry(self, entry_id):
        try:
            entry = WaitingRoomEntry.objects.get(id=entry_id, doctor_id=self.doctor_id)
            entry.delete()
            print(f"Removed waiting room entry with ID {entry_id}.")
        except WaitingRoomEntry.DoesNotExist:
            print(f"WaitingRoomEntry with ID {entry_id} not found for doctor {self.doctor_id}.")
        except Exception as e:
            print(f"Error removing entry {entry_id}: {e}")

    @sync_to_async
    def purge_doctor_history(self):
        """Deletes all 'Done' and 'Cancelled' entries for the current doctor."""
        try:
            deleted_count, _ = WaitingRoomEntry.objects.filter(
                doctor_id=self.doctor_id,
                status__in=['Done', 'Cancelled']
            ).delete()
            print(f"Purged {deleted_count} historical entries for doctor {self.doctor_id}.")
        except Exception as e:
            print(f"Error purging history for doctor {self.doctor_id}: {e}")

