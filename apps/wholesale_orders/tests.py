from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.lenses.models import (
    LensPrescriptionRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
from apps.locations.constants import IndianState
from apps.locations.models import Address
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)
from apps.wholesale.models import WholesaleAccount
from apps.wholesale_catalog.models import (
    WholesaleLensListing,
    WholesaleLensVariant,
)
from apps.wholesale_cart.models import WholesaleCart
from apps.wholesale_cart.services import (
    get_or_create_open_wholesale_cart,
    set_wholesale_cart_item,
)

from .models import (
    WholesaleOrder,
    WholesalePaymentAttempt,
    WholesaleStockReservation,
)
from .services import (
    WholesaleCheckoutError,
    cancel_wholesale_checkout,
    start_wholesale_checkout,
)


User = get_user_model()


class WholesaleCheckoutFoundationTests(TestCase):
    def setUp(self):
        self.colour = Colour.objects.create(
            name="Wholesale Order Clear"
        )

        design = ProductDesign.objects.create(
            name="Wholesale Order Lens",
            kind=ProductDesign.Kind.LENS,
            status=ProductDesign.Status.ACTIVE,
        )
        self.physical_variant = ProductVariant.objects.create(
            design=design,
            colour=self.colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=100,
        )
        offer = ProductOffer.objects.create(
            variant=self.physical_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("600.00"),
            selling_price_including_gst=Decimal("500.00"),
            gst_rate=Decimal("18.00"),
            requires_prescription=True,
            status=ProductOffer.Status.AVAILABLE,
        )
        vision_type = LensVisionType.objects.create(
            code="SV-ORDER",
            name="Single Vision Wholesale Order",
        )
        refractive_index = (
            LensRefractiveIndex.objects.create(
                value=Decimal("1.59"),
                display_name="Wholesale Order Index",
            )
        )
        lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
            is_powered=True,
            require_both_eyes=False,
            selling_unit=(
                LensSpecification.SellingUnit.INDIVIDUAL
            ),
        )
        rule = LensPrescriptionRule.objects.create(
            lens=lens,
            name="Wholesale order range",
            minimum_sphere=Decimal("-6.00"),
            maximum_sphere=Decimal("0.00"),
            minimum_cylinder=Decimal("-2.00"),
            maximum_cylinder=Decimal("0.00"),
        )
        listing = WholesaleLensListing.objects.create(
            lens=lens,
            catalogue_code="ORDER.SV",
            name="Wholesale Order Single Vision",
            box_contents_unit=(
                WholesaleLensListing
                .BoxContentsUnit.INDIVIDUAL_LENS
            ),
            units_per_box=2,
            status=WholesaleLensListing.Status.ACTIVE,
        )
        self.variant = WholesaleLensVariant.objects.create(
            listing=listing,
            prescription_rule=rule,
            base_box_price_including_gst=(
                Decimal("1000.00")
            ),
            boxes_in_stock=20,
            minimum_order_boxes=1,
            order_multiple_boxes=1,
            status=WholesaleLensVariant.Status.AVAILABLE,
        )

        (
            self.user,
            self.account,
            self.address,
            self.prescription,
        ) = self.create_customer(
            username="wholesale-order-user",
            phone_number="+919876543210",
        )

    def create_customer(
        self,
        *,
        username,
        phone_number,
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            email_verified=True,
            phone_number=phone_number,
            phone_verified=True,
        )
        account = WholesaleAccount.objects.create(
            user=user,
            status=WholesaleAccount.Status.APPROVED,
            business_name=f"{username} Optical",
            contact_person_name=f"{username} Manager",
            invoice_email=f"invoice-{username}@example.com",
            gstin="22AAAAA0000A1Z5",
        )
        address = Address.objects.create(
            user=user,
            recipient_name=f"{username} Manager",
            phone_number=phone_number,
            address_line_1="10 Wholesale Order Road",
            city="Kolkata",
            district="Kolkata",
            state=IndianState.values[0],
            postal_code="700001",
            is_default_billing=True,
        )
        prescription = Prescription.objects.create(
            user=user,
            prescription_file=SimpleUploadedFile(
                f"{username}.pdf",
                b"%PDF-1.4 wholesale order",
                content_type="application/pdf",
            ),
            status=Prescription.Status.APPROVED,
        )
        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-2.00"),
            cylinder=Decimal("-0.50"),
            axis=90,
        )
        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            sphere=Decimal("-1.50"),
            cylinder=Decimal("-0.25"),
            axis=90,
        )

        return user, account, address, prescription

    def create_ready_cart(
        self,
        *,
        user=None,
        prescription=None,
        boxes=2,
    ):
        user = user or self.user
        prescription = prescription or self.prescription

        cart = get_or_create_open_wholesale_cart(
            user=user
        )
        set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=boxes,
        )

        return cart

    def start_checkout(self, *, cart=None):
        cart = cart or self.create_ready_cart()

        return start_wholesale_checkout(
            cart=cart,
            payment_method=(
                WholesalePaymentAttempt.Method.BANK_TRANSFER
            ),
            reservation_minutes=30,
        )

    def test_checkout_creates_immutable_snapshots(self):
        result = self.start_checkout()
        order = result.order
        item = order.items.get()

        self.assertTrue(result.created)
        self.assertEqual(
            order.status,
            WholesaleOrder.Status.PAYMENT_PENDING,
        )
        self.assertEqual(order.total_boxes, 2)
        self.assertEqual(
            order.grand_total_including_gst,
            Decimal("2000.00"),
        )
        self.assertEqual(
            order.business_snapshot["business_name"],
            self.account.business_name,
        )
        self.assertEqual(
            order.billing_address.postal_code,
            "700001",
        )
        self.assertEqual(
            item.prescription_snapshot["sphere"],
            "-2.00",
        )
        self.assertEqual(
            item.variant_snapshot["catalogue_code"],
            "ORDER.SV",
        )

    def test_checkout_creates_payment_and_fulfillment(self):
        result = self.start_checkout()

        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.PENDING,
        )
        self.assertEqual(
            result.payment_attempt.amount_including_gst,
            result.order.grand_total_including_gst,
        )
        self.assertEqual(
            result.fulfillment.status,
            result.fulfillment.Status.PENDING,
        )

    def test_checkout_reserves_without_consuming_stock(self):
        result = self.start_checkout()

        reservation = (
            result.order.stock_reservations.get()
        )

        self.variant.refresh_from_db()
        self.physical_variant.refresh_from_db()

        self.assertEqual(
            reservation.boxes_reserved,
            2,
        )
        self.assertEqual(
            reservation.physical_units_reserved,
            4,
        )
        self.assertEqual(
            self.variant.boxes_in_stock,
            20,
        )
        self.assertEqual(
            self.physical_variant.stock_quantity,
            100,
        )

    def test_active_checkout_creation_is_idempotent(self):
        cart = self.create_ready_cart()

        first = self.start_checkout(cart=cart)
        second = self.start_checkout(cart=cart)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(
            first.order.pk,
            second.order.pk,
        )
        self.assertEqual(
            WholesaleOrder.objects.count(),
            1,
        )

    def test_active_checkout_cart_is_not_reopened(self):
        result = self.start_checkout()

        reopened = get_or_create_open_wholesale_cart(
            user=self.user
        )

        self.assertEqual(
            reopened.pk,
            result.order.source_cart_id,
        )
        self.assertEqual(
            reopened.status,
            WholesaleCart.Status.CHECKOUT_STARTED,
        )

    def test_wholesale_stock_cannot_be_overreserved(self):
        self.variant.boxes_in_stock = 3
        self.variant.save()

        first_cart = self.create_ready_cart(
            boxes=2
        )
        self.start_checkout(cart=first_cart)

        (
            second_user,
            _second_account,
            _second_address,
            second_prescription,
        ) = self.create_customer(
            username="second-wholesale-order-user",
            phone_number="+919876543211",
        )
        second_cart = self.create_ready_cart(
            user=second_user,
            prescription=second_prescription,
            boxes=2,
        )

        with self.assertRaises(
            WholesaleCheckoutError
        ) as context:
            self.start_checkout(cart=second_cart)

        self.assertEqual(
            context.exception.code,
            "insufficient_available_wholesale_stock",
        )

    def test_shared_stock_cannot_be_overreserved(self):
        self.variant.boxes_in_stock = 20
        self.variant.save()

        self.physical_variant.stock_quantity = 3
        self.physical_variant.save()

        first_cart = self.create_ready_cart(
            boxes=1
        )
        self.start_checkout(cart=first_cart)

        (
            second_user,
            _second_account,
            _second_address,
            second_prescription,
        ) = self.create_customer(
            username="shared-stock-order-user",
            phone_number="+919876543212",
        )
        second_cart = self.create_ready_cart(
            user=second_user,
            prescription=second_prescription,
            boxes=1,
        )

        with self.assertRaises(
            WholesaleCheckoutError
        ) as context:
            self.start_checkout(cart=second_cart)

        self.assertEqual(
            context.exception.code,
            "insufficient_available_shared_stock",
        )

    def test_cancellation_releases_reservations(self):
        result = self.start_checkout()

        cancelled = cancel_wholesale_checkout(
            order=result.order,
            reason="Customer requested cancellation.",
        )

        reservation = (
            cancelled.stock_reservations.get()
        )
        result.payment_attempt.refresh_from_db()
        cancelled.source_cart.refresh_from_db()

        self.assertEqual(
            cancelled.status,
            WholesaleOrder.Status.CANCELLED,
        )
        self.assertEqual(
            reservation.status,
            WholesaleStockReservation.Status.RELEASED,
        )
        self.assertEqual(
            result.payment_attempt.status,
            WholesalePaymentAttempt.Status.CANCELLED,
        )
        self.assertEqual(
            cancelled.source_cart.status,
            WholesaleCart.Status.OPEN,
        )

    def test_address_snapshot_does_not_follow_source(self):
        result = self.start_checkout()

        self.address.address_line_1 = "Changed Later"
        self.address.save()

        result.order.billing_address.refresh_from_db()

        self.assertEqual(
            result.order.billing_address.address_line_1,
            "10 Wholesale Order Road",
        )

    def test_order_item_price_does_not_follow_catalogue(self):
        result = self.start_checkout()
        item = result.order.items.get()

        self.variant.base_box_price_including_gst = (
            Decimal("1500.00")
        )
        self.variant.save()

        item.refresh_from_db()

        self.assertEqual(
            item.applied_box_price_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(
            item.subtotal_including_gst,
            Decimal("2000.00"),
        )
