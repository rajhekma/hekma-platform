import os
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import requests

from ...repositories.device_tokens_repo import get_active_device_tokens, register_device_token
from ...repositories.patient_timezone_repo import set_patient_timezone
from ...repositories.medication_notification_repo import log_notification
from ...repositories.medication_repo import get_medication
from .exceptions import MedicationNotFoundError


@runtime_checkable
class PushNotificationProvider(Protocol):
    """Contract for push notification delivery (DIP)."""

    def send(self, device_token: str, title: str, body: str, data: Dict[str, Any]) -> bool:
        ...


class FcmPushNotificationProvider:
    """Firebase Cloud Messaging implementation."""

    def __init__(self, server_key: Optional[str] = None):
        self._server_key = (server_key or os.getenv("FCM_SERVER_KEY", "")).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self._server_key)

    def send(self, device_token: str, title: str, body: str, data: Dict[str, Any]) -> bool:
        if not self.is_configured:
            return False

        response = requests.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={
                "Authorization": f"key={self._server_key}",
                "Content-Type": "application/json",
            },
            json={
                "to": device_token,
                "notification": {"title": title, "body": body},
                "data": data,
            },
            timeout=15,
        )
        response.raise_for_status()
        return True


class MedicationNotificationService:
    """Sends medication reminders and registers device tokens."""

    def __init__(self, push_provider: Optional[PushNotificationProvider] = None):
        self._push = push_provider or FcmPushNotificationProvider()

    def register_device(
        self,
        patient_id: str,
        device_token: str,
        platform: str,
        timezone_name: Optional[str] = None,
    ) -> Dict:
        if timezone_name and str(timezone_name).strip():
            set_patient_timezone(patient_id, str(timezone_name).strip())
        return register_device_token(patient_id, device_token, platform)

    def send_reminder(
        self,
        patient_id: str,
        medication_id: int,
        scheduled_time: int,
        reminder_id: Optional[int] = None,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        medication = get_medication(medication_id)
        if not medication:
            raise MedicationNotFoundError("Medication not found")
        if medication["patient_id"] != patient_id:
            raise MedicationNotFoundError("Medication does not belong to this patient")

        notification_title = title or f"Medication reminder: {medication['name']}"
        notification_body = body or f"Time to take {medication['name']} ({medication['dosage']})"

        data_payload = {
            "type": "medication_reminder",
            "patientId": patient_id,
            "medicationId": str(medication_id),
            "scheduledTime": str(scheduled_time),
            "reminderId": str(reminder_id) if reminder_id else "",
        }

        tokens = get_active_device_tokens(patient_id)
        sent_count = 0
        errors: List[str] = []

        for token_row in tokens:
            try:
                if self._push.send(
                    token_row["device_token"],
                    notification_title,
                    notification_body,
                    data_payload,
                ):
                    sent_count += 1
            except Exception as exc:
                errors.append(str(exc))

        log_entry = log_notification(
            patient_id=patient_id,
            medication_id=medication_id,
            reminder_id=reminder_id,
            scheduled_time=scheduled_time,
            status="sent" if sent_count else "failed",
            payload={
                "title": notification_title,
                "body": notification_body,
                "data": data_payload,
                "sentCount": sent_count,
                "errors": errors,
            },
        )

        return {
            "sentCount": sent_count,
            "deviceCount": len(tokens),
            "errors": errors,
            "notification": log_entry,
            "fcmConfigured": getattr(self._push, "is_configured", False),
        }
