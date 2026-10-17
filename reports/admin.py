from django.contrib import admin
from .models import (
    IssueReport, ReportPhoto, InspectionPhoto, WorkOrder,
    RepairUpdate, RepairUpdatePhoto, InfoRequest, Notification, Feedback,
    FollowUpRequest, ReportScreening, InspectionValidation,
)

admin.site.register(IssueReport)
admin.site.register(ReportPhoto)
admin.site.register(InspectionPhoto)
admin.site.register(WorkOrder)
admin.site.register(RepairUpdate)
admin.site.register(RepairUpdatePhoto)
admin.site.register(InfoRequest)
admin.site.register(Notification)
admin.site.register(Feedback)
admin.site.register(FollowUpRequest)
admin.site.register(ReportScreening)
admin.site.register(InspectionValidation)