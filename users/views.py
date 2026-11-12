from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from reports.models import Feedback, Notification, IssueReport, ReportScreening
from .models import User, Personnel, Citizen, PendingCitizenRegistration
from django.contrib import messages
from datetime import date, timezone
from datetime import datetime, timedelta
from django.db import transaction, IntegrityError
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .serializers import ( CitizenRegisterSerializer, LoginSerializer, CitizenProfileSerializer, )
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from functools import wraps
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from difflib import SequenceMatcher
from math import radians, sin, cos, sqrt, atan2
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import AllowAny

User = get_user_model()

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
    from django.db.models import Count, OuterRef, Subquery
    from reports.models import (
        IssueReport,
        WorkOrder,
        InspectionValidation,
    )
    from infrastructure.models import Infrastructure
    from users.models import Personnel

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access the dashboard."
        )

    # Latest inspection information for each report.
    latest_inspection = InspectionValidation.objects.filter(
        report_id=OuterRef("report_id")
    ).order_by("-inspection_date")

    reports = IssueReport.objects.all()
    total = reports.count()

    # Count reports by their current workflow status.
    status_counts = {
        row["status"]: row["total"]
        for row in reports.values("status").annotate(
            total=Count("report_id")
        )
    }

    needs_info = status_counts.get("Needs More Info", 0)
    screening = (
        status_counts.get("Pending Screening", 0)
        + needs_info
    )

    awaiting_inspection = status_counts.get("Validated", 0)

    ongoing = (
        status_counts.get("Work Order Issued", 0)
        + status_counts.get("In Progress", 0)
    )

    resolved = status_counts.get("Resolved", 0)
    rejected = status_counts.get("Rejected", 0)


    # Inspected reports waiting for a work order.
    ready_qs = (
        reports.filter(status="Inspected")
        .annotate(
            severity_level=Subquery(
                latest_inspection.values("severity_rating")[:1]
            ),
            inspection_date=Subquery(
                latest_inspection.values("inspection_date")[:1]
            ),
        )
        .select_related("citizen")
        .order_by("-updated_date")
    )

    ready_count = ready_qs.count()

    # Work orders with update requests from Field Engineers.
    update_qs = (
        WorkOrder.objects.filter(update_requested=True)
        .select_related(
            "report",
            "assigned_field_engineer__user",
        )
        .order_by("-update_requested_date")
    )

    update_request_count = update_qs.count()

    # High-severity reports that remain unresolved.
    high_qs = (
        reports.filter(
            inspection_validations__severity_rating="High",
            inspection_validations__validation_result="Confirmed",
        )
        .exclude(
            status__in=[
                "Resolved",
                "Rejected",
                "Not Confirmed",
            ]
        )
        .annotate(
            severity_level=Subquery(
                latest_inspection.values("severity_rating")[:1]
            ),
            inspection_date=Subquery(
                latest_inspection.values("inspection_date")[:1]
            ),
        )
        .select_related("citizen")
        .distinct()
        .order_by("-reported_date")
    )

    high_open_count = high_qs.count()

    context = {
        "total": total,
        "screening": screening,
        "needs_info": needs_info,
        "awaiting_inspection": awaiting_inspection,
        "ongoing": ongoing,
        "resolved": resolved,

        "ready_count": ready_count,
        "ready_for_work_order": ready_qs[:5],

        "update_request_count": update_request_count,
        "update_requests": update_qs[:5],

        "high_open_count": high_open_count,
        "high_open": high_qs[:5],

        "recent_activity": (
            reports.select_related("citizen")
            .order_by("-updated_date")[:8]
        ),

        "active_work_orders": (
            WorkOrder.objects
            .exclude(status="Completed")
            .count()
        ),

        "infrastructure_total": Infrastructure.objects.count(),

        "infrastructure_maintenance": (
            Infrastructure.objects
            .filter(status="maintenance")
            .count()
        ),

        "personnel_total": Personnel.objects.count(),
    }

    return render(
        request,
        "users/district/district_dashboard.html",
        context,
    )


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
        is_active = request.POST.get("is_active", "1") == "1"

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
            is_active=is_active,
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


