from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from reports.models import Notification
from .models import User, Personnel, Citizen
from django.contrib import messages
from datetime import date, timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import ( CitizenRegisterSerializer, LoginSerializer, CitizenProfileSerializer, )
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from functools import wraps

def login_view(request):

    if request.user.is_authenticated:
        if request.user.role == "district_engineer":
            return redirect("district_dashboard")
        if request.user.role == "fru":
            return redirect("fru_dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is None:
            return render(request, "users/login.html", {
                "error": "Invalid username or password."
            })

        if user.role == "district_engineer":
            login(request, user)
            return redirect("district_dashboard")

        if user.role == "fru":
            login(request, user)
            return redirect("fru_dashboard")

        # Citizens and field engineers use the mobile app, so no web session
        return render(request, "users/login.html", {
            "error": "This account uses the mobile app. Please log in there."
        })

    return render(request, "users/login.html")

@login_required
def district_dashboard(request):

    from django.db.models import Count
    from reports.models import IssueReport, WorkOrder
    from infrastructure.models import Infrastructure

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access the dashboard."
        )

    reports = IssueReport.objects.all()
    total = reports.count()

    status_counts = {
        row["status"]: row["total"]
        for row in reports.values("status").annotate(total=Count("report_id"))
    }

    needs_info = status_counts.get("Needs More Info", 0)
    screening = status_counts.get("Pending Screening", 0) + needs_info
    awaiting_inspection = status_counts.get("Validated", 0)
    ongoing = status_counts.get("Work Order Issued", 0) + status_counts.get("In Progress", 0)
    resolved = status_counts.get("Resolved", 0)
    rejected = status_counts.get("Rejected", 0)

    valid_total = total - rejected
    resolution_rate = round(resolved / valid_total * 100) if valid_total else 0

    # Items that need the District Engineer to act
    ready_qs = reports.filter(
        status="Inspected"
    ).select_related("citizen").order_by("-reported_date")
    ready_count = ready_qs.count()

    update_qs = WorkOrder.objects.filter(update_requested=True).select_related(
        "report", "assigned_field_engineer__user"
    ).order_by("-update_requested_date")
    update_request_count = update_qs.count()

    high_qs = reports.none()
    high_open_count = 0
    high_open_count = high_qs.count()

    context = {
        "total": total,
        "screening": screening,
        "needs_info": needs_info,
        "awaiting_inspection": awaiting_inspection,
        "ongoing": ongoing,
        "resolved": resolved,
        "resolution_rate": resolution_rate,
        "ready_count": ready_count,
        "ready_for_work_order": ready_qs[:5],
        "update_request_count": update_request_count,
        "update_requests": update_qs[:5],
        "high_open_count": high_open_count,
        "high_open": high_qs[:5],
        "recent_activity": reports.select_related("citizen").order_by("-updated_date")[:8],
        "active_work_orders": WorkOrder.objects.exclude(status="Completed").count(),
        "infrastructure_total": Infrastructure.objects.count(),
        "infrastructure_maintenance": Infrastructure.objects.filter(status="maintenance").count(),
        "personnel_total": Personnel.objects.count(),
    }

    return render(request, "users/district/district_dashboard.html", context)

def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def add_personnel(request):

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        contact_number = request.POST.get("contact_number")
        address = request.POST.get("address")
        position = request.POST.get("position")

        # ----------------------------
        # Validation
        # ----------------------------

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(
                request,
                "users/district/add_personnel.html"
            )

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(
                request,
                "users/district/add_personnel.html"
            )

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return render(
                request,
                "users/district/add_personnel.html"
            )

        # ----------------------------
        # Create User
        # ----------------------------

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=position,
        )

        # ----------------------------
        # Create Personnel
        # ----------------------------

        employee_id = generate_employee_id()

        Personnel.objects.create(
            user=user,
            employee_id=employee_id,
            contact_number=contact_number,
            address=address,
            position=position,
        )

        messages.success(
            request,
            f"Personnel added successfully. Employee ID: {employee_id}"
        )

        return redirect("personnel")

    return render(request, "users/district/add_personnel.html")


def generate_employee_id():
    """Generates the next sequential Employee ID for the current year, e.g. EMP-2026-0001."""

    year = date.today().year
    prefix = f"EMP-{year}-"

    last_personnel = (
        Personnel.objects
        .filter(employee_id__startswith=prefix)
        .order_by("-employee_id")
        .first()
    )

    if last_personnel:
        last_number = int(last_personnel.employee_id.split("-")[-1])
        next_number = last_number + 1
    else:
        next_number = 1

    return f"{prefix}{next_number:04d}"

@login_required
def personnel(request):

    personnel_list = Personnel.objects.select_related("user").all().order_by("-id")

    context = {
        "personnel_list": personnel_list,
    }

    return render(request, "users/district/personnel.html", context)

