# pexip_events/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
from asgiref.sync import async_to_sync
from waitingroom.models import WaitingRoomEntry, Doctor, Patient # Import your models
from channels.layers import get_channel_layer
from django.conf import settings # Import settings to access Pexip configuration (for logging doctor link)
from channels.db import database_sync_to_async # Ensure this is imported for async DB operations

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
        logger.info(f"[_update_entry_status_and_notify] Attempting to update status for patient UUID: {patient_uuid_str} to '{new_status}'")
        entry = WaitingRoomEntry.objects.select_related('doctor', 'patient').get(patient__uuid=patient_uuid_str)
        old_status = entry.status

        if old_status != new_status:
            entry.status = new_status
            entry.save()
            logger.info(f"[_update_entry_status_and_notify] Successfully updated WaitingRoomEntry for patient {patient_uuid_str} from '{old_status}' to '{new_status}'")

            channel_layer = get_channel_layer()
            doctor_group_name = f'waiting_room_{entry.doctor.id}'
            logger.info(f"[_update_entry_status_and_notify] Sending WebSocket update to group: {doctor_group_name}")

            async_to_sync(channel_layer.group_send)(
                doctor_group_name,
                {
                    'type': 'waiting_list_update',
                    'message': f'Patient {entry.patient.name} status changed to {new_status}'
                }
            )
            logger.info(f"[_update_entry_status_and_notify] WebSocket message sent for {patient_uuid_str}.")
        else:
            logger.info(f"[_update_entry_status_and_notify] Status for patient {patient_uuid_str} is already '{new_status}'. No update needed.")

    except WaitingRoomEntry.DoesNotExist:
        logger.warning(f"[_update_entry_status_and_notify] WaitingRoomEntry not found for patient UUID: {patient_uuid_str}. Cannot update status.")
    except Exception as e:
        logger.error(f"[_update_entry_status_and_notify] Error for {patient_uuid_str}: {e}", exc_info=True)


@csrf_exempt
async def pexip_event_sink_view(request):
    """
    Handles Pexip Infinity Event Sink POST requests.
    Receives events like participant connect/disconnect, conference start/stop.
    """
    # Ensure it's a POST request. If not, return 200 OK with an informative message,
    # as Pexip might expect 200 even for method not allowed.
    if request.method != 'POST':
        logger.warning(f"[pexip_event_sink_view] Received non-POST request: {request.method}. Expected POST.")
        return JsonResponse({"status": "error", "message": "Only POST requests are allowed for Pexip Event Sinks."}, status=200)

    try:
        event_data = json.loads(request.body)
        logger.info(f"[pexip_event_sink_view] Received Pexip Event Sink data: {json.dumps(event_data, indent=2)}")

        event_type = event_data.get('event')
        conference_alias = event_data.get('data', {}).get('destination_alias')
        participant_display_name = event_data.get('data', {}).get('display_name')
        participant_role = event_data.get('data', {}).get('role')

        logger.info(f"[pexip_event_sink_view] Parsed Event: Type={event_type}, Alias={conference_alias}, Role={participant_role}, DisplayName={participant_display_name}")

        if not conference_alias:
            logger.warning("[pexip_event_sink_view] Pexip event received without conference_alias (patient UUID).")
            # Return 200 OK even for missing alias, as Pexip expects 200 for valid receipt.
            return JsonResponse({"status": "error", "message": "Missing conference_alias"}, status=200)

        # Ensure conference_alias is a string before passing to async function
        conference_alias_str = str(conference_alias)

        if event_type == 'participant_connected' and participant_role == 'guest':
            logger.info(f"[pexip_event_sink_view] Guest CONNECTED event detected for '{participant_display_name}' ({conference_alias_str}). Calling status update.")
            await _update_entry_status_and_notify(conference_alias_str, 'In Call')

        elif event_type == 'participant_disconnected' and participant_role == 'guest':
            logger.info(f"[pexip_event_sink_view] Guest DISCONNECTED event detected for '{participant_display_name}' ({conference_alias_str}). Calling status update.")
            await _update_entry_status_and_notify(conference_alias_str, 'Left Call')

        elif event_type == 'conference_ended':
            logger.info(f"[pexip_event_sink_view] Conference ENDED event detected for '{conference_alias_str}'. Calling status update.")
            await _update_entry_status_and_notify(conference_alias_str, 'Left Call')
        else:
            logger.info(f"[pexip_event_sink_view] Unhandled Pexip event type or role: Type={event_type}, Role={participant_role}. No status update performed.")


        return JsonResponse({"status": "success", "message": "Event received and processed (if applicable)."})

    except json.JSONDecodeError:
        logger.error("[pexip_event_sink_view] Invalid JSON in request body. Returning 200 OK with error message.")
        # Return 200 OK even for JSON decode error, as Pexip expects 200.
        return JsonResponse({"status": "error", "message": "Invalid JSON in request body."}, status=200)
    except Exception as e:
        logger.error(f"[pexip_event_sink_view] Unhandled error processing request: {e}", exc_info=True)
        # Return 200 OK even for unhandled exceptions.
        return JsonResponse({"status": "error", "message": f"Server error: {str(e)}"}, status=200)
