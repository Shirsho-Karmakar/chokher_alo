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
    RetailCartError,
    add_standard_offer,
    get_or_create_open_retail_cart,
)
from apps.retail_orders.models import (
    RetailCheckoutPolicy,
    RetailFulfillmentGroup,
    RetailOrder,
    RetailOrderAddressSnapshot,
    RetailPaymentAttempt,
    RetailStockReservation,
    StoreLocation,
)
from apps.retail_orders.services import (
    RetailCheckoutError,
    create_retail_checkout,
)


User = get_user_model()


class RetailCheckoutCreationTests(TestCase):
    def setUp(self):
        self.state = IndianState.values[0]

        self.user = User.objects.create_user(
            username="checkout-customer",
            phone_number="+919876543210",
            phone_verified=True,
        )

        self.policy = RetailCheckoutPolicy.objects.create(
            name="Default retail checkout",
            delivery_fee_including_gst=Decimal("80.00"),
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

        self.address = Address.objects.create(
            user=self.user,
            label="Home",
            recipient_name="Checkout Customer",
            phone_number="+919876543210",
            address_line_1="10 Test Road",
            city="Test City",
            district="Test District",
            state=self.state,
            postal_code="700010",
            is_default_delivery=True,
            is_default_billing=True,
        )

        self.serviceable = ServiceablePincode.objects.create(
            postal_code=self.address.postal_code,
            status=ServiceablePincode.Status.ACTIVE,
            state=self.state,
            city=self.address.city,
            district=self.address.district,
        )

        colour = Colour.objects.create(
            name="Checkout Black"
        )
        design = ProductDesign.objects.create(
            name="Checkout Case",
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

        self.cart = get_or_create_open_retail_cart(
            user=self.user
        )

    def add_item(self, quantity=1):
        return add_standard_offer(
            cart=self.cart,
            offer=self.offer,
            quantity=quantity,
        )

    def test_online_delivery_creates_snapshots_and_reservation(self):
        self.add_item(quantity=1)

        before = timezone.now()

        result = create_retail_checkout(
            cart=self.cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
            billing_same_as_shipping=True,
        )

        order = result.order
        self.cart.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(
            order.delivery_fee_including_gst,
            Decimal("80.00"),
        )
        self.assertEqual(
            order.grand_total_including_gst,
            Decimal("580.00"),
        )
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.CHECKOUT_STARTED,
        )

        # Online checkout reserves but does not yet deduct stock.
        self.assertEqual(self.variant.stock_quantity, 10)

        reservation = (
            RetailStockReservation.objects.get(
                order=order
            )
        )

        self.assertEqual(
            reservation.status,
            RetailStockReservation.Status.ACTIVE,
        )
        self.assertGreater(
            reservation.expires_at,
            before,
        )
        self.assertLessEqual(
            reservation.expires_at,
            before + timedelta(minutes=16),
        )

        snapshots = {
            snapshot.address_type: snapshot
            for snapshot
            in order.address_snapshots.all()
        }

        self.assertEqual(
            snapshots["shipping"].district,
            "Test District",
        )
        self.assertEqual(
            snapshots["billing"].source_address_id,
            self.address.pk,
        )

        self.assertEqual(
            result.payment_attempt.allowed_payment_methods,
            [
                "upi",
                "debit_card",
                "netbanking",
                "wallet",
            ],
        )
        self.assertNotIn(
            "credit_card",
            result.payment_attempt.allowed_payment_methods,
        )

    def test_free_delivery_threshold_is_applied(self):
        self.add_item(quantity=2)

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

        self.assertEqual(
            result.order.subtotal_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(
            result.order.delivery_fee_including_gst,
            Decimal("0.00"),
        )

    def test_inactive_serviceable_pin_is_rejected(self):
        self.add_item()

        self.serviceable.status = (
            ServiceablePincode.Status.INACTIVE
        )
        self.serviceable.save()

        with self.assertRaises(RetailCheckoutError) as context:
            create_retail_checkout(
                cart=self.cart,
                fulfillment_method=(
                    RetailOrder.FulfillmentMethod.DELIVERY
                ),
                payment_method=(
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
                shipping_address=self.address,
            )

        self.assertEqual(
            context.exception.code,
            "delivery_not_serviceable",
        )
        self.assertEqual(RetailOrder.objects.count(), 0)

    def test_pay_at_store_uses_default_store_and_commits_stock(self):
        self.add_item(quantity=2)

        result = create_retail_checkout(
            cart=self.cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.STORE_PICKUP
            ),
            payment_method=(
                RetailOrder.PaymentMethod.PAY_AT_STORE
            ),
            billing_address=self.address,
        )

        order = result.order
        self.cart.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(order.store_location, self.store)
        self.assertEqual(
            order.status,
            RetailOrder.Status.CONFIRMED,
        )
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.UNPAID,
        )
        self.assertEqual(
            self.cart.status,
            RetailCart.Status.CONVERTED,
        )
        self.assertEqual(self.variant.stock_quantity, 8)

        reservation = (
            RetailStockReservation.objects.get(
                order=order
            )
        )

        self.assertEqual(
            reservation.status,
            RetailStockReservation.Status.CONSUMED,
        )
        self.assertEqual(
            reservation.reason,
            RetailStockReservation.Reason.PAY_AT_STORE,
        )
        self.assertIsNotNone(reservation.consumed_at)

        attempt = RetailPaymentAttempt.objects.get(
            order=order
        )
        self.assertEqual(
            attempt.allowed_payment_methods,
            [],
        )

        main_group = order.fulfillment_groups.get(
            group_type=(
                RetailFulfillmentGroup.GroupType.MAIN_PICKUP
            )
        )
        self.assertEqual(
            main_group.store_location,
            self.store,
        )

    def test_active_reservation_blocks_a_second_checkout(self):
        self.variant.stock_quantity = 1
        self.variant.save()

        self.add_item()

        create_retail_checkout(
            cart=self.cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

        second_user = User.objects.create_user(
            username="second-checkout-customer",
            phone_number="+919876543211",
            phone_verified=True,
        )
        second_address = Address.objects.create(
            user=second_user,
            recipient_name="Second Customer",
            phone_number="+919876543211",
            address_line_1="11 Test Road",
            city="Test City",
            district="Test District",
            state=self.state,
            postal_code="700010",
            is_default_delivery=True,
            is_default_billing=True,
        )
        second_cart = get_or_create_open_retail_cart(
            user=second_user
        )
        add_standard_offer(
            cart=second_cart,
            offer=self.offer,
            quantity=1,
        )

        with self.assertRaises(RetailCheckoutError) as context:
            create_retail_checkout(
                cart=second_cart,
                fulfillment_method=(
                    RetailOrder.FulfillmentMethod.DELIVERY
                ),
                payment_method=(
                    RetailOrder.PaymentMethod.RAZORPAY
                ),
                shipping_address=second_address,
            )

        self.assertEqual(
            context.exception.code,
            "insufficient_stock",
        )

    def test_order_snapshots_do_not_change_with_source_records(self):
        self.add_item()

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

        order_item = result.order.items.get()
        snapshot = (
            result.order.address_snapshots.get(
                address_type=(
                    RetailOrderAddressSnapshot
                    .AddressType.SHIPPING
                )
            )
        )

        self.address.recipient_name = "Changed Customer"
        self.address.city = "Changed City"
        self.address.save()

        self.offer.selling_price_including_gst = (
            Decimal("650.00")
        )
        self.offer.save()

        snapshot.refresh_from_db()
        order_item.refresh_from_db()

        self.assertEqual(
            snapshot.recipient_name,
            "Checkout Customer",
        )
        self.assertEqual(snapshot.city, "Test City")
        self.assertEqual(
            order_item.product_snapshot[
                "selling_price_including_gst"
            ],
            "500.00",
        )

    def test_checkout_started_blocks_creation_of_second_cart(self):
        self.add_item()

        create_retail_checkout(
            cart=self.cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

        with self.assertRaises(RetailCartError) as context:
            get_or_create_open_retail_cart(user=self.user)

        self.assertEqual(
            context.exception.code,
            "checkout_in_progress",
        )
