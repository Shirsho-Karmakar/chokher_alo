from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

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
    RetailOrder,
    StoreLocation,
)
from apps.retail_orders.services import (
    confirm_online_payment,
    create_retail_checkout,
)


User = get_user_model()


class RetailStaffOrderAPIViewTests(TestCase):
    def setUp(self):
        self.state = IndianState.values[0]

        self.customer = User.objects.create_user(
            username="staff-api-customer",
            email="customer@example.com",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.staff = User.objects.create_user(
            username="staff-api-manager",
            phone_number="+919876543211",
            phone_verified=True,
            is_staff=True,
        )
        self.unprivileged_staff = User.objects.create_user(
            username="staff-api-unprivileged",
            phone_number="+919876543212",
            phone_verified=True,
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="staff-api-superuser",
            email="superuser@example.com",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="retail_orders",
            codename="change_retailorder",
        )
        self.staff.user_permissions.add(permission)

        RetailCheckoutPolicy.objects.create(
            name="Staff API policy",
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
            user=self.customer,
            recipient_name="Staff API Customer",
            phone_number="+919876543210",
            address_line_1="10 Staff API Road",
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
            name="Staff API Black"
        )
        design = ProductDesign.objects.create(
            name="Staff API Product",
            kind=ProductDesign.Kind.ACCESSORY,
            status=ProductDesign.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=30,
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
            user=self.customer
        )
        add_standard_offer(
            cart=cart,
            offer=self.offer,
            quantity=quantity,
        )
        return cart

    def create_pickup_order(self, quantity=1):
        return create_retail_checkout(
            cart=self.create_cart(quantity),
            fulfillment_method=(
                RetailOrder.FulfillmentMethod.STORE_PICKUP
            ),
            payment_method=(
                RetailOrder.PaymentMethod.PAY_AT_STORE
            ),
            billing_address=self.address,
        )

    def create_delivery_order(self, quantity=1):
        result = create_retail_checkout(
            cart=self.create_cart(quantity),
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
                f"pay_staff_api_{result.payment_attempt.pk}"
            ),
            provider_signature="verified",
            signature_verified=True,
        )

        result.order.refresh_from_db()
        return result

    def test_staff_order_list_requires_login(self):
        response = self.client.get(
            reverse("retail_orders:staff_order_list")
        )

        self.assertEqual(response.status_code, 302)

    def test_staff_order_list_requires_permission(self):
        self.client.force_login(self.unprivileged_staff)

        response = self.client.get(
            reverse("retail_orders:staff_order_list")
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"]["code"],
            "order_permission_required",
        )

    def test_staff_can_filter_and_search_orders(self):
        result = self.create_pickup_order()
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("retail_orders:staff_order_list"),
            {
                "status": RetailOrder.Status.CONFIRMED,
                "q": result.order.order_number,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"]["total_items"],
            1,
        )
        self.assertEqual(
            response.json()["orders"][0]["order_number"],
            result.order.order_number,
        )

    def test_start_processing_endpoint_creates_audit(self):
        result = self.create_pickup_order()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "retail_orders:staff_start_processing",
                kwargs={
                    "order_number": (
                        result.order.order_number
                    )
                },
            ),
            {"note": "Accepted by staff."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["order"]["status"],
            RetailOrder.Status.PROCESSING,
        )
        self.assertEqual(
            response.json()["order"]["status_history"][0][
                "note"
            ],
            "Accepted by staff.",
        )

    def test_staff_detail_includes_available_actions(self):
        result = self.create_pickup_order()
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse(
                "retail_orders:staff_order_detail",
                kwargs={
                    "order_number": (
                        result.order.order_number
                    )
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "start_processing",
            response.json()["order"]["staff_operations"][
                "order_actions"
            ],
        )

    def test_shipping_requires_tracking_fields(self):
        result = self.create_delivery_order()
        self.client.force_login(self.staff)

        self.client.post(
            reverse(
                "retail_orders:staff_start_processing",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )
        self.client.post(
            reverse(
                "retail_orders:staff_mark_packed",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        response = self.client.post(
            reverse(
                "retail_orders:staff_mark_shipped",
                kwargs={
                    "order_number": result.order.order_number
                },
            ),
            {},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "invalid_request",
        )

    def test_delivery_order_can_complete_through_api(self):
        result = self.create_delivery_order()
        self.client.force_login(self.staff)

        self.client.post(
            reverse(
                "retail_orders:staff_start_processing",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )
        self.client.post(
            reverse(
                "retail_orders:staff_mark_packed",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        shipped = self.client.post(
            reverse(
                "retail_orders:staff_mark_shipped",
                kwargs={
                    "order_number": result.order.order_number
                },
            ),
            {
                "carrier_name": "Test Courier",
                "tracking_number": "TRACK-API-1",
            },
        )
        delivered = self.client.post(
            reverse(
                "retail_orders:staff_mark_delivered",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        self.assertEqual(shipped.status_code, 200)
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(
            delivered.json()["order"]["status"],
            RetailOrder.Status.DELIVERED,
        )

    def test_pickup_payment_and_delivery_flow(self):
        result = self.create_pickup_order()
        self.client.force_login(self.staff)

        self.client.post(
            reverse(
                "retail_orders:staff_start_processing",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )
        self.client.post(
            reverse(
                "retail_orders:staff_ready_for_pickup",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        payment = self.client.post(
            reverse(
                "retail_orders:staff_record_store_payment",
                kwargs={
                    "order_number": result.order.order_number
                },
            ),
            {"receipt_reference": "STORE-API-1"},
        )
        delivered = self.client.post(
            reverse(
                "retail_orders:staff_mark_delivered",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        self.assertEqual(payment.status_code, 200)
        self.assertEqual(
            payment.json()["order"]["payment_status"],
            RetailOrder.PaymentStatus.PAID,
        )
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(
            delivered.json()["order"]["status"],
            RetailOrder.Status.DELIVERED,
        )

    def test_customer_frame_receipt_endpoint_is_audited(self):
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

        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "retail_orders:staff_customer_frame_received",
                kwargs={"group_id": group.pk},
            ),
            {"note": "Frame received safely."},
        )

        self.assertEqual(response.status_code, 200)

        group.refresh_from_db()

        self.assertEqual(
            group.status,
            RetailFulfillmentGroup.Status.COMPLETED,
        )
        self.assertEqual(
            group.status_history.get().note,
            "Frame received safely.",
        )

    def test_invalid_transition_returns_conflict(self):
        result = self.create_pickup_order()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "retail_orders:staff_mark_delivered",
                kwargs={
                    "order_number": result.order.order_number
                },
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"],
            "invalid_status_transition",
        )

    def test_superuser_can_access_staff_order_api(self):
        self.create_pickup_order()
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("retail_orders:staff_order_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["pagination"]["total_items"],
            1,
        )
