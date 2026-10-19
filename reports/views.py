
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from .models import InspectionAssignment


from .models import (
    IssueReport,
    ReportPhoto,
    InspectionPhoto,
    WorkOrder,
    RepairUpdate,
    RepairUpdatePhoto,
    InfoRequest,
    Notification,
    Feedback,
    FollowUpRequest,
    ReportScreening,
    InspectionValidation,
)

from .serializers import (
    IssueReportSerializer,
    WorkOrderSerializer,
    RepairUpdateSerializer,
    NotificationSerializer,
    FeedbackSerializer,
    FollowUpRequestSerializer,
    MyInspectionSerializer,
)

from .notifications import notify_users, notify_role


# =========================================================
# ISSUE REPORTS
# =========================================================

class IssueReportCreateView(generics.CreateAPIView):
    """Citizen: submit a new infrastructure issue report."""

    queryset = IssueReport.objects.all()
    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        if self.request.user.role != 'citizen':
            raise PermissionDenied(
                'Only citizens can submit reports.'
            )

        report = serializer.save(citizen=self.request.user)

        for key in self.request.FILES:
            if key.startswith('photo_'):
                ReportPhoto.objects.create(
                    report=report,
                    file_path=self.request.FILES[key],
                    photo_type='Initial Report',
                )

        notify_role(
            'fru',
            'report_submitted',
            'New report submitted',
            f'"{report.title}" is waiting for screening.',
            report,
        )


class IssueReportListView(generics.ListAPIView):
    """List reports according to the user's role."""

    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role == 'citizen':
            return IssueReport.objects.filter(
                citizen=user
            ).order_by('-reported_date')

        if user.role in ('fru', 'field_engineer', 'district_engineer'):
            return IssueReport.objects.all().order_by('-reported_date')

        return IssueReport.objects.none()


class MyIssueReportListView(generics.ListAPIView):
    """Citizen: list only their own reports."""

    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role != 'citizen':
            return IssueReport.objects.none()

        return (
            IssueReport.objects
            .filter(citizen=self.request.user)
            .select_related('infrastructure')
            .prefetch_related(
                'photos',
                'screenings',
                'inspection_photos',
                'inspection_validations',
                'info_requests',
                'follow_ups',
                'work_order__repair_updates__photos',
            )
            .order_by('-reported_date')
        )



class ValidatedIssueReportListView(generics.ListAPIView):
    """Field Engineer: list assigned reports with assignment details."""

    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role != 'field_engineer':
            return IssueReport.objects.none()

        if not hasattr(user, 'personnel'):
            return IssueReport.objects.none()

        assigned_report_ids = InspectionAssignment.objects.filter(
            assigned_field_engineer=user.personnel,
            is_active=True,
        ).values_list('report_id', flat=True)

        return IssueReport.objects.filter(
            report_id__in=assigned_report_ids,
            status='Validated',
        ).order_by('-reported_date')

    def list(self, request, *args, **kwargs):
        user = request.user

        if user.role != 'field_engineer':
            raise PermissionDenied(
                'Only field engineers can view assigned inspection reports.'
            )

        if not hasattr(user, 'personnel'):
            raise PermissionDenied(
                'Your account has no personnel record.'
            )

        reports = self.get_queryset()
        data = self.get_serializer(reports, many=True).data

        active_assignments = InspectionAssignment.objects.filter(
            assigned_field_engineer=user.personnel,
            is_active=True,
            report_id__in=reports.values_list('report_id', flat=True),
        ).select_related(
            'assigned_by__user',
        )

        assignment_by_report = {
            assignment.report_id: assignment
            for assignment in active_assignments
        }

        for report_data in data:
            report_id = report_data['report_id']
            assignment = assignment_by_report.get(report_id)

            report_data['inspection_assignment'] = None

            if assignment:
                assigned_by_name = None

                if assignment.assigned_by:
                    assigned_by_name = (
                        assignment.assigned_by.user.get_full_name()
                    )

                report_data['inspection_assignment'] = {
                    'id': assignment.id,
                    'assigned_date': assignment.assigned_date,
                    'remarks': assignment.remarks,
                    'assigned_by_name': assigned_by_name,
                }

        return Response(data)




