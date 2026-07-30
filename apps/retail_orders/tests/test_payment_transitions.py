from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.locations.constants import IndianState
from apps.locations.models import Address, ServiceablePincode
from apps.retail_cart.models import RetailCart
from apps.retail_cart.services import (
    add_standard_offer,
    get_or_create_open_retail_cart,
)
from apps.retail_orders.models import (
    RetailCheckoutPolicy,
    RetailOrder,
    RetailOrderNotificationEvent,
    RetailPaymentAttempt,
    RetailStockReservation,
    StoreLocation,
)
from apps.retail_orders.services import (
    RetailCheckoutError,
    cancel_retail_order,
    confirm_online_payment,
    create_retail_checkout,
    expire_online_payment_attempt,
    fail_online_payment,
    mark_retail_order_refunded,
)


User = get_user_model()


class RetailPaymentTransitionTests(TestCase):
    def setUp(self):
        self.state = IndianState.values[0]

        self.user = User.objects.create_user(
            username="payment-transition-user",
            email="payment@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )

        RetailCheckoutPolicy.objects.create(
            name="Payment transition policy",
            delivery_fee_including_gst=Decimal("50.00"),
            free_delivery_threshold_including_gst=(
                Decimal("1000.00")
            ),
            payment_reservation_minutes=15,
            cancellation_window_hours=24,
            pay_at_store_enabled=True,
        )

        self.store = StoreLocation.objects.create(
            code="MAIN",
            name="Main Store",
            address_line_1="1 Main Road",
            city="Kolkata",
            state="West Bengal",
            postal_code="700001",
            is_default_pickup=True,
        )

        self.address = Address.objects.create(
            user=self.user,
            recipient_name="Payment Customer",
            phone_number="+919876543210",
            address_line_1="10 Payment Road",
            city="Kolkata",
            district="Kolkata",
            state=self.state,
            postal_code="700010",
            is_default_delivery=True,
            is_default_billing=True,
        )

        ServiceablePincode.objects.create(
            postal_code="700010",
            status=ServiceablePincode.Status.ACTIVE,
            state=self.state,
            city="Kolkata",
            district="Kolkata",
        )

        colour = Colour.objects.create(
            name="Payment Black"
        )
        design = ProductDesign.objects.create(
            name="Payment Test Product",
            kind=ProductDesign.Kind.ACCESSORY,
            status=ProductDesign.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=10,
        )
        self.offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.ACCESSORY,
            mrp_including_gst=Decimal("700.00"),
            selling_price_including_gst=Decimal("500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

    def create_online_checkout(self, quantity=1):
        cart = get_or_create_open_retail_cart(
            user=self.user
        )
        add_standard_offer(
            cart=cart,
            offer=self.offer,
            quantity=quantity,
        )

        return create_retail_checkout(
            cart=cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

    def create_pay_at_store_checkout(self, quantity=1):
        cart = get_or_create_open_retail_cart(
            user=self.user
        )
        add_standard_offer(
            cart=cart,
            offer=self.offer,
            quantity=quantity,
        )

        return create_retail_checkout(
            cart=cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.STORE_PICKUP
            ),
            payment_method=(
                RetailOrder.PaymentMethod.PAY_AT_STORE
            ),
            billing_address=self.address,
        )

    def test_confirmed_payment_consumes_stock_and_cart(self):
        result = self.create_online_checkout(quantity=2)

        order = confirm_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_confirmed_1",
            provider_signature="verified-signature",
            signature_verified=True,
            response_payload={"status": "captured"},
        )

        order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        self.variant.refresh_from_db()
        order.source_cart.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 8)
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            order.status,
            RetailOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            order.source_cart.status,
            RetailCart.Status.CONVERTED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.CAPTURED,
        )
        self.assertTrue(
            result.payment_attempt.signature_verified
        )
        self.assertEqual(
            order.stock_reservations.get().status,
            RetailStockReservation.Status.CONSUMED,
        )

        events = order.notification_events.filter(
            event_type=(
                RetailOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED
            )
        )

        self.assertEqual(events.count(), 2)

    def test_failed_payment_releases_stock_and_reopens_cart(self):
        result = self.create_online_checkout()

        order = fail_online_payment(
            payment_attempt=result.payment_attempt,
            response_payload={"reason": "declined"},
        )

        order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        self.variant.refresh_from_db()
        order.source_cart.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(
            order.status,
            RetailOrder.Status.PAYMENT_FAILED,
        )
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.FAILED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.FAILED,
        )
        self.assertEqual(
            order.stock_reservations.get().status,
            RetailStockReservation.Status.RELEASED,
        )
        self.assertEqual(
            order.source_cart.status,
            RetailCart.Status.OPEN,
        )

        reopened = get_or_create_open_retail_cart(
            user=self.user
        )
        self.assertEqual(
            reopened.pk,
            order.source_cart_id,
        )

    def test_expired_payment_releases_reservation(self):
        result = self.create_online_checkout()
        past = timezone.now() - timedelta(minutes=1)

        RetailPaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(expires_at=past)

        RetailStockReservation.objects.filter(
            order=result.order
        ).update(expires_at=past)

        result.payment_attempt.refresh_from_db()

        order = expire_online_payment_attempt(
            payment_attempt=result.payment_attempt
        )

        order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        order.source_cart.refresh_from_db()

        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.EXPIRED,
        )
        self.assertEqual(
            order.stock_reservations.get().status,
            RetailStockReservation.Status.EXPIRED,
        )
        self.assertEqual(
            order.source_cart.status,
            RetailCart.Status.OPEN,
        )

    def test_invalid_signature_does_not_consume_stock(self):
        result = self.create_online_checkout()

        with self.assertRaises(RetailCheckoutError) as context:
            confirm_online_payment(
                payment_attempt=result.payment_attempt,
                provider_payment_id="pay_invalid_signature",
                provider_signature="invalid",
                signature_verified=False,
            )

        self.assertEqual(
            context.exception.code,
            "payment_signature_invalid",
        )

        self.variant.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(
            result.order.stock_reservations.get().status,
            RetailStockReservation.Status.ACTIVE,
        )

    def test_pay_at_store_cancellation_restores_stock(self):
        result = self.create_pay_at_store_checkout(
            quantity=2
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        order = cancel_retail_order(
            order=result.order,
            cancelled_by=self.user,
            reason="Changed my mind",
        )

        order.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(
            order.status,
            RetailOrder.Status.CANCELLED,
        )
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.UNPAID,
        )
        self.assertEqual(
            order.stock_reservations.get().status,
            RetailStockReservation.Status.RELEASED,
        )
        self.assertEqual(
            order.notification_events.filter(
                event_type=(
                    RetailOrderNotificationEvent
                    .EventType.CANCELLED
                )
            ).count(),
            2,
        )

    def test_paid_order_cancellation_enters_refund_pending(self):
        result = self.create_online_checkout(
            quantity=2
        )

        order = confirm_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_cancelled_order",
            provider_signature="signature",
            signature_verified=True,
        )

        order = cancel_retail_order(
            order=order,
            cancelled_by=self.user,
            reason="Cancel before processing",
        )

        order.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.REFUND_PENDING,
        )
        self.assertEqual(
            order.status,
            RetailOrder.Status.CANCELLED,
        )

    def test_processing_order_cannot_be_cancelled(self):
        result = self.create_pay_at_store_checkout()

        result.order.status = RetailOrder.Status.PROCESSING
        result.order.processing_started_at = timezone.now()
        result.order.save()

        with self.assertRaises(RetailCheckoutError) as context:
            cancel_retail_order(
                order=result.order,
                cancelled_by=self.user,
                reason="Too late",
            )

        self.assertEqual(
            context.exception.code,
            "order_processing_started",
        )

    def test_refund_completion_updates_order_and_attempt(self):
        result = self.create_online_checkout()

        order = confirm_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_refunded_order",
            provider_signature="signature",
            signature_verified=True,
        )
        order = cancel_retail_order(
            order=order,
            cancelled_by=self.user,
            reason="Refund requested",
        )

        order = mark_retail_order_refunded(
            order=order,
            refund_payload={
                "provider_refund_id": "rfnd_123",
            },
        )

        order.refresh_from_db()
        result.payment_attempt.refresh_from_db()

        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.REFUNDED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.REFUNDED,
        )
        self.assertEqual(
            result.payment_attempt.response_payload[
                "refund"
            ]["provider_refund_id"],
            "rfnd_123",
        )
        self.assertEqual(
            order.notification_events.filter(
                event_type=(
                    RetailOrderNotificationEvent
                    .EventType.REFUNDED
                )
            ).count(),
            2,
        )
