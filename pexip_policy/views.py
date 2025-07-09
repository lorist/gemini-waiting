# pexip_policy/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
from asgiref.sync import sync_to_async
from waitingroom.models import WaitingRoomEntry, Doctor, Patient # Import your models
from django.conf import settings # Import settings to access Pexip configuration (for logging doctor link)

logger = logging.getLogger(__name__)

# This decorator allows Django to run synchronous database operations
# within an asynchronous view (pexip_policy_view).
@sync_to_async
def _get_conference_details(conference_alias, role):
    """
    Retrieves conference details based on the conference alias (patient UUID)
    and participant role. This function is designed to be called asynchronously.
    """
    try:
        # For a patient (guest), the conference_alias is their UUID.
        # They should only be allowed if their status is 'Waiting' or 'In Progress'.
        if role == 'guest':
            entry = WaitingRoomEntry.objects.select_related('doctor', 'patient').get(
                patient__uuid=conference_alias,
                status__in=['Waiting', 'In Progress']
            )
            return {
                "conference_id": str(entry.patient.uuid), # Pexip conference ID
                "display_name": f"{entry.patient.name}'s Virtual Room", # MODIFIED: Consistent conference name
                "host_pin": entry.host_pin,
                "guest_pin": entry.guest_pin,
                "service_type": "conference",
            }
        # For a doctor (host), the conference_alias is the patient's UUID they are trying to join.
        # The doctor should be able to connect if the patient is 'In Progress' or already 'In Call'.
        elif role == 'host':
            entry = WaitingRoomEntry.objects.select_related('doctor', 'patient').get(
                patient__uuid=conference_alias,
                status__in=['In Progress', 'In Call']
            )
            return {
                "conference_id": str(entry.patient.uuid), # Pexip conference ID
                "display_name": f"{entry.patient.name}'s Virtual Room", # MODIFIED: Consistent conference name
                "host_pin": entry.host_pin,
                "guest_pin": entry.guest_pin,
                "service_type": "conference",
            }
        else:
            logger.warning(f"Unsupported role '{role}' in policy request for alias '{conference_alias}'.")
            return None

    except WaitingRoomEntry.DoesNotExist:
        logger.info(f"No active waiting room entry found for UUID: {conference_alias} with role {role} and appropriate status. Denying conference creation.")
        return None
    except Exception as e:
        logger.error(f"Error in _get_conference_details for alias {conference_alias}, role {role}: {e}", exc_info=True)
        return None


@csrf_exempt
async def pexip_policy_view(request):
    """
    Pexip Policy Service Configuration endpoint.
    This view receives requests from Pexip Infinity to determine conference parameters.
    """
    if request.method != 'GET':
        logger.warning(f"Received non-GET request to policy endpoint: {request.method}")
        return HttpResponseBadRequest("Only GET requests are allowed for Pexip Policy Service.")

    # Pexip sends parameters as query parameters
    conference_alias = request.GET.get('local_alias') # The alias Pexip is trying to resolve
    remote_display_name = request.GET.get('remote_display_name', '') # Get display name, default to empty string
    role = request.GET.get('role') # Get role, can be None if not provided

    logger.info(f"Received Pexip policy request (Alias: {conference_alias}, Display Name: {remote_display_name}, Role: {role})")

    # Infer role if not provided (common for some Pexip client versions/configurations)
    if role is None:
        if remote_display_name.lower().startswith('dr.'):
            role = 'host'
            logger.info(f"Inferred role as 'host' based on display name: '{remote_display_name}'")
        else:
            role = 'guest' # Default to guest if not clearly a doctor
            logger.info(f"Inferred role as 'guest' based on display name: '{remote_display_name}'")

    if not conference_alias:
        logger.warning("Policy request received without local_alias.")
        return JsonResponse({
            "action": "reject",
            "result": {
                "disconnect": True,
                "disconnect_cause": "MISSING_ALIAS",
                "message": "Missing conference alias in policy request."
            }
        })

    # Fetch details asynchronously
    conference_details = await _get_conference_details(conference_alias, role)

    if conference_details:
        # Construct and log the doctor's join link if the role is host
        if role == 'host':
            doctor_join_link = (
                f"https://{settings.PEXIP_ADDRESS}/{settings.PEXIP_PATH}/m/?"
                f"conference={conference_details['conference_id']}&"
                f"name={remote_display_name}&"
                f"role=host&"
                f"pin={conference_details['host_pin']}"
            )
            logger.info(f"Doctor Join Link for {remote_display_name}: {doctor_join_link}")

        response_data = {
            "status": "success",
            "action": "continue", # Allow the conference to proceed
            "result": {
                "name": conference_details["display_name"], # This will now be consistent
                "service_tag": conference_details["conference_id"],
                "service_type": conference_details["service_type"],
                "allow_guests": True,
                "direct_media": "best_effort",
                "enable_overlay_text": True,
                "pin": conference_details["host_pin"],
                "guest_pin": conference_details["guest_pin"],
                "disconnect_on_host_disconnect": True
            }
        }
    else:
        # Deny response if conference details are not found
        response_data = {
            "action": "reject",
            "result": {
                "disconnect": True,
                "disconnect_cause": "CONFERENCE_NOT_FOUND",
                "message": "Conference not found or not in an active state for this role."
            }
        }

    return JsonResponse(response_data)
