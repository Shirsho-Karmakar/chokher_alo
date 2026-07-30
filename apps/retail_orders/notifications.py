import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import RetailOrderNotificationEvent


logger = logging.getLogger(__name__)


class NotificationDeliveryError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class NotificationMessage:
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True)
class NotificationBackendResult:
    provider: str
    message_id: str | None = None
    response: dict | None = None


@dataclass(frozen=True)
class NotificationDeliveryOutcome:
    event_id: int
    status: str
    sent: bool
    skipped: bool
    error: str | None = None


@dataclass(frozen=True)
class NotificationBatchResult:
    processed: int
    sent: int
    failed: int
    skipped: int


SUBJECTS = {
    RetailOrderNotificationEvent.EventType.PAYMENT_CONFIRMED: (
        "Payment confirmed"
    ),
    RetailOrderNotificationEvent.EventType.PROCESSING: (
        "Your order is being processed"
    ),
    RetailOrderNotificationEvent.EventType.SHIPPED: (
        "Your order has shipped"
    ),
    RetailOrderNotificationEvent.EventType.READY_FOR_PICKUP: (
        "Your order is ready for pickup"
    ),
    RetailOrderNotificationEvent.EventType.DELIVERED: (
        "Your order has been delivered"
    ),
    RetailOrderNotificationEvent.EventType.CANCELLED: (
        "Your order has been cancelled"
    ),
    RetailOrderNotificationEvent.EventType.REFUNDED: (
        "Your refund has been completed"
    ),
}


class DjangoEmailNotificationBackend:
    """
    Deliver email through Django's configured EMAIL_BACKEND.

    Development defaults to Django's console backend.
    """

    def send(
        self,
        *,
        event: RetailOrderNotificationEvent,
        message: NotificationMessage,
    ) -> NotificationBackendResult:
        email = EmailMultiAlternatives(
            subject=message.subject,
            body=message.text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[event.recipient],
        )

        if message.html:
            email.attach_alternative(
                message.html,
                "text/html",
            )

        sent_count = email.send(fail_silently=False)

        if sent_count != 1:
            raise NotificationDeliveryError(
                "email_not_sent",
                "The email backend did not confirm delivery.",
            )

        return NotificationBackendResult(
            provider="django_email",
            response={"sent_count": sent_count},
        )


class DevelopmentSMSNotificationBackend:
    """
    Safe local SMS backend.

    It does not contact an SMS provider. Messages are written to logs.
    """

    def send(
        self,
        *,
        event: RetailOrderNotificationEvent,
        message: NotificationMessage,
    ) -> NotificationBackendResult:
        logger.info(
            "Development SMS recipient=%s event_id=%s message=%s",
            event.recipient,
            event.pk,
            message.text,
        )

        return NotificationBackendResult(
            provider="development_sms",
            message_id=f"dev-sms-{event.pk}",
            response={"logged": True},
        )


def _notification_context(event):
    return {
        "event": event,
        "event_type": event.event_type,
        "order": event.order,
        "payload": event.payload or {},
    }


def render_email_notification(event):
    subject_prefix = SUBJECTS.get(
        event.event_type,
        "Order update",
    )

    subject = (
        f"{subject_prefix} — {event.order.order_number}"
    )
    context = _notification_context(event)

    return NotificationMessage(
        subject=subject,
        text=render_to_string(
            "retail_orders/notifications/email.txt",
            context,
        ).strip(),
        html=render_to_string(
            "retail_orders/notifications/email.html",
            context,
        ).strip(),
    )


def render_sms_notification(event):
    return NotificationMessage(
        subject="",
        text=render_to_string(
            "retail_orders/notifications/sms.txt",
            _notification_context(event),
        ).strip(),
    )


def _load_backend(setting_name):
    backend_path = getattr(settings, setting_name)
    backend_class = import_string(backend_path)
    return backend_class()


@transaction.atomic
def deliver_notification_event(
    *,
    event,
    email_backend=None,
    sms_backend=None,
):
    """
    Lock, deliver, and finalize one notification event.

    A sent or cancelled event is never delivered again.
    """
    event = (
        RetailOrderNotificationEvent.objects
        .select_for_update(of=("self",))
        .select_related(
            "order",
            "order__user",
            "order__store_location",
        )
        .get(pk=event.pk)
    )

    if event.status in {
        RetailOrderNotificationEvent.Status.SENT,
        RetailOrderNotificationEvent.Status.CANCELLED,
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
        event.status = RetailOrderNotificationEvent.Status.FAILED

        if not event.last_error:
            event.last_error = (
                "Maximum notification delivery attempts reached."
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
            == RetailOrderNotificationEvent.Channel.EMAIL
        ):
            backend = (
                email_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_EMAIL_BACKEND"
                )
            )
            message = render_email_notification(event)

        elif (
            event.channel
            == RetailOrderNotificationEvent.Channel.SMS
        ):
            backend = (
                sms_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_SMS_BACKEND"
                )
            )
            message = render_sms_notification(event)

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
        event.status = RetailOrderNotificationEvent.Status.FAILED
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
    event.status = RetailOrderNotificationEvent.Status.SENT
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


def process_pending_notification_events(*, limit=None):
    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )
    batch_size = (
        limit
        if limit is not None
        else settings.RETAIL_NOTIFICATION_BATCH_SIZE
    )

    event_ids = list(
        RetailOrderNotificationEvent.objects
        .filter(
            status__in=[
                RetailOrderNotificationEvent.Status.PENDING,
                RetailOrderNotificationEvent.Status.FAILED,
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
        event = RetailOrderNotificationEvent.objects.get(
            pk=event_id
        )
        outcome = deliver_notification_event(event=event)

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
