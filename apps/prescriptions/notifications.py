from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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
    Prescription,
    PrescriptionNotificationEvent,
)


User = get_user_model()


REVIEW_EVENT_TYPES = {
    Prescription.Status.APPROVED: (
        PrescriptionNotificationEvent.EventType.APPROVED
    ),
    Prescription.Status.CLARIFICATION_REQUIRED: (
        PrescriptionNotificationEvent
        .EventType.CLARIFICATION_REQUIRED
    ),
    Prescription.Status.REJECTED: (
        PrescriptionNotificationEvent.EventType.REJECTED
    ),
}


def _verified_destinations(user):
    destinations = []

    if (
        user.email
        and getattr(user, "email_verified", False)
    ):
        destinations.append(
            (
                PrescriptionNotificationEvent.Channel.EMAIL,
                user.email,
            )
        )

    if (
        user.phone_number
        and getattr(user, "phone_verified", False)
    ):
        destinations.append(
            (
                PrescriptionNotificationEvent.Channel.SMS,
                user.phone_number,
            )
        )

    return destinations


def _reviewers():
    permission = Permission.objects.get(
        content_type__app_label="prescriptions",
        codename="review_prescription",
    )

    return (
        User.objects
        .filter(
            is_active=True,
            is_staff=True,
        )
        .filter(
            Q(is_superuser=True)
            | Q(user_permissions=permission)
            | Q(groups__permissions=permission)
        )
        .distinct()
        .order_by("pk")
    )


def _create_event(
    *,
    prescription,
    recipient_user,
    event_type,
    channel,
    recipient,
    deduplication_key,
    payload,
):
    event, _ = (
        PrescriptionNotificationEvent.objects
        .get_or_create(
            deduplication_key=deduplication_key,
            defaults={
                "prescription": prescription,
                "recipient_user": recipient_user,
                "event_type": event_type,
                "channel": channel,
                "recipient": recipient,
                "payload": payload,
            },
        )
    )

    return event


def queue_prescription_submitted_notifications(
    prescription,
):
    events = []

    for reviewer in _reviewers():
        for channel, recipient in _verified_destinations(
            reviewer
        ):
            events.append(
                _create_event(
                    prescription=prescription,
                    recipient_user=reviewer,
                    event_type=(
                        PrescriptionNotificationEvent
                        .EventType.SUBMITTED
                    ),
                    channel=channel,
                    recipient=recipient,
                    deduplication_key=(
                        f"prescription:{prescription.pk}:"
                        f"submitted:{reviewer.pk}:{channel}"
                    ),
                    payload={
                        "prescription_id": prescription.pk,
                        "customer_id": prescription.user_id,
                        "customer_notes": (
                            prescription.customer_notes
                        ),
                    },
                )
            )

    return tuple(events)


def queue_prescription_review_notifications(
    *,
    prescription,
    previous_status,
):
    if prescription.status == previous_status:
        return ()

    event_type = REVIEW_EVENT_TYPES.get(
        prescription.status
    )

    if event_type is None:
        return ()

    payload = {
        "prescription_id": prescription.pk,
        "previous_status": previous_status,
        "new_status": prescription.status,
        "status_label": prescription.get_status_display(),
        "customer_review_message": (
            prescription.customer_review_message
        ),
        "reviewed_at": (
            prescription.reviewed_at.isoformat()
            if prescription.reviewed_at
            else None
        ),
    }

    events = []

    for channel, recipient in _verified_destinations(
        prescription.user
    ):
        events.append(
            _create_event(
                prescription=prescription,
                recipient_user=prescription.user,
                event_type=event_type,
                channel=channel,
                recipient=recipient,
                deduplication_key=(
                    f"prescription:{prescription.pk}:"
                    f"{event_type}:{channel}"
                ),
                payload=payload,
            )
        )

    return tuple(events)


def _load_backend(setting_name):
    backend_path = getattr(settings, setting_name)
    backend_class = import_string(backend_path)
    return backend_class()


def _context(event):
    return {
        "event": event,
        "event_type": event.event_type,
        "prescription": event.prescription,
        "payload": event.payload or {},
    }


def render_prescription_email(event):
    subjects = {
        PrescriptionNotificationEvent.EventType.SUBMITTED: (
            "New prescription submitted"
        ),
        PrescriptionNotificationEvent.EventType.APPROVED: (
            "Your prescription was approved"
        ),
        (
            PrescriptionNotificationEvent
            .EventType.CLARIFICATION_REQUIRED
        ): "Prescription clarification required",
        PrescriptionNotificationEvent.EventType.REJECTED: (
            "Prescription review update"
        ),
    }

    return NotificationMessage(
        subject=(
            f"{subjects[event.event_type]} — "
            f"Prescription #{event.prescription_id}"
        ),
        text=render_to_string(
            "prescriptions/notifications/email.txt",
            _context(event),
        ).strip(),
        html=render_to_string(
            "prescriptions/notifications/email.html",
            _context(event),
        ).strip(),
    )


def render_prescription_sms(event):
    return NotificationMessage(
        subject="",
        text=render_to_string(
            "prescriptions/notifications/sms.txt",
            _context(event),
        ).strip(),
    )


@transaction.atomic
def deliver_prescription_notification_event(
    *,
    event,
    email_backend=None,
    sms_backend=None,
):
    event = (
        PrescriptionNotificationEvent.objects
        .select_for_update(of=("self",))
        .select_related(
            "prescription",
            "prescription__user",
        )
        .get(pk=event.pk)
    )

    if event.status in {
        PrescriptionNotificationEvent.Status.SENT,
        PrescriptionNotificationEvent.Status.CANCELLED,
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
            PrescriptionNotificationEvent.Status.FAILED
        )

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
            == PrescriptionNotificationEvent.Channel.EMAIL
        ):
            backend = (
                email_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_EMAIL_BACKEND"
                )
            )
            message = render_prescription_email(event)

        elif (
            event.channel
            == PrescriptionNotificationEvent.Channel.SMS
        ):
            backend = (
                sms_backend
                or _load_backend(
                    "RETAIL_NOTIFICATION_SMS_BACKEND"
                )
            )
            message = render_prescription_sms(event)

        else:
            raise RuntimeError(
                "Unsupported prescription notification channel."
            )

        result: NotificationBackendResult = backend.send(
            event=event,
            message=message,
        )

    except Exception as exc:
        event.status = (
            PrescriptionNotificationEvent.Status.FAILED
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
    event.status = PrescriptionNotificationEvent.Status.SENT
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


def process_pending_prescription_notifications(
    *,
    limit=None,
):
    batch_size = (
        limit
        if limit is not None
        else settings.RETAIL_NOTIFICATION_BATCH_SIZE
    )
    maximum_attempts = (
        settings.RETAIL_NOTIFICATION_MAX_ATTEMPTS
    )

    event_ids = list(
        PrescriptionNotificationEvent.objects
        .filter(
            status__in=[
                PrescriptionNotificationEvent.Status.PENDING,
                PrescriptionNotificationEvent.Status.FAILED,
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
        event = PrescriptionNotificationEvent.objects.get(
            pk=event_id
        )
        outcome = (
            deliver_prescription_notification_event(
                event=event
            )
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
