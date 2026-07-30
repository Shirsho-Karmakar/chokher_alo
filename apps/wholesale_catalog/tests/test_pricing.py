from decimal import Decimal

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
from apps.wholesale_catalog.models import (
    WholesaleBulkPriceTier,
    WholesaleLensListing,
    WholesaleLensVariant,
)
from apps.wholesale_catalog.pricing import (
    WholesalePricingError,
    quote_wholesale_boxes,
)


class WholesalePricingTests(TestCase):
    def setUp(self):
        colour = Colour.objects.create(
            name="Wholesale Pricing Clear"
        )
        design = ProductDesign.objects.create(
            name="Wholesale Pricing Lens",
            kind=ProductDesign.Kind.LENS,
            status=ProductDesign.Status.ACTIVE,
        )
        product_variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
        )
        offer = ProductOffer.objects.create(
            variant=product_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("1000.00"),
            selling_price_including_gst=Decimal("800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )
        vision_type = LensVisionType.objects.create(
            code="WSP",
            name="Wholesale Pricing Vision",
        )
        index = LensRefractiveIndex.objects.create(
            value=Decimal("1.59"),
        )
        lens = LensSpecification.objects.create(
            offer=offer,
            vision_type=vision_type,
            refractive_index=index,
        )
        rule = LensPrescriptionRule.objects.create(
            lens=lens,
            name="Wholesale range",
        )
        listing = WholesaleLensListing.objects.create(
            lens=lens,
            catalogue_code="WSP.CR",
            name="Wholesale Pricing Listing",
            status=WholesaleLensListing.Status.ACTIVE,
        )

        self.variant = WholesaleLensVariant.objects.create(
            listing=listing,
            prescription_rule=rule,
            base_box_price_including_gst=Decimal("1000.00"),
            boxes_in_stock=100,
            minimum_order_boxes=5,
            order_multiple_boxes=5,
            status=WholesaleLensVariant.Status.AVAILABLE,
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

    def test_base_price_is_used_below_first_tier(self):
        quote = quote_wholesale_boxes(
            variant=self.variant,
            boxes=5,
        )

        self.assertEqual(
            quote.applied_box_price_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(
            quote.subtotal_including_gst,
            Decimal("5000.00"),
        )

    def test_first_bulk_tier_is_applied(self):
        quote = quote_wholesale_boxes(
            variant=self.variant,
            boxes=10,
        )

        self.assertEqual(
            quote.applied_box_price_including_gst,
            Decimal("900.00"),
        )
        self.assertEqual(
            quote.subtotal_including_gst,
            Decimal("9000.00"),
        )

    def test_open_ended_tier_is_applied(self):
        quote = quote_wholesale_boxes(
            variant=self.variant,
            boxes=25,
        )

        self.assertEqual(
            quote.applied_box_price_including_gst,
            Decimal("800.00"),
        )
        self.assertEqual(
            quote.subtotal_including_gst,
            Decimal("20000.00"),
        )

    def test_minimum_order_is_enforced(self):
        with self.assertRaises(WholesalePricingError):
            quote_wholesale_boxes(
                variant=self.variant,
                boxes=1,
            )

    def test_order_multiple_is_enforced(self):
        with self.assertRaises(WholesalePricingError):
            quote_wholesale_boxes(
                variant=self.variant,
                boxes=7,
            )

    def test_stock_is_enforced(self):
        with self.assertRaises(WholesalePricingError):
            quote_wholesale_boxes(
                variant=self.variant,
                boxes=105,
            )
