# myapp/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async, async_to_sync
from waitingroom.models import WaitingRoomEntry, Doctor, Patient
import uuid
import random
import logging
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class WaitingRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.doctor_id = self.scope['url_route']['kwargs']['doctor_id']
        self.doctor_group_name = f'waiting_room_{self.doctor_id}'
        self.patient_uuid = None # Initialize patient_uuid for this consumer instance

        await self.channel_layer.group_add(
            self.doctor_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"[Consumer] WebSocket connected for doctor {self.doctor_id}")

        await self.send_waiting_list()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.doctor_group_name,
            self.channel_name
        )
        logger.info(f"[Consumer] WebSocket disconnected for doctor {self.doctor_id} with code {close_code}")

        # If this consumer was associated with a patient, update their status to 'Left Call'
        # This handles unexpected disconnects (e.g., browser crash, tab close without clicking button)
        if self.patient_uuid:
            logger.info(f"[Consumer] Patient {self.patient_uuid} disconnected. Updating status to 'Left Call'.")
            # Call the async database function to update the status
            await self.update_patient_status_on_disconnect(self.patient_uuid)


    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        logger.info(f"[Consumer] Received message from client: Type={message_type}")

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
            # Store the patient_uuid with this consumer instance
            self.patient_uuid = patient_uuid
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
        elif message_type == 'purge_history':
            requested_doctor_id = text_data_json.get('doctor_id')
            if str(requested_doctor_id) == str(self.doctor_id):
                await self.purge_doctor_history()
                await self.channel_layer.group_send(
                    self.doctor_group_name,
                    {
                        'type': 'waiting_list_update',
                        'message': 'History purged'
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Unauthorized purge request.'
                }))
        elif message_type == 'chat_message':
            sender = text_data_json.get('sender')
            message = text_data_json.get('message')
            patient_uuid = text_data_json.get('patient_uuid')
            logger.info(f"[Consumer] Chat message from {sender} (Patient UUID: {patient_uuid}): {message}")

            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'send_chat_message',
                    'sender': sender,
                    'message': message,
                    'patient_uuid': patient_uuid
                }
            )
        elif message_type == 'leave_queue':
            patient_uuid_to_remove = text_data_json.get('patient_uuid')
            doctor_id_for_removal = text_data_json.get('doctor_id')
            logger.info(f"[Consumer] Patient {patient_uuid_to_remove} explicitly leaving queue for doctor {doctor_id_for_removal}.")
            await self._mark_patient_as_cancelled(patient_uuid_to_remove, doctor_id_for_removal)
        elif message_type == 'drawing_data':
            drawing_data = text_data_json.get('data')
            patient_uuid_for_drawing = text_data_json.get('patient_uuid')
            logger.debug(f"[Consumer] Received drawing data for patient {patient_uuid_for_drawing}: {drawing_data}")
            await self.channel_layer.group_send(
                self.doctor_group_name,
                {
                    'type': 'send_drawing_data',
                    'data': drawing_data,
                    'patient_uuid': patient_uuid_for_drawing
                }
            )
        elif message_type == 'whiteboard_toggle': # NEW: Handle whiteboard toggle from client
            patient_uuid_toggle = text_data_json.get('patient_uuid')
            is_active = text_data_json.get('is_active')
            logger.info(f"[Consumer] Whiteboard toggle for patient {patient_uuid_toggle}: active={is_active}")
            await self._update_whiteboard_active_status(patient_uuid_toggle, is_active)
            # No need to send waiting_list_update here, as _update_whiteboard_active_status already does it.
        elif message_type == 'request_whiteboard_history': # NEW: Handle request for whiteboard history
            patient_uuid_history = text_data_json.get('patient_uuid')
            logger.info(f"[Consumer] Request for whiteboard history for patient {patient_uuid_history}.")
            whiteboard_data = await self._get_whiteboard_data(patient_uuid_history)
            await self.send(text_data=json.dumps({
                'type': 'whiteboard_history',
                'patient_uuid': patient_uuid_history,
                'data': whiteboard_data
            }))


    async def waiting_list_update(self, event):
        logger.info(f"[Consumer] Received 'waiting_list_update' event in group for doctor {self.doctor_id}.")
        await self.send_waiting_list()

    async def send_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'sender': event['sender'],
            'message': event['message'],
            'patient_uuid': event['patient_uuid']
        }))
        logger.info(f"[Consumer] Sent chat message to client: {event['sender']} - {event['message']}")

    async def send_drawing_data(self, event):
        await self.send(text_data=json.dumps({
            'type': 'drawing_data',
            'data': event['data'],
            'patient_uuid': event['patient_uuid']
        }))
        logger.debug(f"[Consumer] Sent drawing data to client for patient {event['patient_uuid']}.")


    @sync_to_async
    def _generate_unique_pin(self):
        """Generates a unique 6-digit PIN."""
        while True:
            pin = str(random.randint(100000, 999999))
            if not WaitingRoomEntry.objects.filter(host_pin=pin).exists() and \
               not WaitingRoomEntry.objects.filter(guest_pin=pin).exists():
                return pin

    @sync_to_async
    def get_waiting_list_data(self):
        try:
            doctor = Doctor.objects.get(id=self.doctor_id)
            waiting_entries = WaitingRoomEntry.objects.filter(
                doctor=doctor
            ).exclude(
                status__in=['Done', 'Cancelled', 'Left Call']
            ).select_related('patient').order_by('arrived_at')
            data = []
            for entry in waiting_entries:
                data.append({
                    'id': entry.id,
                    'patient_name': entry.patient.name,
                    'patient_uuid': str(entry.patient.uuid),
                    'status': entry.status,
                    'arrived_at': entry.arrived_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'doctor_id': entry.doctor.id,
                    'host_pin': entry.host_pin,
                    'guest_pin': entry.guest_pin,
                    'added_by_doctor': entry.added_by_doctor,
                    'whiteboard_active': entry.whiteboard_active, # NEW: Include whiteboard_active status
                })
            logger.info(f"[Consumer] Fetched waiting list data for doctor {self.doctor_id}: {len(data)} entries.")
            return data
        except Doctor.DoesNotExist:
            logger.error(f"[Consumer] Doctor with ID {self.doctor_id} not found.")
            return []
        except Exception as e:
            logger.error(f"[Consumer] Error fetching waiting list for doctor {self.doctor_id}: {e}", exc_info=True)
            return []

    async def send_waiting_list(self):
        waiting_list = await self.get_waiting_list_data()
        logger.info(f"[Consumer] Sending waiting_list to doctor {self.doctor_id} via WebSocket.")
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
            logger.info(f"[Consumer] Updated entry {entry_id} to status {new_status} via direct client command.")
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry with ID {entry_id} not found for doctor {self.doctor_id}.")
        except Exception as e:
            logger.error(f"[Consumer] Error updating status for entry {entry_id}: {e}", exc_info=True)

    @sync_to_async
    def update_patient_status_on_disconnect(self, patient_uuid_str):
        """
        Updates a patient's WaitingRoomEntry status to 'Left Call' when their WebSocket disconnects.
        This is for unexpected disconnections.
        """
        try:
            entry = WaitingRoomEntry.objects.select_related('patient').get(
                patient__uuid=patient_uuid_str,
                doctor_id=self.doctor_id,
                status__in=['Waiting', 'In Progress', 'In Call']
            )
            entry.status = 'Left Call'
            entry.save()
            logger.info(f"[Consumer] Patient {patient_uuid_str} status updated to 'Left Call' on disconnect.")

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': f'Patient {entry.patient.name} left the queue unexpectedly.'
                }
            )
        except WaitingRoomEntry.DoesNotExist:
            logger.info(f"[Consumer] No active WaitingRoomEntry found for patient {patient_uuid_str} on disconnect, or already handled.")
        except Exception as e:
            logger.error(f"[Consumer] Error updating patient {patient_uuid_str} status on disconnect: {e}", exc_info=True)

    @sync_to_async
    def _mark_patient_as_cancelled(self, patient_uuid_str, doctor_id_str):
        """
        Marks a patient's WaitingRoomEntry status as 'Cancelled' when they explicitly leave the queue.
        """
        try:
            entry = WaitingRoomEntry.objects.select_related('patient').get(
                patient__uuid=patient_uuid_str,
                doctor_id=doctor_id_str, # Use the doctor_id from the message
                status__in=['Waiting', 'In Progress', 'In Call']
            )
            entry.status = 'Cancelled'
            entry.save()
            logger.info(f"[Consumer] Patient {patient_uuid_str} explicitly marked as 'Cancelled' for doctor {doctor_id_str}.")

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': f'Patient {entry.patient.name} explicitly left the queue.'
                }
            )
        except WaitingRoomEntry.DoesNotExist:
            logger.info(f"[Consumer] No active WaitingRoomEntry found for patient {patient_uuid_str} to cancel, or already handled.")
        except Exception as e:
            logger.error(f"[Consumer] Error marking patient {patient_uuid_str} as cancelled: {e}", exc_info=True)

    @sync_to_async
    def _update_whiteboard_active_status(self, patient_uuid_str, is_active):
        """
        Updates the whiteboard_active status for a given patient.
        """
        try:
            entry = WaitingRoomEntry.objects.get(patient__uuid=patient_uuid_str, doctor_id=self.doctor_id)
            entry.whiteboard_active = is_active
            entry.save()
            logger.info(f"[Consumer] Whiteboard active status for patient {patient_uuid_str} set to {is_active}.")
            # Notify the doctor's dashboard about the change
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                self.doctor_group_name,
                {
                    'type': 'waiting_list_update', # Trigger a waiting list update to refresh badge
                    'message': f'Whiteboard status changed for patient {entry.patient.name}.'
                }
            )
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry for patient {patient_uuid_str} not found for whiteboard status update.")
        except Exception as e:
            logger.error(f"[Consumer] Error updating whiteboard active status for patient {patient_uuid_str}: {e}", exc_info=True)

    @sync_to_async
    def _get_whiteboard_data(self, patient_uuid_str):
        """
        Retrieves the whiteboard_data for a given patient.
        """
        try:
            entry = WaitingRoomEntry.objects.get(patient__uuid=patient_uuid_str, doctor_id=self.doctor_id)
            return json.loads(entry.whiteboard_data)
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry for patient {patient_uuid_str} not found for whiteboard data retrieval.")
            return []
        except json.JSONDecodeError:
            logger.error(f"[Consumer] Error decoding whiteboard_data for patient {patient_uuid_str}. Data: {entry.whiteboard_data}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"[Consumer] Error getting whiteboard data for patient {patient_uuid_str}: {e}", exc_info=True)
            return []

    @sync_to_async
    def _save_whiteboard_data(self, patient_uuid_str, drawing_data):
        """
        Saves the current whiteboard drawing data for a given patient.
        This will append new drawing commands to the existing data.
        """
        try:
            entry = WaitingRoomEntry.objects.get(patient__uuid=patient_uuid_str, doctor_id=self.doctor_id)
            current_data = json.loads(entry.whiteboard_data)
            current_data.append(drawing_data)
            entry.whiteboard_data = json.dumps(current_data)
            entry.save()
            logger.debug(f"[Consumer] Saved drawing data for patient {patient_uuid_str}.")
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry for patient {patient_uuid_str} not found for saving whiteboard data.")
        except json.JSONDecodeError:
            logger.error(f"[Consumer] Error decoding existing whiteboard_data for patient {patient_uuid_str} during save. Data: {entry.whiteboard_data}", exc_info=True)
        except Exception as e:
            logger.error(f"[Consumer] Error saving whiteboard data for patient {patient_uuid_str}: {e}", exc_info=True)

    @sync_to_async
    def _clear_whiteboard_data(self, patient_uuid_str):
        """
        Clears all whiteboard drawing data for a given patient.
        """
        try:
            entry = WaitingRoomEntry.objects.get(patient__uuid=patient_uuid_str, doctor_id=self.doctor_id)
            entry.whiteboard_data = '[]'
            entry.save()
            logger.info(f"[Consumer] Cleared whiteboard data for patient {patient_uuid_str}.")
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry for patient {patient_uuid_str} not found for clearing whiteboard data.")
        except Exception as e:
            logger.error(f"[Consumer] Error clearing whiteboard data for patient {patient_uuid_str}: {e}", exc_info=True)


    async def add_patient_to_waiting_room(self, patient_name, patient_uuid):
        try:
            doctor = await sync_to_async(Doctor.objects.get)(id=self.doctor_id)
            is_added_by_doctor = False

            if patient_uuid:
                patient, created = await sync_to_async(Patient.objects.get_or_create)(
                    uuid=uuid.UUID(patient_uuid),
                    defaults={'name': patient_name}
                )
                if not created and patient.name != patient_name:
                    patient.name = patient_name
                    await sync_to_async(patient.save)()
            else:
                patient, created = await sync_to_async(Patient.objects.get_or_create)(name=patient_name)
                if created:
                    patient.uuid = uuid.uuid4()
                    await sync_to_async(patient.save)()
                is_added_by_doctor = True

            if not await sync_to_async(WaitingRoomEntry.objects.filter(
                doctor=doctor, patient=patient, status__in=['Waiting', 'In Progress', 'In Call']
            ).exists)():
                host_pin = await self._generate_unique_pin()
                guest_pin = await self._generate_unique_pin()
                await sync_to_async(WaitingRoomEntry.objects.create)(
                    doctor=doctor,
                    patient=patient,
                    status='Waiting',
                    host_pin=host_pin,
                    guest_pin=guest_pin,
                    added_by_doctor=is_added_by_doctor,
                )
                logger.info(f"[Consumer] Added patient {patient_name} (UUID: {patient.uuid}) to waiting room for doctor {self.doctor_id}. Added by doctor: {is_added_by_doctor}")
            else:
                logger.info(f"[Consumer] Patient {patient_name} (UUID: {patient.uuid}) is already in the active queue for doctor {self.doctor_id}.")

        except Doctor.DoesNotExist:
            logger.error(f"[Consumer] Doctor with ID {self.doctor_id} not found.")
        except Exception as e:
            logger.error(f"[Consumer] Error adding patient {patient_name}: {e}", exc_info=True)

    @sync_to_async
    def remove_waiting_entry(self, entry_id):
        try:
            entry = WaitingRoomEntry.objects.get(id=entry_id, doctor_id=self.doctor_id)
            entry.delete()
            logger.info(f"[Consumer] Removed waiting room entry with ID {entry_id}.")
        except WaitingRoomEntry.DoesNotExist:
            logger.warning(f"[Consumer] WaitingRoomEntry with ID {entry_id} not found for doctor {self.doctor_id}.")
        except Exception as e:
            logger.error(f"[Consumer] Error removing entry {entry_id}: {e}", exc_info=True)

    @sync_to_async
    def purge_doctor_history(self):
        try:
            deleted_count, _ = WaitingRoomEntry.objects.filter(
                doctor_id=self.doctor_id,
                status__in=['Done', 'Cancelled', 'Left Call']
            ).delete()
            logger.info(f"[Consumer] Purged {deleted_count} historical entries for doctor {self.doctor_id}.")
        except Exception as e:
            logger.error(f"[Consumer] Error purging history for doctor {self.doctor_id}: {e}", exc_info=True)

