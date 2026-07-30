from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.retail_cart.models import RetailCart, RetailCartItem
from apps.retail_orders.models import (
    RetailCheckoutPolicy,
    RetailOrder,
    RetailOrderAddressSnapshot,
    RetailOrderItem,
    RetailPaymentAttempt,
    RetailStockReservation,
    StoreLocation,
)


User = get_user_model()


class RetailOrderModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="retail-order-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.cart = RetailCart.objects.create(user=self.user)

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

        colour = Colour.objects.create(
            name="Order Test Black"
        )
        design = ProductDesign.objects.create(
            name="Order Test Frame",
            kind=ProductDesign.Kind.FRAME,
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
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

    def create_pickup_order(self, **overrides):
        data = {
            "user": self.user,
            "source_cart": self.cart,
            "payment_method": (
                RetailOrder.PaymentMethod.PAY_AT_STORE
            ),
            "payment_status": (
                RetailOrder.PaymentStatus.UNPAID
            ),
            "fulfillment_method": (
                RetailOrder.FulfillmentMethod.STORE_PICKUP
            ),
            "store_location": self.store,
            "subtotal_including_gst": Decimal("1200.00"),
            "delivery_fee_including_gst": Decimal("0.00"),
            "grand_total_including_gst": Decimal("1200.00"),
        }
        data.update(overrides)

        return RetailOrder.objects.create(**data)

    def test_only_one_default_store_is_allowed(self):
        duplicate = StoreLocation(
            code="SECOND",
            name="Second Store",
            address_line_1="2 Main Road",
            city="Kolkata",
            state="West Bengal",
            postal_code="700002",
            is_default_pickup=True,
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_only_one_active_checkout_policy_is_allowed(self):
        RetailCheckoutPolicy.objects.create(
            name="Default",
            delivery_fee_including_gst=Decimal("80.00"),
            free_delivery_threshold_including_gst=(
                Decimal("1500.00")
            ),
        )

        duplicate = RetailCheckoutPolicy(
            name="Second",
            delivery_fee_including_gst=Decimal("100.00"),
            free_delivery_threshold_including_gst=(
                Decimal("2000.00")
            ),
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_delivery_policy_applies_free_delivery_threshold(self):
        policy = RetailCheckoutPolicy.objects.create(
            name="Default",
            delivery_fee_including_gst=Decimal("80.00"),
            free_delivery_threshold_including_gst=(
                Decimal("1500.00")
            ),
        )

        self.assertEqual(
            policy.delivery_fee_for(Decimal("1000.00")),
            Decimal("80.00"),
        )
        self.assertEqual(
            policy.delivery_fee_for(Decimal("1500.00")),
            Decimal("0.00"),
        )

    def test_order_receives_permanent_number(self):
        order = self.create_pickup_order()

        self.assertRegex(
            order.order_number,
            r"^CHA-R-[0-9]{8}-[0-9]{6,}$",
        )

        original_number = order.order_number

        order.customer_notes = "Updated"
        order.save()
        order.refresh_from_db()

        self.assertEqual(order.order_number, original_number)

    def test_pay_at_store_requires_store_pickup(self):
        order = RetailOrder(
            user=self.user,
            source_cart=self.cart,
            payment_method=(
                RetailOrder.PaymentMethod.PAY_AT_STORE
            ),
            payment_status=RetailOrder.PaymentStatus.UNPAID,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            subtotal_including_gst=Decimal("1200.00"),
            delivery_fee_including_gst=Decimal("0.00"),
            grand_total_including_gst=Decimal("1200.00"),
        )

        with self.assertRaises(ValidationError):
            order.save()

    def test_customer_can_cancel_before_processing(self):
        order = self.create_pickup_order(
            status=RetailOrder.Status.CONFIRMED,
            cancellable_until=(
                timezone.now() + timedelta(hours=12)
            ),
        )

        self.assertTrue(order.can_customer_cancel)
        self.assertIsNone(order.cancellation_block_reason)

    def test_processing_blocks_customer_cancellation(self):
        order = self.create_pickup_order(
            status=RetailOrder.Status.PROCESSING,
            processing_started_at=timezone.now(),
        )

        self.assertFalse(order.can_customer_cancel)
        self.assertEqual(
            order.cancellation_block_reason,
            "order_processing_started",
        )

    def test_address_snapshot_rejects_invalid_pin_code(self):
        order = self.create_pickup_order()

        address = RetailOrderAddressSnapshot(
            order=order,
            address_type=(
                RetailOrderAddressSnapshot
                .AddressType.SHIPPING
            ),
            recipient_name="Customer",
            phone_number="+919876543210",
            address_line_1="1 Test Road",
            city="Kolkata",
            state="West Bengal",
            postal_code="000001",
        )

        with self.assertRaises(ValidationError):
            address.save()

    def test_order_item_calculates_immutable_line_total(self):
        order = self.create_pickup_order()

        item = RetailOrderItem.objects.create(
            order=order,
            source_cart_item_id=1,
            item_type=RetailCartItem.ItemType.STANDARD,
            offer=self.offer,
            product_variant=self.variant,
            sku=self.offer.sku,
            product_name="Order Test Frame",
            quantity=2,
            unit_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
        )

        self.assertEqual(
            item.line_total_including_gst,
            Decimal("2400.00"),
        )
        self.assertFalse(item.is_non_refundable)

    def test_online_reservation_requires_expiry(self):
        order = self.create_pickup_order(
            payment_method=RetailOrder.PaymentMethod.RAZORPAY,
            payment_status=RetailOrder.PaymentStatus.PENDING,
        )
        item = RetailOrderItem.objects.create(
            order=order,
            item_type=RetailCartItem.ItemType.STANDARD,
            offer=self.offer,
            product_variant=self.variant,
            sku=self.offer.sku,
            product_name="Order Test Frame",
            quantity=1,
            unit_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
        )

        reservation = RetailStockReservation(
            order=order,
            order_item=item,
            product_variant=self.variant,
            quantity=1,
            reason=(
                RetailStockReservation.Reason.ONLINE_PAYMENT
            ),
        )

        with self.assertRaises(ValidationError):
            reservation.save()

    def test_credit_card_method_is_rejected(self):
        order = self.create_pickup_order(
            payment_method=RetailOrder.PaymentMethod.RAZORPAY,
            payment_status=RetailOrder.PaymentStatus.PENDING,
        )

        attempt = RetailPaymentAttempt(
            order=order,
            payment_method=RetailOrder.PaymentMethod.RAZORPAY,
            amount_including_gst=Decimal("1200.00"),
            allowed_payment_methods=[
                "upi",
                "credit_card",
            ],
        )

        with self.assertRaises(ValidationError):
            attempt.save()
