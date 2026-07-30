from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import (
    Brand,
    Category,
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)


class CatalogueModelTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name="Example Brand")
        self.colour = Colour.objects.create(
            name="Black",
            hex_value="#000000",
        )
        self.category = Category.objects.create(
            name="Frames",
            code="FRM",
        )
        self.design = ProductDesign.objects.create(
            name="Classic Square",
            supplier_model_number="MODEL-101",
            brand=self.brand,
            kind=ProductDesign.Kind.FRAME,
            status=ProductDesign.Status.ACTIVE,
        )
        self.design.categories.add(self.category)

        self.variant = ProductVariant.objects.create(
            design=self.design,
            colour=self.colour,
            size_label="Medium",
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=10,
        )

    def test_design_gets_permanent_slug(self):
        original_slug = self.design.slug

        self.assertTrue(original_slug)
        self.assertIn("classic-square", original_slug)

        self.design.name = "Renamed Square"
        self.design.save()
        self.design.refresh_from_db()

        self.assertEqual(self.design.slug, original_slug)

    def test_variant_gets_permanent_physical_sku(self):
        original_sku = self.variant.physical_sku

        self.assertTrue(original_sku.startswith("CHA-STK-"))

        self.variant.size_label = "Large"
        self.variant.save()
        self.variant.refresh_from_db()

        self.assertEqual(
            self.variant.physical_sku,
            original_sku,
        )

    def test_multiple_offers_share_same_physical_variant(self):
        frame_offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )
        sunglass_offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.SUNGLASSES,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1700.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        self.assertEqual(
            frame_offer.variant_id,
            sunglass_offer.variant_id,
        )
        self.assertEqual(self.variant.offers.count(), 2)

    def test_offer_gets_category_specific_sku(self):
        offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.SUNGLASSES,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1700.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        original_sku = offer.sku

        self.assertTrue(original_sku.startswith("CHA-SUN-"))

        offer.status = ProductOffer.Status.SOLD_OUT
        offer.save()
        offer.refresh_from_db()

        self.assertEqual(offer.sku, original_sku)

    def test_coming_soon_offer_hides_price(self):
        offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.ZERO_POWER,
            mrp_including_gst=Decimal("1800.00"),
            selling_price_including_gst=Decimal("1500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.COMING_SOON,
        )

        self.assertFalse(offer.price_visible)

    def test_sold_out_offer_shows_previous_price(self):
        offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.SOLD_OUT,
        )

        self.assertTrue(offer.price_visible)

    def test_zero_quantity_makes_available_offer_sold_out(self):
        self.variant.stock_quantity = 0
        self.variant.save()

        offer = ProductOffer.objects.create(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        self.assertEqual(
            offer.effective_status,
            ProductOffer.Status.SOLD_OUT,
        )

    def test_selling_price_cannot_exceed_mrp(self):
        offer = ProductOffer(
            variant=self.variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1000.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        with self.assertRaises(ValidationError):
            offer.save()

    def test_accessory_measurements_can_be_empty(self):
        accessory_design = ProductDesign.objects.create(
            name="Eyewear Case",
            kind=ProductDesign.Kind.ACCESSORY,
            status=ProductDesign.Status.ACTIVE,
        )
        accessory_variant = ProductVariant.objects.create(
            design=accessory_design,
            colour=self.colour,
            stock_mode=ProductVariant.StockMode.STATUS_ONLY,
            manual_stock_status=(
                ProductVariant.StockStatus.AVAILABLE
            ),
        )

        self.assertIsNone(accessory_variant.lens_width_mm)
        self.assertIsNone(accessory_variant.lens_height_mm)
        self.assertIsNone(accessory_variant.frame_width_mm)
