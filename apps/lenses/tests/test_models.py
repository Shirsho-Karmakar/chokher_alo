from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import (
    Brand,
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.lenses.models import (
    LensAllowedAxis,
    LensPrescriptionRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)


class LensModelTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name="Lens Brand")
        self.colour = Colour.objects.create(name="Clear")

        self.vision_type = LensVisionType.objects.create(
            code="SV",
            name="Single Vision",
        )
        self.index = LensRefractiveIndex.objects.create(
            value=Decimal("1.56"),
            display_name="Standard Thin",
        )

    def create_offer(
        self,
        *,
        design_kind=ProductDesign.Kind.LENS,
        offer_type=ProductOffer.OfferType.LENS,
        requires_prescription=True,
    ):
        design = ProductDesign.objects.create(
            name=f"Lens Design {ProductDesign.objects.count()}",
            kind=design_kind,
            brand=self.brand,
            status=ProductDesign.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(
            design=design,
            colour=self.colour,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )

        return ProductOffer.objects.create(
            variant=variant,
            offer_type=offer_type,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=requires_prescription,
        )

    def test_powered_lens_specification_can_be_created(self):
        offer = self.create_offer()

        specification = LensSpecification.objects.create(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
            is_powered=True,
            selling_unit=LensSpecification.SellingUnit.PAIR,
        )

        self.assertTrue(specification.is_powered)

    def test_non_lens_offer_is_rejected(self):
        offer = self.create_offer(
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
        )

        specification = LensSpecification(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
        )

        with self.assertRaises(ValidationError):
            specification.save()

    def test_powered_lens_requires_prescription_offer(self):
        offer = self.create_offer(
            requires_prescription=False,
        )

        specification = LensSpecification(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
            is_powered=True,
        )

        with self.assertRaises(ValidationError):
            specification.save()

    def test_box_unit_requires_units_per_box(self):
        offer = self.create_offer()

        specification = LensSpecification(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
            selling_unit=LensSpecification.SellingUnit.BOX,
        )

        with self.assertRaises(ValidationError):
            specification.save()

    def test_invalid_prescription_range_is_rejected(self):
        offer = self.create_offer()
        specification = LensSpecification.objects.create(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
        )

        rule = LensPrescriptionRule(
            lens=specification,
            name="Invalid sphere range",
            minimum_sphere=Decimal("2.00"),
            maximum_sphere=Decimal("-2.00"),
        )

        with self.assertRaises(ValidationError):
            rule.save()

    def test_axis_can_be_added_to_exact_axis_rule(self):
        offer = self.create_offer()
        specification = LensSpecification.objects.create(
            offer=offer,
            vision_type=self.vision_type,
            refractive_index=self.index,
        )
        rule = LensPrescriptionRule.objects.create(
            lens=specification,
            name="Axis 90",
            axis_mode=LensPrescriptionRule.AxisMode.EXACT,
        )

        axis = LensAllowedAxis.objects.create(
            rule=rule,
            axis=90,
        )

        self.assertEqual(axis.axis, 90)
