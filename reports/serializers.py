
from rest_framework import serializers
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


class ReportPhotoSerializer(serializers.ModelSerializer):
    issue_report_id = serializers.IntegerField(
        source="report_id",
        read_only=True,
    )

    class Meta:
        model = ReportPhoto
        fields = [
            "report_photo_id",
            "issue_report_id",
            "file_path",
            "uploaded_date",
            "photo_type",
        ]


class InspectionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionPhoto
        fields = ["id", "image", "uploaded_at"]


class RepairUpdatePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepairUpdatePhoto
        fields = ["id", "image", "uploaded_at"]


class RepairUpdateSerializer(serializers.ModelSerializer):
    photos = RepairUpdatePhotoSerializer(many=True, read_only=True)
    submitted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RepairUpdate
        fields = [
            "id",
            "work_order",
            "submitted_by",
            "submitted_by_name",
            "status_update",
            "progress_remarks",
            "delay_reason",
            "completion_details",
            "update_date",
            "photos",
        ]
        read_only_fields = ["submitted_by", "update_date"]

    def get_submitted_by_name(self, obj):
        if obj.submitted_by:
            return obj.submitted_by.user.get_full_name()
        return None



class WorkOrderSerializer(serializers.ModelSerializer):
    report_title = serializers.CharField(
        source="report.title",
        read_only=True,
    )
    report_id = serializers.IntegerField(
        source="report.report_id",
        read_only=True,
    )
    report_latitude = serializers.FloatField(
        source="report.latitude",
        read_only=True,
        allow_null=True,
    )
    report_longitude = serializers.FloatField(
        source="report.longitude",
        read_only=True,
        allow_null=True,
    )
    report_address = serializers.CharField(
        source="report.geographic_address",
        read_only=True,
        allow_null=True,
    )

    assigned_field_engineer_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    repair_updates = RepairUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "report",
            "report_id",
            "report_title",
            "report_latitude",
            "report_longitude",
            "report_address",
            "assigned_field_engineer",
            "assigned_field_engineer_name",
            "issued_by",
            "approved_by",
            "approved_by_name",
            "work_order_details",
            "status",
            "date_issued",
            "date_completed",
            "update_requested",
            "update_request_message",
            "update_requested_date",
            "repair_updates",
        ]
        read_only_fields = [
            "issued_by",
            "approved_by",
            "date_issued",
            "status",
            "date_completed",
        ]

    def get_assigned_field_engineer_name(self, obj):
        if obj.assigned_field_engineer:
            return obj.assigned_field_engineer.user.get_full_name()
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.user.get_full_name()
        return None


    def get_assigned_field_engineer_name(self, obj):
        if obj.assigned_field_engineer:
            return obj.assigned_field_engineer.user.get_full_name()
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.user.get_full_name()
        return None


class InfoRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()

    class Meta:
        model = InfoRequest
        fields = [
            "id",
            "request_message",
            "requested_by_name",
            "requested_date",
            "response_message",
            "response_date",
        ]

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.user.get_full_name()
        return None


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            "id",
            "report",
            "rating",
            "comment",
            "date_created",
        ]
        read_only_fields = ["id", "date_created"]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError(
                "Rating must be between 1 and 5."
            )
        return value


class FollowUpRequestSerializer(serializers.ModelSerializer):
    responded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FollowUpRequest
        fields = [
            "id",
            "report",
            "message",
            "submitted_date",
            "status",
            "response",
            "responded_by_name",
            "responded_date",
        ]
        read_only_fields = [
            "id",
            "submitted_date",
            "status",
            "response",
            "responded_by_name",
            "responded_date",
        ]

    def get_responded_by_name(self, obj):
        if obj.responded_by:
            return obj.responded_by.user.get_full_name()
        return None

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Please write your question."
            )
        return value.strip()


class ReportScreeningSerializer(serializers.ModelSerializer):
    screened_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportScreening
        fields = [
            "id",
            "screened_by",
            "screened_by_name",
            "completeness_status",
            "duplicate_status",
            "jurisdiction_status",
            "screening_result",
            "remarks",
            "screening_date",
        ]
        read_only_fields = ["screened_by", "screening_date"]

    def get_screened_by_name(self, obj):
        if obj.screened_by:
            return obj.screened_by.user.get_full_name()
        return None


class InspectionValidationSerializer(serializers.ModelSerializer):
    inspected_by_name = serializers.SerializerMethodField()

    class Meta:
        model = InspectionValidation
        fields = [
            "id",
            "validation_result",
            "severity_rating",
            "findings",
            "recommended_repairs",
            "comments",
            "inspected_by_name",
            "inspection_date",
        ]

    def get_inspected_by_name(self, obj):
        if obj.inspected_by:
            return obj.inspected_by.user.get_full_name()
        return None


class MyInspectionSerializer(InspectionValidationSerializer):
    report_id = serializers.IntegerField(
        source="report.report_id",
        read_only=True,
    )
    report_title = serializers.CharField(
        source="report.title",
        read_only=True,
    )
    report_address = serializers.CharField(
        source="report.geographic_address",
        read_only=True,
    )
    report_status = serializers.CharField(
        source="report.status",
        read_only=True,
    )
    photos = serializers.SerializerMethodField()

    class Meta(InspectionValidationSerializer.Meta):
        fields = InspectionValidationSerializer.Meta.fields + [
            "report_id",
            "report_title",
            "report_address",
            "report_status",
            "photos",
        ]

    def get_photos(self, obj):
        request = self.context.get("request")
        urls = []

        for photo in obj.report.inspection_photos.all():
            url = photo.image.url
            urls.append(
                request.build_absolute_uri(url) if request else url
            )

        return urls


class IssueReportSerializer(serializers.ModelSerializer):
    photos = ReportPhotoSerializer(many=True, read_only=True)
    screenings = ReportScreeningSerializer(many=True, read_only=True)
    inspection_photos = InspectionPhotoSerializer(
        many=True,
        read_only=True,
    )
    inspection_validations = InspectionValidationSerializer(
        many=True,
        read_only=True,
    )
    work_order = WorkOrderSerializer(read_only=True, required=False)
    info_requests = InfoRequestSerializer(many=True, read_only=True)
    feedback = FeedbackSerializer(read_only=True)
    follow_ups = FollowUpRequestSerializer(many=True, read_only=True)
    infrastructure_name = serializers.CharField(
        source="infrastructure.infra_name",
        read_only=True,
        allow_null=True,
    )
    class Meta:
        model = IssueReport
        fields = [
            "report_id",
            "citizen",
            "infrastructure",
            "infrastructure_not_listed",
            "infrastructure_type",
            "title",
            "description",
            "latitude",
            "longitude",
            "geographic_address",
            "location_method",
            "status",
            "reported_date",
            "updated_date",
            "photos",
            "screenings",
            "inspection_photos",
            "inspection_validations",
            "work_order",
            "info_requests",
            "feedback",
            "follow_ups",
            "infrastructure_name"
        ]
        read_only_fields = [
            "report_id",
            "citizen",
            "status",
            "reported_date",
            "updated_date",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    report_id = serializers.IntegerField(
        source="report.report_id",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "message",
            "report",
            "report_id",
            "is_read",
            "created_at",
        ]