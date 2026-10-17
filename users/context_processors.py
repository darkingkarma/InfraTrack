def notifications(request):
    if request.user.is_authenticated:
        from reports.models import Notification
        return {
            "unread_notifications_count": Notification.objects.filter(
                recipient=request.user, is_read=False
            ).count()
        }
    return {}

def follow_ups(request):
    """Pending follow-up count for the web sidebar (staff only)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role not in ("fru", "district_engineer"):
        return {}

    from reports.models import FollowUpRequest
    return {
        "pending_follow_ups_count": FollowUpRequest.objects.filter(status="Pending").count(),
    }