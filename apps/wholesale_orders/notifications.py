from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.retail_orders.notifications import (
    NotificationBatchResult,
    NotificationDeliveryError,
    NotificationDeliveryOutcome,
    NotificationMessage,
)

from .models import (
    WholesaleOrder,
    WholesaleOrderNotificationEvent,
)


SUBJECTS = {
    WholesaleOrderNotificationEvent
    .EventType.PAYMENT_CONFIRMED: "Wholesale payment confirmed",
    WholesaleOrderNotificationEvent
    .EventType.PAYMENT_FAILED: "Wholesale payment failed",
    WholesaleOrderNotificationEvent
    .EventType.PROCESSING: "Wholesale order processing",
    WholesaleOrderNotificationEvent
    .EventType.SHIPPED: "Wholesale order shipped",
    WholesaleOrderNotificationEvent
    .EventType.DELIVERED: "Wholesale order delivered",
    WholesaleOrderNotificationEvent
    .EventType.CANCELLED: "Wholesale order cancelled",
    WholesaleOrderNotificationEvent
    .EventType.REFUNDED: "Wholesale refund completed",
}


@transaction.atomic
def queue_wholesale_order_notification(
    *,
    order,
    event_type,
    payload=None,
):
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .get(pk=order.pk)
    )

    payload = dict(payload or {})
    recipients = []

    invoice_email = str(
        order.business_snapshot.get("invoice_email")
        or ""
    ).strip()

    phone_number = str(
        order.business_snapshot.get("phone_number")
        or ""
    ).strip()

    if invoice_email:
        recipients.append(
            (
                WholesaleOrderNotificationEvent
                .Channel.EMAIL,
                invoice_email,
            )
        )

    if phone_number:
        recipients.append(
            (
                WholesaleOrderNotificationEvent
                .Channel.SMS,
                phone_number,
            )
        )

    events = []

    for channel, recipient in recipients:
        event, _created = (
            WholesaleOrderNotificationEvent.objects
            .get_or_create(
                order=order,
                event_type=event_type,
                channel=channel,
                defaults={
                    "recipient": recipient,
                    "payload": payload,
                },
            )
        )
        events.append(event)

    return tuple(events)


def _context(event):
    return {
        "event": event,
        "event_type": event.event_type,
        "order": event.order,
        "payload": event.payload or {},
    }


def render_wholesale_email(event):
    prefix = SUBJECTS.get(
        event.event_type,
        "Wholesale order update",
    )

    return NotificationMessage(
        subject=(
            f"{prefix} — {event.order.order_number}"
        ),
        text=render_to_string(
            "wholesale_orders/notifications/email.txt",
            _context(event),
        ).strip(),
        html=render_to_string(
            "wholesale_orders/notifications/email.html",
            _context(event),
        ).strip(),
    )


def render_wholesale_sms(event):
    return NotificationMessage(
        subject="",
        text=render_to_string(
            "wholesale_orders/notifications/sms.txt",
            _context(event),
        ).strip(),
    )


def _load_backend(setting_name):
    backend_class = import_string(
        getattr(settings, setting_name)
    )
    return backend_class()


@transaction.atomic
def deliver_wholesale_notification(
    *,
    event,
    email_backend=None,
    sms_backend=None,
):
    event = (
        WholesaleOrderNotificationEvent.objects
        .select_for_update(of=("self",))
        .select_related(
            "order",
            "order__wholesale_account",
            "order__wholesale_account__user",
        )
        .get(pk=event.pk)
    )

    if event.status in {
        WholesaleOrderNotificationEvent.Status.SENT,
        WholesaleOrderNotificationEvent.Status.CANCELLED,
    }:
        return NotificationDeliveryOutcome(
            event_id=event.pk,
            status=event.status,
            sent=False,
            skipped=True,
        )

    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )

    if event.attempt_count >= maximum_attempts:
        event.status = (
            WholesaleOrderNotificationEvent.Status.FAILED
        )

        if not event.last_error:
            event.last_error = (
                "Maximum notification delivery "
                "attempts reached."
            )

        event.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return NotificationDeliveryOutcome(
            event_id=event.pk,
            status=event.status,
            sent=False,
            skipped=True,
            error=event.last_error,
        )

    event.attempt_count += 1
    event.save(
        update_fields=[
            "attempt_count",
            "updated_at",
        ]
    )

    try:
        if (
            event.channel
            == WholesaleOrderNotificationEvent.Channel.EMAIL
        ):
            backend = (
                email_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_EMAIL_BACKEND"
                )
            )
            message = render_wholesale_email(event)

        elif (
            event.channel
            == WholesaleOrderNotificationEvent.Channel.SMS
        ):
            backend = (
                sms_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_SMS_BACKEND"
                )
            )
            message = render_wholesale_sms(event)

        else:
            raise NotificationDeliveryError(
                "unsupported_notification_channel",
                "The notification channel is unsupported.",
            )

        result = backend.send(
            event=event,
            message=message,
        )

    except Exception as exc:
        event.status = (
            WholesaleOrderNotificationEvent.Status.FAILED
        )
        event.last_error = str(exc)[:2000]
        event.save(
            update_fields=[
                "status",
                "last_error",
                "updated_at",
            ]
        )

        return NotificationDeliveryOutcome(
            event_id=event.pk,
            status=event.status,
            sent=False,
            skipped=False,
            error=event.last_error,
        )

    payload = dict(event.payload or {})
    payload["delivery"] = {
        "provider": result.provider,
        "message_id": result.message_id,
        "response": result.response or {},
        "attempt": event.attempt_count,
    }

    event.payload = payload
    event.status = (
        WholesaleOrderNotificationEvent.Status.SENT
    )
    event.last_error = ""
    event.sent_at = timezone.now()
    event.save(
        update_fields=[
            "payload",
            "status",
            "last_error",
            "sent_at",
            "updated_at",
        ]
    )

    return NotificationDeliveryOutcome(
        event_id=event.pk,
        status=event.status,
        sent=True,
        skipped=False,
    )


def process_pending_wholesale_notifications(
    *,
    limit=None,
):
    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )
    batch_size = (
        limit
        if limit is not None
        else settings.RETAIL_NOTIFICATION_BATCH_SIZE
    )

    event_ids = list(
        WholesaleOrderNotificationEvent.objects
        .filter(
            status__in=[
                WholesaleOrderNotificationEvent
                .Status.PENDING,
                WholesaleOrderNotificationEvent
                .Status.FAILED,
            ],
            attempt_count__lt=maximum_attempts,
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:batch_size]
    )

    sent = 0
    failed = 0
    skipped = 0

    for event_id in event_ids:
        event = (
            WholesaleOrderNotificationEvent.objects
            .get(pk=event_id)
        )
        outcome = deliver_wholesale_notification(
            event=event
        )

        if outcome.sent:
            sent += 1
        elif outcome.skipped:
            skipped += 1
        else:
            failed += 1

    return NotificationBatchResult(
        processed=len(event_ids),
        sent=sent,
        failed=failed,
        skipped=skipped,
    )
