from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.retail_orders.notifications import (
    NotificationBackendResult,
    NotificationBatchResult,
    NotificationDeliveryOutcome,
    NotificationMessage,
)

from .models import (
    ProductDesign,
    ProductOffer,
    ProductStockAlert,
    ProductVariant,
)


@dataclass(frozen=True)
class StockAlertDeliveryEnvelope:
    pk: int
    recipient: str


def _load_backend(setting_name):
    backend_path = getattr(settings, setting_name)
    backend_class = import_string(backend_path)
    return backend_class()


def _notification_context(alert):
    return {
        "alert": alert,
        "offer": alert.offer,
        "variant": alert.offer.variant,
        "design": alert.offer.variant.design,
    }


def render_stock_alert_email(alert):
    return NotificationMessage(
        subject=(
            f"Back in stock — "
            f"{alert.offer.variant.design.name}"
        ),
        text=render_to_string(
            "catalog/notifications/stock_alert_email.txt",
            _notification_context(alert),
        ).strip(),
        html=render_to_string(
            "catalog/notifications/stock_alert_email.html",
            _notification_context(alert),
        ).strip(),
    )


def render_stock_alert_sms(alert):
    return NotificationMessage(
        subject="",
        text=render_to_string(
            "catalog/notifications/stock_alert_sms.txt",
            _notification_context(alert),
        ).strip(),
    )


def available_stock_alerts():
    """
    Return active alerts whose offers are currently purchasable.

    This mirrors ProductOffer.effective_status at the database level.
    """
    return (
        ProductStockAlert.objects
        .filter(
            status=ProductStockAlert.Status.ACTIVE,
            offer__is_active=True,
            offer__status=ProductOffer.Status.AVAILABLE,
            offer__variant__is_active=True,
            offer__variant__design__status=(
                ProductDesign.Status.ACTIVE
            ),
        )
        .filter(
            Q(
                offer__variant__stock_mode=(
                    ProductVariant.StockMode.QUANTITY
                ),
                offer__variant__stock_quantity__gt=0,
            )
            | Q(
                offer__variant__stock_mode=(
                    ProductVariant.StockMode.STATUS_ONLY
                ),
                offer__variant__manual_stock_status=(
                    ProductVariant.StockStatus.AVAILABLE
                ),
            )
        )
    )


@transaction.atomic
def deliver_stock_alert(
    *,
    alert,
    email_backend=None,
    sms_backend=None,
):
    """
    Deliver one available stock alert exactly once.

    Delivery-state updates intentionally use QuerySet.update().
    ProductStockAlert.save() performs customer-facing validation
    that only applies when an alert is requested for an unavailable
    product. Once stock returns, the worker must still be able to
    update attempts and mark the existing alert as notified.
    """
    alert = (
        ProductStockAlert.objects
        .select_for_update(of=("self",))
        .select_related(
            "user",
            "offer",
            "offer__variant",
            "offer__variant__colour",
            "offer__variant__design",
            "offer__variant__design__brand",
        )
        .get(pk=alert.pk)
    )

    if alert.status in {
        ProductStockAlert.Status.NOTIFIED,
        ProductStockAlert.Status.CANCELLED,
        ProductStockAlert.Status.FAILED,
    }:
        return NotificationDeliveryOutcome(
            event_id=alert.pk,
            status=alert.status,
            sent=False,
            skipped=True,
        )

    if alert.status != ProductStockAlert.Status.ACTIVE:
        return NotificationDeliveryOutcome(
            event_id=alert.pk,
            status=alert.status,
            sent=False,
            skipped=True,
        )

    if (
        alert.offer.effective_status
        != ProductOffer.Status.AVAILABLE
    ):
        return NotificationDeliveryOutcome(
            event_id=alert.pk,
            status=alert.status,
            sent=False,
            skipped=True,
        )

    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )

    if alert.attempt_count >= maximum_attempts:
        error_message = (
            alert.last_error
            or "Maximum stock-alert delivery attempts reached."
        )
        now = timezone.now()

        ProductStockAlert.objects.filter(
            pk=alert.pk
        ).update(
            status=ProductStockAlert.Status.FAILED,
            last_error=error_message,
            updated_at=now,
        )

        alert.status = ProductStockAlert.Status.FAILED
        alert.last_error = error_message

        return NotificationDeliveryOutcome(
            event_id=alert.pk,
            status=alert.status,
            sent=False,
            skipped=True,
            error=alert.last_error,
        )

    alert.attempt_count += 1
    attempt_updated_at = timezone.now()

    ProductStockAlert.objects.filter(
        pk=alert.pk
    ).update(
        attempt_count=alert.attempt_count,
        updated_at=attempt_updated_at,
    )

    envelope = StockAlertDeliveryEnvelope(
        pk=alert.pk,
        recipient=alert.destination,
    )

    try:
        if alert.channel == ProductStockAlert.Channel.EMAIL:
            backend = (
                email_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_EMAIL_BACKEND"
                )
            )
            message = render_stock_alert_email(alert)

        elif alert.channel == ProductStockAlert.Channel.SMS:
            backend = (
                sms_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_SMS_BACKEND"
                )
            )
            message = render_stock_alert_sms(alert)

        else:
            raise RuntimeError(
                "Unsupported stock-alert delivery channel."
            )

        result: NotificationBackendResult = backend.send(
            event=envelope,
            message=message,
        )

    except Exception as exc:
        error_message = str(exc)[:2000]
        new_status = (
            ProductStockAlert.Status.FAILED
            if alert.attempt_count >= maximum_attempts
            else ProductStockAlert.Status.ACTIVE
        )
        now = timezone.now()

        ProductStockAlert.objects.filter(
            pk=alert.pk
        ).update(
            status=new_status,
            attempt_count=alert.attempt_count,
            last_error=error_message,
            updated_at=now,
        )

        alert.status = new_status
        alert.last_error = error_message

        return NotificationDeliveryOutcome(
            event_id=alert.pk,
            status=alert.status,
            sent=False,
            skipped=False,
            error=alert.last_error,
        )

    delivery_payload = {
        **(alert.delivery_payload or {}),
        "provider": result.provider,
        "message_id": result.message_id,
        "response": result.response or {},
        "attempt": alert.attempt_count,
    }
    notified_at = timezone.now()

    ProductStockAlert.objects.filter(
        pk=alert.pk
    ).update(
        delivery_payload=delivery_payload,
        status=ProductStockAlert.Status.NOTIFIED,
        last_error="",
        notified_at=notified_at,
        updated_at=notified_at,
    )

    alert.delivery_payload = delivery_payload
    alert.status = ProductStockAlert.Status.NOTIFIED
    alert.last_error = ""
    alert.notified_at = notified_at

    return NotificationDeliveryOutcome(
        event_id=alert.pk,
        status=alert.status,
        sent=True,
        skipped=False,
    )


def process_available_stock_alerts(*, limit=None):
    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )
    batch_size = (
        limit
        if limit is not None
        else settings.RETAIL_NOTIFICATION_BATCH_SIZE
    )

    alert_ids = list(
        available_stock_alerts()
        .filter(
            attempt_count__lt=maximum_attempts,
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:batch_size]
    )

    sent = 0
    failed = 0
    skipped = 0

    for alert_id in alert_ids:
        alert = ProductStockAlert.objects.get(
            pk=alert_id
        )
        outcome = deliver_stock_alert(alert=alert)

        if outcome.sent:
            sent += 1
        elif outcome.skipped:
            skipped += 1
        else:
            failed += 1

    return NotificationBatchResult(
        processed=len(alert_ids),
        sent=sent,
        failed=failed,
        skipped=skipped,
    )