@login_required
def edit_personnel(request, pk):

    person = get_object_or_404(
        Personnel.objects.select_related("user"),
        pk=pk
    )

    user = person.user

    if request.method == "POST":

        email = request.POST.get("email")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        contact_number = request.POST.get("contact_number")
        address = request.POST.get("address")
        position = request.POST.get("position")
        new_password = request.POST.get("new_password")
        is_active = request.POST.get("is_active", "1") == "1"

        # ----------------------------
        # Validation
        # ----------------------------

        if User.objects.filter(email=email).exclude(pk=user.pk).exists():

            messages.error(
                request,
                "Email already in use by another account."
            )

            return redirect("edit_personnel", pk=pk)

        # ----------------------------
        # Update User
        # ----------------------------

        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = position
        user.is_active = is_active

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

        messages.success(
            request,
            "Personnel updated successfully."
        )

        return redirect("personnel")

    return render(request, "users/district/edit_personnel.html", {
        "person": person
    })


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
def fru_dashboard(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "fru":
        raise PermissionDenied(
            "Only FRU personnel can access this dashboard."
        )

    today = timezone.localdate()

    start_of_today = timezone.make_aware(
        datetime.combine(today, datetime.min.time())
    )

    start_of_tomorrow = timezone.make_aware(
        datetime.combine(
            today + timedelta(days=1),
            datetime.min.time()
        )
    )

    pending_count = IssueReport.objects.filter(
        status="Pending Screening"
    ).count()

    screened_today = ReportScreening.objects.filter(
        screening_date__gte=start_of_today,
        screening_date__lt=start_of_tomorrow,
    ).count()

    rejected_count = IssueReport.objects.filter(
        status="Rejected"
    ).count()

    needs_info_count = IssueReport.objects.filter(
        status="Needs More Info"
    ).count()

    context = {
        "pending_count": pending_count,
        "screened_today": screened_today,
        "rejected_count": rejected_count,
        "needs_info_count": needs_info_count,
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
    from django.http import HttpResponseForbidden

    if request.user.role != "fru":
        return HttpResponseForbidden(
            "Only FRU personnel can screen reports."
        )

    report = get_object_or_404(IssueReport, pk=pk)


    # A report needing more information can only be rescreened
    # after the citizen responds to the latest information request.
    if report.status == "Needs More Info":
        latest_info_request = (
            report.info_requests
            .order_by("-requested_date", "-pk")
            .first()
        )

        citizen_has_responded = (
            latest_info_request is not None
            and latest_info_request.response_date is not None
            and bool(
                latest_info_request.response_message
                and latest_info_request.response_message.strip()
            )
        )

        if not citizen_has_responded:
            messages.error(
                request,
                "This report is waiting for the citizen to provide "
                "the requested information before it can be screened again."
            )
            return redirect("pending_reports")

        # Suggest jurisdiction based on the registered infrastructure.
    jurisdiction_suggestion = {
        "status": "Manual Verification Needed",
        "message": (
            "No registered infrastructure is linked to this report. "
            "Please verify its jurisdiction manually."
        ),
        "infrastructure": None,
        "type_matches": None,
    }

    if report.infrastructure_id:
        infrastructure = report.infrastructure

        type_matches = (
            str(report.infrastructure_type).lower()
            == str(infrastructure.infra_type).lower()
        )

        jurisdiction_suggestion = {
            "status": (
                "Reference Found"
                if type_matches
                else "Infrastructure Type Mismatch"
            ),
            "message": (
                "A registered infrastructure is linked to this report. "
                "Review its details and verify jurisdiction before deciding."
                if type_matches
                else
                "The report type does not match the registered "
                "infrastructure type. Please review it and verify "
                "jurisdiction manually."
            ),
            "infrastructure": infrastructure,
            "type_matches": type_matches,
        }

        # Find possible duplicate reports.
    possible_duplicates = []

    if report.latitude is not None and report.longitude is not None:
        try:
            current_lat = float(report.latitude)
            current_lon = float(report.longitude)

            if (
                -90 <= current_lat <= 90
                and -180 <= current_lon <= 180
            ):
                existing_reports = (
                    IssueReport.objects
                    .exclude(pk=report.pk)
                    .exclude(status="Rejected")
                    .filter(
                        infrastructure_type=report.infrastructure_type
                    )
                    .order_by("-reported_date")
                )

                current_text = (
                    f"{report.title or ''} "
                    f"{report.description or ''}"
                ).lower().strip()

                for existing in existing_reports:
                    try:
                        existing_lat = float(existing.latitude)
                        existing_lon = float(existing.longitude)
                    except (TypeError, ValueError):
                        continue

                    if not (
                        -90 <= existing_lat <= 90
                        and -180 <= existing_lon <= 180
                    ):
                        continue

                    # Calculate distance between the two locations.
                    lat1 = radians(current_lat)
                    lon1 = radians(current_lon)
                    lat2 = radians(existing_lat)
                    lon2 = radians(existing_lon)

                    dlat = lat2 - lat1
                    dlon = lon2 - lon1

                    a = (
                        sin(dlat / 2) ** 2
                        + cos(lat1) * cos(lat2)
                        * sin(dlon / 2) ** 2
                    )

                    distance = (
                        6371000
                        * 2
                        * atan2(sqrt(a), sqrt(1 - a))
                    )

                    existing_text = (
                        f"{existing.title or ''} "
                        f"{existing.description or ''}"
                    ).lower().strip()

                    text_similarity = SequenceMatcher(
                        None,
                        current_text,
                        existing_text,
                    ).ratio()

                    # Flag nearby reports with similar descriptions,
                    # or reports with very similar descriptions.
                    if (
                        distance <= 500
                        and text_similarity >= 0.25
                    ) or text_similarity >= 0.65:
                        possible_duplicates.append({
                            "report": existing,
                            "distance": round(distance),
                            "similarity": round(
                                text_similarity * 100
                            ),
                        })

        except (TypeError, ValueError):
            pass

    possible_duplicates = possible_duplicates[:10]

    is_awaiting_screening = report.status in (
        "Pending Screening",
        "Needs More Info",
    )

    if not is_awaiting_screening and request.method == "POST":
        messages.error(
            request,
            "This report has already been screened and cannot be screened again here."
        )
        return redirect("pending_reports")

    # Calculate completeness from the saved report data.
    photos_exist = report.photos.filter(
        file_path__isnull=False
    ).exclude(file_path="").exists()

    try:
        latitude = float(report.latitude)
        longitude = float(report.longitude)
        coordinates_valid = (
            -90 <= latitude <= 90
            and -180 <= longitude <= 180
        )
    except (TypeError, ValueError):
        coordinates_valid = False

    infrastructure_types = {
        choice[0] for choice in IssueReport._meta
        .get_field("infrastructure_type").choices
    }

    completeness_checks = [
        {
            "label": "Report title",
            "passed": bool(report.title and report.title.strip()),
        },
        {
            "label": "Report description",
            "passed": bool(
                report.description and report.description.strip()
            ),
        },
        {
            "label": "Infrastructure type",
            "passed": report.infrastructure_type in infrastructure_types,
        },
        {
            "label": "Valid GPS coordinates",
            "passed": coordinates_valid,
        },
        {
            "label": "Location description",
            "passed": bool(
                report.geographic_address
                and report.geographic_address.strip()
            ),
        },
        {
            "label": "At least one uploaded photo",
            "passed": photos_exist,
        },
    ]

    is_complete = all(
        check["passed"] for check in completeness_checks
    )

    completeness_status = "Complete" if is_complete else "Incomplete"

    def render_screening_page():
        return render(
            request,
            "users/fru/screen_report.html",
            {
                "report": report,
                "completeness_checks": completeness_checks,
                "completeness_status": completeness_status,
                "possible_duplicates": possible_duplicates,
                "jurisdiction_suggestion": jurisdiction_suggestion,
            },
        )

    if request.method == "POST":
        if not hasattr(request.user, "personnel"):
            messages.error(
                request,
                "Your account has no personnel record, so it can't screen reports."
            )
            return redirect("pending_reports")

        screening_result = request.POST.get(
            "screening_result", ""
        ).strip()
        screening_remarks = request.POST.get(
            "screening_remarks", ""
        ).strip()
        duplicate_status = request.POST.get("duplicate_status", "")
        jurisdiction_status = request.POST.get("jurisdiction_status", "")

        if duplicate_status not in ("Not Duplicate", "Duplicate"):
            messages.error(request, "Invalid duplicate status.")
            return render_screening_page()

        if jurisdiction_status not in (
            "Within Jurisdiction",
            "Outside Jurisdiction",
        ):
            messages.error(request, "Invalid jurisdiction status.")
            return render_screening_page()

        if screening_result not in (
            "Validated",
            "Needs More Info",
            "Rejected",
        ):
            messages.error(request, "Invalid screening result.")
            return render_screening_page()

        failed_checks = (
            not is_complete
            or duplicate_status != "Not Duplicate"
            or jurisdiction_status != "Within Jurisdiction"
        )

        if screening_result == "Validated" and failed_checks:
            messages.error(
                request,
                "This report cannot be validated because one or more "
                "screening checks failed. Choose Needs More Info or Rejected."
            )
            return render_screening_page()

        if (
            screening_result in ("Needs More Info", "Rejected")
            and not screening_remarks
        ):
            messages.error(
                request,
                "Please provide remarks explaining your decision."
            )
            return render_screening_page()

        ReportScreening.objects.create(
            report=report,
            screened_by=request.user.personnel,
            completeness_status=completeness_status,
            duplicate_status=duplicate_status,
            jurisdiction_status=jurisdiction_status,
            screening_result=screening_result,
            remarks=screening_remarks,
        )

        report.status = screening_result
        report.save(update_fields=["status", "updated_date"])

        if screening_result == "Needs More Info":
            InfoRequest.objects.create(
                report=report,
                requested_by=request.user.personnel,
                request_message=screening_remarks,
            )
            notify_users(
                [report.citizen],
                "info_requested",
                "More information needed",
                screening_remarks,
                report,
            )

        elif screening_result == "Validated":
            # Notify the Citizen
            notify_users(
                [report.citizen],
                "report_validated",
                "Your report was validated",
                f'"{report.title}" passed screening and is waiting for a field inspection.',
                report,
            )

            # Notify Field Engineers
            notify_role(
                "field_engineer",
                "report_validated",
                "New report to inspect",
                f'"{report.title}" is ready for inspection.',
                report,
            )

            # Notify the District Engineer
            notify_role(
                "district_engineer",
                "report_validated",
                "New validated report",
                f'"{report.title}" has been validated by the FRU and is ready for inspection assignment.',
                report,
            )

        elif screening_result == "Rejected":
            notify_users(
                [report.citizen],
                "report_rejected",
                "Your report was rejected",
                screening_remarks,
                report,
            )

        messages.success(request, "Report screened successfully.")
        return redirect("pending_reports")

    return render_screening_page()



@login_required
def validated_reports(request):
    from django.db.models import Q, OuterRef, Subquery, Prefetch
    from reports.models import (
        IssueReport,
        ReportScreening,
        InspectionValidation,
    )

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access validated reports."
        )

    search_query = request.GET.get("q", "").strip()

    # Find the latest screening date for each report
    latest_screening = ReportScreening.objects.filter(
        report_id=OuterRef("report_id")
    ).order_by("-screening_date")

    reports = (
        IssueReport.objects
        .filter(status="Validated")
        .annotate(
            latest_screening_date=Subquery(
                latest_screening.values("screening_date")[:1]
            )
        )
        .select_related("citizen")
        .prefetch_related(
            Prefetch(
                "screenings",
                queryset=ReportScreening.objects
                .select_related("screened_by__user")
                .order_by("-screening_date"),
            ),
            Prefetch(
                "inspection_validations",
                queryset=InspectionValidation.objects
                .select_related("inspected_by__user")
                .order_by("-inspection_date"),
            ),
        )
    )

    # Search by title, location, citizen name, or infrastructure type
    if search_query:
        search_filter = (
            Q(title__icontains=search_query)
            | Q(geographic_address__icontains=search_query)
            | Q(citizen__first_name__icontains=search_query)
            | Q(citizen__last_name__icontains=search_query)
            | Q(infrastructure_type__icontains=search_query)
        )

        if search_query.isdigit():
            search_filter |= Q(report_id=int(search_query))

        reports = reports.filter(search_filter)

    # Latest screened reports first
    reports = reports.order_by(
        "-latest_screening_date",
        "-reported_date",
    )

    return render(
        request,
        "users/district/validated_reports.html",
        {
            "reports": reports,
            "search_query": search_query,
        },
    )


@login_required
def screening_history(request):
    from django.http import HttpResponseForbidden
    from django.db.models import Q
    from reports.models import ReportScreening

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "fru":
        return HttpResponseForbidden(
            "Only FRU personnel can access screening history."
        )

    search_query = request.GET.get("q", "").strip()
    result_filter = request.GET.get("result", "").strip()
    completeness_filter = request.GET.get("completeness", "").strip()
    duplicate_filter = request.GET.get("duplicate", "").strip()
    jurisdiction_filter = request.GET.get("jurisdiction", "").strip()
    sort_order = request.GET.get("sort", "newest").strip()

    screenings = ReportScreening.objects.select_related(
        "report",
        "report__citizen",
        "screened_by",
        "screened_by__user",
    )

    # Search by report title, citizen, or FRU personnel.
    if search_query:
        search_conditions = (
            Q(report__title__icontains=search_query)
            | Q(report__citizen__first_name__icontains=search_query)
            | Q(report__citizen__last_name__icontains=search_query)
            | Q(report__citizen__username__icontains=search_query)
            | Q(screened_by__user__first_name__icontains=search_query)
            | Q(screened_by__user__last_name__icontains=search_query)
            | Q(screened_by__user__username__icontains=search_query)
        )

        if search_query.isdigit():
            search_conditions |= Q(
                report__report_id=int(search_query)
            )

        screenings = screenings.filter(search_conditions)

    # Screening result filter.
    if result_filter in ("Validated", "Needs More Info", "Rejected"):
        screenings = screenings.filter(
            screening_result=result_filter
        )

    # Completeness filter.
    if completeness_filter in ("Complete", "Incomplete"):
        screenings = screenings.filter(
            completeness_status=completeness_filter
        )

    # Duplicate filter.
    if duplicate_filter in ("Not Duplicate", "Duplicate"):
        screenings = screenings.filter(
            duplicate_status=duplicate_filter
        )

    # Jurisdiction filter.
    if jurisdiction_filter in (
        "Within Jurisdiction",
        "Outside Jurisdiction",
    ):
        screenings = screenings.filter(
            jurisdiction_status=jurisdiction_filter
        )

    # Sorting.
    if sort_order == "oldest":
        screenings = screenings.order_by("screening_date", "pk")
    else:
        sort_order = "newest"
        screenings = screenings.order_by("-screening_date", "-pk")

    context = {
        "screenings": screenings,
        "search_query": search_query,
        "result_filter": result_filter,
        "completeness_filter": completeness_filter,
        "duplicate_filter": duplicate_filter,
        "jurisdiction_filter": jurisdiction_filter,
        "sort_order": sort_order,
    }

    return render(
        request,
        "users/fru/screening_history.html",
        context,
    )

@login_required

def screening_details(request, pk):
    from django.http import HttpResponseForbidden
    from reports.models import ReportScreening

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "fru":
        return HttpResponseForbidden(
            "Only FRU personnel can view screening details."
        )

    screening = get_object_or_404(
        ReportScreening.objects.select_related(
            "report",
            "report__citizen",
            "report__infrastructure",
            "screened_by",
            "screened_by__user",
        ).prefetch_related(
            "report__photos",
            "report__info_requests",
            "report__screenings",
        ),
        pk=pk,
    )

    return render(
        request,
        "users/fru/screening_details.html",
        {
            "screening": screening,
            "report": screening.report,
        },
    )


@login_required
def work_orders(request):
    from django.db.models import Q, OuterRef, Subquery
    from reports.models import IssueReport, InspectionValidation

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access work orders."
        )

    search_query = request.GET.get("q", "").strip()

    # Get the most recent inspection date for each report.
    latest_inspection = InspectionValidation.objects.filter(
        report_id=OuterRef("report_id")
    ).order_by("-inspection_date")

    reports = IssueReport.objects.filter(
        status="Inspected"
    ).annotate(
        latest_inspection_date=Subquery(
            latest_inspection.values("inspection_date")[:1]
        )
    ).select_related(
        "citizen",
        "infrastructure",
    )

    # Search by report ID, title, location, or infrastructure type.
    if search_query:
        search_filter = (
            Q(title__icontains=search_query)
            | Q(geographic_address__icontains=search_query)
            | Q(infrastructure_type__icontains=search_query)
        )

        if search_query.isdigit():
            search_filter |= Q(report_id=int(search_query))

        reports = reports.filter(search_filter)

    # Most recently inspected reports appear first.
    reports = reports.order_by(
        "-latest_inspection_date",
        "-updated_date",
    )

    return render(
        request,
        "users/district/work_orders.html",
        {
            "reports": reports,
            "search_query": search_query,
        },
    )



