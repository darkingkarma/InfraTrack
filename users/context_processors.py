def notifications_context(request):
    if not request.user.is_authenticated:
        return {
            "unread_notifications_count": 0,
            "recent_notifications": [],
        }

    from reports.models import Notification

    user_notifications = Notification.objects.filter(
        recipient=request.user
    )

    return {
        "unread_notifications_count": user_notifications.filter(
            is_read=False
        ).count(),
        "recent_notifications": user_notifications.select_related(
            "report"
        ).order_by("-created_at")[:5],
    }

def follow_ups(request):
    """Pending follow-up count for the web sidebar (staff only)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role not in ("fru", "district_engineer"):
        return {}

    from reports.models import FollowUpRequest
    return {
        "pending_follow_ups_count": FollowUpRequest.objects.filter(status="Pending").count(),
    }