@login_required
def view_personnel(request, pk):

    person = get_object_or_404(Personnel.objects.select_related("user"), pk=pk)

    return render(request, "users/district/view_personnel.html", {
        "person": person
    })

@login_required
def delete_personnel(request, pk):

    if request.method == "POST":

        person = get_object_or_404(Personnel, pk=pk)
        person.user.delete()   # deletes the linked User; Personnel cascades if FK is CASCADE

        messages.success(request, "Personnel deleted successfully.")

        return redirect("personnel")

    return redirect("personnel")

@login_required
def edit_personnel(request, pk):

    person = get_object_or_404(Personnel.objects.select_related("user"), pk=pk)
    user = person.user

    if request.method == "POST":

        email = request.POST.get("email")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        contact_number = request.POST.get("contact_number")
        address = request.POST.get("address")
        position = request.POST.get("position")
        new_password = request.POST.get("new_password")

        # ----------------------------
        # Validation
        # ----------------------------

        if User.objects.filter(email=email).exclude(pk=user.pk).exists():

            messages.error(request, "Email already in use by another account.")
            return redirect("edit_personnel", pk=pk)

        # ----------------------------
        # Update User
        # ----------------------------

        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = position

        if new_password:
            user.set_password(new_password)

        user.save()

        # ----------------------------
        # Update Personnel
        # ----------------------------

        person.contact_number = contact_number
        person.address = address
        person.position = position
        person.save()

        messages.success(request, "Personnel updated successfully.")

        return redirect("personnel")

    return render(request, "users/district/edit_personnel.html", {
        "person": person
    })

@login_required

def fru_dashboard(request):
    from reports.models import IssueReport, ReportScreening
    from django.utils import timezone

    pending_count = IssueReport.objects.filter(
        status="Pending Screening"
    ).count()

    start_of_today = timezone.localtime().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    screened_today = ReportScreening.objects.filter(
        screening_date__gte=start_of_today
    ).count()

    context = {
        "pending_count": pending_count,
        "screened_today": screened_today,
        "notifications_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count(),
    }

    return render(
        request,
        "users/fru/fru_dashboard.html",
        context
    )



@login_required
def pending_reports(request):

    from reports.models import IssueReport

    reports = IssueReport.objects.filter(
        status="Pending Screening"
    ).prefetch_related('info_requests').order_by('-reported_date')

    context = {
        "reports": reports,
    }

    return render(request, "users/fru/pending_reports.html", context)


@login_required
def screen_report(request, pk):

    from reports.models import IssueReport, InfoRequest, ReportScreening
    from reports.notifications import notify_users, notify_role
    from django.utils import timezone

    report = get_object_or_404(IssueReport, pk=pk)

    if request.method == "POST":

        if not hasattr(request.user, "personnel"):
            messages.error(request, "Your account has no personnel record, so it can't screen reports.")
            return redirect("pending_reports")

        screening_result = request.POST.get("screening_result")
        screening_remarks = request.POST.get("screening_remarks")
        completeness_status = request.POST.get("completeness_status", "Complete")
        duplicate_status = request.POST.get("duplicate_status", "Not Duplicate")
        jurisdiction_status = request.POST.get("jurisdiction_status", "Within Jurisdiction")

        failed_checks = (
            completeness_status != "Complete"
            or duplicate_status != "Not Duplicate"
            or jurisdiction_status != "Within Jurisdiction"
        )
        if screening_result == "Validated" and failed_checks:
            messages.error(
                request,
                "A report that is incomplete, a duplicate, or outside DPWH Iligan "
                "jurisdiction cannot be validated. Choose Needs More Info or Rejected."
            )
            return render(request, "users/fru/screen_report.html", {
                "report": report,
            })

        report.status = screening_result
        report.screening_remarks = screening_remarks
        report.screened_by = request.user.personnel
        report.screened_date = timezone.now()
        report.save()

        ReportScreening.objects.create(
            report=report,
            screened_by=request.user.personnel,
            completeness_status=completeness_status,
            duplicate_status=duplicate_status,
            jurisdiction_status=jurisdiction_status,
            screening_result=screening_result,
            remarks=screening_remarks or "",
        )

        if screening_result == "Needs More Info":
            InfoRequest.objects.create(
                report=report,
                requested_by=request.user.personnel,
                request_message=screening_remarks,
            )
            notify_users(
                [report.citizen], 'info_requested', 'More information needed',
                screening_remarks or f'Please add more details to "{report.title}".', report,
            )
        elif screening_result == "Validated":
            notify_users(
                [report.citizen], 'report_validated', 'Your report was validated',
                f'"{report.title}" passed screening and is waiting for a field inspection.', report,
            )
            notify_role(
                'field_engineer', 'report_validated', 'New report to inspect',
                f'"{report.title}" is ready for inspection.', report,
            )
        elif screening_result == "Rejected":
            notify_users(
                [report.citizen], 'report_rejected', 'Your report was rejected',
                screening_remarks or f'"{report.title}" was rejected during screening.', report,
            )

        messages.success(request, "Report screened successfully.")
        return redirect("pending_reports")

    return render(request, "users/fru/screen_report.html", {
        "report": report,
    })

