from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ("district_engineer", "District Engineer"),
        ("fru", "FRU Personnel"),
        ("field_engineer", "Field Engineer"),
        ("citizen", "Citizen"),
    ]

    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    REQUIRED_FIELDS = ["email", "role"]

    def __str__(self):
        return self.username


class Personnel(models.Model):

    POSITION_CHOICES = [
        ("district_engineer", "District Engineer"),
        ("fru", "FRU Personnel"),
        ("field_engineer", "Field Engineer"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    employee_id = models.CharField(
        max_length=20,
        unique=True
    )

    contact_number = models.CharField(
        max_length=20
    )

    address = models.TextField(
        blank=True
    )

    position = models.CharField(
        max_length=30,
        choices=POSITION_CHOICES
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"

class Citizen(models.Model):

    citizen_id = models.AutoField(
        primary_key=True
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="citizen_profile"
    )

    contact_number = models.CharField(
        max_length=20
    )

    address = models.TextField()

    date_created = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.user.get_full_name()


class PendingCitizenRegistration(models.Model):
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    username = models.CharField(max_length=150)
    email = models.EmailField()
    contact_number = models.CharField(max_length=20)
    address = models.TextField()
    password_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
