from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Infrastructure, InfrastructureImage


@login_required
def infrastructure_list(request):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    infrastructures = Infrastructure.objects.prefetch_related(
        "images"
    ).order_by("-infrastructure_id")

    return render(
        request,
        "infrastructure/infrastructure_list.html",
        {"infrastructures": infrastructures},
    )

@login_required
def add_infrastructure(request):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    if request.method == "POST":
        infra_name = request.POST.get("infra_name", "").strip()
        infra_type = request.POST.get("infra_type", "").strip()
        road_classification = request.POST.get(
            "road_classification", ""
        ).strip()
        latitude_input = request.POST.get("latitude", "").strip()
        longitude_input = request.POST.get("longitude", "").strip()
        location_description = request.POST.get(
            "location_description", ""
        ).strip()
        status = request.POST.get("status", "").strip()

        form_data = {
            "infra_name": infra_name,
            "infra_type": infra_type,
            "road_classification": road_classification,
            "latitude": latitude_input,
            "longitude": longitude_input,
            "location_description": location_description,
            "status": status,
        }

        def show_error(message):
            return render(
                request,
                "infrastructure/add_infrastructure.html",
                {
                    "error": message,
                    **form_data,
                },
            )

        if not infra_name:
            return show_error("Infrastructure name is required.")

        valid_types = dict(Infrastructure.INFRA_TYPE_CHOICES)
        if infra_type not in valid_types:
            return show_error("Please select a valid infrastructure type.")

        if not latitude_input or not longitude_input:
            return show_error("Latitude and longitude are required.")

        try:
            latitude = Decimal(latitude_input)
            longitude = Decimal(longitude_input)

            if not latitude.is_finite() or not longitude.is_finite():
                raise InvalidOperation

        except (InvalidOperation, ValueError):
            return show_error(
                "Latitude and longitude must be valid numbers."
            )

        if not Decimal("-90") <= latitude <= Decimal("90"):
            return show_error(
                "Invalid latitude. Enter a value between -90 and 90."
            )

        if not Decimal("-180") <= longitude <= Decimal("180"):
            return show_error(
                "Invalid longitude. Enter a value between -180 and 180."
            )

        # Ensure values fit the model's DecimalField(max_digits=10,
        # decimal_places=7) without database errors.
        if (
            latitude.as_tuple().exponent < -7
            or longitude.as_tuple().exponent < -7
        ):
            return show_error(
                "Coordinates can have a maximum of 7 decimal places."
            )

        if not status:
            return show_error("Status is required.")

        valid_statuses = dict(Infrastructure.STATUS_CHOICES)
        if status not in valid_statuses:
            return show_error("Please select a valid infrastructure status.")

        infrastructure = Infrastructure.objects.create(
            managed_by=request.user.personnel,
            infra_name=infra_name,
            infra_type=infra_type,
            road_classification=road_classification,
            latitude=latitude,
            longitude=longitude,
            location_description=location_description,
            status=status,
        )

        # Save multiple regular infrastructure images.
        for image in request.FILES.getlist("regular_images"):
            InfrastructureImage.objects.create(
                infrastructure=infrastructure,
                image=image,
                image_type="regular",
            )

        # Save multiple satellite images.
        for image in request.FILES.getlist("satellite_images"):
            InfrastructureImage.objects.create(
                infrastructure=infrastructure,
                image=image,
                image_type="satellite",
            )

        messages.success(
            request,
            "Infrastructure added successfully.",
        )
        return redirect("infrastructure_list")

    return render(
        request,
        "infrastructure/add_infrastructure.html",
    )


