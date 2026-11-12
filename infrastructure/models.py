from django.db import models
from users.models import Personnel
# Create your models here.
class Infrastructure(models.Model):

    INFRA_TYPE_CHOICES = [
        ("road", "Road"),
        ("bridge", "Bridge"),
        ("drainage", "Drainage"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("maintenance", "Maintenance"),
        ("closed", "Closed"),
    ]

    infrastructure_id = models.AutoField(
        primary_key=True
    )

    managed_by = models.ForeignKey(
        Personnel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_infrastructures"
    )

    infra_name = models.CharField(
        max_length=255
    )

    infra_type = models.CharField(
        max_length=55,
        choices=INFRA_TYPE_CHOICES
    )

    road_classification = models.CharField(
        max_length=255,
        blank=True
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7
    )

    location_description = models.CharField(
        max_length=255,
        blank=True
    )

    status = models.CharField(
        max_length=255,
        choices=STATUS_CHOICES,
        default="active"
    )

    date_added = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.infra_name



class InfrastructureImage(models.Model):

    IMAGE_TYPE_CHOICES = [
        ("regular", "Infrastructure Image"),
        ("satellite", "Satellite Image"),
    ]

    image_id = models.AutoField(
        primary_key=True
    )

    infrastructure = models.ForeignKey(
        Infrastructure,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="infrastructure/images/"
    )

    image_type = models.CharField(
        max_length=20,
        choices=IMAGE_TYPE_CHOICES
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.infrastructure.infra_name} - "
            f"{self.get_image_type_display()}"
        )
