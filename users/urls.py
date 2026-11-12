from django.urls import path
from . import views
from .views import CitizenRegisterAPIView, CitizenVerifyEmailAPIView, LoginAPIView, CitizenProfileAPIView, CitizenChangePasswordAPIView, VerifyTokenAPIView

urlpatterns = [
    path("", views.landing_page, name="landing_page"),
    path("login/", views.login_view, name="login"),
    path("district-dashboard/", views.district_dashboard, name="district_dashboard"),
    path("logout/", views.logout_view, name="logout"),
    path("personnel/add/", views.add_personnel, name="add_personnel"),
    path("personnel/", views.personnel, name="personnel"),
    path("personnel/<int:pk>/view/", views.view_personnel, name="view_personnel"),
    path("personnel/<int:pk>/edit/", views.edit_personnel, name="edit_personnel"),
    path("personnel/<int:pk>/delete/", views.delete_personnel, name="delete_personnel"),
    path("district/assign-inspection/",views.assign_inspection,name="assign_inspection"),
    path("validated-reports/", views.validated_reports, name="validated_reports"),
    path("work-orders/", views.work_orders, name="work_orders"),
    path("work-orders/<int:pk>/create/", views.create_work_order, name="create_work_order"),
    path("repair-monitoring/", views.repair_monitoring, name="repair_monitoring"),
    path("work-orders/<int:pk>/view/", views.view_work_order, name="view_work_order"),
    path("work-orders/<int:pk>/request-update/", views.request_work_order_update, name="request_work_order_update"),
    path("report-history/", views.report_history, name="report_history"),
    path("report-history/<int:pk>/view/", views.view_report_history_detail, name="view_report_history_detail"),
    path(
        "personnel-reports/",
        views.personnel_reports,
        name="personnel_reports",
    ),
    path("fru-dashboard/", views.fru_dashboard, name="fru_dashboard"),
    path("pending-reports/", views.pending_reports, name="pending_reports"),
    path("pending-reports/<int:pk>/screen/", views.screen_report, name="screen_report"),
    path("screening-history/",views.screening_history,name="screening_history"),
    path("fru/screening-history/<int:pk>/",views.screening_details,name="screening_details",),
    path("notifications/", views.notifications_page, name="notifications"),
    path("notifications/<int:pk>/", views.open_notification, name="open_notification"),
    path("follow-ups/", views.follow_ups, name="follow_ups"),
    path("follow-ups/<int:pk>/reply/", views.reply_follow_up, name="reply_follow_up"),
    #dont delete
    path("api/citizen/register/", CitizenRegisterAPIView.as_view(), name="citizen_register"),
    path("api/login/", LoginAPIView.as_view(), name="api-login",),
    path(
        "api/verify-token/",
        VerifyTokenAPIView.as_view(),
        name="verify-token",
    ),
    path("api/citizen/profile/", CitizenProfileAPIView.as_view(), name="citizen-profile",),
    path("api/citizen/change-password/",CitizenChangePasswordAPIView.as_view(),name="citizen_change_password"),
    path('feedback/', views.feedback_list, name='feedback_list'),
    path(
        "api/citizen/verify-email/",
        CitizenVerifyEmailAPIView.as_view(),
        name="verify-citizen-email",
    ),
    
    path(
        "api/password-reset/request/",
        views.PasswordResetRequestAPIView.as_view(),
        name="password_reset_request"
    ),
    path(
        "api/password-reset/confirm/",
        views.PasswordResetConfirmAPIView.as_view(),
        name="password_reset_confirm"
    ),

    path(
        "reset-password/",
        views.password_reset_page,
        name="password_reset_page"
    ),

]