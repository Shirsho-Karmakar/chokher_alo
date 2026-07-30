from django.core.management.base import BaseCommand

from apps.retail_orders.services import (
    expire_due_online_payment_attempts,
)


class Command(BaseCommand):
    help = (
        "Expire overdue Razorpay payment attempts, release "
        "their stock reservations, and reopen their carts."
    )

    def handle(self, *args, **options):
        expired_count = expire_due_online_payment_attempts()

        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {expired_count} retail payment "
                f"attempt(s)."
            )
        )
