from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.retail_orders.notifications import (
    NotificationBackendResult,
)
from apps.wholesale_cart.models import WholesaleCart

from . import tests as foundation_tests
from .models import (
    WholesaleInvoice,
    WholesaleOrderNotificationEvent,
    WholesalePaymentAttempt,
)
from .notifications import (
    deliver_wholesale_notification,
)
from .services import (
    confirm_wholesale_bank_transfer,
    mark_wholesale_order_delivered,
    mark_wholesale_order_shipped,
    start_wholesale_checkout,
    start_wholesale_order_processing,
)


User = get_user_model()


class RecordingWholesaleSMSBackend:
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
            provider="recording_wholesale_sms",
            message_id=f"wh-sms-{event.pk}",
        )


class FlakyWholesaleSMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1

        if type(self).calls == 1:
            raise RuntimeError(
                "Temporary wholesale SMS failure."
            )

        return NotificationBackendResult(
            provider="flaky_wholesale_sms",
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
        "apps.wholesale_orders."
        "test_notifications_invoices."
        "RecordingWholesaleSMSBackend"
    ),
    RETAIL_NOTIFICATION_MAX_ATTEMPTS=3,
    RETAIL_NOTIFICATION_BATCH_SIZE=100,
    WHOLESALE_INVOICE_SELLER_NAME="Chokher Alo Test",
    WHOLESALE_INVOICE_SELLER_GSTIN="19AAAAA0000A1Z5",
    WHOLESALE_INVOICE_SELLER_ADDRESS=(
        "1 Test Road, Kolkata"
    ),
    WHOLESALE_INVOICE_SELLER_STATE="West Bengal",
    WHOLESALE_INVOICE_SELLER_EMAIL=(
        "billing@example.com"
    ),
)
class WholesaleNotificationInvoiceTests(TestCase):
    create_ready_cart = (
        foundation_tests
        .WholesaleCheckoutFoundationTests
        .create_ready_cart
    )
    create_customer = (
        foundation_tests
        .WholesaleCheckoutFoundationTests
        .create_customer
    )

    def setUp(self):
        (
            foundation_tests
            .WholesaleCheckoutFoundationTests
            .setUp(self)
        )
        RecordingWholesaleSMSBackend.messages = []
        FlakyWholesaleSMSBackend.calls = 0

        self.operator = User.objects.create_user(
            username="wholesale-invoice-operator",
            email="operator@example.com",
            phone_number="+919876543299",
            phone_verified=True,
            is_staff=True,
            is_superuser=True,
        )

    def create_confirmed_order(self):
        cart = self.create_ready_cart()
        result = start_wholesale_checkout(
            cart=cart,
            payment_method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            ),
            reservation_minutes=30,
        )

        order = confirm_wholesale_bank_transfer(
            payment_attempt=result.payment_attempt,
            actor=self.operator,
            transfer_reference="BANK-INVOICE-001",
        )

        return order

    def test_confirmation_creates_immutable_invoice(self):
        order = self.create_confirmed_order()
        invoice = WholesaleInvoice.objects.get(
            order=order
        )

        self.assertEqual(
            invoice.seller_snapshot["name"],
            "Chokher Alo Test",
        )
        self.assertEqual(
            invoice.business_snapshot["business_name"],
            self.account.business_name,
        )
        self.assertEqual(
            invoice.grand_total_including_gst,
            order.grand_total_including_gst,
        )
        self.assertEqual(len(invoice.items_snapshot), 1)

    def test_repeated_confirmation_does_not_duplicate_invoice(
        self,
    ):
        order = self.create_confirmed_order()
        attempt = order.payment_attempts.get(
            status=WholesalePaymentAttempt.Status.PAID
        )

        confirm_wholesale_bank_transfer(
            payment_attempt=attempt,
            actor=self.operator,
            transfer_reference="BANK-INVOICE-001",
        )

        self.assertEqual(
            WholesaleInvoice.objects.filter(
                order=order
            ).count(),
            1,
        )

    def test_invoice_snapshot_does_not_follow_sources(self):
        order = self.create_confirmed_order()
        invoice = order.invoice
        original_business_name = (
            invoice.business_snapshot["business_name"]
        )

        self.account.business_name = "Changed Later"
        self.account.save()

        invoice.refresh_from_db()

        self.assertEqual(
            invoice.business_snapshot["business_name"],
            original_business_name,
        )

    def test_customer_can_open_printable_invoice(self):
        order = self.create_confirmed_order()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "wholesale_orders:invoice_detail",
                args=[order.order_number],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            order.invoice.invoice_number,
        )
        self.assertContains(response, order.order_number)
        self.assertIn(
            "inline; filename=",
            response["Content-Disposition"],
        )

    def test_other_customer_cannot_open_invoice(self):
        order = self.create_confirmed_order()

        other_user, *_rest = self.create_customer(
            username="other-invoice-user",
            phone_number="+919876543211",
        )
        self.client.force_login(other_user)

        response = self.client.get(
            reverse(
                "wholesale_orders:invoice_detail",
                args=[order.order_number],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_confirmation_queues_email_and_sms(self):
        order = self.create_confirmed_order()

        events = order.notification_events.filter(
            event_type=(
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            )
        )

        self.assertEqual(events.count(), 2)
        self.assertEqual(
            set(events.values_list("channel", flat=True)),
            {
                WholesaleOrderNotificationEvent
                .Channel.EMAIL,
                WholesaleOrderNotificationEvent
                .Channel.SMS,
            },
        )

    def test_email_and_sms_events_are_delivered(self):
        order = self.create_confirmed_order()
        email_event = order.notification_events.get(
            event_type=(
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            ),
            channel=(
                WholesaleOrderNotificationEvent.Channel.EMAIL
            ),
        )
        sms_event = order.notification_events.get(
            event_type=(
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            ),
            channel=(
                WholesaleOrderNotificationEvent.Channel.SMS
            ),
        )

        deliver_wholesale_notification(event=email_event)
        deliver_wholesale_notification(event=sms_event)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            order.order_number,
            mail.outbox[0].subject,
        )
        self.assertEqual(
            len(RecordingWholesaleSMSBackend.messages),
            1,
        )

    def test_sent_notification_is_idempotent(self):
        order = self.create_confirmed_order()
        event = order.notification_events.get(
            event_type=(
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            ),
            channel=(
                WholesaleOrderNotificationEvent.Channel.EMAIL
            ),
        )

        first = deliver_wholesale_notification(event=event)
        second = deliver_wholesale_notification(event=event)

        event.refresh_from_db()

        self.assertTrue(first.sent)
        self.assertTrue(second.skipped)
        self.assertEqual(event.attempt_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.wholesale_orders."
            "test_notifications_invoices."
            "FlakyWholesaleSMSBackend"
        )
    )
    def test_failed_notification_can_be_retried(self):
        order = self.create_confirmed_order()
        event = order.notification_events.get(
            event_type=(
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            ),
            channel=(
                WholesaleOrderNotificationEvent.Channel.SMS
            ),
        )

        first = deliver_wholesale_notification(event=event)
        second = deliver_wholesale_notification(event=event)

        event.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.sent)
        self.assertEqual(event.attempt_count, 2)

    def test_fulfillment_events_and_command(self):
        order = self.create_confirmed_order()

        start_wholesale_order_processing(
            order=order,
            actor=self.operator,
        )
        mark_wholesale_order_shipped(
            order=order,
            actor=self.operator,
            carrier_name="Test Courier",
            tracking_number="WHOLESALE-TRACK-1",
        )
        mark_wholesale_order_delivered(
            order=order,
            actor=self.operator,
        )

        event_types = set(
            order.notification_events.values_list(
                "event_type",
                flat=True,
            )
        )

        self.assertTrue(
            {
                WholesaleOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED,
                WholesaleOrderNotificationEvent
                .EventType.PROCESSING,
                WholesaleOrderNotificationEvent
                .EventType.SHIPPED,
                WholesaleOrderNotificationEvent
                .EventType.DELIVERED,
            }.issubset(event_types)
        )

        output = StringIO()

        call_command(
            "process_wholesale_notifications",
            stdout=output,
        )

        self.assertFalse(
            order.notification_events.exclude(
                status=(
                    WholesaleOrderNotificationEvent
                    .Status.SENT
                )
            ).exists()
        )
        self.assertIn("sent", output.getvalue())