class InspectionAssignmentListView(generics.ListAPIView):
    """District Engineer: list validated reports and their assignments."""

    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role != 'district_engineer':
            return IssueReport.objects.none()

        return IssueReport.objects.filter(
            status='Validated'
        ).order_by('-reported_date')

    def list(self, request, *args, **kwargs):
        if request.user.role != 'district_engineer':
            raise PermissionDenied(
                'Only district engineers can manage inspection assignments.'
            )

        reports = self.get_queryset()
        data = self.get_serializer(reports, many=True).data

        active_assignments = InspectionAssignment.objects.filter(
            report_id__in=reports.values_list('report_id', flat=True),
            is_active=True,
        ).select_related(
            'assigned_field_engineer__user',
            'assigned_by__user',
        )

        assignment_by_report = {
            assignment.report_id: assignment
            for assignment in active_assignments
        }

        result = []

        for report_data in data:
            report_id = report_data['report_id']
            assignment = assignment_by_report.get(report_id)

            report_data['inspection_assignment'] = None

            if assignment:
                engineer = assignment.assigned_field_engineer

                report_data['inspection_assignment'] = {
                    'id': assignment.id,
                    'assigned_field_engineer_id': (
                        engineer.id if engineer else None
                    ),
                    'assigned_field_engineer_name': (
                        engineer.user.get_full_name()
                        if engineer else None
                    ),
                    'assigned_by_id': (
                        assignment.assigned_by_id
                    ),
                    'assigned_date': assignment.assigned_date,
                    'remarks': assignment.remarks,
                }

            result.append(report_data)

        return Response(result)

