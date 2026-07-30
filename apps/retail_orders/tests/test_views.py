import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.locations.constants import IndianState
from apps.locations.models import (
    Address,
    ServiceablePincode,
)
from apps.retail_cart.models import RetailCart
from apps.retail_cart.services import (
    add_standard_offer,
    get_or_create_open_retail_cart,
)
from apps.retail_orders.models import (
    RetailCheckoutPolicy,
    RetailOrder,
    RetailPaymentAttempt,
    RetailPaymentWebhookEvent,
    RetailStockReservation,
    StoreLocation,
)
from apps.retail_orders.razorpay_gateway import (
    RazorpayGatewayError,
    amount_to_subunits,
)
from apps.retail_orders.services import (
    create_retail_checkout,
)


User = get_user_model()


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_chokher_alo",
    RAZORPAY_KEY_SECRET="test-key-secret",
    RAZORPAY_WEBHOOK_SECRET="test-webhook-secret",
    RAZORPAY_API_BASE_URL="https://api.razorpay.com/v1",
    RAZORPAY_REQUEST_TIMEOUT_SECONDS=15,
)
class RetailOrderAPIViewTests(TestCase):
    def setUp(self):
        self.state = IndianState.values[0]

        self.user = User.objects.create_user(
            username="retail-order-api-user",
            email="orders@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.other_user = User.objects.create_user(
            username="other-retail-order-user",
            email="other-orders@example.com",
            email_verified=True,
            phone_number="+919876543211",
            phone_verified=True,
        )

        RetailCheckoutPolicy.objects.create(
            name="Retail API checkout policy",
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
            phone_number="+919876543210",
            address_line_1="1 Main Road",
            city="Kolkata",
            state="West Bengal",
            postal_code="700001",
            is_default_pickup=True,
        )

        self.address = self.create_address(
            user=self.user,
            recipient_name="Order API Customer",
            phone_number="+919876543210",
        )
        self.other_address = self.create_address(
            user=self.other_user,
            recipient_name="Other Order Customer",
            phone_number="+919876543211",
        )

        ServiceablePincode.objects.create(
            postal_code="700010",
            status=ServiceablePincode.Status.ACTIVE,
            state=self.state,
            city="Kolkata",
            district="Kolkata",
        )

        colour = Colour.objects.create(
            name="Retail Order API Black"
        )
        design = ProductDesign.objects.create(
            name="Retail Order API Case",
            kind=ProductDesign.Kind.ACCESSORY,
            status=ProductDesign.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=20,
        )
        self.offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.ACCESSORY,
            mrp_including_gst=Decimal("700.00"),
            selling_price_including_gst=Decimal("500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        self.cart = get_or_create_open_retail_cart(
            user=self.user
        )

    def create_address(
        self,
        *,
        user,
        recipient_name,
        phone_number,
    ):
        return Address.objects.create(
            user=user,
            label="Home",
            recipient_name=recipient_name,
            phone_number=phone_number,
            address_line_1="10 Checkout Road",
            city="Kolkata",
            district="Kolkata",
            state=self.state,
            postal_code="700010",
            is_default_delivery=True,
            is_default_billing=True,
        )

    def add_item(self, *, cart=None, quantity=1):
        return add_standard_offer(
            cart=cart or self.cart,
            offer=self.offer,
            quantity=quantity,
        )

    def create_online_checkout(
        self,
        *,
        provider_order_id="order_test_local",
        quantity=1,
    ):
        self.add_item(quantity=quantity)

        result = create_retail_checkout(
            cart=self.cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

        RetailPaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(
            provider_order_id=provider_order_id,
            status=RetailPaymentAttempt.Status.PENDING,
        )
        result.payment_attempt.refresh_from_db()

        return result

    def create_pay_at_store_checkout(
        self,
        *,
        cart=None,
        address=None,
        quantity=1,
    ):
        cart = cart or self.cart
        address = address or self.address

        self.add_item(
            cart=cart,
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
            billing_address=address,
        )

    def webhook_signature(self, raw_body):
        return hmac.new(
            b"test-webhook-secret",
            raw_body,
            hashlib.sha256,
        ).hexdigest()

    def post_webhook(
        self,
        *,
        payload,
        event_id,
        signature=None,
    ):
        raw_body = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        return self.client.post(
            reverse("retail_orders:razorpay_webhook"),
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=(
                signature
                if signature is not None
                else self.webhook_signature(raw_body)
            ),
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )

    def captured_webhook_payload(
        self,
        *,
        result,
        payment_id,
        amount=None,
        currency="INR",
    ):
        return {
            "entity": "event",
            "event": "payment.captured",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "entity": "payment",
                        "order_id": (
                            result.payment_attempt
                            .provider_order_id
                        ),
                        "amount": (
                            amount
                            if amount is not None
                            else amount_to_subunits(
                                result.payment_attempt
                                .amount_including_gst
                            )
                        ),
                        "currency": currency,
                        "status": "captured",
                        "captured": True,
                    }
                }
            },
        }

    def test_checkout_preview_requires_login(self):
        response = self.client.post(
            reverse("retail_orders:checkout_preview"),
            {
                "fulfillment_method": (
                    RetailOrder
                    .FulfillmentMethod.DELIVERY
                ),
                "payment_method": (
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
            },
        )

        self.assertEqual(response.status_code, 302)

    def test_checkout_preview_returns_current_totals(self):
        self.add_item()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("retail_orders:checkout_preview"),
            {
                "fulfillment_method": (
                    RetailOrder
                    .FulfillmentMethod.DELIVERY
                ),
                "payment_method": (
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
                "shipping_address_id": self.address.pk,
            },
        )

        self.assertEqual(response.status_code, 200)

        preview = response.json()["preview"]

        self.assertEqual(
            preview["subtotal_including_gst"],
            "500.00",
        )
        self.assertEqual(
            preview["delivery_fee_including_gst"],
            "50.00",
        )
        self.assertEqual(
            preview["grand_total_including_gst"],
            "550.00",
        )
        self.assertEqual(
            preview["shipping_address"]["district"],
            "Kolkata",
        )
        self.assertIsNone(preview["store_location"])

    def test_pay_at_store_checkout_endpoint_places_order(self):
        self.add_item(quantity=2)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("retail_orders:checkout_create"),
            {
                "fulfillment_method": (
                    RetailOrder
                    .FulfillmentMethod.STORE_PICKUP
                ),
                "payment_method": (
                    RetailOrder
                    .PaymentMethod.PAY_AT_STORE
                ),
                "billing_address_id": self.address.pk,
            },
        )

        self.assertEqual(response.status_code, 201)

        data = response.json()
        order = data["order"]

        self.assertIsNone(data["payment_session"])
        self.assertEqual(
            order["status"],
            RetailOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            order["payment_status"],
            RetailOrder.PaymentStatus.UNPAID,
        )
        self.assertEqual(
            order["store_location"]["code"],
            "MAIN",
        )

        self.variant.refresh_from_db()
        self.cart.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 18)
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.CONVERTED,
        )

    @patch(
        "apps.retail_orders.services."
        "RazorpayGateway.create_order"
    )
    def test_online_checkout_creates_provider_order(
        self,
        create_provider_order,
    ):
        self.add_item()
        self.client.force_login(self.user)

        create_provider_order.return_value = {
            "id": "order_api_created",
            "entity": "order",
            "amount": 55000,
            "currency": "INR",
            "receipt": "test-receipt",
            "status": "created",
        }

        response = self.client.post(
            reverse("retail_orders:checkout_create"),
            {
                "fulfillment_method": (
                    RetailOrder
                    .FulfillmentMethod.DELIVERY
                ),
                "payment_method": (
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
                "shipping_address_id": self.address.pk,
            },
        )

        self.assertEqual(response.status_code, 201)

        session = response.json()["payment_session"]

        self.assertEqual(
            session["provider_order_id"],
            "order_api_created",
        )
        self.assertEqual(session["amount_subunits"], 55000)
        self.assertEqual(
            session["key_id"],
            "rzp_test_chokher_alo",
        )
        self.assertNotIn(
            "credit_card",
            session["allowed_payment_methods"],
        )

        attempt = RetailPaymentAttempt.objects.get(
            provider_order_id="order_api_created"
        )

        self.assertEqual(
            attempt.status,
            RetailPaymentAttempt.Status.PENDING,
        )

        self.variant.refresh_from_db()
        self.cart.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 20)
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.CHECKOUT_STARTED,
        )
        self.assertEqual(
            attempt.order.stock_reservations.get().status,
            RetailStockReservation.Status.ACTIVE,
        )

    @patch(
        "apps.retail_orders.services."
        "RazorpayGateway.create_order"
    )
    def test_gateway_failure_releases_reservation_and_cart(
        self,
        create_provider_order,
    ):
        self.add_item()
        self.client.force_login(self.user)

        create_provider_order.side_effect = (
            RazorpayGatewayError(
                "razorpay_connection_error",
                "Razorpay is unavailable.",
            )
        )

        response = self.client.post(
            reverse("retail_orders:checkout_create"),
            {
                "fulfillment_method": (
                    RetailOrder
                    .FulfillmentMethod.DELIVERY
                ),
                "payment_method": (
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
                "shipping_address_id": self.address.pk,
            },
        )

        self.assertEqual(response.status_code, 502)

        order = RetailOrder.objects.get()
        self.cart.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(
            order.status,
            RetailOrder.Status.PAYMENT_FAILED,
        )
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.OPEN,
        )
        self.assertEqual(self.variant.stock_quantity, 20)
        self.assertEqual(
            order.stock_reservations.get().status,
            RetailStockReservation.Status.RELEASED,
        )

    @patch(
        "apps.retail_orders.views."
        "RazorpayGateway.fetch_payment"
    )
    @patch(
        "apps.retail_orders.views."
        "RazorpayGateway.verify_checkout_signature"
    )
    def test_confirmation_endpoint_captures_payment(
        self,
        verify_signature,
        fetch_payment,
    ):
        result = self.create_online_checkout(
            provider_order_id="order_callback_success"
        )
        self.client.force_login(self.user)

        verify_signature.return_value = True
        fetch_payment.return_value = {
            "id": "pay_callback_success",
            "entity": "payment",
            "order_id": "order_callback_success",
            "amount": amount_to_subunits(
                result.payment_attempt
                .amount_including_gst
            ),
            "currency": "INR",
            "status": "captured",
            "captured": True,
        }

        response = self.client.post(
            reverse("retail_orders:razorpay_confirm"),
            {
                "razorpay_order_id": (
                    "order_callback_success"
                ),
                "razorpay_payment_id": (
                    "pay_callback_success"
                ),
                "razorpay_signature": "valid-signature",
            },
        )

        self.assertEqual(response.status_code, 200)

        result.order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        self.cart.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(
            result.order.payment_status,
            RetailOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.CAPTURED,
        )
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.CONVERTED,
        )
        self.assertEqual(self.variant.stock_quantity, 19)

    def test_other_user_cannot_confirm_payment(self):
        self.create_online_checkout(
            provider_order_id="order_private_payment"
        )
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse("retail_orders:razorpay_confirm"),
            {
                "razorpay_order_id": (
                    "order_private_payment"
                ),
                "razorpay_payment_id": "pay_private",
                "razorpay_signature": "signature",
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_order_list_and_detail_are_private(self):
        own_result = self.create_pay_at_store_checkout()

        other_cart = get_or_create_open_retail_cart(
            user=self.other_user
        )
        other_result = self.create_pay_at_store_checkout(
            cart=other_cart,
            address=self.other_address,
        )

        self.client.force_login(self.user)

        list_response = self.client.get(
            reverse("retail_orders:order_list")
        )

        self.assertEqual(list_response.status_code, 200)

        numbers = {
            order["order_number"]
            for order in list_response.json()["orders"]
        }

        self.assertEqual(
            numbers,
            {own_result.order.order_number},
        )

        own_detail = self.client.get(
            reverse(
                "retail_orders:order_detail",
                kwargs={
                    "order_number": (
                        own_result.order.order_number
                    )
                },
            )
        )
        other_detail = self.client.get(
            reverse(
                "retail_orders:order_detail",
                kwargs={
                    "order_number": (
                        other_result.order.order_number
                    )
                },
            )
        )

        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(other_detail.status_code, 404)
        self.assertEqual(
            own_detail.json()["order"]["items"][0][
                "product_name"
            ],
            "Retail Order API Case",
        )

    def test_cancellation_endpoint_restores_stock(self):
        result = self.create_pay_at_store_checkout(
            quantity=2
        )
        self.client.force_login(self.user)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 18)

        response = self.client.post(
            reverse(
                "retail_orders:order_cancel",
                kwargs={
                    "order_number": (
                        result.order.order_number
                    )
                },
            ),
            {"reason": "No longer required"},
        )

        self.assertEqual(response.status_code, 200)

        self.variant.refresh_from_db()
        result.order.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 20)
        self.assertEqual(
            result.order.status,
            RetailOrder.Status.CANCELLED,
        )
        self.assertEqual(
            response.json()["order"][
                "cancellation_reason"
            ],
            "No longer required",
        )

    def test_invalid_webhook_signature_is_rejected(self):
        result = self.create_online_checkout(
            provider_order_id="order_bad_signature"
        )
        payload = self.captured_webhook_payload(
            result=result,
            payment_id="pay_bad_signature",
        )

        response = self.post_webhook(
            payload=payload,
            event_id="event_bad_signature",
            signature="invalid-signature",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            RetailPaymentWebhookEvent.objects.count(),
            0,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 20)

    def test_captured_webhook_is_idempotent(self):
        result = self.create_online_checkout(
            provider_order_id="order_webhook_success"
        )
        payload = self.captured_webhook_payload(
            result=result,
            payment_id="pay_webhook_success",
        )

        first = self.post_webhook(
            payload=payload,
            event_id="event_webhook_success",
        )
        second = self.post_webhook(
            payload=payload,
            event_id="event_webhook_success",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])

        self.variant.refresh_from_db()
        result.order.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 19)
        self.assertEqual(
            result.order.payment_status,
            RetailOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            RetailPaymentWebhookEvent.objects.count(),
            1,
        )
        self.assertEqual(
            RetailPaymentWebhookEvent.objects.get().status,
            RetailPaymentWebhookEvent.Status.PROCESSED,
        )

    def test_mismatched_webhook_does_not_consume_stock(self):
        result = self.create_online_checkout(
            provider_order_id="order_webhook_mismatch"
        )
        payload = self.captured_webhook_payload(
            result=result,
            payment_id="pay_webhook_mismatch",
            amount=1,
        )

        response = self.post_webhook(
            payload=payload,
            event_id="event_webhook_mismatch",
        )

        self.assertEqual(response.status_code, 500)

        self.variant.refresh_from_db()
        result.order.refresh_from_db()

        self.assertEqual(self.variant.stock_quantity, 20)
        self.assertEqual(
            result.order.payment_status,
            RetailOrder.PaymentStatus.PENDING,
        )
        self.assertEqual(
            result.order.stock_reservations.get().status,
            RetailStockReservation.Status.ACTIVE,
        )

        event = RetailPaymentWebhookEvent.objects.get(
            event_id="event_webhook_mismatch"
        )

        self.assertEqual(
            event.status,
            RetailPaymentWebhookEvent.Status.FAILED,
        )
        self.assertIn(
            "webhook_payment_mismatch",
            event.error_message,
        )

    def test_failed_payment_webhook_reopens_cart(self):
        result = self.create_online_checkout(
            provider_order_id="order_webhook_failed"
        )

        payload = {
            "entity": "event",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_failed",
                        "entity": "payment",
                        "order_id": (
                            "order_webhook_failed"
                        ),
                        "amount": amount_to_subunits(
                            result.payment_attempt
                            .amount_including_gst
                        ),
                        "currency": "INR",
                        "status": "failed",
                        "captured": False,
                    }
                }
            },
        }

        response = self.post_webhook(
            payload=payload,
            event_id="event_webhook_failed",
        )

        self.assertEqual(response.status_code, 200)

        result.order.refresh_from_db()
        result.payment_attempt.refresh_from_db()
        self.cart.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(
            result.order.status,
            RetailOrder.Status.PAYMENT_FAILED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            RetailPaymentAttempt.Status.FAILED,
        )
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.OPEN,
        )
        self.assertEqual(self.variant.stock_quantity, 20)
        self.assertEqual(
            result.order.stock_reservations.get().status,
            RetailStockReservation.Status.RELEASED,
        )
