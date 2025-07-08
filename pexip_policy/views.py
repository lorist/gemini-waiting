# pexip_policy/views.py
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async
import uuid
from waitingroom.models import WaitingRoomEntry, Patient

@csrf_exempt # Pexip will not send CSRF tokens, so this is necessary
async def pexip_service_policy_view(request):
    """
    Handles Pexip Infinity External Policy GET requests for service configuration.
    It returns a JSON response to configure the conference based on the patient's UUID.
    """
    if request.method != 'GET': # Only allow GET requests
        return HttpResponseBadRequest("Only GET requests are allowed for Pexip policy.")

    # For GET requests, parameters are in request.GET
    conference_alias = request.GET.get('local_alias') # 'local_alias' from the example URL
    remote_display_name = request.GET.get('remote_display_name', 'Guest')


    print(f"Received Pexip policy request (Alias: {conference_alias}, Display Name: {remote_display_name})")

    # We are primarily interested in 'conference_create' events, implied by the request
    if conference_alias: # Check for conference_alias directly
        try:
            patient_uuid_obj = uuid.UUID(conference_alias)
        except ValueError:
            print(f"Invalid UUID received as conference_alias: {conference_alias}")
            return JsonResponse({
                "status": "success", # Pexip expects 'success' even for rejections
                "action": "reject",
                "result": {
                    "disconnect": True,
                    "disconnect_cause": "INVALID_CONFERENCE_ALIAS",
                    "message": "Invalid patient ID (UUID) provided as conference alias."
                }
            })

        # Fetch the WaitingRoomEntry using the patient's UUID
        # Only consider entries that are 'In Progress' for joining the call
        # Use select_related to pre-fetch doctor and patient to avoid N+1 queries later
        entry = await sync_to_async(WaitingRoomEntry.objects.filter(
            patient__uuid=patient_uuid_obj,
            status='In Progress'
        ).select_related('patient', 'doctor').first)()

        if entry:
            doctor_name = await sync_to_async(lambda e: e.doctor.name)(entry)
            patient_name = await sync_to_async(lambda e: e.patient.name)(entry)

            return JsonResponse({
                "status": "success",
                "action": "continue", # Allow the conference to proceed
                "result": {
                    "name": f"Dr. {doctor_name}'s Room ({patient_name})",
                    "service_tag": conference_alias,
                    "service_type": "conference",
                    "allow_guests": True,
                    "direct_media": "best_effort",
                    "enable_overlay_text": True,
                    "pin": entry.host_pin,
                    "guest_pin": entry.guest_pin,
                    "disconnect_on_host_disconnect": True
                }
            })
        else:
            # No active 'In Progress' entry found for this UUID
            print(f"No active 'In Progress' waiting room entry found for UUID: {conference_alias}. Denying conference creation.")
            return JsonResponse({
                "status": "success",
                "action": "reject", # Reject conference creation
                "result": {}
            })

    # Default response if conference_alias is missing
    print(f"Missing conference_alias in Pexip policy request.")
    return JsonResponse({
        "status": "success",
        "action": "continue", # Default to rejecting if essential info is missing
        "result": {}
    })
