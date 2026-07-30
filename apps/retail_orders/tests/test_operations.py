from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
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
    RetailFulfillmentGroup,
    RetailFulfillmentStatusHistory,
    RetailOrder,
    RetailOrderNotificationEvent,
    RetailOrderStatusHistory,
    RetailPaymentAttempt,
    RetailStockReservation,
    StoreLocation,
)
from apps.retail_orders.services import (
    RetailOrderOperationError,
    confirm_online_payment,
    create_retail_checkout,
    mark_order_delivered,
    mark_order_packed,
    mark_order_ready_for_pickup,
    mark_order_shipped,
    mark_pay_at_store_paid,
    record_customer_frame_received,
    start_order_processing,
    transition_retail_order,
)


User = get_user_model()


class RetailOrderOperationTests(TestCase):
    def setUp(self):
        self.state = IndianState.values[0]

        self.user = User.objects.create_user(
            username="operations-customer",
            email="operations@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.staff = User.objects.create_user(
            username="operations-staff",
            phone_number="+919876543211",
            phone_verified=True,
            is_staff=True,
        )
        self.non_staff = User.objects.create_user(
            username="operations-non-staff",
            phone_number="+919876543212",
            phone_verified=True,
        )
        self.superuser = User.objects.create_superuser(
            username="operations-superuser",
            email="admin@example.com",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="retail_orders",
            codename="change_retailorder",
        )
        self.staff.user_permissions.add(permission)

        RetailCheckoutPolicy.objects.create(
            name="Operations policy",
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
            recipient_name="Operations Customer",
            phone_number="+919876543210",
            address_line_1="10 Operations Road",
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
            name="Operations Black"
        )
        design = ProductDesign.objects.create(
            name="Operations Product",
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

    def create_cart(self, quantity=1):
        cart = get_or_create_open_retail_cart(
            user=self.user
        )
        add_standard_offer(
            cart=cart,
            offer=self.offer,
            quantity=quantity,
        )
        return cart

    def create_pickup_order(self, quantity=1):
        cart = self.create_cart(quantity=quantity)

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

    def create_delivery_order(self, quantity=1):
        cart = self.create_cart(quantity=quantity)

        result = create_retail_checkout(
            cart=cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

        confirm_online_payment(
            payment_attempt=result.payment_attempt,
            provider_payment_id=(
                f"pay_operations_{result.payment_attempt.pk}"
            ),
            provider_signature="verified",
            signature_verified=True,
        )

        result.order.refresh_from_db()
        return result

    def test_non_staff_cannot_operate_order(self):
        result = self.create_pickup_order()

        with self.assertRaises(
            RetailOrderOperationError
        ) as context:
            start_order_processing(
                order=result.order,
                actor=self.non_staff,
            )

        self.assertEqual(
            context.exception.code,
            "staff_access_required",
        )

    def test_pickup_order_requires_payment_before_delivery(self):
        result = self.create_pickup_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
        )
        mark_order_ready_for_pickup(
            order=result.order,
            actor=self.staff,
        )

        with self.assertRaises(
            RetailOrderOperationError
        ) as context:
            mark_order_delivered(
                order=result.order,
                actor=self.staff,
            )

        self.assertEqual(
            context.exception.code,
            "pay_at_store_payment_required",
        )

    def test_pickup_order_can_be_paid_and_completed(self):
        result = self.create_pickup_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
            note="Order accepted.",
        )
        mark_order_ready_for_pickup(
            order=result.order,
            actor=self.staff,
            note="Ready at counter.",
        )
        mark_pay_at_store_paid(
            order=result.order,
            actor=self.staff,
            receipt_reference="STORE-001",
        )
        order = mark_order_delivered(
            order=result.order,
            actor=self.staff,
            note="Collected by customer.",
        )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            RetailOrder.Status.DELIVERED,
        )
        self.assertEqual(
            order.payment_status,
            RetailOrder.PaymentStatus.PAID,
        )
        self.assertEqual(
            order.status_history.count(),
            3,
        )
        self.assertEqual(
            list(
                order.status_history.values_list(
                    "new_status",
                    flat=True,
                )
            ),
            [
                RetailOrder.Status.PROCESSING,
                RetailOrder.Status.READY_FOR_PICKUP,
                RetailOrder.Status.DELIVERED,
            ],
        )

    def test_shipping_requires_carrier_and_tracking(self):
        result = self.create_delivery_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
        )
        mark_order_packed(
            order=result.order,
            actor=self.staff,
        )

        with self.assertRaises(
            RetailOrderOperationError
        ) as context:
            mark_order_shipped(
                order=result.order,
                actor=self.staff,
                carrier_name="",
                tracking_number="",
            )

        self.assertEqual(
            context.exception.code,
            "carrier_required",
        )

    def test_delivery_order_follows_full_flow(self):
        result = self.create_delivery_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
        )
        mark_order_packed(
            order=result.order,
            actor=self.staff,
        )
        mark_order_shipped(
            order=result.order,
            actor=self.staff,
            carrier_name="Test Courier",
            tracking_number="TRACK-001",
        )
        order = mark_order_delivered(
            order=result.order,
            actor=self.staff,
        )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            RetailOrder.Status.DELIVERED,
        )

        main_group = order.fulfillment_groups.get(
            group_type=(
                RetailFulfillmentGroup
                .GroupType.MAIN_DELIVERY
            )
        )

        self.assertEqual(
            main_group.status,
            RetailFulfillmentGroup.Status.DELIVERED,
        )
        self.assertEqual(
            main_group.carrier_name,
            "Test Courier",
        )
        self.assertEqual(
            main_group.tracking_number,
            "TRACK-001",
        )

        event_types = set(
            order.notification_events.values_list(
                "event_type",
                flat=True,
            )
        )

        self.assertTrue(
            {
                RetailOrderNotificationEvent
                .EventType.PAYMENT_CONFIRMED,
                RetailOrderNotificationEvent
                .EventType.PROCESSING,
                RetailOrderNotificationEvent
                .EventType.SHIPPED,
                RetailOrderNotificationEvent
                .EventType.DELIVERED,
            }.issubset(event_types)
        )

    def test_backward_transition_is_rejected(self):
        result = self.create_delivery_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
        )
        mark_order_packed(
            order=result.order,
            actor=self.staff,
        )

        with self.assertRaises(
            RetailOrderOperationError
        ) as context:
            transition_retail_order(
                order=result.order,
                new_status=RetailOrder.Status.PROCESSING,
                actor=self.staff,
            )

        self.assertEqual(
            context.exception.code,
            "invalid_status_transition",
        )

    def test_superuser_can_explicitly_override_transition(self):
        result = self.create_delivery_order()

        start_order_processing(
            order=result.order,
            actor=self.superuser,
        )
        mark_order_packed(
            order=result.order,
            actor=self.superuser,
        )

        order = transition_retail_order(
            order=result.order,
            new_status=RetailOrder.Status.PROCESSING,
            actor=self.superuser,
            note="Administrative correction.",
            allow_superuser_override=True,
        )

        self.assertEqual(
            order.status,
            RetailOrder.Status.PROCESSING,
        )
        self.assertTrue(
            order.status_history.latest("pk").metadata[
                "superuser_override"
            ]
        )

    def test_customer_frame_receipt_is_audited(self):
        result = self.create_pickup_order()

        group = RetailFulfillmentGroup.objects.create(
            order=result.order,
            group_type=(
                RetailFulfillmentGroup
                .GroupType.CUSTOMER_FRAME_INBOUND
            ),
            title="Customer frame inbound",
            store_location=self.store,
        )

        record_customer_frame_received(
            fulfillment_group=group,
            actor=self.staff,
            note="Frame received undamaged.",
        )

        group.refresh_from_db()

        self.assertEqual(
            group.status,
            RetailFulfillmentGroup.Status.COMPLETED,
        )

        history = group.status_history.get()

        self.assertEqual(
            history.new_status,
            RetailFulfillmentGroup.Status.COMPLETED,
        )
        self.assertEqual(history.changed_by, self.staff)
        self.assertEqual(
            history.note,
            "Frame received undamaged.",
        )

    def test_expiry_command_releases_stock_and_reopens_cart(self):
        cart = self.create_cart()

        result = create_retail_checkout(
            cart=cart,
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.DELIVERY
            ),
            payment_method=(
                RetailOrder.PaymentMethod.RAZORPAY
            ),
            shipping_address=self.address,
        )

        past = timezone.now() - timedelta(minutes=1)

        RetailPaymentAttempt.objects.filter(
            pk=result.payment_attempt.pk
        ).update(expires_at=past)

        RetailStockReservation.objects.filter(
            order=result.order
        ).update(expires_at=past)

        output = StringIO()

        call_command(
            "expire_retail_payments",
            stdout=output,
        )

        result.order.refresh_from_db()
        cart.refresh_from_db()

        self.assertEqual(
            result.order.status,
            RetailOrder.Status.PAYMENT_FAILED,
        )
        self.assertEqual(
            cart.status,
            RetailCart.Status.OPEN,
        )
        self.assertEqual(
            result.order.stock_reservations.get().status,
            RetailStockReservation.Status.EXPIRED,
        )
        self.assertEqual(
            result.order.status_history.get().new_status,
            RetailOrder.Status.PAYMENT_FAILED,
        )
        self.assertIn(
            "Expired 1 retail payment attempt",
            output.getvalue(),
        )

    def test_order_and_group_changes_have_history(self):
        result = self.create_pickup_order()

        start_order_processing(
            order=result.order,
            actor=self.staff,
            note="Start processing.",
        )

        self.assertEqual(
            RetailOrderStatusHistory.objects.filter(
                order=result.order
            ).count(),
            1,
        )
        self.assertGreaterEqual(
            RetailFulfillmentStatusHistory.objects.filter(
                fulfillment_group__order=result.order
            ).count(),
            1,
        )
