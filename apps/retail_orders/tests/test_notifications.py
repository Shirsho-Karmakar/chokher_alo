from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.retail_cart.models import RetailCart
from apps.retail_orders.models import (
    RetailOrder,
    RetailOrderNotificationEvent,
)
from apps.retail_orders.notifications import (
    NotificationBackendResult,
    deliver_notification_event,
)


User = get_user_model()


class RecordingSMSBackend:
    messages = []

    def send(self, *, event, message):
        type(self).messages.append(
            {
                "recipient": event.recipient,
                "message": message.text,
                "event_id": event.pk,
            }
        )

        return NotificationBackendResult(
            provider="recording_sms",
            message_id=f"sms-{event.pk}",
        )


class FailingSMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1
        raise RuntimeError("Temporary SMS failure.")


class FlakySMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1

        if type(self).calls == 1:
            raise RuntimeError("First SMS attempt failed.")

        return NotificationBackendResult(
            provider="flaky_sms",
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
        "apps.retail_orders.tests.test_notifications."
        "RecordingSMSBackend"
    ),
    RETAIL_NOTIFICATION_MAX_ATTEMPTS=2,
    RETAIL_NOTIFICATION_BATCH_SIZE=100,
    DEFAULT_FROM_EMAIL="Chokher Alo <test@example.com>",
)
class RetailNotificationDeliveryTests(TestCase):
    def setUp(self):
        RecordingSMSBackend.messages = []
        FailingSMSBackend.calls = 0
        FlakySMSBackend.calls = 0

        self.user = User.objects.create_user(
            username="notification-customer",
            email="customer@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )

        self.cart = RetailCart.objects.create(
            user=self.user,
            status=RetailCart.Status.CONVERTED,
        )

        self.order = RetailOrder.objects.create(
            user=self.user,
            source_cart=self.cart,
            status=RetailOrder.Status.CONFIRMED,
            payment_method=RetailOrder.PaymentMethod.RAZORPAY,
            payment_status=RetailOrder.PaymentStatus.PAID,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            subtotal_including_gst=Decimal("500.00"),
            delivery_fee_including_gst=Decimal("50.00"),
            grand_total_including_gst=Decimal("550.00"),
        )

    def create_event(
        self,
        *,
        channel,
        event_type=(
            RetailOrderNotificationEvent
            .EventType.PAYMENT_CONFIRMED
        ),
        recipient=None,
        payload=None,
    ):
        if recipient is None:
            recipient = (
                self.user.email
                if channel
                == RetailOrderNotificationEvent.Channel.EMAIL
                else self.user.phone_number
            )

        return RetailOrderNotificationEvent.objects.create(
            order=self.order,
            event_type=event_type,
            channel=channel,
            recipient=recipient,
            payload=payload or {},
        )

    def test_email_event_is_delivered(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.EMAIL
            )
        )

        outcome = deliver_notification_event(
            event=event
        )

        event.refresh_from_db()

        self.assertTrue(outcome.sent)
        self.assertEqual(
            event.status,
            RetailOrderNotificationEvent.Status.SENT,
        )
        self.assertEqual(event.attempt_count, 1)
        self.assertIsNotNone(event.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            self.order.order_number,
            mail.outbox[0].subject,
        )
        self.assertIn(
            "Payment confirmed",
            mail.outbox[0].subject,
        )

    def test_sms_event_uses_configured_backend(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            ),
            event_type=(
                RetailOrderNotificationEvent.EventType.SHIPPED
            ),
            payload={
                "carrier_name": "Test Courier",
                "tracking_number": "TRACK-123",
            },
        )

        deliver_notification_event(event=event)
        event.refresh_from_db()

        self.assertEqual(
            event.status,
            RetailOrderNotificationEvent.Status.SENT,
        )
        self.assertEqual(
            len(RecordingSMSBackend.messages),
            1,
        )
        self.assertIn(
            "TRACK-123",
            RecordingSMSBackend.messages[0]["message"],
        )
        self.assertEqual(
            event.payload["delivery"]["provider"],
            "recording_sms",
        )

    def test_sent_event_is_idempotent(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.EMAIL
            )
        )

        first = deliver_notification_event(event=event)
        second = deliver_notification_event(event=event)

        event.refresh_from_db()

        self.assertTrue(first.sent)
        self.assertTrue(second.skipped)
        self.assertEqual(event.attempt_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.retail_orders.tests.test_notifications."
            "FailingSMSBackend"
        )
    )
    def test_failure_is_recorded(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            )
        )

        outcome = deliver_notification_event(event=event)
        event.refresh_from_db()

        self.assertFalse(outcome.sent)
        self.assertFalse(outcome.skipped)
        self.assertEqual(
            event.status,
            RetailOrderNotificationEvent.Status.FAILED,
        )
        self.assertEqual(event.attempt_count, 1)
        self.assertIn(
            "Temporary SMS failure",
            event.last_error,
        )

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.retail_orders.tests.test_notifications."
            "FlakySMSBackend"
        )
    )
    def test_failed_event_can_be_retried(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            )
        )

        first = deliver_notification_event(event=event)
        second = deliver_notification_event(event=event)

        event.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.sent)
        self.assertEqual(event.attempt_count, 2)
        self.assertEqual(
            event.status,
            RetailOrderNotificationEvent.Status.SENT,
        )
        self.assertEqual(FlakySMSBackend.calls, 2)

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.retail_orders.tests.test_notifications."
            "FailingSMSBackend"
        ),
        RETAIL_NOTIFICATION_MAX_ATTEMPTS=1,
    )
    def test_maximum_attempts_prevent_extra_delivery(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            )
        )

        first = deliver_notification_event(event=event)
        second = deliver_notification_event(event=event)

        event.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.skipped)
        self.assertEqual(event.attempt_count, 1)
        self.assertEqual(FailingSMSBackend.calls, 1)

    def test_cancelled_event_is_not_delivered(self):
        event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.EMAIL
            )
        )
        event.status = (
            RetailOrderNotificationEvent.Status.CANCELLED
        )
        event.save()

        outcome = deliver_notification_event(event=event)

        self.assertTrue(outcome.skipped)
        self.assertEqual(len(mail.outbox), 0)

    def test_management_command_processes_email_and_sms(self):
        email_event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.EMAIL
            )
        )
        sms_event = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            )
        )

        output = StringIO()

        call_command(
            "process_retail_notifications",
            stdout=output,
        )

        email_event.refresh_from_db()
        sms_event.refresh_from_db()

        self.assertEqual(
            email_event.status,
            RetailOrderNotificationEvent.Status.SENT,
        )
        self.assertEqual(
            sms_event.status,
            RetailOrderNotificationEvent.Status.SENT,
        )
        self.assertIn(
            "2 sent",
            output.getvalue(),
        )

    def test_management_command_respects_limit(self):
        first = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.EMAIL
            )
        )
        second = self.create_event(
            channel=(
                RetailOrderNotificationEvent.Channel.SMS
            )
        )

        output = StringIO()

        call_command(
            "process_retail_notifications",
            limit=1,
            stdout=output,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        statuses = {
            first.status,
            second.status,
        }

        self.assertEqual(
            statuses,
            {
                RetailOrderNotificationEvent.Status.SENT,
                RetailOrderNotificationEvent.Status.PENDING,
            },
        )
        self.assertIn(
            "Processed 1 notification event",
            output.getvalue(),
        )
