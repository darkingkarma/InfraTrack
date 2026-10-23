
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from django.contrib.auth import get_user_model

from .models import Notification, PushDevice


logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_BATCH_SIZE = 100


def send_expo_push_notifications(messages):
    """
    Send push messages through the Expo Push API.
    Expo accepts batches of up to 100 messages.
    """
    for start in range(0, len(messages), EXPO_BATCH_SIZE):
        batch = messages[start:start + EXPO_BATCH_SIZE]

        try:
            payload = json.dumps(batch).encode("utf-8")

            request = Request(
                EXPO_PUSH_URL,
                data=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))

            for ticket in result.get("data", []):
                if ticket.get("status") == "error":
                    logger.warning(
                        "Expo push ticket error: %s",
                        ticket.get("message", "Unknown error"),
                    )

        except HTTPError as error:
            logger.error(
                "Expo Push API HTTP error: %s",
                error.code,
            )

        except (URLError, TimeoutError, OSError, ValueError) as error:
            logger.error(
                "Could not send Expo push notifications: %s",
                error,
            )


def notify_users(users, kind, title, message="", report=None):
    """
    Save in-app notifications and send push notifications
    to each recipient's registered mobile devices.
    """
    users = list(users)

    if not users:
        return

    # Preserve the existing in-app notification functionality.
    Notification.objects.bulk_create([
        Notification(
            recipient=user,
            kind=kind,
            title=title,
            message=message,
            report=report,
        )
        for user in users
    ])

    # Find registered Expo tokens for these users.
    user_ids = list({user.pk for user in users})

    devices = PushDevice.objects.filter(
        user_id__in=user_ids
    ).values_list(
        "user_id",
        "expo_push_token",
    )

    # Build a push message for each registered device.
    push_messages = []

    for user_id, token in devices:
        push_messages.append({
            "to": token,
            "title": title,
            "body": message or title,
            "sound": "default",
            "priority": "high",
            "channelId": "default",
            "data": {
                "kind": kind,
                "report_id": report.report_id if report else None,
            },
        })

    if push_messages:
        send_expo_push_notifications(push_messages)


def notify_role(role, kind, title, message="", report=None):
    User = get_user_model()

    users = User.objects.filter(
        role=role,
        is_active=True,
    )

    notify_users(
        users,
        kind,
        title,
        message,
        report,
    )