@login_required
def validated_reports(request):

    from reports.models import IssueReport

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access validated reports."
        )

    reports = IssueReport.objects.filter(status="Validated").select_related(
        "citizen", "screened_by__user"
    ).order_by("-screened_date")

    return render(request, "users/district/validated_reports.html", {
        "reports": reports,
    })

@login_required
def work_orders(request):

    from reports.models import IssueReport

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access work orders."
        )

    reports = IssueReport.objects.filter(status="Inspected").order_by('-inspection_date')

    context = {
        "reports": reports,
    }

    return render(request, "users/district/work_orders.html", context)


@login_required
def create_work_order(request, pk):

    from reports.models import IssueReport, WorkOrder
    from reports.notifications import notify_users

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can create work orders."
        )

    report = get_object_or_404(IssueReport, pk=pk)
    field_engineers = Personnel.objects.filter(position="field_engineer").select_related("user")

    if request.method == "POST":

        if not hasattr(request.user, "personnel"):
            messages.error(request, "Your account has no personnel record, so it can't issue work orders.")
            return redirect("work_orders")

        if WorkOrder.objects.filter(report=report).exists():
            messages.error(request, "A work order already exists for this report.")
            return redirect("work_orders")

        assigned_engineer_id = request.POST.get("assigned_field_engineer")
        work_order_details = request.POST.get("work_order_details")

        assigned_engineer = get_object_or_404(Personnel, pk=assigned_engineer_id)

        WorkOrder.objects.create(
            report=report,
            issued_by=request.user.personnel,
            approved_by=request.user.personnel,
            assigned_field_engineer=assigned_engineer,
            work_order_details=work_order_details,
        )

        report.status = "Work Order Issued"
        report.save()

        notify_users(
            [assigned_engineer.user], 'work_order_assigned', 'New work order assigned',
            f'You were assigned to repair "{report.title}".', report,
        )
        notify_users(
            [report.citizen], 'work_order_issued', 'Repair scheduled',
            f'A work order was issued for "{report.title}".', report,
        )

        messages.success(request, "Work order created and assigned successfully.")
        return redirect("work_orders")

    return render(request, "users/district/create_work_order.html", {
        "report": report,
        "field_engineers": field_engineers,
    })

@login_required
def repair_monitoring(request):

    from reports.models import WorkOrder

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access repair monitoring."
        )

    work_orders = WorkOrder.objects.exclude(status='Issued').select_related(
        'report', 'assigned_field_engineer__user'
    ).prefetch_related('repair_updates').order_by('-date_issued')

    progress_map = {
        'Not Started': 10,
        'In Progress': 50,
        'Completed': 100,
    }

    for wo in work_orders:
        wo.progress_percent = progress_map.get(wo.status, 10)

    context = {
        "work_orders": work_orders,
    }

    return render(request, "users/district/repair_monitoring.html", context)

@login_required
def view_work_order(request, pk):

    from reports.models import WorkOrder

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view this page."
        )

    work_order = get_object_or_404(
        WorkOrder.objects.select_related('report', 'assigned_field_engineer__user', 'issued_by__user')
        .prefetch_related('repair_updates__photos'),
        pk=pk
    )

    return render(request, "users/district/view_work_order.html", {
        "work_order": work_order,
    })

@login_required
def request_work_order_update(request, pk):

    from reports.models import WorkOrder
    from reports.notifications import notify_users
    from django.utils import timezone

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can request updates."
        )

    work_order = get_object_or_404(WorkOrder, pk=pk)

    if request.method == "POST":
        message = request.POST.get("update_request_message", "")

        work_order.update_requested = True
        work_order.update_request_message = message
        work_order.update_requested_date = timezone.now()
        work_order.save()

        if work_order.assigned_field_engineer:
            notify_users(
                [work_order.assigned_field_engineer.user], 'update_requested', 'Update requested',
                message or f'The district engineer asked for a progress update on "{work_order.report.title}".',
                work_order.report,
            )

        messages.success(request, "Update request sent to the field engineer.")

    return redirect("view_work_order", pk=pk)

@login_required
def report_history(request):

    from reports.models import IssueReport

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access report history."
        )

    reports = IssueReport.objects.select_related('citizen').order_by('-reported_date')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        reports = reports.filter(title__icontains=search_query)

    if status_filter:
        reports = reports.filter(status=status_filter)

    context = {
        "reports": reports,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": IssueReport.STATUS_CHOICES,
    }

    return render(request, "users/district/report_history.html", context)