class AssignInspectionView(APIView):
    """District Engineer: assign or reassign a report for inspection."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        if user.role != 'district_engineer':
            raise PermissionDenied(
                'Only district engineers can assign inspection reports.'
            )

        if not hasattr(user, 'personnel'):
            raise PermissionDenied(
                'Your account has no personnel record.'
            )

        engineer_id = request.data.get('assigned_field_engineer_id')
        remarks = request.data.get('remarks', '').strip()

        if not engineer_id:
            return Response(
                {'error': 'Please select a Field Engineer.'},
                status=400,
            )

        from users.models import Personnel

        try:
            engineer = Personnel.objects.select_related('user').get(
                pk=engineer_id,
                position='field_engineer',
            )
        except (Personnel.DoesNotExist, ValueError, TypeError):
            return Response(
                {'error': 'The selected Field Engineer was not found.'},
                status=400,
            )

        with transaction.atomic():
            report = get_object_or_404(
                IssueReport.objects.select_for_update(),
                report_id=pk,
            )

            if report.status != 'Validated':
                return Response(
                    {
                        'error':
                        'Only validated reports can be assigned for inspection.'
                    },
                    status=400,
                )

            active_assignments = InspectionAssignment.objects.filter(
                report=report,
                is_active=True,
            )

            current_assignment = active_assignments.first()

            if (
                current_assignment
                and current_assignment.assigned_field_engineer_id
                == engineer.id
            ):
                return Response(
                    {
                        'message':
                        'This Field Engineer is already assigned to this report.'
                    },
                    status=200,
                )

            active_assignments.update(is_active=False)

            assignment = InspectionAssignment.objects.create(
                report=report,
                assigned_field_engineer=engineer,
                assigned_by=user.personnel,
                remarks=remarks,
                is_active=True,
            )

        notify_users(
            [engineer.user],
            'inspection_assigned',
            'New inspection assigned',
            f'You have been assigned to inspect "{report.title}".',
            report,
        )

        return Response(
            {
                'message': 'Field Engineer assigned successfully.',
                'report_id': report.report_id,
                'assignment_id': assignment.id,
                'assigned_field_engineer_id': engineer.id,
                'assigned_field_engineer_name': (
                    engineer.user.get_full_name()
                ),
                'assigned_date': assignment.assigned_date,
                'remarks': assignment.remarks,
            },
            status=201,
        )

# =========================================================
# FRU SCREENING
# =========================================================

class SubmitScreeningView(APIView):
    """
    FRU: screen a report and record the screening decision.

    Expected request fields:
    completeness_status: Complete / Incomplete
    duplicate_status: Not Duplicate / Duplicate
    jurisdiction_status: Within Jurisdiction / Outside Jurisdiction
    screening_result: Validated / Needs More Info / Rejected
    remarks: optional screening notes
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        if request.user.role != 'fru':
            return Response(
                {'error': 'Only FRU personnel can screen reports.'},
                status=403,
            )

        if not hasattr(request.user, 'personnel'):
            return Response(
                {'error': 'Your account has no personnel record.'},
                status=403,
            )

        report = get_object_or_404(
            IssueReport,
            pk=pk,
        )

        if report.status not in (
            'Pending Screening',
            'Needs More Info',
        ):
            return Response(
                {'error': 'This report is not waiting for screening.'},
                status=400,
            )

        completeness = request.data.get(
            'completeness_status', 'Complete'
        )
        duplicate = request.data.get(
            'duplicate_status', 'Not Duplicate'
        )
        jurisdiction = request.data.get(
            'jurisdiction_status', 'Within Jurisdiction'
        )
        result = request.data.get('screening_result')
        remarks = request.data.get('remarks', '').strip()

        valid_completeness = [
            'Complete',
            'Incomplete',
        ]
        valid_duplicates = [
            'Not Duplicate',
            'Duplicate',
        ]
        valid_jurisdictions = [
            'Within Jurisdiction',
            'Outside Jurisdiction',
        ]
        valid_results = [
            'Validated',
            'Needs More Info',
            'Rejected',
        ]

        if completeness not in valid_completeness:
            return Response(
                {'error': 'Invalid completeness status.'},
                status=400,
            )

        if duplicate not in valid_duplicates:
            return Response(
                {'error': 'Invalid duplicate status.'},
                status=400,
            )

        if jurisdiction not in valid_jurisdictions:
            return Response(
                {'error': 'Invalid jurisdiction status.'},
                status=400,
            )

        if result not in valid_results:
            return Response(
                {'error': 'Invalid screening result.'},
                status=400,
            )

        # Prevent approving reports that fail screening checks.
        if completeness == 'Incomplete' and result == 'Validated':
            return Response(
                {'error': 'Incomplete reports cannot be validated.'},
                status=400,
            )

        if duplicate == 'Duplicate' and result == 'Validated':
            return Response(
                {'error': 'Duplicate reports cannot be validated.'},
                status=400,
            )

        if (
            jurisdiction == 'Outside Jurisdiction'
            and result == 'Validated'
        ):
            return Response(
                {
                    'error':
                    'Reports outside the jurisdiction cannot be validated.'
                },
                status=400,
            )

        if result == 'Needs More Info' and not remarks:
            return Response(
                {
                    'error':
                    'Please explain what additional information is needed.'
                },
                status=400,
            )

        if result == 'Rejected' and not remarks:
            return Response(
                {
                    'error':
                    'Please provide a reason for rejecting the report.'
                },
                status=400,
            )

        screening = ReportScreening.objects.create(
            report=report,
            screened_by=request.user.personnel,
            completeness_status=completeness,
            duplicate_status=duplicate,
            jurisdiction_status=jurisdiction,
            screening_result=result,
            remarks=remarks,
        )

        report.status = result
        report.save()

        if result == 'Needs More Info':
            InfoRequest.objects.create(
                report=report,
                requested_by=request.user.personnel,
                request_message=remarks,
            )

        notify_users(
            [report.citizen],
            'report_screened',
            'Report screening update',
            f'Your report "{report.title}" has been screened. '
            f'Status: {result}.',
            report,
        )

        from .serializers import ReportScreeningSerializer

        return Response(
            {
                'message': 'Screening submitted successfully.',
                'report_id': report.report_id,
                'status': report.status,
                'screening': ReportScreeningSerializer(
                    screening
                ).data,
            },
            status=201,
        )


# =========================================================
# FIELD ENGINEER INSPECTION
# =========================================================

