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
    LensCoating,
    LensPrescriptionRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
from apps.wholesale_catalog.models import (
    WholesaleBulkPriceTier,
    WholesaleLensListing,
    WholesaleLensVariant,
)


class WholesaleCatalogueModelTests(TestCase):
    def setUp(self):
        brand = Brand.objects.create(
            name="Wholesale Lens Brand"
        )
        colour = Colour.objects.create(
            name="Wholesale Clear"
        )

        design = ProductDesign.objects.create(
            name="Wholesale Powered Lens",
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
            mrp_including_gst=Decimal("1000.00"),
            selling_price_including_gst=Decimal("800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="SV",
            name="Wholesale Single Vision",
        )
        refractive_index = LensRefractiveIndex.objects.create(
            value=Decimal("1.56"),
        )

        self.lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
            is_powered=True,
        )

        self.rule = LensPrescriptionRule.objects.create(
            lens=self.lens,
            name="Minus six sphere",
            minimum_sphere=Decimal("-6.00"),
            maximum_sphere=Decimal("0.00"),
            minimum_cylinder=Decimal("-2.00"),
            maximum_cylinder=Decimal("0.00"),
        )

        self.coating = LensCoating.objects.create(
            code="HC",
            name="HC",
        )
        self.lens.coatings.add(self.coating)

        self.listing = WholesaleLensListing.objects.create(
            lens=self.lens,
            catalogue_code="SV.CR",
            name="Single Vision CR",
            status=WholesaleLensListing.Status.ACTIVE,
            units_per_box=1,
        )

    def create_variant(self, **overrides):
        data = {
            "listing": self.listing,
            "prescription_rule": self.rule,
            "coating": self.coating,
            "base_box_price_including_gst": Decimal("1000.00"),
            "boxes_in_stock": 50,
            "status": WholesaleLensVariant.Status.AVAILABLE,
        }
        data.update(overrides)

        return WholesaleLensVariant.objects.create(**data)

    def test_variant_receives_wholesale_sku(self):
        variant = self.create_variant()

        self.assertTrue(
            variant.sku.startswith("CHA-WHL-")
        )

    def test_zero_stock_derives_sold_out_status(self):
        variant = self.create_variant(
            boxes_in_stock=0,
        )

        self.assertEqual(
            variant.effective_status,
            WholesaleLensVariant.Status.SOLD_OUT,
        )
        self.assertTrue(variant.price_visible)

    def test_coming_soon_hides_price(self):
        variant = self.create_variant(
            status=WholesaleLensVariant.Status.COMING_SOON,
            base_box_price_including_gst=None,
        )

        self.assertFalse(variant.price_visible)

    def test_rule_must_belong_to_listing_lens(self):
        other_design = ProductDesign.objects.create(
            name="Other Wholesale Lens",
            kind=ProductDesign.Kind.LENS,
            status=ProductDesign.Status.ACTIVE,
        )
        other_variant = ProductVariant.objects.create(
            design=other_design,
            colour=self.coating.lens_specifications.first()
            .offer.variant.colour,
            size_label="Other",
        )
        other_offer = ProductOffer.objects.create(
            variant=other_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("1000.00"),
            selling_price_including_gst=Decimal("800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )
        other_lens = LensSpecification.objects.create(
            offer=other_offer,
            vision_type=self.lens.vision_type,
            refractive_index=self.lens.refractive_index,
        )
        other_rule = LensPrescriptionRule.objects.create(
            lens=other_lens,
            name="Other range",
        )

        variant = WholesaleLensVariant(
            listing=self.listing,
            prescription_rule=other_rule,
            base_box_price_including_gst=Decimal("1000.00"),
            boxes_in_stock=10,
            status=WholesaleLensVariant.Status.AVAILABLE,
        )

        with self.assertRaises(ValidationError):
            variant.save()

    def test_overlapping_bulk_tiers_are_rejected(self):
        variant = self.create_variant()

        WholesaleBulkPriceTier.objects.create(
            variant=variant,
            minimum_boxes=10,
            maximum_boxes=24,
            box_price_including_gst=Decimal("900.00"),
        )

        overlapping = WholesaleBulkPriceTier(
            variant=variant,
            minimum_boxes=20,
            maximum_boxes=30,
            box_price_including_gst=Decimal("850.00"),
        )

        with self.assertRaises(ValidationError):
            overlapping.save()

    def test_bulk_price_cannot_exceed_base_price(self):
        variant = self.create_variant()

        tier = WholesaleBulkPriceTier(
            variant=variant,
            minimum_boxes=10,
            box_price_including_gst=Decimal("1100.00"),
        )

        with self.assertRaises(ValidationError):
            tier.save()
