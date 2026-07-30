import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import (
    Brand,
    Colour,
    FrameType,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.lenses.models import (
    LensCoating,
    LensPrescriptionRule,
    LensPriceRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)


User = get_user_model()


class LensCatalogueViewTests(TestCase):
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
            username="lens-api-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.other_user = User.objects.create_user(
            username="other-lens-api-user",
            phone_number="+919876543211",
            phone_verified=True,
        )

        brand = Brand.objects.create(name="API Lens Brand")
        clear = Colour.objects.create(name="API Clear")

        lens_design = ProductDesign.objects.create(
            name="API Single Vision Lens",
            kind=ProductDesign.Kind.LENS,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        self.lens_variant = ProductVariant.objects.create(
            design=lens_design,
            colour=clear,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )
        offer = ProductOffer.objects.create(
            variant=self.lens_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1000.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="SV",
            name="API Single Vision",
        )
        refractive_index = LensRefractiveIndex.objects.create(
            value=Decimal("1.60"),
        )

        self.lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
        )

        LensPrescriptionRule.objects.create(
            lens=self.lens,
            name="Supported range",
            minimum_sphere=Decimal("-8.00"),
            maximum_sphere=Decimal("4.00"),
            minimum_cylinder=Decimal("-4.00"),
            maximum_cylinder=Decimal("4.00"),
            axis_mode=LensPrescriptionRule.AxisMode.ANY,
        )

        incompatible_design = ProductDesign.objects.create(
            name="Positive Power Lens",
            kind=ProductDesign.Kind.LENS,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        incompatible_variant = ProductVariant.objects.create(
            design=incompatible_design,
            colour=clear,
            size_label="Positive",
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )
        incompatible_offer = ProductOffer.objects.create(
            variant=incompatible_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("2500.00"),
            selling_price_including_gst=Decimal("1800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )
        self.incompatible_lens = (
            LensSpecification.objects.create(
                offer=incompatible_offer,
                vision_type=vision_type,
                refractive_index=refractive_index,
            )
        )
        LensPrescriptionRule.objects.create(
            lens=self.incompatible_lens,
            name="Strong positive power only",
            minimum_sphere=Decimal("5.00"),
            maximum_sphere=Decimal("10.00"),
            axis_mode=LensPrescriptionRule.AxisMode.ANY,
        )

        self.coating = LensCoating.objects.create(
            code="BLU",
            name="API Blue-light coating",
        )
        self.lens.coatings.add(self.coating)

        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.COATING,
            name="Blue-light coating",
            coating=self.coating,
            amount_including_gst=Decimal("300.00"),
        )
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.POWER,
            name="High-power surcharge",
            minimum_abs_sphere=Decimal("5.00"),
            amount_including_gst=Decimal("400.00"),
        )

        self.frame_type = FrameType.objects.create(
            name="API Rimless"
        )
        frame_design = ProductDesign.objects.create(
            name="API Rimless Frame",
            kind=ProductDesign.Kind.FRAME,
            brand=brand,
            frame_type=self.frame_type,
            status=ProductDesign.Status.ACTIVE,
        )
        silver = Colour.objects.create(name="API Silver")
        self.frame_variant = ProductVariant.objects.create(
            design=frame_design,
            colour=silver,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=4,
        )

        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.FRAME,
            name="Rimless fitting",
            frame_type=self.frame_type,
            amount_including_gst=Decimal("200.00"),
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
                b"test-prescription",
                content_type="image/jpeg",
            ),
            status=status,
        )

        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-6.00"),
            cylinder=Decimal("-1.00"),
            axis=90,
        )
        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            sphere=Decimal("-2.00"),
            cylinder=Decimal("-0.50"),
            axis=90,
        )

        return prescription

    def test_compatible_catalogue_requires_login(self):
        response = self.client.get(
            reverse("lenses:compatible"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 302)

    def test_approved_prescription_returns_compatible_lens(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("lenses:compatible"),
            {"prescription_id": self.prescription.pk},
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["count"], 1)
        self.assertEqual(
            data["lenses"][0]["lens_id"],
            self.lens.pk,
        )
        self.assertEqual(
            data["lenses"][0]["base_price_including_gst"],
            "1000.00",
        )

    def test_pending_prescription_is_rejected(self):
        pending = self.create_prescription(
            user=self.user,
            status=Prescription.Status.PENDING,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("lenses:compatible"),
            {"prescription_id": pending.pk},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"],
            "prescription_not_approved",
        )

    def test_other_users_prescription_is_not_accessible(self):
        other_prescription = self.create_prescription(
            user=self.other_user,
            status=Prescription.Status.APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("lenses:compatible"),
            {"prescription_id": other_prescription.pk},
        )

        self.assertEqual(response.status_code, 404)

    def test_quote_applies_coating_power_and_frame_charges(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("lenses:quote"),
            {
                "prescription_id": self.prescription.pk,
                "lens_id": self.lens.pk,
                "coating_ids": [str(self.coating.pk)],
                "frame_variant_id": self.frame_variant.pk,
            },
        )

        self.assertEqual(response.status_code, 200)

        quote = response.json()["quote"]

        self.assertEqual(
            quote["total_including_gst"],
            "1900.00",
        )
        self.assertEqual(len(quote["lines"]), 4)

    def test_unavailable_coating_is_rejected(self):
        unavailable = LensCoating.objects.create(
            code="OTHER",
            name="Unavailable coating",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("lenses:quote"),
            {
                "prescription_id": self.prescription.pk,
                "lens_id": self.lens.pk,
                "coating_ids": [str(unavailable.pk)],
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_incompatible_lens_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("lenses:quote"),
            {
                "prescription_id": self.prescription.pk,
                "lens_id": self.incompatible_lens.pk,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "quotation_unavailable",
        )

    def test_non_frame_variant_is_rejected_as_frame(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("lenses:quote"),
            {
                "prescription_id": self.prescription.pk,
                "lens_id": self.lens.pk,
                "frame_variant_id": self.lens_variant.pk,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "invalid_frame_variant",
        )
