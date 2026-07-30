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
    WholesaleBulkPriceTier,
    WholesaleLensListing,
    WholesaleLensVariant,
)

from .models import WholesaleCart, WholesaleCartItem
from .services import (
    WholesaleCartError,
    get_or_create_open_wholesale_cart,
    revalidate_wholesale_cart,
    set_wholesale_cart_item,
)


User = get_user_model()


class WholesaleCartServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="wholesale-cart-user",
            email="wholesale-cart@example.com",
            email_verified=True,
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.account = WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
            business_name="Cart Optical",
            contact_person_name="Cart Manager",
            invoice_email="invoice@example.com",
        )

        Address.objects.create(
            user=self.user,
            recipient_name="Cart Optical",
            phone_number="+919876543210",
            address_line_1="10 Wholesale Road",
            city="Kolkata",
            district="Kolkata",
            state=IndianState.values[0],
            postal_code="700001",
            is_default_billing=True,
        )

        self.unapproved_user = User.objects.create_user(
            username="unapproved-cart-user",
            email="unapproved-cart@example.com",
            phone_number="+919876543211",
            phone_verified=True,
        )
        WholesaleAccount.objects.create(
            user=self.unapproved_user,
            status=WholesaleAccount.Status.UNVERIFIED,
        )

        colour = Colour.objects.create(
            name="Wholesale Clear"
        )
        design = ProductDesign.objects.create(
            name="Wholesale Cart Lens",
            kind=ProductDesign.Kind.LENS,
            status=ProductDesign.Status.ACTIVE,
        )
        self.physical_variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
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
            code="SV-CART",
            name="Single Vision Cart",
        )
        refractive_index = (
            LensRefractiveIndex.objects.create(
                value=Decimal("1.56"),
                display_name="Cart Index",
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
            name="Minus six cart range",
            minimum_sphere=Decimal("-6.00"),
            maximum_sphere=Decimal("0.00"),
            minimum_cylinder=Decimal("-2.00"),
            maximum_cylinder=Decimal("0.00"),
        )
        listing = WholesaleLensListing.objects.create(
            lens=lens,
            catalogue_code="CART.SV",
            name="Wholesale Cart Single Vision",
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
        WholesaleBulkPriceTier.objects.create(
            variant=self.variant,
            minimum_boxes=10,
            box_price_including_gst=Decimal("800.00"),
        )

        self.prescription = self.create_prescription(
            user=self.user,
            right_sphere=Decimal("-2.00"),
            left_sphere=Decimal("-1.50"),
        )

    def create_prescription(
        self,
        *,
        user,
        right_sphere,
        left_sphere,
    ):
        prescription = Prescription.objects.create(
            user=user,
            prescription_file=SimpleUploadedFile(
                "wholesale-cart.pdf",
                b"%PDF-1.4 wholesale cart",
                content_type="application/pdf",
            ),
            status=Prescription.Status.APPROVED,
        )

        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=right_sphere,
            cylinder=Decimal("-0.50"),
            axis=90,
        )
        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            sphere=left_sphere,
            cylinder=Decimal("-0.25"),
            axis=90,
        )

        return prescription

    def test_unapproved_account_cannot_open_cart(self):
        with self.assertRaises(
            WholesaleCartError
        ) as context:
            get_or_create_open_wholesale_cart(
                user=self.unapproved_user
            )

        self.assertEqual(
            context.exception.code,
            "wholesale_access_required",
        )

    def test_only_one_active_cart_is_reused(self):
        first = get_or_create_open_wholesale_cart(
            user=self.user
        )
        second = get_or_create_open_wholesale_cart(
            user=self.user
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            WholesaleCart.objects.count(),
            1,
        )

    def test_checkout_started_cart_is_reopened(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        cart.status = WholesaleCart.Status.CHECKOUT_STARTED
        cart.save()

        reopened = get_or_create_open_wholesale_cart(
            user=self.user
        )

        self.assertEqual(reopened.pk, cart.pk)
        self.assertEqual(
            reopened.status,
            WholesaleCart.Status.OPEN,
        )

    def test_valid_item_gets_price_and_power_snapshots(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )

        item = set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=5,
        )

        self.assertEqual(
            item.validation_status,
            WholesaleCartItem.ValidationStatus.VALID,
        )
        self.assertEqual(
            item.applied_box_price_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(
            item.subtotal_including_gst,
            Decimal("5000.00"),
        )
        self.assertEqual(
            item.prescription_snapshot["sphere"],
            "-2.00",
        )
        self.assertEqual(
            item.variant_snapshot["physical_units_per_box"],
            2,
        )

    def test_other_users_prescription_is_rejected(self):
        other_user = User.objects.create_user(
            username="other-prescription-owner",
            email="other-prescription@example.com",
            phone_number="+919876543212",
            phone_verified=True,
        )
        other_prescription = self.create_prescription(
            user=other_user,
            right_sphere=Decimal("-2.00"),
            left_sphere=Decimal("-1.00"),
        )
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )

        with self.assertRaises(
            WholesaleCartError
        ) as context:
            set_wholesale_cart_item(
                cart=cart,
                variant=self.variant,
                prescription=other_prescription,
                eye=PrescriptionEyeValue.Eye.RIGHT,
                boxes=1,
            )

        self.assertEqual(
            context.exception.code,
            "prescription_not_owned",
        )

    def test_incompatible_eye_is_rejected(self):
        incompatible = self.create_prescription(
            user=self.user,
            right_sphere=Decimal("5.00"),
            left_sphere=Decimal("-1.00"),
        )
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )

        with self.assertRaises(
            WholesaleCartError
        ) as context:
            set_wholesale_cart_item(
                cart=cart,
                variant=self.variant,
                prescription=incompatible,
                eye=PrescriptionEyeValue.Eye.RIGHT,
                boxes=1,
            )

        self.assertEqual(
            context.exception.code,
            "prescription_range_mismatch",
        )

    def test_bulk_price_uses_total_boxes_for_same_sku(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )

        right = set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=5,
        )
        left = set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            boxes=5,
        )

        right.refresh_from_db()
        left.refresh_from_db()

        self.assertEqual(
            right.applied_box_price_including_gst,
            Decimal("800.00"),
        )
        self.assertEqual(
            left.applied_box_price_including_gst,
            Decimal("800.00"),
        )
        self.assertEqual(
            right.pricing_snapshot[
                "aggregate_variant_boxes"
            ],
            10,
        )

    def test_aggregate_wholesale_stock_is_enforced(self):
        self.variant.boxes_in_stock = 9
        self.variant.save()

        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=5,
        )

        with self.assertRaises(
            WholesaleCartError
        ) as context:
            set_wholesale_cart_item(
                cart=cart,
                variant=self.variant,
                prescription=self.prescription,
                eye=PrescriptionEyeValue.Eye.LEFT,
                boxes=5,
            )

        self.assertEqual(
            context.exception.code,
            "insufficient_wholesale_stock",
        )

    def test_shared_physical_stock_is_enforced(self):
        self.physical_variant.stock_quantity = 9
        self.physical_variant.save()

        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )

        with self.assertRaises(
            WholesaleCartError
        ) as context:
            set_wholesale_cart_item(
                cart=cart,
                variant=self.variant,
                prescription=self.prescription,
                eye=PrescriptionEyeValue.Eye.RIGHT,
                boxes=5,
            )

        self.assertEqual(
            context.exception.code,
            "insufficient_shared_stock",
        )

    def test_revalidation_refreshes_changed_price(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        item = set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=5,
        )

        self.variant.base_box_price_including_gst = (
            Decimal("1100.00")
        )
        self.variant.save()

        revalidate_wholesale_cart(cart=cart)
        item.refresh_from_db()

        self.assertEqual(
            item.applied_box_price_including_gst,
            Decimal("1100.00"),
        )

    def test_incomplete_business_details_block_checkout(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=1,
        )

        self.account.business_name = ""
        self.account.save(
            update_fields=[
                "business_name",
                "updated_at",
            ]
        )

        readiness = revalidate_wholesale_cart(
            cart=cart
        )

        self.assertFalse(readiness.ready)
        self.assertIn(
            "business_name",
            readiness.missing_checkout_details,
        )

    def test_complete_valid_cart_is_checkout_ready(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=2,
        )

        readiness = revalidate_wholesale_cart(
            cart=cart
        )

        self.assertTrue(readiness.ready)
        self.assertEqual(
            readiness.subtotal_including_gst,
            Decimal("2000.00"),
        )

    def test_suspended_account_invalidates_cart(self):
        cart = get_or_create_open_wholesale_cart(
            user=self.user
        )
        item = set_wholesale_cart_item(
            cart=cart,
            variant=self.variant,
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            boxes=1,
        )

        self.account.status = WholesaleAccount.Status.SUSPENDED
        self.account.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        readiness = revalidate_wholesale_cart(
            cart=cart
        )
        item.refresh_from_db()

        self.assertFalse(readiness.ready)
        self.assertEqual(
            item.validation_code,
            "wholesale_access_required",
        )