class SubmitInspectionView(generics.UpdateAPIView):
    """Field Engineer: submit inspection findings."""

    queryset = IssueReport.objects.all()
    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def update(self, request, *args, **kwargs):
        if request.user.role != 'field_engineer':
            return Response(
                {
                    'error':
                    'Only field engineers can submit inspections.'
                },
                status=403,
            )

        if not hasattr(request.user, 'personnel'):
            return Response(
                {'error': 'Your account has no personnel record.'},
                status=403,
            )

        report = self.get_object()

        if not InspectionAssignment.objects.filter(
            report=report,
            assigned_field_engineer=request.user.personnel,
            is_active=True,
        ).exists():
            return Response(
                {
                    'error': 'This report is not currently assigned to you for inspection.'
                },
                status=403,
            )

        if report.status != 'Validated':
            return Response(
                {
                    'error':
                    'This report is not waiting for inspection.'
                },
                status=400,
            )

        validation_result = request.data.get(
            'validation_result', 'Confirmed'
        )

        if validation_result not in ('Confirmed', 'Not Confirmed'):
            return Response(
                {'error': 'Invalid validation result.'},
                status=400,
            )

        severity = request.data.get('severity_rating')

        if severity not in ('Low', 'Medium', 'High'):
            return Response(
                {'error': 'Please select a valid severity rating.'},
                status=400,
            )

        findings = request.data.get(
            'inspection_remarks', ''
        ).strip()

        recommended = request.data.get(
            'recommended_action', ''
        ).strip()

        comments = request.data.get(
            'comments', ''
        ).strip()

        if not findings:
            return Response(
                {'error': 'Please describe your findings.'},
                status=400,
            )

        if validation_result == 'Confirmed' and not recommended:
            return Response(
                {'error': 'Please add a recommended action.'},
                status=400,
            )

        InspectionValidation.objects.create(
            report=report,
            inspected_by=request.user.personnel,
            validation_result=validation_result,
            severity_rating=severity,
            findings=findings,
            recommended_repairs=recommended,
            comments=comments,
        )

        report.status = (
            'Inspected'
            if validation_result == 'Confirmed'
            else 'Not Confirmed'
        )
        report.save()

        for key in request.FILES:
            if key.startswith('inspection_photo_'):
                InspectionPhoto.objects.create(
                    report=report,
                    image=request.FILES[key],
                )

        if validation_result == 'Confirmed':
            notify_role(
                'district_engineer',
                'report_inspected',
                'Inspection completed',
                f'"{report.title}" was inspected and is ready for a work order.',
                report,
            )

            notify_users(
                [report.citizen],
                'report_inspected',
                'Your report was inspected',
                f'A field engineer inspected "{report.title}".',
                report,
            )
        else:
            notify_role(
                'district_engineer',
                'report_not_confirmed',
                'Problem not confirmed',
                f'The field engineer could not confirm the problem in "{report.title}".',
                report,
            )

            notify_users(
                [report.citizen],
                'report_not_confirmed',
                'Problem could not be confirmed',
                f'A field engineer visited the location of "{report.title}" '
                'but could not confirm the problem.',
                report,
            )

        return Response(
            self.get_serializer(report).data
        )


class InspectedReportListView(generics.ListAPIView):
    """District Engineer: list reports ready for work orders."""

    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role != 'district_engineer':
            return IssueReport.objects.none()

        return IssueReport.objects.filter(
            status='Inspected'
        ).order_by('-updated_date')


# =========================================================
# WORK ORDERS
# =========================================================

class CreateWorkOrderView(generics.CreateAPIView):
    """District Engineer: create and assign a work order."""

    queryset = WorkOrder.objects.all()
    serializer_class = WorkOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != 'district_engineer':
            raise PermissionDenied(
                'Only district engineers can create work orders.'
            )

        if not hasattr(user, 'personnel'):
            raise PermissionDenied(
                'Your account has no personnel record.'
            )

        report = serializer.validated_data['report']

        if report.status != 'Inspected':
            raise PermissionDenied(
                'A work order can only be created for an inspected report.'
            )

        if WorkOrder.objects.filter(report=report).exists():
            raise PermissionDenied(
                'A work order already exists for this report.'
            )

        work_order = serializer.save(
            issued_by=user.personnel,
            approved_by=user.personnel,
        )

        report.status = 'Work Order Issued'
        report.save()