@login_required

def create_work_order(request, pk):
    from reports.models import IssueReport, WorkOrder, InspectionValidation
    from reports.notifications import notify_users

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can create work orders."
        )

    report = get_object_or_404(
        IssueReport.objects.select_related(
            "citizen",
            "infrastructure",
        ),
        report_id=pk,
    )

    field_engineers = Personnel.objects.filter(
        position="field_engineer"
    ).select_related("user")

    # Get the latest inspection record for this report.
    inspection = report.inspection_validations.first()

    # Allow work orders only for confirmed, inspected reports.
    can_create_work_order = (
        inspection is not None
        and inspection.validation_result == "Confirmed"
        and report.status == "Inspected"
        and not WorkOrder.objects.filter(report=report).exists()
    )

    if request.method == "POST":

        if not hasattr(request.user, "personnel"):
            messages.error(
                request,
                "Your account has no personnel record, "
                "so it cannot issue work orders."
            )
            return redirect("work_orders")

        if not can_create_work_order:
            messages.error(
                request,
                "A work order cannot be created. "
                "The report must have a confirmed inspection "
                "and must not already have a work order."
            )
            return redirect("work_orders")

        assigned_engineer_id = request.POST.get(
            "assigned_field_engineer"
        )
        work_order_details = request.POST.get(
            "work_order_details", ""
        ).strip()

        if not assigned_engineer_id or not work_order_details:
            messages.error(
                request,
                "Please select a Field Engineer and enter "
                "the work order details."
            )
        else:
            assigned_engineer = get_object_or_404(
                field_engineers,
                pk=assigned_engineer_id,
            )

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
                [assigned_engineer.user],
                "work_order_assigned",
                "New work order assigned",
                f'You were assigned to repair "{report.title}".',
                report,
            )

            notify_users(
                [report.citizen],
                "work_order_issued",
                "Repair scheduled",
                f'A work order was issued for "{report.title}".',
                report,
            )

            messages.success(
                request,
                "Work order created and assigned successfully."
            )
            return redirect("work_orders")

    return render(
        request,
        "users/district/create_work_order.html",
        {
            "report": report,
            "field_engineers": field_engineers,
            "inspection": inspection,
            "can_create_work_order": can_create_work_order,
        },
    )


