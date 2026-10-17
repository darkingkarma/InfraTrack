
from django.urls import path

from .views import (
    IssueReportCreateView,
    IssueReportListView,
    MyIssueReportListView,
    ValidatedIssueReportListView,
    SubmitScreeningView,
    SubmitInspectionView,
    InspectedReportListView,
    CreateWorkOrderView,
    MyWorkOrderListView,
    FieldEngineerListView,
    SubmitRepairUpdateView,
    RespondToInfoRequestView,
    NotificationListView,
    UnreadNotificationCountView,
    MarkNotificationReadView,
    MarkAllNotificationsReadView,
    SubmitFeedbackView,
    SubmitFollowUpView,
    MyInspectionListView,
)

urlpatterns = [
    # Issue reports
    path('create/', IssueReportCreateView.as_view(), name='report-create'),
    path('list/', IssueReportListView.as_view(), name='report-list'),
    path('my-reports/', MyIssueReportListView.as_view(), name='my-reports'),
    path('validated/', ValidatedIssueReportListView.as_view(), name='validated-reports'),

    # FRU screening
    path(
        '<int:pk>/screen/',
        SubmitScreeningView.as_view(),
        name='submit-screening',
    ),

    # Field Engineer inspection
    path(
        '<int:pk>/inspect/',
        SubmitInspectionView.as_view(),
        name='submit-inspection',
    ),
    path(
        'my-inspections/',
        MyInspectionListView.as_view(),
        name='my-inspections',
    ),

    # Citizen responses
    path(
        '<int:pk>/respond/',
        RespondToInfoRequestView.as_view(),
        name='respond-info-request',
    ),

    # District Engineer work-order management
    path('inspected/', InspectedReportListView.as_view(), name='inspected-reports'),
    path('work-orders/create/', CreateWorkOrderView.as_view(), name='work-order-create'),
    path('field-engineers/', FieldEngineerListView.as_view(), name='field-engineers'),

    # Field Engineer repair updates
    path('work-orders/my-orders/', MyWorkOrderListView.as_view(), name='my-work-orders'),
    path(
        'work-orders/repair-update/',
        SubmitRepairUpdateView.as_view(),
        name='submit-repair-update',
    ),

    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notifications-list'),
    path(
        'notifications/unread-count/',
        UnreadNotificationCountView.as_view(),
        name='notifications-unread-count',
    ),
    path(
        'notifications/read-all/',
        MarkAllNotificationsReadView.as_view(),
        name='notifications-read-all',
    ),
    path(
        'notifications/<int:pk>/read/',
        MarkNotificationReadView.as_view(),
        name='notification-read',
    ),

    # Citizen feedback and follow-ups
    path('feedback/', SubmitFeedbackView.as_view(), name='submit-feedback'),
    path('follow-ups/', SubmitFollowUpView.as_view(), name='submit-follow-up'),
]
