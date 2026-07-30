import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.lenses.models import (
    LensCoating,
    LensPrescriptionRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
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


User = get_user_model()


class WholesaleCatalogueViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.temporary_media = tempfile.TemporaryDirectory()
        cls.media_override = override_settings(
            MEDIA_ROOT=cls.temporary_media.name
        )
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        cls.temporary_media.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username="approved-wholesale-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        WholesaleAccount.objects.create(
            user=self.user,
            status=WholesaleAccount.Status.APPROVED,
        )

        self.retail_user = User.objects.create_user(
            username="retail-only-user",
            phone_number="+919876543211",
            phone_verified=True,
        )

        self.unapproved_user = User.objects.create_user(
            username="unapproved-wholesale-user",
            phone_number="+919876543212",
            phone_verified=True,
        )
        WholesaleAccount.objects.create(
            user=self.unapproved_user,
            status=WholesaleAccount.Status.UNVERIFIED,
        )

        self.other_user = User.objects.create_user(
            username="other-prescription-user",
            phone_number="+919876543213",
            phone_verified=True,
        )

        colour = Colour.objects.create(
            name="Protected Wholesale Clear"
        )
        design = ProductDesign.objects.create(
            name="Protected Wholesale Lens",
            kind=ProductDesign.Kind.LENS,
            status=ProductDesign.Status.ACTIVE,
        )
        product_variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )
        offer = ProductOffer.objects.create(
            variant=product_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("1200.00"),
            selling_price_including_gst=Decimal("900.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="WSV",
            name="Protected Wholesale Vision",
        )
        refractive_index = LensRefractiveIndex.objects.create(
            value=Decimal("1.61"),
        )
        lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
        )

        self.coating = LensCoating.objects.create(
            code="HC",
            name="Protected HC",
        )
        lens.coatings.add(self.coating)

        self.matching_rule = LensPrescriptionRule.objects.create(
            lens=lens,
            name="Minus range",
            minimum_sphere=Decimal("-6.00"),
            maximum_sphere=Decimal("0.00"),
            minimum_cylinder=Decimal("-2.00"),
            maximum_cylinder=Decimal("0.00"),
        )
        self.nonmatching_rule = (
            LensPrescriptionRule.objects.create(
                lens=lens,
                name="Strong positive range",
                minimum_sphere=Decimal("5.00"),
                maximum_sphere=Decimal("10.00"),
            )
        )

        listing = WholesaleLensListing.objects.create(
            lens=lens,
            catalogue_code="WSV.CR",
            name="Protected Wholesale Listing",
            status=WholesaleLensListing.Status.ACTIVE,
            units_per_box=10,
        )

        self.variant = WholesaleLensVariant.objects.create(
            listing=listing,
            prescription_rule=self.matching_rule,
            coating=self.coating,
            base_box_price_including_gst=Decimal("1000.00"),
            boxes_in_stock=50,
            minimum_order_boxes=5,
            order_multiple_boxes=5,
            status=WholesaleLensVariant.Status.AVAILABLE,
            internal_notes="Never expose this note.",
        )

        self.nonmatching_variant = (
            WholesaleLensVariant.objects.create(
                listing=listing,
                prescription_rule=self.nonmatching_rule,
                coating=self.coating,
                base_box_price_including_gst=Decimal("1100.00"),
                boxes_in_stock=50,
                minimum_order_boxes=5,
                order_multiple_boxes=5,
                status=WholesaleLensVariant.Status.AVAILABLE,
            )
        )

        WholesaleBulkPriceTier.objects.create(
            variant=self.variant,
            minimum_boxes=10,
            maximum_boxes=24,
            box_price_including_gst=Decimal("900.00"),
        )
        WholesaleBulkPriceTier.objects.create(
            variant=self.variant,
            minimum_boxes=25,
            maximum_boxes=None,
            box_price_including_gst=Decimal("800.00"),
        )

        self.prescription = self.create_prescription(
            user=self.user,
            status=Prescription.Status.APPROVED,
        )

    def create_prescription(self, *, user, status):
        prescription = Prescription.objects.create(
            user=user,
            prescription_file=SimpleUploadedFile(
                "prescription.jpg",
                b"wholesale-prescription",
                content_type="image/jpeg",
            ),
            status=status,
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

        return prescription

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(
                "/wholesale/login/?next="
            )
        )

    def test_retail_user_is_forbidden(self):
        self.client.force_login(self.retail_user)

        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 403)

    def test_unapproved_wholesale_user_is_forbidden(self):
        self.client.force_login(self.unapproved_user)

        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 403)

    def test_approved_user_sees_only_matching_rows(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["count"], 1)
        self.assertEqual(
            data["variants"][0]["variant_id"],
            self.variant.pk,
        )
        self.assertEqual(
            set(data["variants"][0]["matching_eyes"]),
            {"right", "left"},
        )

        response_text = response.content.decode()

        self.assertNotIn("boxes_in_stock", response_text)
        self.assertNotIn("internal_notes", response_text)
        self.assertNotIn(
            "Never expose this note.",
            response_text,
        )

    def test_pending_prescription_is_rejected(self):
        pending = self.create_prescription(
            user=self.user,
            status=Prescription.Status.PENDING,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {"prescription_id": pending.pk},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"],
            "prescription_not_approved",
        )

    def test_other_users_prescription_returns_not_found(self):
        other_prescription = self.create_prescription(
            user=self.other_user,
            status=Prescription.Status.APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("wholesale_catalog:lenses"),
            {
                "prescription_id": (
                    other_prescription.pk
                )
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_bulk_quote_applies_matching_tier(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("wholesale_catalog:quote"),
            {
                "prescription_id": self.prescription.pk,
                "variant_id": self.variant.pk,
                "eye": PrescriptionEyeValue.Eye.RIGHT,
                "boxes": 10,
            },
        )

        self.assertEqual(response.status_code, 200)

        quote = response.json()["quote"]

        self.assertEqual(
            quote["applied_box_price_including_gst"],
            "900.00",
        )
        self.assertEqual(
            quote["subtotal_including_gst"],
            "9000.00",
        )
        self.assertIsNotNone(quote["bulk_tier_id"])

    def test_nonmatching_variant_cannot_be_quoted(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("wholesale_catalog:quote"),
            {
                "prescription_id": self.prescription.pk,
                "variant_id": self.nonmatching_variant.pk,
                "eye": PrescriptionEyeValue.Eye.RIGHT,
                "boxes": 5,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "prescription_range_mismatch",
        )

    def test_quantity_above_stock_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("wholesale_catalog:quote"),
            {
                "prescription_id": self.prescription.pk,
                "variant_id": self.variant.pk,
                "eye": PrescriptionEyeValue.Eye.RIGHT,
                "boxes": 55,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"],
            "wholesale_quote_unavailable",
        )
