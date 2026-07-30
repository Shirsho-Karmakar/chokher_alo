from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.prescriptions.models import (
    Prescription,
    PrescriptionNotificationEvent,
)
from apps.prescriptions.notifications import (
    deliver_prescription_notification_event,
    queue_prescription_review_notifications,
    queue_prescription_submitted_notifications,
)
from apps.retail_orders.notifications import (
    NotificationBackendResult,
)


User = get_user_model()


class RecordingPrescriptionSMSBackend:
    messages = []

    def send(self, *, event, message):
        type(self).messages.append(
            {
                "recipient": event.recipient,
                "text": message.text,
            }
        )

        return NotificationBackendResult(
            provider="recording_prescription_sms",
            message_id=f"prescription-sms-{event.pk}",
        )


class FlakyPrescriptionSMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1

        if type(self).calls == 1:
            raise RuntimeError(
                "Temporary prescription SMS failure."
            )

        return NotificationBackendResult(
            provider="flaky_prescription_sms",
            message_id=f"retry-{event.pk}",
        )


@override_settings(
    EMAIL_BACKEND=(
        "django.core.mail.backends.locmem.EmailBackend"
    ),
    RETAIL_NOTIFICATION_EMAIL_BACKEND=(
        "apps.retail_orders.notifications."
        "DjangoEmailNotificationBackend"
    ),
    RETAIL_NOTIFICATION_SMS_BACKEND=(
        "apps.prescriptions.tests.test_notifications."
        "RecordingPrescriptionSMSBackend"
    ),
    RETAIL_NOTIFICATION_MAX_ATTEMPTS=3,
)
class PrescriptionNotificationTests(TestCase):
    def setUp(self):
        RecordingPrescriptionSMSBackend.messages = []
        FlakyPrescriptionSMSBackend.calls = 0

        self.customer = User.objects.create_user(
            username="prescription-notification-customer",
            email="prescription-customer@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.reviewer = User.objects.create_user(
            username="prescription-notification-reviewer",
            email="prescription-reviewer@example.com",
            email_verified=True,
            phone_number="+919876543211",
            phone_verified=True,
            is_staff=True,
        )

        permission = Permission.objects.get(
            content_type__app_label="prescriptions",
            codename="review_prescription",
        )
        self.reviewer.user_permissions.add(permission)

        self.prescription = Prescription.objects.create(
            user=self.customer,
            prescription_file=SimpleUploadedFile(
                "prescription.pdf",
                b"%PDF-1.4 test prescription",
                content_type="application/pdf",
            ),
            customer_notes="Please review this prescription.",
        )

    def test_submission_queues_verified_reviewer_channels(self):
        events = queue_prescription_submitted_notifications(
            self.prescription
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(
            set(
                event.channel
                for event in events
            ),
            {
                PrescriptionNotificationEvent.Channel.EMAIL,
                PrescriptionNotificationEvent.Channel.SMS,
            },
        )

    def test_submission_queue_is_idempotent(self):
        queue_prescription_submitted_notifications(
            self.prescription
        )
        queue_prescription_submitted_notifications(
            self.prescription
        )

        self.assertEqual(
            PrescriptionNotificationEvent.objects.count(),
            2,
        )

    def test_approval_queues_customer_channels(self):
        previous_status = self.prescription.status
        self.prescription.status = (
            Prescription.Status.APPROVED
        )
        self.prescription.save()

        events = queue_prescription_review_notifications(
            prescription=self.prescription,
            previous_status=previous_status,
        )

        self.assertEqual(len(events), 2)
        self.assertTrue(
            all(
                event.recipient_user == self.customer
                for event in events
            )
        )

    def test_rejection_payload_contains_customer_message(self):
        previous_status = self.prescription.status
        self.prescription.status = (
            Prescription.Status.REJECTED
        )
        self.prescription.customer_review_message = (
            "The uploaded image is unreadable."
        )
        self.prescription.save()

        events = queue_prescription_review_notifications(
            prescription=self.prescription,
            previous_status=previous_status,
        )

        self.assertEqual(
            events[0].payload["customer_review_message"],
            "The uploaded image is unreadable.",
        )
        self.assertNotIn(
            "admin_notes",
            events[0].payload,
        )

    def test_processing_command_sends_email_and_sms(self):
        previous_status = self.prescription.status
        self.prescription.status = (
            Prescription.Status.APPROVED
        )
        self.prescription.save()

        queue_prescription_review_notifications(
            prescription=self.prescription,
            previous_status=previous_status,
        )

        output = StringIO()

        call_command(
            "process_prescription_notifications",
            stdout=output,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            len(RecordingPrescriptionSMSBackend.messages),
            1,
        )
        self.assertEqual(
            PrescriptionNotificationEvent.objects.filter(
                status=PrescriptionNotificationEvent.Status.SENT
            ).count(),
            2,
        )
        self.assertIn("2 sent", output.getvalue())

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.prescriptions.tests.test_notifications."
            "FlakyPrescriptionSMSBackend"
        )
    )
    def test_failed_event_can_be_retried(self):
        event = PrescriptionNotificationEvent.objects.create(
            prescription=self.prescription,
            recipient_user=self.customer,
            event_type=(
                PrescriptionNotificationEvent
                .EventType.APPROVED
            ),
            channel=(
                PrescriptionNotificationEvent.Channel.SMS
            ),
            recipient=self.customer.phone_number,
            deduplication_key=(
                f"prescription:{self.prescription.pk}:"
                "retry-test:sms"
            ),
        )

        first = deliver_prescription_notification_event(
            event=event
        )
        second = deliver_prescription_notification_event(
            event=event
        )

        event.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.sent)
        self.assertEqual(event.attempt_count, 2)
        self.assertEqual(
            event.status,
            PrescriptionNotificationEvent.Status.SENT,
        )