@login_required

def repair_monitoring(request):
    from django.db.models import Q, Prefetch
    from reports.models import WorkOrder, RepairUpdate

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access repair monitoring."
        )

    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    work_orders = WorkOrder.objects.select_related(
        "report",
        "assigned_field_engineer__user",
    ).prefetch_related(
        Prefetch(
            "repair_updates",
            queryset=RepairUpdate.objects.order_by("-update_date"),
            to_attr="ordered_repair_updates",
        )
    )

    if search_query:
        filters = Q(report__title__icontains=search_query)

        if search_query.isdigit():
            filters |= Q(pk=int(search_query))

        filters |= Q(
            assigned_field_engineer__user__first_name__icontains=search_query
        )
        filters |= Q(
            assigned_field_engineer__user__last_name__icontains=search_query
        )
        filters |= Q(
            assigned_field_engineer__user__username__icontains=search_query
        )

        work_orders = work_orders.filter(filters)

    valid_statuses = ["Issued", "In Progress", "Completed"]

    if status_filter in valid_statuses:
        work_orders = work_orders.filter(status=status_filter)
    else:
        status_filter = ""

    work_orders = work_orders.order_by("-date_issued")

    for wo in work_orders:
        wo.latest_repair_update = (
            wo.ordered_repair_updates[0]
            if wo.ordered_repair_updates
            else None
        )

    return render(
        request,
        "users/district/repair_monitoring.html",
        {
            "work_orders": work_orders,
            "search_query": search_query,
            "status_filter": status_filter,
        },
    )

