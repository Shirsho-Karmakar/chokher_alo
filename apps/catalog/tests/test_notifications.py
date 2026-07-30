from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductStockAlert,
    ProductVariant,
)
from apps.catalog.notifications import deliver_stock_alert
from apps.retail_orders.notifications import (
    NotificationBackendResult,
)


User = get_user_model()


class RecordingStockAlertSMSBackend:
    messages = []

    def send(self, *, event, message):
        type(self).messages.append(
            {
                "recipient": event.recipient,
                "text": message.text,
                "event_id": event.pk,
            }
        )

        return NotificationBackendResult(
            provider="recording_stock_sms",
            message_id=f"stock-sms-{event.pk}",
        )


class FlakyStockAlertSMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1

        if type(self).calls == 1:
            raise RuntimeError(
                "Temporary stock-alert SMS failure."
            )

        return NotificationBackendResult(
            provider="flaky_stock_sms",
            message_id=f"retry-{event.pk}",
        )


class FailingStockAlertSMSBackend:
    calls = 0

    def send(self, *, event, message):
        type(self).calls += 1

        raise RuntimeError(
            "Permanent stock-alert SMS failure."
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
        "apps.catalog.tests.test_notifications."
        "RecordingStockAlertSMSBackend"
    ),
    RETAIL_NOTIFICATION_MAX_ATTEMPTS=2,
    RETAIL_NOTIFICATION_BATCH_SIZE=100,
)
class ProductStockAlertNotificationTests(TestCase):
    def setUp(self):
        RecordingStockAlertSMSBackend.messages = []
        FlakyStockAlertSMSBackend.calls = 0
        FailingStockAlertSMSBackend.calls = 0

        self.user = User.objects.create_user(
            username="stock-alert-customer",
            email="stock-customer@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )

        self.colour = Colour.objects.create(
            name="Stock Alert Black"
        )

        self.offer = self.create_sold_out_offer(
            name="Stock Alert Frame",
        )

    def create_sold_out_offer(self, *, name):
        design = ProductDesign.objects.create(
            name=name,
            kind=ProductDesign.Kind.FRAME,
            status=ProductDesign.Status.ACTIVE,
        )

        variant = ProductVariant.objects.create(
            design=design,
            colour=self.colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=0,
        )

        return ProductOffer.objects.create(
            variant=variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1200.00"),
            selling_price_including_gst=Decimal("999.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.SOLD_OUT,
        )

    def make_available(self, offer=None):
        offer = offer or self.offer

        offer.status = ProductOffer.Status.AVAILABLE
        offer.save()

        offer.variant.stock_quantity = 5
        offer.variant.save()

        offer.refresh_from_db()

        return offer

    def create_alert(
        self,
        *,
        offer=None,
        channel=ProductStockAlert.Channel.EMAIL,
    ):
        offer = offer or self.offer

        destination = (
            self.user.email
            if channel == ProductStockAlert.Channel.EMAIL
            else self.user.phone_number
        )

        return ProductStockAlert.objects.create(
            user=self.user,
            offer=offer,
            channel=channel,
            destination=destination,
        )

    def test_unavailable_alert_is_skipped(self):
        alert = self.create_alert()

        outcome = deliver_stock_alert(alert=alert)
        alert.refresh_from_db()

        self.assertTrue(outcome.skipped)
        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.ACTIVE,
        )
        self.assertEqual(alert.attempt_count, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_available_email_alert_is_sent_once(self):
        alert = self.create_alert()
        self.make_available()

        first = deliver_stock_alert(alert=alert)
        second = deliver_stock_alert(alert=alert)

        alert.refresh_from_db()

        self.assertTrue(first.sent)
        self.assertTrue(second.skipped)
        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.NOTIFIED,
        )
        self.assertEqual(alert.attempt_count, 1)
        self.assertIsNotNone(alert.notified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            "Back in stock",
            mail.outbox[0].subject,
        )

    def test_available_sms_alert_is_sent(self):
        alert = self.create_alert(
            channel=ProductStockAlert.Channel.SMS
        )
        self.make_available()

        deliver_stock_alert(alert=alert)
        alert.refresh_from_db()

        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.NOTIFIED,
        )
        self.assertEqual(
            len(RecordingStockAlertSMSBackend.messages),
            1,
        )
        self.assertIn(
            self.offer.sku,
            RecordingStockAlertSMSBackend.messages[0]["text"],
        )
        self.assertEqual(
            alert.delivery_payload["provider"],
            "recording_stock_sms",
        )

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.catalog.tests.test_notifications."
            "FlakyStockAlertSMSBackend"
        )
    )
    def test_failed_alert_can_be_retried(self):
        alert = self.create_alert(
            channel=ProductStockAlert.Channel.SMS
        )
        self.make_available()

        first = deliver_stock_alert(alert=alert)
        second = deliver_stock_alert(alert=alert)

        alert.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.sent)
        self.assertEqual(alert.attempt_count, 2)
        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.NOTIFIED,
        )

    @override_settings(
        RETAIL_NOTIFICATION_SMS_BACKEND=(
            "apps.catalog.tests.test_notifications."
            "FailingStockAlertSMSBackend"
        ),
        RETAIL_NOTIFICATION_MAX_ATTEMPTS=1,
    )
    def test_maximum_attempts_marks_alert_failed(self):
        alert = self.create_alert(
            channel=ProductStockAlert.Channel.SMS
        )
        self.make_available()

        first = deliver_stock_alert(alert=alert)
        second = deliver_stock_alert(alert=alert)

        alert.refresh_from_db()

        self.assertFalse(first.sent)
        self.assertTrue(second.skipped)
        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.FAILED,
        )
        self.assertEqual(alert.attempt_count, 1)
        self.assertEqual(
            FailingStockAlertSMSBackend.calls,
            1,
        )

    def test_cancelled_alert_is_never_delivered(self):
        alert = self.create_alert()
        alert.status = ProductStockAlert.Status.CANCELLED
        alert.save()

        self.make_available()

        outcome = deliver_stock_alert(alert=alert)

        self.assertTrue(outcome.skipped)
        self.assertEqual(len(mail.outbox), 0)

    def test_command_processes_only_available_alerts(self):
        available_alert = self.create_alert()
        self.make_available()

        unavailable_offer = self.create_sold_out_offer(
            name="Still Sold Out Frame",
        )
        unavailable_alert = self.create_alert(
            offer=unavailable_offer,
            channel=ProductStockAlert.Channel.SMS,
        )

        output = StringIO()

        call_command(
            "process_stock_alerts",
            stdout=output,
        )

        available_alert.refresh_from_db()
        unavailable_alert.refresh_from_db()

        self.assertEqual(
            available_alert.status,
            ProductStockAlert.Status.NOTIFIED,
        )
        self.assertEqual(
            unavailable_alert.status,
            ProductStockAlert.Status.ACTIVE,
        )
        self.assertEqual(
            unavailable_alert.attempt_count,
            0,
        )
        self.assertIn(
            "Processed 1 stock alert",
            output.getvalue(),
        )

    def test_new_active_alert_can_follow_terminal_failure(self):
        alert = self.create_alert(
            channel=ProductStockAlert.Channel.SMS
        )

        alert.status = ProductStockAlert.Status.FAILED
        alert.save()

        replacement = ProductStockAlert.objects.create(
            user=self.user,
            offer=self.offer,
            channel=ProductStockAlert.Channel.SMS,
            destination=self.user.phone_number,
        )

        self.assertEqual(
            replacement.status,
            ProductStockAlert.Status.ACTIVE,
        )
