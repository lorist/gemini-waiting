# myapp/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import WaitingRoomEntry, Doctor, Patient

class WaitingRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.doctor_id = self.scope['url_route']['kwargs']['doctor_id']
        self.doctor_group_name = f'waiting_room_{self.doctor_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.doctor_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WebSocket connected for doctor {self.doctor_id}")

        # REMOVED: No longer send initial waiting list here for patients.
        # The 'add_patient' message or doctor dashboard connection will trigger updates.
        # await self.send_waiting_list()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.doctor_group_name,
            self.channel_name
        )
        print(f"WebSocket disconnected for doctor {self.doctor_id} with code {close_code}")

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'update_status':
            entry_id = text_data_json.get('entry_id')
            new_status = text_data_json.get('status')
            await self.update_waiting_entry_status(entry_id, new_status)
            # After updating, broadcast the new list to all clients in the group
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'Waiting list updated' # A generic message, actual data will be fetched by the handler
                }
            )
        elif message_type == 'add_patient':
            patient_name = text_data_json.get('patient_name')
            await self.add_patient_to_waiting_room(patient_name)
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'New patient added'
                }
            )
        elif message_type == 'remove_patient': # This action explicitly deletes the entry
            entry_id = text_data_json.get('entry_id')
            await self.remove_waiting_entry(entry_id)
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': 'Patient removed'
                }
            )

    # Receive message from room group (broadcast to all connected clients in the group)
    async def waiting_list_update(self, event):
        # Send updated waiting list to WebSocket
        await self.send_waiting_list()

    @sync_to_async
    def get_waiting_list_data(self):
        """
        Fetches the current ACTIVE waiting list for the doctor.
        Excludes patients with 'Done' or 'Cancelled' status.
        """
        try:
            doctor = Doctor.objects.get(id=self.doctor_id)
            waiting_entries = WaitingRoomEntry.objects.filter(
                doctor=doctor
            ).exclude(
                status__in=['Done', 'Cancelled'] # Filter out done/cancelled patients
            ).select_related('patient').order_by('arrived_at')
            data = []
            for entry in waiting_entries:
                data.append({
                    'id': entry.id,
                    'patient_name': entry.patient.name,
                    'status': entry.status,
                    'arrived_at': entry.arrived_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'doctor_id': entry.doctor.id # NEW: Include doctor_id for patient-side filtering
                })
            return data
        except Doctor.DoesNotExist:
            print(f"Doctor with ID {self.doctor_id} not found.")
            return []
        except Exception as e:
            print(f"Error fetching waiting list: {e}")
            return []

    async def send_waiting_list(self):
        """Sends the current waiting list to the connected client."""
        waiting_list = await self.get_waiting_list_data()
        await self.send(text_data=json.dumps({
            'type': 'waiting_list',
            'data': waiting_list
        }))

    @sync_to_async
    def update_waiting_entry_status(self, entry_id, new_status):
        """Updates the status of a waiting room entry."""
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
    def add_patient_to_waiting_room(self, patient_name):
        """Adds a new patient to the waiting room."""
        try:
            doctor = Doctor.objects.get(id=self.doctor_id)
            # Find or create patient
            patient, created = Patient.objects.get_or_create(name=patient_name)
            WaitingRoomEntry.objects.create(doctor=doctor, patient=patient, status='Waiting')
            print(f"Added patient {patient_name} to waiting room for doctor {self.doctor_id}")
        except Doctor.DoesNotExist:
            print(f"Doctor with ID {self.doctor_id} not found.")
        except Exception as e:
            print(f"Error adding patient {patient_name}: {e}")

    @sync_to_async
    def remove_waiting_entry(self, entry_id):
        """Removes a waiting room entry from the database."""
        try:
            entry = WaitingRoomEntry.objects.get(id=entry_id, doctor_id=self.doctor_id)
            entry.delete()
            print(f"Removed waiting room entry with ID {entry_id}.")
        except WaitingRoomEntry.DoesNotExist:
            print(f"WaitingRoomEntry with ID {entry_id} not found for doctor {self.doctor_id}.")
        except Exception as e:
            print(f"Error removing entry {entry_id}: {e}")