class MyWorkOrderListView(generics.ListAPIView):
    """Field Engineer: list work orders assigned to them."""

    serializer_class = WorkOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role != 'field_engineer':
            return WorkOrder.objects.none()

        if not hasattr(user, 'personnel'):
            return WorkOrder.objects.none()

        return WorkOrder.objects.filter(
            assigned_field_engineer=user.personnel
        ).order_by('-date_issued')


class FieldEngineerListView(generics.ListAPIView):
    """District Engineer: list field engineers for assignment."""

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        if request.user.role != 'district_engineer':
            raise PermissionDenied(
                'Only district engineers can view field engineers for assignment.'
            )

        from users.models import Personnel

        engineers = Personnel.objects.filter(
            position='field_engineer'
        ).select_related('user')

        data = [
            {
                'id': engineer.id,
                'name': engineer.user.get_full_name(),
                'employee_id': engineer.employee_id,
            }
            for engineer in engineers
        ]

        return Response(data)


# =========================================================
# REPAIR UPDATES
# =========================================================

class SubmitRepairUpdateView(generics.CreateAPIView):
    """Field Engineer: submit work progress updates."""

    queryset = RepairUpdate.objects.all()
    serializer_class = RepairUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != 'field_engineer':
            raise PermissionDenied(
                'Only field engineers can submit repair updates.'
            )

        if not hasattr(user, 'personnel'):
            raise PermissionDenied(
                'Your account has no personnel record.'
            )

        work_order = serializer.validated_data['work_order']

        if work_order.assigned_field_engineer != user.personnel:
            raise PermissionDenied(
                'This work order is not assigned to you.'
            )

        if work_order.status == 'Completed':
            raise PermissionDenied(
                'This work order has already been completed.'
            )

        repair_update = serializer.save(
            submitted_by=user.personnel
        )

        for key in self.request.FILES:
            if key.startswith('repair_photo_'):
                RepairUpdatePhoto.objects.create(
                    repair_update=repair_update,
                    image=self.request.FILES[key],
                )

        work_order.update_requested = False
        work_order.update_request_message = None
        work_order.update_requested_date = None

        if repair_update.status_update == 'Completed':
            work_order.status = 'Completed'
            work_order.date_completed = timezone.now()

            work_order.report.status = 'Resolved'
            work_order.report.save()

        elif repair_update.status_update == 'In Progress':
            work_order.status = 'In Progress'

            work_order.report.status = 'In Progress'
            work_order.report.save()

        elif repair_update.status_update == 'Not Started':
            # WorkOrder choices use "Issued", not "Not Started".
            work_order.status = 'Issued'

        work_order.save()

        report = work_order.report

        notify_role(
            'district_engineer',
            'repair_update',
            'Repair update submitted',
            f'{repair_update.status_update}: "{report.title}"',
            report,
        )

        if repair_update.status_update == 'Completed':
            notify_users(
                [report.citizen],
                'report_resolved',
                'Your report was resolved',
                f'The repair for "{report.title}" is complete.',
                report,
            )

        elif repair_update.status_update == 'In Progress':
            notify_users(
                [report.citizen],
                'repair_progress',
                'Repair in progress',
                f'Work has started on "{report.title}".',
                report,
            )


# =========================================================
# CITIZEN RESPONSES TO INFORMATION REQUESTS
# =========================================================

