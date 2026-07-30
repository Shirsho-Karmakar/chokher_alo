import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.catalog.models import (
    Brand,
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.lenses.matching import (
    compatible_lenses_for_prescription,
)
from apps.lenses.models import (
    LensAllowedAxis,
    LensPrescriptionRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)


User = get_user_model()


class LensMatchingTests(TestCase):
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
            username="lens-match-user",
            phone_number="+919876543210",
            phone_verified=True,
        )

        brand = Brand.objects.create(name="Matching Brand")
        colour = Colour.objects.create(name="Transparent")

        design = ProductDesign.objects.create(
            name="Single Vision Lens",
            kind=ProductDesign.Kind.LENS,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )
        offer = ProductOffer.objects.create(
            variant=variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="SV",
            name="Single Vision",
        )
        refractive_index = LensRefractiveIndex.objects.create(
            value=Decimal("1.56"),
        )

        self.specification = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
            is_powered=True,
            require_both_eyes=True,
        )

        self.rule = LensPrescriptionRule.objects.create(
            lens=self.specification,
            name="Minus power axis 90",
            minimum_sphere=Decimal("-6.00"),
            maximum_sphere=Decimal("0.00"),
            minimum_cylinder=Decimal("-2.00"),
            maximum_cylinder=Decimal("0.00"),
            axis_mode=LensPrescriptionRule.AxisMode.EXACT,
        )
        LensAllowedAxis.objects.create(
            rule=self.rule,
            axis=90,
        )

    def create_prescription(
        self,
        *,
        status=Prescription.Status.APPROVED,
        right_axis=90,
        left_axis=90,
        include_left=True,
    ):
        prescription = Prescription.objects.create(
            user=self.user,
            prescription_file=SimpleUploadedFile(
                "prescription.jpg",
                b"test-file",
                content_type="image/jpeg",
            ),
            status=status,
        )

        PrescriptionEyeValue.objects.create(
            prescription=prescription,
            eye=PrescriptionEyeValue.Eye.RIGHT,
            sphere=Decimal("-2.00"),
            cylinder=Decimal("-0.50"),
            axis=right_axis,
        )

        if include_left:
            PrescriptionEyeValue.objects.create(
                prescription=prescription,
                eye=PrescriptionEyeValue.Eye.LEFT,
                sphere=Decimal("-1.75"),
                cylinder=Decimal("-0.25"),
                axis=left_axis,
            )

        return prescription

    def test_approved_matching_prescription_returns_lens(self):
        prescription = self.create_prescription()

        matches = compatible_lenses_for_prescription(
            prescription
        )

        self.assertEqual(matches, [self.specification])

    def test_pending_prescription_returns_no_lenses(self):
        prescription = self.create_prescription(
            status=Prescription.Status.PENDING,
        )

        self.assertEqual(
            compatible_lenses_for_prescription(prescription),
            [],
        )

    def test_wrong_axis_does_not_match(self):
        prescription = self.create_prescription(
            right_axis=45,
        )

        self.assertEqual(
            compatible_lenses_for_prescription(prescription),
            [],
        )

    def test_missing_left_eye_does_not_match_when_required(self):
        prescription = self.create_prescription(
            include_left=False,
        )

        self.assertEqual(
            compatible_lenses_for_prescription(prescription),
            [],
        )
