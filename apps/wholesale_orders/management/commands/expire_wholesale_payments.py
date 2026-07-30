from django.core.management.base import BaseCommand

from apps.wholesale_orders.services import (
    expire_due_wholesale_payment_attempts,
)


class Command(BaseCommand):
    help = (
        "Expire overdue wholesale payment attempts, "
        "release reservations, and reopen carts."
    )

    def handle(self, *args, **options):
        expired_count = (
            expire_due_wholesale_payment_attempts()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {expired_count} wholesale "
                "payment attempt(s)."
            )
        )
