# pexip_events/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
from asgiref.sync import async_to_sync
from waitingroom.models import WaitingRoomEntry, Doctor, Patient
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

# Helper function to update status and notify via WebSocket
@database_sync_to_async
def _update_entry_status_and_notify(patient_uuid_str, new_status):
    """
    Updates the status of a WaitingRoomEntry and sends a WebSocket notification
    to the associated doctor's dashboard.
    This function runs in a separate thread because it performs synchronous DB operations.
    """
    try:
        # Find the WaitingRoomEntry by patient UUID (which is the conference_alias)
        # Use select_related to pre-fetch doctor and patient to avoid N+1 queries later
        entry = WaitingRoomEntry.objects.select_related('doctor', 'patient').get(patient__uuid=patient_uuid_str)
        old_status = entry.status

        # Only update if the status is actually changing
        if old_status != new_status:
            entry.status = new_status
            entry.save()
            logger.info(f"Updated WaitingRoomEntry for patient {patient_uuid_str} from '{old_status}' to '{new_status}'")

            # Get the channel layer instance
            channel_layer = get_channel_layer()
            # Determine the group name for the doctor's dashboard
            doctor_group_name = f'waiting_room_{entry.doctor.id}'

            # Send a generic update message to the doctor's dashboard.
            # This will trigger the dashboard to re-fetch and re-render its waiting list.
            # Use async_to_sync because channel_layer.group_send is async, but this helper is sync.
            async_to_sync(channel_layer.group_send)(
                doctor_group_name,
                {
                    'type': 'waiting_list_update', # This type is handled by the consumer
                    'message': f'Patient {entry.patient.name} status changed to {new_status}'
                }
            )
        else:
            logger.info(f"Status for patient {patient_uuid_str} is already '{new_status}'. No update needed.")

    except WaitingRoomEntry.DoesNotExist:
        logger.warning(f"WaitingRoomEntry not found for patient UUID: {patient_uuid_str}. Cannot update status.")
    except Exception as e:
        logger.error(f"Error in _update_entry_status_and_notify for {patient_uuid_str}: {e}", exc_info=True)


@csrf_exempt # Pexip will not send CSRF tokens, so this is necessary
async def pexip_event_sink_view(request):
    """
    Handles Pexip Infinity Event Sink POST requests.
    Receives events like participant connect/disconnect, conference start/stop.
    """
    if request.method != 'POST':
        logger.warning(f"Received non-POST request to event sink: {request.method}")
        return HttpResponseBadRequest("Only POST requests are allowed for Pexip Event Sinks.")

    try:
        event_data = json.loads(request.body)
        logger.info(f"Received Pexip Event Sink data: {json.dumps(event_data, indent=2)}")

        # FIXED: Directly get 'event' as it's a string, not a nested dict
        event_type = event_data.get('event')
        # In our setup, the conference alias in Pexip events is the patient's UUID
        conference_alias = event_data.get('data', {}).get('destination_alias') # Use destination_alias as conference_alias might be the friendly name
        participant_display_name = event_data.get('data', {}).get('display_name')
        participant_role = event_data.get('data', {}).get('role') # 'host' or 'guest'

        # Ensure we have the necessary identifiers
        if not conference_alias:
            logger.warning("Pexip event received without conference_alias (patient UUID).")
            return JsonResponse({"status": "error", "message": "Missing conference_alias"}, status=400)

        # Handle participant connect event for guests (patients)
        if event_type == 'participant_connected' and participant_role == 'guest': # Corrected event name
            logger.info(f"Guest CONNECTED: '{participant_display_name}' to conference '{conference_alias}'")
            # Update patient status to 'In Call'
            await _update_entry_status_and_notify(conference_alias, 'In Call')

        # Handle participant disconnect event for guests (patients)
        elif event_type == 'participant_disconnected' and participant_role == 'guest': # Corrected event name
            logger.info(f"Guest DISCONNECTED: '{participant_display_name}' from conference '{conference_alias}'")
            # Update patient status to 'Left Call'
            await _update_entry_status_and_notify(conference_alias, 'Left Call')

        # Handle conference end event (e.g., doctor ended the call)
        elif event_type == 'conference_ended': # Corrected event name
            logger.info(f"Conference ENDED: '{conference_alias}'. Marking related patients as Left Call.")
            # When a conference ends, all associated patients should be marked as 'Left Call'
            await _update_entry_status_and_notify(conference_alias, 'Left Call')

        # Pexip expects a 200 OK response to acknowledge receipt of the event
        return JsonResponse({"status": "success", "message": "Event received"})

    except json.JSONDecodeError:
        logger.error("Invalid JSON in Pexip Event Sink request body.")
        return HttpResponseBadRequest("Invalid JSON in request body.")
    except Exception as e:
        logger.error(f"Error processing Pexip Event Sink request: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": f"Server error: {str(e)}"}, status=500)

