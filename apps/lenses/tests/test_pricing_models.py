from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

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
    LensPriceRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)


class LensPriceRuleModelTests(TestCase):
    def setUp(self):
        brand = Brand.objects.create(name="Pricing Brand")
        colour = Colour.objects.create(name="Clear")

        design = ProductDesign.objects.create(
            name="Pricing Lens",
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
            value=Decimal("1.56"),
        )

        self.lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
        )
        self.coating = LensCoating.objects.create(
            code="BLU",
            name="Blue-light coating",
        )
        self.lens.coatings.add(self.coating)

    def test_coating_rule_requires_coating(self):
        rule = LensPriceRule(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.COATING,
            name="Missing coating",
            amount_including_gst=Decimal("300.00"),
        )

        with self.assertRaises(ValidationError):
            rule.save()

    def test_power_rule_requires_power_condition(self):
        rule = LensPriceRule(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.POWER,
            name="No range",
            amount_including_gst=Decimal("400.00"),
        )

        with self.assertRaises(ValidationError):
            rule.save()

    def test_frame_rule_requires_frame_condition(self):
        rule = LensPriceRule(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.FRAME,
            name="No frame condition",
            amount_including_gst=Decimal("200.00"),
        )

        with self.assertRaises(ValidationError):
            rule.save()

    def test_valid_frame_rule_can_be_created(self):
        frame_type = FrameType.objects.create(
            name="Rimless"
        )

        rule = LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.FRAME,
            name="Rimless fitting",
            amount_including_gst=Decimal("200.00"),
            frame_type=frame_type,
        )

        self.assertEqual(
            rule.amount_including_gst,
            Decimal("200.00"),
        )