@login_required
def edit_infrastructure(request, infrastructure_id):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can edit infrastructure."
        )

    infrastructure = get_object_or_404(
        Infrastructure,
        infrastructure_id=infrastructure_id,
    )

    if request.method == "POST":
        infra_name = request.POST.get("infra_name", "").strip()
        infra_type = request.POST.get("infra_type", "").strip()
        road_classification = request.POST.get(
            "road_classification", ""
        ).strip()
        latitude_input = request.POST.get("latitude", "").strip()
        longitude_input = request.POST.get("longitude", "").strip()
        location_description = request.POST.get(
            "location_description", ""
        ).strip()
        status = request.POST.get("status", "").strip()

        form_data = {
            "infra_name": infra_name,
            "infra_type": infra_type,
            "road_classification": road_classification,
            "latitude": latitude_input,
            "longitude": longitude_input,
            "location_description": location_description,
            "status": status,
        }

        def show_error(message):
            return render(
                request,
                "infrastructure/edit_infrastructure.html",
                {
                    "error": message,
                    "infrastructure": infrastructure,
                    **form_data,
                },
            )

        if not infra_name:
            return show_error("Infrastructure name is required.")

        if infra_type not in dict(Infrastructure.INFRA_TYPE_CHOICES):
            return show_error("Please select a valid infrastructure type.")

        if not latitude_input or not longitude_input:
            return show_error("Latitude and longitude are required.")

        try:
            latitude = Decimal(latitude_input)
            longitude = Decimal(longitude_input)

            if not latitude.is_finite() or not longitude.is_finite():
                raise InvalidOperation

        except (InvalidOperation, ValueError):
            return show_error(
                "Latitude and longitude must be valid numbers."
            )

        if not Decimal("-90") <= latitude <= Decimal("90"):
            return show_error(
                "Invalid latitude. Enter a value between -90 and 90."
            )

        if not Decimal("-180") <= longitude <= Decimal("180"):
            return show_error(
                "Invalid longitude. Enter a value between -180 and 180."
            )

        if (
            latitude.as_tuple().exponent < -7
            or longitude.as_tuple().exponent < -7
        ):
            return show_error(
                "Coordinates can have a maximum of 7 decimal places."
            )

        if status not in dict(Infrastructure.STATUS_CHOICES):
            return show_error("Please select a valid infrastructure status.")

        infrastructure.infra_name = infra_name
        infrastructure.infra_type = infra_type
        infrastructure.road_classification = road_classification
        infrastructure.latitude = latitude
        infrastructure.longitude = longitude
        infrastructure.location_description = location_description
        infrastructure.status = status
        infrastructure.save()

        # Append new images without deleting existing ones.
        for image in request.FILES.getlist("regular_images"):
            InfrastructureImage.objects.create(
                infrastructure=infrastructure,
                image=image,
                image_type="regular",
            )

        for image in request.FILES.getlist("satellite_images"):
            InfrastructureImage.objects.create(
                infrastructure=infrastructure,
                image=image,
                image_type="satellite",
            )

        messages.success(
            request,
            "Infrastructure updated successfully.",
        )
        return redirect("infrastructure_list")

    return render(
        request,
        "infrastructure/edit_infrastructure.html",
        {"infrastructure": infrastructure},
    )


@login_required
def view_infrastructure(request, infrastructure_id):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view infrastructure details."
        )

    infrastructure = get_object_or_404(
        Infrastructure.objects.prefetch_related("images"),
        infrastructure_id=infrastructure_id,
    )

    return render(
        request,
        "infrastructure/view_infrastructure.html",
        {
            "infrastructure": infrastructure,
            "regular_images": infrastructure.images.filter(
                image_type="regular"
            ),
            "satellite_images": infrastructure.images.filter(
                image_type="satellite"
            ),
        },
    )


@login_required
def delete_infrastructure(request, infrastructure_id):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    if request.method == "POST":
        infrastructure = get_object_or_404(
            Infrastructure,
            infrastructure_id=infrastructure_id,
        )
        infrastructure.delete()

        messages.success(
            request,
            "Infrastructure deleted successfully.",
        )
        return redirect("infrastructure_list")

    return redirect("infrastructure_list")


@login_required
def map(request):
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view the map."
        )

    infrastructures = Infrastructure.objects.prefetch_related(
        "images"
    ).all()

    infrastructure_data = []

    for item in infrastructures:
        regular_images = []
        satellite_images = []

        for image in item.images.all():
            if not image.image:
                continue

            image_data = {
                "url": image.image.url,
            }

            if image.image_type == "regular":
                regular_images.append(image_data)

            elif image.image_type == "satellite":
                satellite_images.append(image_data)

        infrastructure_data.append({
            "infrastructure_id": item.infrastructure_id,
            "infra_name": item.infra_name,
            "infra_type": item.infra_type,
            "road_classification": item.road_classification,
            "location_description": item.location_description,
            "status": item.status,
            "latitude": str(item.latitude),
            "longitude": str(item.longitude),
            "regular_images": regular_images,
            "satellite_images": satellite_images,
        })

    return render(
        request,
        "infrastructure/map.html",
        {"infrastructure_data": infrastructure_data},
    )




@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mobile_infrastructure_list(request):
    if request.user.role != "citizen":
        return Response(
            {"detail": "Only citizens can access this endpoint."},
            status=403,
        )

    infrastructures = (
        Infrastructure.objects
        .filter(status="active")
        .prefetch_related("images")
        .order_by("infra_name")
    )

    data = []

    for item in infrastructures:
        regular_images = []
        satellite_images = []

        for image in item.images.all():
            if not image.image:
                continue

            image_url = request.build_absolute_uri(image.image.url)

            if image.image_type == "regular":
                regular_images.append(image_url)
            elif image.image_type == "satellite":
                satellite_images.append(image_url)

        data.append({
            "infrastructure_id": item.infrastructure_id,
            "infra_name": item.infra_name,
            "infra_type": item.infra_type,
            "road_classification": item.road_classification,
            "location_description": item.location_description,
            "latitude": str(item.latitude),
            "longitude": str(item.longitude),
            "status": item.status,
            "regular_images": regular_images,
            "satellite_images": satellite_images,
        })

    return Response(data)
