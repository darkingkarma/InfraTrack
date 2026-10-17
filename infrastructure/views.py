from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.shortcuts import render, redirect, get_object_or_404
from .models import Infrastructure
from django.contrib import messages

@login_required
def infrastructure_list(request):

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    infrastructures = Infrastructure.objects.all()

    return render(
        request,
        "infrastructure/infrastructure_list.html",
        {
            "infrastructures": infrastructures
        }
    )


@login_required
def add_infrastructure(request):

    # Only District Engineer can add infrastructure
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    if request.method == "POST":

        infra_name = request.POST.get("infra_name")
        infra_type = request.POST.get("infra_type")
        road_classification = request.POST.get("road_classification")
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")
        location_description = request.POST.get("location_description")
        status = request.POST.get("status")

        # Validation

        if not infra_name:
            return render(
                request,
                "infrastructure/add_infrastructure.html",
                {
                    "error": "Infrastructure name is required."
                }
            )

        if not infra_type:
            return render(
                request,
                "infrastructure/add_infrastructure.html",
                {
                    "error": "Infrastructure type is required."
                }
            )

        if not latitude or not longitude:
            return render(
                request,
                "infrastructure/add_infrastructure.html",
                {
                    "error": "Latitude and longitude are required."
                }
            )

        if not status:
            return render(
                request,
                "infrastructure/add_infrastructure.html",
                {
                    "error": "Status is required."
                }
            )

        # Create infrastructure

        Infrastructure.objects.create(
            managed_by=request.user.personnel,
            infra_name=infra_name,
            infra_type=infra_type,
            road_classification=road_classification,
            latitude=latitude,
            longitude=longitude,
            location_description=location_description,
            status=status,
        )

        return redirect("infrastructure_list")

    return render(
        request,
        "infrastructure/add_infrastructure.html"
    )

@login_required
def edit_infrastructure(request, infrastructure_id):

    # Only District Engineer can edit infrastructure
    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can manage infrastructure."
        )

    infrastructure = get_object_or_404(
        Infrastructure,
        infrastructure_id=infrastructure_id
    )

    if request.method == "POST":

        infrastructure.infra_name = request.POST.get("infra_name")
        infrastructure.infra_type = request.POST.get("infra_type")
        infrastructure.road_classification = request.POST.get(
            "road_classification"
        )
        infrastructure.latitude = request.POST.get("latitude")
        infrastructure.longitude = request.POST.get("longitude")
        infrastructure.location_description = request.POST.get(
            "location_description"
        )
        infrastructure.status = request.POST.get("status")

        infrastructure.save()

        return redirect("infrastructure_list")

    return render(
        request,
        "infrastructure/edit_infrastructure.html",
        {
            "infrastructure": infrastructure
        }
    )

@login_required
def view_infrastructure(request, infrastructure_id):

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view infrastructure details."
        )

    infrastructure = get_object_or_404(
        Infrastructure,
        infrastructure_id=infrastructure_id
    )

    return render(
        request,
        "infrastructure/view_infrastructure.html",
        {
            "infrastructure": infrastructure
        }
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
            infrastructure_id=infrastructure_id
        )

        infrastructure.delete()

        messages.success(
            request,
            "Infrastructure deleted successfully."
        )

        return redirect("infrastructure_list")

    return redirect("infrastructure_list")

@login_required
def map(request):

    if request.user.role != "district_engineer":
        return HttpResponseForbidden(
            "Only District Engineer can view the map."
        )

    infrastructure_data = list(
        Infrastructure.objects.values(
            "infrastructure_id",
            "infra_name",
            "infra_type",
            "latitude",
            "longitude",
            "location_description",
        )
    )

    return render(
        request,
        "infrastructure/map.html",
        {
            "infrastructure_data": infrastructure_data
        }
    )



from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Infrastructure

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mobile_infrastructure_list(request):
    if request.user.role != "citizen":
        return Response(
            {"detail": "Only citizens can access this endpoint."},
            status=403,
        )

    infrastructures = Infrastructure.objects.filter(
        status="active"
    ).order_by("infra_name")

    data = [
        {
            "infrastructure_id": item.infrastructure_id,
            "infra_name": item.infra_name,
            "infra_type": item.infra_type,
            "location_description": item.location_description,
            "latitude": str(item.latitude),
            "longitude": str(item.longitude),
            "status": item.status,
        }
        for item in infrastructures
    ]

    return Response(data)