@login_required
def view_work_order(request, pk):
    from django.contrib.auth.decorators import login_required
    from django.db.models import Prefetch
    from reports.models import WorkOrder, RepairUpdate, InspectionValidation

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view this page."
        )

    work_order = get_object_or_404(
        WorkOrder.objects.select_related(
            "report",
            "report__citizen",
            "report__infrastructure",
            "assigned_field_engineer__user",
            "issued_by__user",
            "approved_by__user",
        ).prefetch_related(
            Prefetch(
                "repair_updates",
                queryset=RepairUpdate.objects.prefetch_related(
                    "photos"
                ).order_by("-update_date"),
                to_attr="ordered_repair_updates",
            ),
        ),
        pk=pk,
    )

    inspection = (
        InspectionValidation.objects.filter(
            report=work_order.report
        )
        .select_related("inspected_by__user")
        .order_by("-inspection_date")
        .first()
    )

    return render(
        request,
        "users/district/view_work_order.html",
        {
            "work_order": work_order,
            "inspection": inspection,
        },
    )

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
    from django.db.models import Q
    from reports.models import IssueReport

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access report history."
        )

    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    work_order_filter = request.GET.get("work_order", "").strip()

    reports = IssueReport.objects.select_related(
        "citizen",
        "infrastructure",
        "work_order",
    ).order_by("-reported_date")

    # Search reports
    if search_query:
        search_filter = (
            Q(title__icontains=search_query)
            | Q(citizen__first_name__icontains=search_query)
            | Q(citizen__last_name__icontains=search_query)
            | Q(citizen__username__icontains=search_query)
        )

        if search_query.isdigit():
            search_filter |= Q(report_id=int(search_query))

        reports = reports.filter(search_filter)

    # Filter by report status
    valid_statuses = [
        value for value, label in IssueReport.STATUS_CHOICES
    ]

    if status_filter in valid_statuses:
        reports = reports.filter(status=status_filter)
    else:
        status_filter = ""

    # Filter by Work Order existence
    if work_order_filter == "issued":
        reports = reports.filter(work_order__isnull=False)

    elif work_order_filter == "none":
        reports = reports.filter(work_order__isnull=True)

    else:
        work_order_filter = ""

    context = {
        "reports": reports,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": IssueReport.STATUS_CHOICES,
        "work_order_filter": work_order_filter,
    }

    return render(
        request,
        "users/district/report_history.html",
        context,
    )


@login_required
def view_report_history_detail(request, pk):
    from django.urls import reverse
    from django.db.models import Prefetch
    from reports.models import (
        IssueReport,
        ReportScreening,
        InspectionValidation,
        RepairUpdate,
    )

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view this page."
        )

    report = get_object_or_404(
        IssueReport.objects
        .select_related(
            "citizen",
            "infrastructure",
            "work_order",
            "feedback",
        )
        .prefetch_related(
            "photos",
            "inspection_photos",
            "info_requests",
            Prefetch(
                "screenings",
                queryset=ReportScreening.objects
                .select_related("screened_by__user")
                .order_by("-screening_date"),
                to_attr="history_screenings",
            ),
            Prefetch(
                "inspection_validations",
                queryset=InspectionValidation.objects
                .select_related("inspected_by__user")
                .order_by("-inspection_date"),
                to_attr="history_inspections",
            ),
            Prefetch(
                "work_order__repair_updates",
                queryset=RepairUpdate.objects
                .select_related("submitted_by__user")
                .prefetch_related("photos")
                .order_by("-update_date"),
                to_attr="history_repair_updates",
            ),
        ),
        report_id=pk,
    )

    if hasattr(report, "work_order"):
        report.work_order.history_repair_updates = (
            report.work_order.history_repair_updates
        )

    # Determine where the user came from
    return_pages = {
        "validated_reports": {
            "url": reverse("validated_reports"),
            "label": "Back to Validated Reports",
        },
        "report_history": {
            "url": reverse("report_history"),
            "label": "Back to Report History",
        },
    }

    return_page = request.GET.get("from", "report_history")
    back_page = return_pages.get(
        return_page,
        return_pages["report_history"],
    )

    return render(
        request,
        "users/district/view_report_history.html",
        {
            "report": report,
            "back_url": back_page["url"],
            "back_label": back_page["label"],
        },
    )


def landing_page(request):
    return render(request, "users/landing_page.html")

#important dont delete


