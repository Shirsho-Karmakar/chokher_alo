from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.retail_orders.razorpay_gateway import (
    amount_to_subunits,
)
from apps.wholesale_cart.models import WholesaleCart

from . import tests as foundation_tests
from .models import (
    WholesaleOrder,
    WholesalePaymentAttempt,
    WholesaleStockReservation,
)
from .services import (
    WholesaleCheckoutError,
    cancel_wholesale_checkout,
    confirm_wholesale_bank_transfer,
    confirm_wholesale_online_payment,
    expire_wholesale_payment_attempt,
    fail_wholesale_payment,
    mark_wholesale_order_refunded,
    prepare_wholesale_razorpay_payment,
    start_wholesale_checkout,
)


User = get_user_model()


class FakeWholesaleRazorpayGateway:
    key_id = "rzp_test_wholesale"

    def __init__(self):
        self.calls = 0

    def create_order(
        self,
        *,
        amount_including_gst,
        currency,
        receipt,
        notes,
    ):
        self.calls += 1

        return {
            "id": "order_wholesale_test_1",
            "amount": amount_to_subunits(
                amount_including_gst
            ),
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
        }


class WholesalePaymentLifecycleTests(TestCase):
    create_customer = (
        foundation_tests
        .WholesaleCheckoutFoundationTests
        .create_customer
    )
    create_ready_cart = (
        foundation_tests
        .WholesaleCheckoutFoundationTests
        .create_ready_cart
    )

    def setUp(self):
        (
            foundation_tests
            .WholesaleCheckoutFoundationTests
            .setUp(self)
        )

    def create_checkout(self, *, method, boxes=2):
        cart = self.create_ready_cart(boxes=boxes)

        return start_wholesale_checkout(
            cart=cart,
            payment_method=method,
            reservation_minutes=30,
        )

    def create_operator(self):
        return User.objects.create_user(
            username="wholesale-payment-operator",
            email="wholesale-operator@example.com",
            phone_number="+919876543299",
            phone_verified=True,
            is_staff=True,
            is_superuser=True,
        )

    def prepare_online_attempt(self):
        result = self.create_checkout(
            method=WholesalePaymentAttempt.Method.RAZORPAY
        )
        result.payment_attempt.provider_order_id = (
            "order_wholesale_confirm"
        )
        result.payment_attempt.save(
            update_fields=[
                "provider_order_id",
                "updated_at",
            ]
        )
        return result

    def test_prepare_razorpay_order_is_idempotent(self):
        result = self.create_checkout(
            method=WholesalePaymentAttempt.Method.RAZORPAY
        )
        gateway = FakeWholesaleRazorpayGateway()

        first = prepare_wholesale_razorpay_payment(
            payment_attempt=result.payment_attempt,
            gateway=gateway,
        )
        second = prepare_wholesale_razorpay_payment(
            payment_attempt=result.payment_attempt,
            gateway=gateway,
        )

        self.assertEqual(gateway.calls, 1)
        self.assertEqual(
            first.provider_order_id,
            second.provider_order_id,
        )

    def test_online_confirmation_consumes_stock_and_cart(self):
        result = self.prepare_online_attempt()

        order = confirm_wholesale_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_wholesale_1",
            provider_signature="verified-signature",
            signature_verified=True,
            response_payload={"status": "captured"},
        )

        result.payment_attempt.refresh_from_db()
        order.source_cart.refresh_from_db()
        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()
        reservation = order.stock_reservations.get()

        self.assertEqual(
            order.status,
            WholesaleOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.PAID,
        )
        self.assertTrue(
            result.payment_attempt.signature_verified
        )
        self.assertEqual(
            reservation.status,
            WholesaleStockReservation.Status.CONSUMED,
        )
        self.assertEqual(self.variant.boxes_in_stock, 18)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            96,
        )
        self.assertEqual(
            order.source_cart.status,
            WholesaleCart.Status.CONVERTED,
        )

    def test_online_confirmation_is_idempotent(self):
        result = self.prepare_online_attempt()

        confirm_wholesale_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_wholesale_repeat",
            provider_signature="verified",
            signature_verified=True,
        )
        confirm_wholesale_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id="pay_wholesale_repeat",
            provider_signature="verified",
            signature_verified=True,
        )

        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()

        self.assertEqual(self.variant.boxes_in_stock, 18)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            96,
        )

    def test_invalid_signature_does_not_consume_stock(self):
        result = self.prepare_online_attempt()

        with self.assertRaises(
            WholesaleCheckoutError
        ) as context:
            confirm_wholesale_online_payment(
                payment_attempt=result.payment_attempt,
                provider_payment_id="pay_invalid",
                provider_signature="invalid",
                signature_verified=False,
            )

        self.assertEqual(
            context.exception.code,
            "payment_signature_invalid",
        )
        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()

        self.assertEqual(self.variant.boxes_in_stock, 20)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            100,
        )

    def test_expired_online_confirmation_is_rejected(self):
        result = self.prepare_online_attempt()
        past = timezone.now() - timedelta(minutes=1)

        WholesalePaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(expires_at=past)
        WholesaleStockReservation.objects.filter(
            order=result.order
        ).update(expires_at=past)

        result.payment_attempt.refresh_from_db()

        with self.assertRaises(
            WholesaleCheckoutError
        ) as context:
            confirm_wholesale_online_payment(
                payment_attempt=result.payment_attempt,
                provider_payment_id="pay_expired",
                provider_signature="verified",
                signature_verified=True,
            )

        self.assertEqual(
            context.exception.code,
            "payment_attempt_expired",
        )

    def test_bank_transfer_requires_staff_operator(self):
        result = self.create_checkout(
            method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            )
        )

        with self.assertRaises(
            WholesaleCheckoutError
        ) as context:
            confirm_wholesale_bank_transfer(
                payment_attempt=result.payment_attempt,
                actor=self.user,
                transfer_reference="BANK-001",
            )

        self.assertEqual(
            context.exception.code,
            "staff_payment_access_required",
        )

    def test_bank_transfer_confirmation_consumes_stock(self):
        result = self.create_checkout(
            method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            )
        )

        order = confirm_wholesale_bank_transfer(
            payment_attempt=result.payment_attempt,
            actor=self.create_operator(),
            transfer_reference="BANK-PAID-001",
        )

        result.payment_attempt.refresh_from_db()
        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()

        self.assertEqual(
            order.payment_status,
            WholesaleOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            result.payment_attempt.provider_payment_id,
            "BANK-PAID-001",
        )
        self.assertEqual(self.variant.boxes_in_stock, 18)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            96,
        )

    def test_failed_payment_releases_reservations(self):
        result = self.prepare_online_attempt()

        order = fail_wholesale_payment(
            payment_attempt=result.payment_attempt,
            response_payload={"reason": "declined"},
        )

        result.payment_attempt.refresh_from_db()
        order.source_cart.refresh_from_db()
        reservation = order.stock_reservations.get()

        self.assertEqual(
            order.status,
            WholesaleOrder.Status.PAYMENT_FAILED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.FAILED,
        )
        self.assertEqual(
            reservation.status,
            WholesaleStockReservation.Status.RELEASED,
        )
        self.assertEqual(
            order.source_cart.status,
            WholesaleCart.Status.OPEN,
        )

    def test_expired_payment_releases_and_reopens(self):
        result = self.prepare_online_attempt()
        past = timezone.now() - timedelta(minutes=1)

        WholesalePaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(expires_at=past)
        WholesaleStockReservation.objects.filter(
            order=result.order
        ).update(expires_at=past)

        result.payment_attempt.refresh_from_db()

        order = expire_wholesale_payment_attempt(
            payment_attempt=result.payment_attempt
        )

        result.payment_attempt.refresh_from_db()
        order.source_cart.refresh_from_db()

        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.EXPIRED,
        )
        self.assertEqual(
            order.stock_reservations.get().status,
            WholesaleStockReservation.Status.EXPIRED,
        )
        self.assertEqual(
            order.source_cart.status,
            WholesaleCart.Status.OPEN,
        )

    def test_expiry_command_processes_due_attempts(self):
        result = self.prepare_online_attempt()
        past = timezone.now() - timedelta(minutes=1)

        WholesalePaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(expires_at=past)
        WholesaleStockReservation.objects.filter(
            order=result.order
        ).update(expires_at=past)

        output = StringIO()

        call_command(
            "expire_wholesale_payments",
            stdout=output,
        )

        result.payment_attempt.refresh_from_db()

        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.EXPIRED,
        )
        self.assertIn(
            "Expired 1 wholesale payment attempt",
            output.getvalue(),
        )

    def test_paid_cancellation_restores_stock(self):
        result = self.create_checkout(
            method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            )
        )
        order = confirm_wholesale_bank_transfer(
            payment_attempt=result.payment_attempt,
            actor=self.create_operator(),
            transfer_reference="BANK-CANCEL-001",
        )

        cancelled = cancel_wholesale_checkout(
            order=order,
            reason="Business requested cancellation.",
        )

        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()
        cancelled.source_cart.refresh_from_db()

        self.assertEqual(
            cancelled.payment_status,
            WholesaleOrder.PaymentStatus.REFUND_PENDING,
        )
        self.assertEqual(self.variant.boxes_in_stock, 20)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            100,
        )
        self.assertEqual(
            cancelled.stock_reservations.get().status,
            WholesaleStockReservation.Status.RELEASED,
        )
        self.assertEqual(
            cancelled.source_cart.status,
            WholesaleCart.Status.CONVERTED,
        )

    def test_refund_completion_is_idempotent(self):
        result = self.create_checkout(
            method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            )
        )
        order = confirm_wholesale_bank_transfer(
            payment_attempt=result.payment_attempt,
            actor=self.create_operator(),
            transfer_reference="BANK-REFUND-001",
        )
        order = cancel_wholesale_checkout(
            order=order,
            reason="Refund requested.",
        )

        first = mark_wholesale_order_refunded(
            order=order,
            refund_payload={"reference": "REFUND-001"},
        )
        second = mark_wholesale_order_refunded(
            order=order,
            refund_payload={"reference": "REFUND-001"},
        )

        result.payment_attempt.refresh_from_db()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            second.payment_status,
            WholesaleOrder.PaymentStatus.REFUNDED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.REFUNDED,
        )
