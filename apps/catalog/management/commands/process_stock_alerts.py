from django.core.management.base import BaseCommand

from apps.catalog.notifications import (
    process_available_stock_alerts,
)


class Command(BaseCommand):
    help = (
        "Deliver active back-in-stock alerts for retail "
        "offers that have become available."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of alerts to process.",
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

        result = process_available_stock_alerts(
            limit=limit
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Processed "
                f"{result.processed} stock alert(s): "
                f"{result.sent} sent, "
                f"{result.failed} failed, "
                f"{result.skipped} skipped."
            )
        )
