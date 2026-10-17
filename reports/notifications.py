from django.contrib.auth import get_user_model
from .models import Notification


def notify_users(users, kind, title, message='', report=None):
    Notification.objects.bulk_create([
        Notification(recipient=u, kind=kind, title=title, message=message, report=report)
        for u in users
    ])


def notify_role(role, kind, title, message='', report=None):
    User = get_user_model()
    notify_users(User.objects.filter(role=role, is_active=True), kind, title, message, report)