@login_required
def view_report_history_detail(request, pk):

    from reports.models import IssueReport

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view this page."
        )

    report = get_object_or_404(
        IssueReport.objects.select_related('citizen', 'screened_by__user', 'inspected_by__user')
        .prefetch_related('photos', 'inspection_photos', 'info_requests', 'work_order__repair_updates__photos'),
        pk=pk
    )

    return render(request, "users/district/view_report_history.html", {
        "report": report,
    })


def landing_page(request):
    return render(request, "users/landing_page.html")

#important dont delete
class CitizenRegisterAPIView(APIView):

    def post(self, request):
        serializer = CitizenRegisterSerializer(
            data=request.data
        )

        if serializer.is_valid():
            user = serializer.save()

            return Response({
                "message": "Citizen registered successfully.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "role": user.role,
                }
            }, status=status.HTTP_201_CREATED)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

class LoginAPIView(APIView):

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data
        )

        if serializer.is_valid():
            user = serializer.validated_data["user"]

            token, created = Token.objects.get_or_create(
                user=user
            )

            return Response({
                "message": "Login successful.",
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "role": user.role,
                }
            }, status=status.HTTP_200_OK)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

class CitizenProfileAPIView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        if user.role != "citizen":
            return Response(
                {
                    "error": "This endpoint is for citizens only."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            citizen = user.citizen_profile

        except Citizen.DoesNotExist:
            return Response(
                {
                    "error": "Citizen profile not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CitizenProfileSerializer(citizen)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

@login_required
def notifications_page(request):

    from reports.models import Notification

    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return redirect("notifications")

    notifications = Notification.objects.filter(recipient=request.user)[:100]

    return render(request, "users/notifications.html", {
        "notifications": notifications,
    })


@login_required
def open_notification(request, pk):

    from reports.models import Notification

    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])

    if notification.kind == "follow_up" and request.user.role in ("fru", "district_engineer"):
        return redirect("follow_ups")

    report = notification.report
    if report is None:
        return redirect("notifications")

    if request.user.role == "fru":
        if report.status == "Pending Screening":
            return redirect("screen_report", pk=report.pk)
        return redirect("pending_reports")

    if request.user.role == "district_engineer":
        work_order = getattr(report, "work_order", None)
        if work_order:
            return redirect("view_work_order", pk=work_order.pk)
        if report.status == "Inspected":
            return redirect("create_work_order", pk=report.pk)
        return redirect("view_report_history_detail", pk=report.pk)

    return redirect("notifications")

def role_required(*roles):
    """Login required, and the user's role must be one of `roles`."""
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return HttpResponseForbidden(
                    "You don't have permission to access this page."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator



@role_required("fru", "district_engineer")
def follow_ups(request):

    from reports.models import FollowUpRequest

    status_filter = request.GET.get("status", "Pending")

    items = FollowUpRequest.objects.select_related(
        "report", "citizen", "responded_by__user"
    )

    if status_filter in ("Pending", "Answered"):
        items = items.filter(status=status_filter)

    # Oldest question first while pending, newest first otherwise
    items = items.order_by("submitted_date" if status_filter == "Pending" else "-submitted_date")

    return render(request, "users/follow_ups.html", {
        "items": items,
        "status_filter": status_filter,
        "pending_total": FollowUpRequest.objects.filter(status="Pending").count(),
        "answered_total": FollowUpRequest.objects.filter(status="Answered").count(),
    })


@role_required("fru", "district_engineer")
def reply_follow_up(request, pk):

    from reports.models import FollowUpRequest
    from reports.notifications import notify_users
    from django.utils import timezone as dj_timezone

    if request.method != "POST":
        return redirect("follow_ups")

    follow_up = get_object_or_404(
        FollowUpRequest.objects.select_related("report", "citizen"), pk=pk
    )

    if not hasattr(request.user, "personnel"):
        messages.error(request, "Your account has no personnel record, so it can't reply.")
        return redirect("follow_ups")

    if follow_up.status == "Answered":
        messages.info(request, "This follow-up was already answered.")
        return redirect("follow_ups")

    response_text = request.POST.get("response", "").strip()
    if not response_text:
        messages.error(request, "Please write a reply.")
        return redirect("follow_ups")

    follow_up.response = response_text
    follow_up.status = "Answered"
    follow_up.responded_by = request.user.personnel
    follow_up.responded_date = dj_timezone.now()
    follow_up.save()

    notify_users(
        [follow_up.citizen], "follow_up_reply", "Reply to your follow-up",
        response_text, follow_up.report,
    )

    messages.success(request, "Reply sent to the citizen.")
    return redirect("follow_ups")