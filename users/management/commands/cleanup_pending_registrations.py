
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import PendingCitizenRegistration


class Command(BaseCommand):
    help = "Delete pending citizen registrations older than 24 hours."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=24)

        deleted_count, _ = (
            PendingCitizenRegistration.objects
            .filter(created_at__lt=cutoff)
            .delete()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup completed. Deleted {deleted_count} old record(s)."
            )
        )
