from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import User, Citizen
import re

User = get_user_model()


class CitizenRegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    contact_number = serializers.CharField(max_length=20)
    address = serializers.CharField()

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False
    )

    def validate_password(self, value):
        errors = []

        if len(value) < 8:
            errors.append(
                "Password must be at least 8 characters long."
            )

        if not re.search(r"[A-Z]", value):
            errors.append(
                "Password must contain at least one uppercase letter."
            )

        if not re.search(r"[a-z]", value):
            errors.append(
                "Password must contain at least one lowercase letter."
            )

        if not re.search(r"[0-9]", value):
            errors.append(
                "Password must contain at least one number."
            )

        if not re.search(r"[^A-Za-z0-9]", value):
            errors.append(
                "Password must contain at least one special character."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Username is already taken."
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "Email is already registered."
            )
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")

        password = validated_data.pop("password")
        contact_number = validated_data.pop("contact_number")
        address = validated_data.pop("address")

        user = User.objects.create_user(
            **validated_data,
            password=password,
            role="citizen"
        )

        Citizen.objects.create(
            user=user,
            contact_number=contact_number,
            address=address
        )

        return user

class LoginSerializer(serializers.Serializer):
    username_or_email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username_or_email = data["username_or_email"]
        password = data["password"]

        user = User.objects.filter(
            email=username_or_email
        ).first()

        if user is None:
            user = User.objects.filter(
                username=username_or_email
            ).first()

        if user is None or not user.check_password(password):
            raise serializers.ValidationError(
                "Invalid username/email or password."
            )

        if user.role not in ["citizen", "field_engineer"]:
            raise serializers.ValidationError(
                "This login is for citizens and field engineers only."
            )

        data["user"] = user
        return data


class CitizenProfileSerializer(serializers.ModelSerializer):

    first_name = serializers.CharField(
        source="user.first_name",
        required=False,
        allow_blank=True,
    )

    last_name = serializers.CharField(
        source="user.last_name",
        required=False,
        allow_blank=True,
    )

    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    email = serializers.EmailField(
        source="user.email",
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Citizen
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "contact_number",
            "address",
        ]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})

        # Update the related Django User fields.
        user = instance.user

        for field, value in user_data.items():
            setattr(user, field, value)

        if user_data:
            user.save()

        # Update the Citizen profile fields.
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        return instance
