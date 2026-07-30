from django.core.management.base import BaseCommand

from apps.wholesale_orders.notifications import (
    process_pending_wholesale_notifications,
)


class Command(BaseCommand):
    help = (
        "Deliver pending and retryable wholesale "
        "order email/SMS notifications."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            help=(
                "Maximum number of notification events "
                "to process."
            ),
        )

    def handle(self, *args, **options):
        limit = options.get("limit")

        if limit is not None and limit < 1:
            self.stderr.write(
                self.style.ERROR(
                    "--limit must be greater than zero."
                )
            )
            return

        result = process_pending_wholesale_notifications(
            limit=limit
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Processed "
                f"{result.processed} notification event(s): "
                f"{result.sent} sent, "
                f"{result.failed} failed, "
                f"{result.skipped} skipped."
            )
        )