class RespondToInfoRequestView(generics.GenericAPIView):
    """Citizen: provide additional information for a report."""

    queryset = IssueReport.objects.all()
    serializer_class = IssueReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        if request.user.role != 'citizen':
            raise PermissionDenied(
                'Only citizens can respond to information requests.'
            )

        report = get_object_or_404(
            IssueReport,
            pk=pk,
            citizen=request.user,
        )

        if report.status != 'Needs More Info':
            return Response(
                {
                    'error':
                    'This report is not waiting for more information.'
                },
                status=400,
            )

        response_message = request.data.get(
            'response_message', ''
        ).strip()

        if not response_message:
            return Response(
                {
                    'error':
                    'Please provide the additional information.'
                },
                status=400,
            )

        info_request = report.info_requests.filter(
            response_date__isnull=True
        ).order_by('-requested_date').first()

        if info_request is None:
            latest_screening = report.screenings.first()

            info_request = InfoRequest.objects.create(
                report=report,
                request_message=(
                    latest_screening.remarks or ''
                    if latest_screening
                    else ''
                ),
            )

        info_request.response_message = response_message
        info_request.response_date = timezone.now()
        info_request.save()

        for key in request.FILES:
            if key.startswith('photo_'):
                ReportPhoto.objects.create(
                    report=report,
                    file_path=request.FILES[key],
                    photo_type='Additional Evidence',
                )

        report.status = 'Pending Screening'
        report.save()

        notify_role(
            'fru',
            'info_provided',
            'Citizen replied',
            f'More information was added to "{report.title}". '
            'It is ready for re-screening.',
            report,
        )

        return Response(
            self.get_serializer(report).data
        )


# =========================================================
# NOTIFICATIONS
# =========================================================

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        )[:300]


class UnreadNotificationCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()

        return Response({'count': count})


class MarkNotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification,
            pk=pk,
            recipient=request.user,
        )

        notification.is_read = True
        notification.save(update_fields=['is_read'])

        return Response({'status': 'ok'})


class MarkAllNotificationsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True)

        return Response({'status': 'ok'})


# =========================================================
# CITIZEN FEEDBACK
# =========================================================

class SubmitFeedbackView(generics.CreateAPIView):
    """Citizen: rate their own resolved report once."""

    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if request.user.role != 'citizen':
            return Response(
                {'error': 'Only citizens can submit feedback.'},
                status=403,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = serializer.validated_data['report']

        if report.citizen != request.user:
            return Response(
                {
                    'error':
                    'You can only give feedback on your own report.'
                },
                status=403,
            )

        if report.status != 'Resolved':
            return Response(
                {
                    'error':
                    'Feedback is only allowed once the report is Resolved.'
                },
                status=400,
            )

        if Feedback.objects.filter(report=report).exists():
            return Response(
                {
                    'error':
                    'Feedback was already submitted for this report.'
                },
                status=400,
            )

        serializer.save(user=request.user)

        return Response(serializer.data, status=201)


# =========================================================
# CITIZEN FOLLOW-UPS
# =========================================================

class SubmitFollowUpView(generics.CreateAPIView):
    """Citizen: ask for an update on their own report."""

    queryset = FollowUpRequest.objects.all()
    serializer_class = FollowUpRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if request.user.role != 'citizen':
            return Response(
                {'error': 'Only citizens can send follow-ups.'},
                status=403,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = serializer.validated_data['report']

        if report.citizen != request.user:
            return Response(
                {
                    'error':
                    'You can only follow up on your own report.'
                },
                status=403,
            )

        if report.follow_ups.filter(status='Pending').exists():
            return Response(
                {
                    'error':
                    'You already have a pending follow-up on this report. '
                    'Please wait for a reply.'
                },
                status=400,
            )

        serializer.save(citizen=request.user)

        for role in ('fru', 'district_engineer'):
            notify_role(
                role,
                'follow_up',
                'Citizen follow-up',
                f'A citizen asked for an update on "{report.title}".',
                report,
            )

        return Response(serializer.data, status=201)


# =========================================================
# FIELD ENGINEER INSPECTION HISTORY
# =========================================================

class MyInspectionListView(generics.ListAPIView):
    """Field Engineer: list inspections submitted by the current user."""

    serializer_class = MyInspectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role != 'field_engineer':
            return InspectionValidation.objects.none()

        if not hasattr(user, 'personnel'):
            return InspectionValidation.objects.none()

        return InspectionValidation.objects.filter(
            inspected_by=user.personnel
        ).select_related(
            'report',
            'inspected_by__user',
        ).prefetch_related(
            'report__inspection_photos',
        ).order_by('-inspection_date')