class CitizenRegisterAPIView(APIView):
    import logging

    logger = logging.getLogger(__name__)

    def post(self, request):
        serializer = CitizenRegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data.copy()
        data.pop("confirm_password")

        password = data.pop("password")

        # Prevent duplicate pending registrations.
        if PendingCitizenRegistration.objects.filter(
            username=data["username"]
        ).exists():
            return Response(
                {"username": ["A registration with this username is already pending verification."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        if PendingCitizenRegistration.objects.filter(
            email=data["email"]
        ).exists():
            return Response(
                {"email": ["A registration with this email is already pending verification."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save pending details only; do not create a User yet.
        pending = PendingCitizenRegistration.objects.create(
            **data,
            password_hash=make_password(password)
        )

        verification_token = signing.dumps(
            pending.pk,
            salt="citizen-email-verification"
        )

        verification_url = (
            request.build_absolute_uri(
                reverse("verify-citizen-email")
            )
            + "?token="
            + verification_token
        )

        try:
            send_mail(
                subject="Verify Your InfraTrack Email",
                message=(
                    f"Hello {pending.first_name},\n\n"
                    "Thank you for registering with InfraTrack.\n"
                    "Click the link below to verify your email and complete registration:\n\n"
                    f"{verification_url}\n\n"
                    "This link expires after 24 hours.\n\n"
                    "If you did not register, you can ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[pending.email],
                fail_silently=False,
            )

        except Exception:
            logger.exception("Citizen registration email failed")
            pending.delete()

            return Response(
                {
                    "message": "We could not send the verification email. No account was created. Please try again later."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response(
            {
                "message": (
                    "A verification email has been sent. "
                    "Verify your email to complete registration."
                )
            },
            status=status.HTTP_200_OK
        )




class CitizenVerifyEmailAPIView(APIView):

    def get(self, request):
        token = request.query_params.get("token")

        if not token:
            return render(
                request,
                "users/citizen_email_error.html",
                {"message": "The verification token is missing."},
                status=400
            )

        try:
            pending_id = signing.loads(
                token,
                salt="citizen-email-verification",
                max_age=86400
            )

        except signing.SignatureExpired:
            return render(
                request,
                "users/citizen_email_error.html",
                {"message": "Your verification link has expired. Please register again."},
                status=400
            )

        except signing.BadSignature:
            return render(
                request,
                "users/citizen_email_error.html",
                {"message": "This verification link is invalid."},
                status=400
            )

        try:
            pending = PendingCitizenRegistration.objects.get(
                pk=pending_id
            )

        except PendingCitizenRegistration.DoesNotExist:
            return render(
                request,
                "users/citizen_email_error.html",
                {"message": "This registration has already been completed or cancelled."},
                status=400
            )

        # Check for duplicate username or email.
        if User.objects.filter(
            username=pending.username
        ).exists() or User.objects.filter(
            email=pending.email
        ).exists():

            pending.delete()

            return render(
                request,
                "users/citizen_email_error.html",
                {
                    "message": (
                        "This username or email is already registered. "
                        "Please start registration again."
                    )
                },
                status=400
            )

        try:
            with transaction.atomic():

                user = User.objects.create(
                    username=pending.username,
                    first_name=pending.first_name,
                    last_name=pending.last_name,
                    email=pending.email,
                    password=pending.password_hash,
                    role="citizen",
                    is_active=True
                )

                Citizen.objects.create(
                    user=user,
                    contact_number=pending.contact_number,
                    address=pending.address
                )

                pending.delete()

        except IntegrityError:
            return render(
                request,
                "users/citizen_email_error.html",
                {
                    "message": (
                        "Registration could not be completed because "
                        "the username or email may already be registered. "
                        "Please try again."
                    )
                },
                status=400
            )

        return render(
            request,
            "users/citizen_email_verified.html"
        )



class LoginAPIView(APIView):

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data["user"]

            # Block citizens who have not verified their email.
            if user.role == "citizen" and not user.is_active:
                return Response(
                    {
                        "message": (
                            "Please verify your email before logging in."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            token, created = Token.objects.get_or_create(user=user)

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

class VerifyTokenAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "valid": True,
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            }
        }, status=status.HTTP_200_OK)

class CitizenProfileAPIView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_citizen(self, request):
        if request.user.role != "citizen":
            return None, Response(
                {
                    "error": "This endpoint is for citizens only."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            citizen = request.user.citizen_profile
        except Citizen.DoesNotExist:
            return None, Response(
                {
                    "error": "Citizen profile not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return citizen, None

    def get(self, request):
        citizen, error_response = self.get_citizen(request)

        if error_response:
            return error_response

        serializer = CitizenProfileSerializer(citizen)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    def put(self, request):
        return self.update_profile(request, partial=False)

    def patch(self, request):
        return self.update_profile(request, partial=True)

    def update_profile(self, request, partial=False):
        citizen, error_response = self.get_citizen(request)

        if error_response:
            return error_response

        serializer = CitizenProfileSerializer(
            citizen,
            data=request.data,
            partial=partial,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class CitizenChangePasswordAPIView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        current_password = request.data.get(
            "current_password", ""
        )
        new_password = request.data.get(
            "new_password", ""
        )
        confirm_password = request.data.get(
            "confirm_password", ""
        )

        # Check required fields
        if not current_password or not new_password or not confirm_password:
            return Response(
                {"error": "All password fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the current password
        if not user.check_password(current_password):
            return Response(
                {"current_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check password confirmation
        if new_password != confirm_password:
            return Response(
                {"confirm_password": ["New passwords do not match."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent reusing the current password
        if user.check_password(new_password):
            return Response(
                {"new_password": [
                    "Your new password must be different from your current password."
                ]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Apply Django's configured password validators
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            return Response(
                {"new_password": error.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save the new password securely
        user.set_password(new_password)
        user.save()

        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip()

        if not email:
            return Response(
                {"message": "Please enter your email address."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Only active mobile-app accounts can request a reset.
        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
            role__in=["citizen", "field_engineer"]
        ).first()

        # Always return the same response so people cannot discover
        # whether an email address has an account.
        generic_response = {
            "message": (
                "If an active InfraTrack account uses that email, "
                "a password reset link will be sent."
            )
        }

        if not user:
            return Response(generic_response, status=status.HTTP_200_OK)

        # Create a signed token containing the user's ID and email.
        reset_token = signing.dumps(
            {
                "user_id": user.pk,
                "email": user.email,
            },
            salt="infratrack-password-reset"
        )

        reset_link = (
            f"infratrack://reset-password?token={reset_token}"
        )

        subject = "InfraTrack Password Reset"

        message = (
            f"Hello {user.first_name or 'InfraTrack user'},\n\n"
            "We received a request to reset your InfraTrack password.\n\n"
            "Open the following link on your device to reset your password:\n\n"
            f"{reset_link}\n\n"
            "This link will expire after 30 minutes.\n\n"
            "If you did not request this password reset, you can ignore "
            "this email. Your password will remain unchanged.\n\n"
            "Regards,\n"
            "InfraTrack Support"
        )

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False
            )
        except Exception:
            # Do not reveal whether the email belongs to an account.
            # Check the Django server logs if email delivery fails.
            pass

        return Response(generic_response, status=status.HTTP_200_OK)


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token", "").strip()
        new_password = request.data.get("new_password", "")
        confirm_password = request.data.get("confirm_password", "")

        if not token or not new_password or not confirm_password:
            return Response(
                {"message": "Please complete all required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_password != confirm_password:
            return Response(
                {"message": "The passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate the signed token and its 30-minute expiration.
        try:
            token_data = signing.loads(
                token,
                salt="infratrack-password-reset",
                max_age=1800
            )
        except signing.SignatureExpired:
            return Response(
                {"message": "This password reset link has expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )
        except signing.BadSignature:
            return Response(
                {"message": "This password reset link is invalid."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find the account associated with the token.
        user = User.objects.filter(
            pk=token_data.get("user_id"),
            email__iexact=token_data.get("email", ""),
            is_active=True,
            role__in=["citizen", "field_engineer"]
        ).first()

        if not user:
            return Response(
                {"message": "This password reset link is invalid or the account is unavailable."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Apply Django's configured password validators.
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            return Response(
                {"message": " ".join(error.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save the new password.
        user.set_password(new_password)
        user.save(update_fields=["password"])

        # Invalidate existing DRF login tokens.
        Token.objects.filter(user=user).delete()

        return Response(
            {
                "message": (
                    "Your password has been reset successfully. "
                    "Please log in using your new password."
                )
            },
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


@login_required
def assign_inspection(request):
    from django.db import transaction
    from django.db.models import Q, OuterRef, Subquery
    from reports.models import (
        IssueReport,
        InspectionAssignment,
        ReportScreening,
    )
    from reports.notifications import notify_users

    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can assign inspection reports."
        )

    # Search and filter values from the GET form
    search_query = request.GET.get("q", "").strip()
    assignment_filter = request.GET.get("assignment", "").strip()

    # Get the latest screening date for each report
    latest_screening = ReportScreening.objects.filter(
        report_id=OuterRef("report_id")
    ).order_by("-screening_date")

    # Show the most recently screened validated reports first
    reports = IssueReport.objects.filter(
        status="Validated"
    ).annotate(
        latest_screening_date=Subquery(
            latest_screening.values("screening_date")[:1]
        )
    ).select_related(
        "citizen"
    ).order_by(
        "-latest_screening_date",
        "-reported_date",
    )

    # Search by report title, location, citizen name, or infrastructure type
    search_filter = (
        Q(title__icontains=search_query)
        | Q(geographic_address__icontains=search_query)
        | Q(citizen__first_name__icontains=search_query)
        | Q(citizen__last_name__icontains=search_query)
        | Q(infrastructure_type__icontains=search_query)
    )

    # Allow exact report ID searches when the query is numeric
    if search_query.isdigit():
        search_filter |= Q(report_id=int(search_query))

    if search_query:
        reports = reports.filter(search_filter)

    # Get report IDs that currently have an active assignment
    active_assignment_ids = InspectionAssignment.objects.filter(
        is_active=True
    ).values_list("report_id", flat=True)

    if assignment_filter == "unassigned":
        reports = reports.exclude(
            report_id__in=active_assignment_ids
        )
    elif assignment_filter == "assigned":
        reports = reports.filter(
            report_id__in=active_assignment_ids
        )

    # Get active Field Engineers
    field_engineers = Personnel.objects.filter(
        position="field_engineer",
        user__is_active=True,
    ).select_related(
        "user"
    ).order_by("user__first_name", "user__last_name")

    if request.method == "POST":
        report_id = request.POST.get("report_id")
        engineer_id = request.POST.get("assigned_field_engineer")
        remarks = request.POST.get("remarks", "").strip()

        if not hasattr(request.user, "personnel"):
            messages.error(
                request,
                "Your account has no personnel record."
            )
            return redirect("assign_inspection")

        report = get_object_or_404(
            IssueReport,
            report_id=report_id,
            status="Validated",
        )

        engineer = get_object_or_404(
            field_engineers,
            pk=engineer_id,
        )

        with transaction.atomic():
            active_assignments = InspectionAssignment.objects.filter(
                report=report,
                is_active=True,
            )

            current_assignment = active_assignments.first()

            if (
                current_assignment
                and current_assignment.assigned_field_engineer_id
                == engineer.pk
            ):
                messages.info(
                    request,
                    "This Field Engineer is already assigned to this report."
                )
                return redirect("assign_inspection")

            active_assignments.update(is_active=False)

            InspectionAssignment.objects.create(
                report=report,
                assigned_field_engineer=engineer,
                assigned_by=request.user.personnel,
                remarks=remarks,
                is_active=True,
            )

        notify_users(
            [engineer.user],
            "inspection_assigned",
            "New inspection assigned",
            f'You have been assigned to inspect "{report.title}".',
            report,
        )

        messages.success(
            request,
            f'Inspection assigned to '
            f'{engineer.user.get_full_name() or engineer.user.username}.'
        )
        return redirect("assign_inspection")

    # Attach each report's current active assignment
    assignments = InspectionAssignment.objects.filter(
        report__in=reports,
        is_active=True,
    ).select_related(
        "assigned_field_engineer__user"
    )

    assignments_by_report = {
        assignment.report_id: assignment
        for assignment in assignments
    }

    for report in reports:
        report.active_inspection_assignment = (
            assignments_by_report.get(report.report_id)
        )

    return render(
        request,
        "users/district/assign_inspection.html",
        {
            "reports": reports,
            "field_engineers": field_engineers,
            "search_query": search_query,
            "assignment_filter": assignment_filter,
        },
    )

@role_required("fru", "district_engineer")
def follow_ups(request):
    from django.db.models import Q
    from reports.models import FollowUpRequest

    status_filter = request.GET.get("status", "Pending")
    search_query = request.GET.get("q", "").strip()

    if status_filter not in ("Pending", "Answered", "All"):
        status_filter = "Pending"

    items = FollowUpRequest.objects.select_related(
        "report",
        "citizen",
        "responded_by__user",
    )

    if status_filter in ("Pending", "Answered"):
        items = items.filter(status=status_filter)

    if search_query:
        search_term = search_query.lstrip("#").strip()

        search_filter = (
            Q(citizen__first_name__icontains=search_query)
            | Q(citizen__last_name__icontains=search_query)
            | Q(citizen__username__icontains=search_query)
            | Q(report__title__icontains=search_query)
            | Q(message__icontains=search_query)
        )

        if search_term.isdigit():
            search_filter |= Q(report__report_id=int(search_term))

        items = items.filter(search_filter)

    if status_filter == "Pending":
        items = items.order_by("submitted_date")
    else:
        items = items.order_by("-submitted_date")

    return render(
        request,
        "users/follow_ups.html",
        {
            "items": items,
            "status_filter": status_filter,
            "search_query": search_query,
            "pending_total": FollowUpRequest.objects.filter(
                status="Pending"
            ).count(),
            "answered_total": FollowUpRequest.objects.filter(
                status="Answered"
            ).count(),
        },
    )

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

@login_required
def feedback_list(request):
    if request.user.role != "district_engineer":
        raise PermissionDenied

    feedbacks = Feedback.objects.all().order_by('-date_created')

    return render(request, 'users/district/feedback_list.html', {
        'feedbacks': feedbacks
    })


@login_required
def personnel_reports(request):
    from datetime import datetime, time, timedelta
    from django.utils import timezone
    from reports.models import (
        ReportScreening,
        InspectionValidation,
        RepairUpdate,
        WorkOrder,
    )
    from .models import Personnel

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can access Personnel Reports."
        )

    today = timezone.localdate()
    first_day = today.replace(day=1)

    # Read date filters. Default: current month.
    start_date_text = request.GET.get(
        "start_date", first_day.isoformat()
    )
    end_date_text = request.GET.get(
        "end_date", today.isoformat()
    )

    try:
        start_date = datetime.strptime(
            start_date_text, "%Y-%m-%d"
        ).date()
        end_date = datetime.strptime(
            end_date_text, "%Y-%m-%d"
        ).date()
    except ValueError:
        start_date = first_day
        end_date = today
        start_date_text = start_date.isoformat()
        end_date_text = end_date.isoformat()

    if start_date > end_date:
        start_date, end_date = end_date, start_date
        start_date_text = start_date.isoformat()
        end_date_text = end_date.isoformat()

    # Convert the selected local dates into timezone-aware datetimes.
    # This avoids relying on MariaDB timezone tables for __date lookups.

    start_datetime = timezone.make_aware(
        datetime.combine(start_date, time.min),
        timezone.get_current_timezone()
    )

    end_datetime = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        timezone.get_current_timezone()
    )

    selected_role = request.GET.get("role", "").strip()
    selected_personnel = request.GET.get("personnel", "").strip()

    personnel_list = Personnel.objects.select_related(
        "user"
    ).filter(
        position__in=["fru", "field_engineer", "district_engineer"]
    ).order_by("user__last_name", "user__first_name")

    events = []

    def add_event(activity_date, person, role, activity, accomplishment):
        if not activity_date:
            return

        if not (start_date <= timezone.localtime(activity_date).date() <= end_date):
            return

        if selected_role and role != selected_role:
            return

        person_id = str(person.pk) if person else ""

        if selected_personnel and person_id != selected_personnel:
            return

        if person:
            full_name = person.user.get_full_name().strip()
            employee_name = full_name or person.user.username
        else:
            employee_name = "Personnel record unavailable"

        role_label = {
            "fru": "FRU Personnel",
            "field_engineer": "Field Engineer",
            "district_engineer": "District Engineer",
        }.get(role, "Unknown")

        events.append({
            "date": activity_date,
            "employee": employee_name,
            "role": role_label,
            "role_value": role,
            "activity": activity,
            "accomplishment": accomplishment,
            "personnel_id": person_id,
            "event_type": activity,
        })

    # 1. FRU screening activities
    screenings = ReportScreening.objects.select_related(
    "screened_by__user", "report"
    ).filter(
        screening_date__gte=start_datetime,
        screening_date__lt=end_datetime,
    )

    for item in screenings:
        person = item.screened_by
        add_event(
            item.screening_date,
            person,
            "fru",
            "Report Screening",
            f'Report #{item.report_id}: {item.screening_result}',
        )

    # 2. Field Engineer inspection activities
    inspections = InspectionValidation.objects.select_related(
    "inspected_by__user", "report"
    ).filter(
        inspection_date__gte=start_datetime,
        inspection_date__lt=end_datetime,
    )

    for item in inspections:
        person = item.inspected_by
        add_event(
            item.inspection_date,
            person,
            "field_engineer",
            "Site Inspection",
            f'Report #{item.report_id}: {item.validation_result}',
        )

    # 3. Field Engineer repair progress updates
    repair_updates = RepairUpdate.objects.select_related(
    "submitted_by__user", "work_order__report"
    ).filter(
        update_date__gte=start_datetime,
        update_date__lt=end_datetime,
    )

    for item in repair_updates:
        person = item.submitted_by
        add_event(
            item.update_date,
            person,
            "field_engineer",
            "Repair Progress Update",
            (
                f'Work Order #{item.work_order_id}: '
                f'{item.status_update}'
            ),
        )

    # 4. Work orders issued by personnel
    work_orders = WorkOrder.objects.select_related(
        "issued_by__user",
        "assigned_field_engineer__user",
        "report",
    )

    issued_orders = work_orders.filter(
        date_issued__gte=start_datetime,
        date_issued__lt=end_datetime,
    )

    for item in issued_orders:
        add_event(
            item.date_issued,
            item.issued_by,
            "district_engineer",
            "Work Order Issued",
            f'Work Order #{item.pk} for Report #{item.report_id}',
        )

    # 5. Work orders completed by the assigned Field Engineer
    completed_orders = work_orders.filter(
        date_completed__gte=start_datetime,
        date_completed__lt=end_datetime,
        date_completed__isnull=False,
    )

    for item in completed_orders:
        add_event(
            item.date_completed,
            item.assigned_field_engineer,
            "field_engineer",
            "Work Order Completed",
            f'Work Order #{item.pk} for Report #{item.report_id}',
        )

    # Sort newest activity first
    events.sort(key=lambda item: item["date"], reverse=True)

    # Summary cards use the filtered activity records.
    total_screenings = sum(
        1 for e in events if e["activity"] == "Report Screening"
    )
    total_inspections = sum(
        1 for e in events if e["activity"] == "Site Inspection"
    )
    total_work_orders = sum(
        1 for e in events
        if e["activity"] in [
            "Work Order Issued",
            "Work Order Completed",
            "Repair Progress Update",
        ]
    )

    personnel_ids = {
        e["personnel_id"] for e in events if e["personnel_id"]
    }

    context = {
        "events": events,
        "personnel_list": personnel_list,
        "start_date": start_date_text,
        "end_date": end_date_text,
        "selected_role": selected_role,
        "selected_personnel": selected_personnel,
        "total_screenings": total_screenings,
        "total_inspections": total_inspections,
        "total_work_orders": total_work_orders,
        "total_personnel": len(personnel_ids),
    }

    return render(
        request,
        "users/district/personnel_reports.html",
        context,
    )
