import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import (
    Brand,
    Colour,
    FrameShape,
    FrameType,
    Material,
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
from apps.lenses.pricing import LensPricingError, quote_lens
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)


User = get_user_model()


class LensPricingTests(TestCase):
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
            username="lens-pricing-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

        brand = Brand.objects.create(name="Quote Brand")
        clear = Colour.objects.create(name="Clear")

        lens_design = ProductDesign.objects.create(
            name="Quote Lens",
            kind=ProductDesign.Kind.LENS,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        lens_variant = ProductVariant.objects.create(
            design=lens_design,
            colour=clear,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )
        offer = ProductOffer.objects.create(
            variant=lens_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1000.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="SV",
            name="Single Vision",
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
            name="Standard supported range",
            minimum_sphere=Decimal("-10.00"),
            maximum_sphere=Decimal("10.00"),
            minimum_cylinder=Decimal("-4.00"),
            maximum_cylinder=Decimal("4.00"),
            axis_mode=LensPrescriptionRule.AxisMode.ANY,
        )

        self.coating = LensCoating.objects.create(
            code="BLU",
            name="Blue-light coating",
        )
        self.lens.coatings.add(self.coating)

        self.frame_type = FrameType.objects.create(
            name="Rimless"
        )
        frame_shape = FrameShape.objects.create(
            name="Rectangle"
        )
        material = Material.objects.create(name="Titanium")

        frame_design = ProductDesign.objects.create(
            name="Rimless Frame",
            kind=ProductDesign.Kind.FRAME,
            brand=brand,
            frame_type=self.frame_type,
            frame_shape=frame_shape,
            material=material,
            status=ProductDesign.Status.ACTIVE,
        )
        frame_colour = Colour.objects.create(name="Silver")
        self.frame_variant = ProductVariant.objects.create(
            design=frame_design,
            colour=frame_colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=5,
        )

        self.prescription = Prescription.objects.create(
            user=self.user,
            prescription_file=SimpleUploadedFile(
                "prescription.jpg",
                b"test-file",
                content_type="image/jpeg",
            ),
            status=Prescription.Status.APPROVED,
        )
        PrescriptionEyeValue.objects.create(
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-6.00"),
            cylinder=Decimal("-1.00"),
            axis=90,
        )
        PrescriptionEyeValue.objects.create(
            prescription=self.prescription,
            eye=PrescriptionEyeValue.Eye.LEFT,
            sphere=Decimal("-2.00"),
            cylinder=Decimal("-0.50"),
            axis=90,
        )

    def test_base_price_only_quote(self):
        quote = quote_lens(
            lens=self.lens,
            prescription=self.prescription,
        )

        self.assertEqual(
            quote.total_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(len(quote.lines), 1)

    def test_all_configured_adjustments_are_applied(self):
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.INDEX,
            name="1.60 index addition",
            amount_including_gst=Decimal("500.00"),
        )
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
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.FRAME,
            name="Rimless fitting surcharge",
            frame_type=self.frame_type,
            amount_including_gst=Decimal("200.00"),
        )

        quote = quote_lens(
            lens=self.lens,
            prescription=self.prescription,
            selected_coatings=[self.coating],
            frame_variant=self.frame_variant,
        )

        self.assertEqual(
            quote.total_including_gst,
            Decimal("2400.00"),
        )
        self.assertEqual(len(quote.lines), 5)

    def test_strongest_eye_triggers_power_surcharge(self):
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.POWER,
            name="High power",
            minimum_abs_sphere=Decimal("5.00"),
            amount_including_gst=Decimal("400.00"),
        )

        quote = quote_lens(
            lens=self.lens,
            prescription=self.prescription,
        )

        self.assertEqual(
            quote.total_including_gst,
            Decimal("1400.00"),
        )

    def test_only_highest_priority_non_stackable_rule_applies(self):
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.POWER,
            name="Lower priority",
            minimum_abs_sphere=Decimal("4.00"),
            amount_including_gst=Decimal("200.00"),
            priority=1,
        )
        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.POWER,
            name="Higher priority",
            minimum_abs_sphere=Decimal("5.00"),
            amount_including_gst=Decimal("400.00"),
            priority=10,
        )

        quote = quote_lens(
            lens=self.lens,
            prescription=self.prescription,
        )

        self.assertEqual(
            quote.total_including_gst,
            Decimal("1400.00"),
        )

    def test_unapproved_prescription_is_rejected(self):
        self.prescription.status = Prescription.Status.PENDING
        self.prescription.save()

        with self.assertRaises(LensPricingError):
            quote_lens(
                lens=self.lens,
                prescription=self.prescription,
            )

    def test_unavailable_coating_is_rejected(self):
        unavailable = LensCoating.objects.create(
            code="OTHER",
            name="Unavailable coating",
        )

        with self.assertRaises(LensPricingError):
            quote_lens(
                lens=self.lens,
                prescription=self.prescription,
                selected_coatings=[unavailable],
            )
