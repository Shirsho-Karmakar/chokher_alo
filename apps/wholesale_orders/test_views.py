import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.retail_orders.razorpay_gateway import (
    amount_to_subunits,
)
from apps.wholesale_cart.models import WholesaleCart

from . import tests as foundation_tests
from .models import (
    WholesaleOrder,
    WholesalePaymentAttempt,
    WholesalePaymentWebhookEvent,
)
from .services import (
    confirm_wholesale_bank_transfer,
    start_wholesale_checkout,
)


User = get_user_model()


class AcceptingWebhookGateway:
    def verify_webhook_signature(
        self,
        *,
        raw_body,
        signature,
    ):
        return True


class RejectingWebhookGateway:
    def verify_webhook_signature(
        self,
        *,
        raw_body,
        signature,
    ):
        return False


class WholesaleOrderViewTests(TestCase):
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

    def create_operator(self):
        return User.objects.create_user(
            username="wholesale-view-operator",
            email="wholesale-view-operator@example.com",
            phone_number="+919876543299",
            phone_verified=True,
            is_staff=True,
            is_superuser=True,
        )

    def create_checkout(
        self,
        *,
        payment_method=(
            WholesalePaymentAttempt.Method.BANK_TRANSFER
        ),
        user=None,
        prescription=None,
        boxes=2,
    ):
        cart = self.create_ready_cart(
            user=user,
            prescription=prescription,
            boxes=boxes,
        )

        return start_wholesale_checkout(
            cart=cart,
            payment_method=payment_method,
            reservation_minutes=30,
        )

    def create_razorpay_checkout(self):
        result = self.create_checkout(
            payment_method=(
                WholesalePaymentAttempt.Method.RAZORPAY
            )
        )

        result.payment_attempt.provider_order_id = (
            "order_wholesale_webhook"
        )
        result.payment_attempt.save(
            update_fields=[
                "provider_order_id",
                "updated_at",
            ]
        )

        return result

    def captured_webhook_payload(
        self,
        *,
        attempt,
        payment_id="pay_wholesale_webhook",
        provider_order_id=None,
    ):
        return {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": (
                            provider_order_id
                            or attempt.provider_order_id
                        ),
                        "amount": amount_to_subunits(
                            attempt.amount_including_gst
                        ),
                        "currency": attempt.currency,
                        "status": "captured",
                        "captured": True,
                    }
                }
            },
        }

    def post_webhook(
        self,
        *,
        payload,
        event_id,
        gateway_class=AcceptingWebhookGateway,
    ):
        with patch(
            "apps.wholesale_orders.views.RazorpayGateway",
            gateway_class,
        ):
            return self.client.post(
                reverse(
                    "wholesale_orders:razorpay_webhook"
                ),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=(
                    "verified-webhook-signature"
                ),
                HTTP_X_RAZORPAY_EVENT_ID=event_id,
            )

    def test_checkout_create_endpoint_creates_bank_transfer_order(
        self,
    ):
        cart = self.create_ready_cart()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "wholesale_orders:checkout_create"
            ),
            {
                "payment_method": (
                    WholesalePaymentAttempt
                    .Method.BANK_TRANSFER
                ),
                "customer_notes": (
                    "Deliver during business hours."
                ),
            },
        )

        self.assertEqual(response.status_code, 201)

        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["created"])
        self.assertIsNone(payload["payment_session"])
        self.assertEqual(
            payload["order"]["status"],
            WholesaleOrder.Status.PAYMENT_PENDING,
        )
        self.assertEqual(
            payload["order"]["payment_attempts"][0][
                "method"
            ],
            WholesalePaymentAttempt.Method.BANK_TRANSFER,
        )

        cart.refresh_from_db()

        self.assertEqual(
            cart.status,
            WholesaleCart.Status.CHECKOUT_STARTED,
        )

    def test_customer_order_list_and_detail_are_scoped(self):
        own_result = self.create_checkout()

        (
            other_user,
            _other_account,
            _other_address,
            other_prescription,
        ) = self.create_customer(
            username="other-wholesale-view-user",
            phone_number="+919876543211",
        )

        other_result = self.create_checkout(
            user=other_user,
            prescription=other_prescription,
        )

        self.client.force_login(self.user)

        list_response = self.client.get(
            reverse("wholesale_orders:order_list")
        )

        self.assertEqual(
            list_response.status_code,
            200,
        )

        order_numbers = {
            order["order_number"]
            for order in list_response.json()["orders"]
        }

        self.assertEqual(
            order_numbers,
            {own_result.order.order_number},
        )

        own_detail = self.client.get(
            reverse(
                "wholesale_orders:order_detail",
                args=[own_result.order.order_number],
            )
        )
        other_detail = self.client.get(
            reverse(
                "wholesale_orders:order_detail",
                args=[other_result.order.order_number],
            )
        )

        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(other_detail.status_code, 404)

    def test_customer_can_cancel_pending_checkout(self):
        result = self.create_checkout()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "wholesale_orders:order_cancel",
                args=[result.order.order_number],
            ),
            {
                "reason": (
                    "The business no longer needs the order."
                )
            },
        )

        self.assertEqual(response.status_code, 200)

        result.order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        result.order.source_cart.refresh_from_db()

        self.assertEqual(
            result.order.status,
            WholesaleOrder.Status.CANCELLED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.CANCELLED,
        )
        self.assertEqual(
            result.order.source_cart.status,
            WholesaleCart.Status.OPEN,
        )

    def test_non_staff_cannot_access_staff_orders(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "wholesale_orders:staff_order_list"
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"]["code"],
            "staff_access_required",
        )

    def test_staff_can_confirm_bank_transfer(self):
        result = self.create_checkout()
        operator = self.create_operator()
        self.client.force_login(operator)

        response = self.client.post(
            reverse(
                "wholesale_orders:"
                "staff_confirm_bank_transfer",
                args=[result.order.order_number],
            ),
            {
                "transfer_reference": "BANK-API-001",
                "note": "Verified against bank statement.",
            },
        )

        self.assertEqual(response.status_code, 200)

        result.order.refresh_from_db()
        result.payment_attempt.refresh_from_db()

        self.assertEqual(
            result.order.status,
            WholesaleOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            result.order.payment_status,
            WholesaleOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            result.payment_attempt.provider_payment_id,
            "BANK-API-001",
        )

    def test_staff_can_complete_fulfillment_sequence(self):
        result = self.create_checkout()
        operator = self.create_operator()

        confirm_wholesale_bank_transfer(
            payment_attempt=result.payment_attempt,
            actor=operator,
            transfer_reference="BANK-FULFILL-001",
        )

        self.client.force_login(operator)

        processing_response = self.client.post(
            reverse(
                "wholesale_orders:"
                "staff_start_processing",
                args=[result.order.order_number],
            ),
            {"note": "Picking stock."},
        )

        shipped_response = self.client.post(
            reverse(
                "wholesale_orders:staff_mark_shipped",
                args=[result.order.order_number],
            ),
            {
                "carrier_name": "Wholesale Courier",
                "tracking_number": "WHOLESALE-TRACK-1",
                "note": "Collected by courier.",
            },
        )

        delivered_response = self.client.post(
            reverse(
                "wholesale_orders:"
                "staff_mark_delivered",
                args=[result.order.order_number],
            ),
            {"note": "Delivered to business."},
        )

        self.assertEqual(
            processing_response.status_code,
            200,
        )
        self.assertEqual(
            shipped_response.status_code,
            200,
        )
        self.assertEqual(
            delivered_response.status_code,
            200,
        )

        result.order.refresh_from_db()
        result.order.fulfillment.refresh_from_db()

        self.assertEqual(
            result.order.status,
            WholesaleOrder.Status.DELIVERED,
        )
        self.assertEqual(
            result.order.fulfillment.tracking_number,
            "WHOLESALE-TRACK-1",
        )

    def test_captured_webhook_confirms_payment(self):
        result = self.create_razorpay_checkout()
        payload = self.captured_webhook_payload(
            attempt=result.payment_attempt
        )

        response = self.post_webhook(
            payload=payload,
            event_id="evt-wholesale-captured-1",
        )

        self.assertEqual(response.status_code, 200)

        result.order.refresh_from_db()
        result.payment_attempt.refresh_from_db()

        event = WholesalePaymentWebhookEvent.objects.get(
            event_id="evt-wholesale-captured-1"
        )

        self.assertEqual(
            event.status,
            WholesalePaymentWebhookEvent.Status.PROCESSED,
        )
        self.assertEqual(
            result.order.status,
            WholesaleOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.PAID,
        )

    def test_duplicate_webhook_is_idempotent(self):
        result = self.create_razorpay_checkout()
        payload = self.captured_webhook_payload(
            attempt=result.payment_attempt,
            payment_id="pay-wholesale-duplicate",
        )

        first = self.post_webhook(
            payload=payload,
            event_id="evt-wholesale-duplicate",
        )
        second = self.post_webhook(
            payload=payload,
            event_id="evt-wholesale-duplicate",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])

        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()

        self.assertEqual(self.variant.boxes_in_stock, 18)
        self.assertEqual(
            self.physical_variant.stock_quantity,
            96,
        )
        self.assertEqual(
            WholesalePaymentWebhookEvent.objects.filter(
                event_id="evt-wholesale-duplicate"
            ).count(),
            1,
        )

    def test_unknown_webhook_order_is_ignored(self):
        result = self.create_razorpay_checkout()
        payload = self.captured_webhook_payload(
            attempt=result.payment_attempt,
            provider_order_id="order-not-known",
        )

        response = self.post_webhook(
            payload=payload,
            event_id="evt-wholesale-unknown",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ignored"])

        event = WholesalePaymentWebhookEvent.objects.get(
            event_id="evt-wholesale-unknown"
        )

        self.assertEqual(
            event.status,
            WholesalePaymentWebhookEvent.Status.IGNORED,
        )

    def test_invalid_webhook_signature_is_rejected(self):
        result = self.create_razorpay_checkout()
        payload = self.captured_webhook_payload(
            attempt=result.payment_attempt
        )

        response = self.post_webhook(
            payload=payload,
            event_id="evt-wholesale-invalid-signature",
            gateway_class=RejectingWebhookGateway,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "webhook_signature_invalid",
        )
        self.assertFalse(
            WholesalePaymentWebhookEvent.objects.filter(
                event_id=(
                    "evt-wholesale-invalid-signature"
                )
            ).exists()
        )
