import base64
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import (
    Brand,
    Category,
    Colour,
    FrameShape,
    FrameType,
    Material,
    ProductDesign,
    ProductImage,
    ProductOffer,
    ProductStockAlert,
    ProductVariant,
)


User = get_user_model()


ONE_PIXEL_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
)


class RetailCatalogueViewTests(TestCase):
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
            username="catalogue-customer",
            phone_number="+919876543210",
            phone_verified=True,
        )

        self.brand = Brand.objects.create(
            name="Retail API Brand"
        )
        self.category = Category.objects.create(
            name="Retail Frames",
            code="RFM",
        )
        self.black = Colour.objects.create(
            name="Retail Black",
            hex_value="#000000",
        )
        self.blue = Colour.objects.create(
            name="Retail Blue",
            hex_value="#0000FF",
        )
        material = Material.objects.create(
            name="Retail Acetate"
        )
        shape = FrameShape.objects.create(
            name="Retail Square"
        )
        frame_type = FrameType.objects.create(
            name="Retail Full Rim"
        )

        self.design = ProductDesign.objects.create(
            name="Retail Classic Frame",
            supplier_model_number="RF-101",
            kind=ProductDesign.Kind.FRAME,
            brand=self.brand,
            gender=ProductDesign.Gender.UNISEX,
            material=material,
            frame_shape=shape,
            frame_type=frame_type,
            description="A test retail frame.",
            status=ProductDesign.Status.ACTIVE,
        )
        self.design.categories.add(self.category)

        self.black_variant = ProductVariant.objects.create(
            design=self.design,
            colour=self.black,
            size_label="Medium",
            lens_width_mm=Decimal("52.00"),
            lens_height_mm=Decimal("38.00"),
            frame_width_mm=Decimal("138.00"),
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=5,
        )
        self.blue_variant = ProductVariant.objects.create(
            design=self.design,
            colour=self.blue,
            size_label="Medium",
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=0,
        )

        self.available_offer = ProductOffer.objects.create(
            variant=self.black_variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            supports_powered_lenses=True,
        )
        self.sunglasses_offer = ProductOffer.objects.create(
            variant=self.black_variant,
            offer_type=ProductOffer.OfferType.SUNGLASSES,
            mrp_including_gst=Decimal("2500.00"),
            selling_price_including_gst=Decimal("1900.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.SOLD_OUT,
        )
        self.sold_out_offer = ProductOffer.objects.create(
            variant=self.blue_variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("2000.00"),
            selling_price_including_gst=Decimal("1500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            supports_powered_lenses=True,
        )

        coming_design = ProductDesign.objects.create(
            name="Coming Soon Frame",
            kind=ProductDesign.Kind.FRAME,
            gender=ProductDesign.Gender.UNISEX,
            status=ProductDesign.Status.COMING_SOON,
        )
        coming_variant = ProductVariant.objects.create(
            design=coming_design,
            colour=self.black,
            size_label="Coming",
        )
        self.coming_offer = ProductOffer.objects.create(
            variant=coming_variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("3000.00"),
            selling_price_including_gst=Decimal("2200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        draft_design = ProductDesign.objects.create(
            name="Hidden Draft Frame",
            kind=ProductDesign.Kind.FRAME,
            status=ProductDesign.Status.DRAFT,
        )
        draft_variant = ProductVariant.objects.create(
            design=draft_design,
            colour=self.black,
            size_label="Draft",
        )
        self.draft_offer = ProductOffer.objects.create(
            variant=draft_variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1000.00"),
            selling_price_including_gst=Decimal("800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        self.image = ProductImage.objects.create(
            variant=self.black_variant,
            image=SimpleUploadedFile(
                "retail-frame.gif",
                ONE_PIXEL_GIF,
                content_type="image/gif",
            ),
            alt_text="Retail black frame",
            is_primary=True,
        )

    def test_public_list_hides_draft_products(self):
        response = self.client.get(
            reverse("catalog:product_list")
        )

        self.assertEqual(response.status_code, 200)

        skus = {
            product["sku"]
            for product in response.json()["products"]
        }

        self.assertIn(self.available_offer.sku, skus)
        self.assertIn(self.sold_out_offer.sku, skus)
        self.assertIn(self.coming_offer.sku, skus)
        self.assertNotIn(self.draft_offer.sku, skus)

    def test_catalogue_filters_by_category_colour_and_type(self):
        response = self.client.get(
            reverse("catalog:product_list"),
            {
                "category": self.category.slug,
                "colour": self.black.pk,
                "offer_type": (
                    ProductOffer.OfferType.FRAME_ONLY
                ),
            },
        )

        self.assertEqual(response.status_code, 200)

        products = response.json()["products"]

        self.assertEqual(len(products), 1)
        self.assertEqual(
            products[0]["sku"],
            self.available_offer.sku,
        )

    def test_sold_out_price_is_visible_and_coming_price_hidden(self):
        response = self.client.get(
            reverse("catalog:product_list")
        )
        products = {
            product["sku"]: product
            for product in response.json()["products"]
        }

        sold_out = products[self.sold_out_offer.sku]
        coming = products[self.coming_offer.sku]

        self.assertEqual(sold_out["status"], "sold_out")
        self.assertTrue(sold_out["price_visible"])
        self.assertEqual(
            sold_out["selling_price_including_gst"],
            "1500.00",
        )

        self.assertEqual(coming["status"], "coming_soon")
        self.assertFalse(coming["price_visible"])
        self.assertIsNone(
            coming["selling_price_including_gst"]
        )

    def test_product_detail_includes_power_options_and_images(self):
        response = self.client.get(
            reverse(
                "catalog:product_detail",
                kwargs={"sku": self.available_offer.sku},
            )
        )

        self.assertEqual(response.status_code, 200)

        product = response.json()["product"]

        self.assertTrue(
            product["purchase_options"][
                "supports_powered_lenses"
            ]
        )
        self.assertEqual(
            product["measurements_mm"]["lens_width"],
            "52.00",
        )
        self.assertEqual(len(product["images"]), 1)
        self.assertEqual(
            product["other_offers_for_variant"][0]["sku"],
            self.sunglasses_offer.sku,
        )

    def test_public_product_image_can_be_streamed(self):
        response = self.client.get(
            reverse(
                "catalog:product_image",
                kwargs={"image_id": self.image.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertIn(
            "public",
            response["Cache-Control"],
        )

    def test_catalogue_is_paginated(self):
        response = self.client.get(
            reverse("catalog:product_list"),
            {
                "page": 1,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()["products"]),
            1,
        )
        self.assertGreater(
            response.json()["pagination"]["total_items"],
            1,
        )

    def test_stock_alert_requires_login(self):
        response = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.sold_out_offer.sku,
                "channel": ProductStockAlert.Channel.SMS,
            },
        )

        self.assertEqual(response.status_code, 302)

    def test_sms_stock_alert_is_created_idempotently(self):
        self.client.force_login(self.user)

        first = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.sold_out_offer.sku,
                "channel": ProductStockAlert.Channel.SMS,
            },
        )
        second = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.sold_out_offer.sku,
                "channel": ProductStockAlert.Channel.SMS,
            },
        )

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(
            ProductStockAlert.objects.count(),
            1,
        )

    def test_stock_alert_is_rejected_for_available_offer(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.available_offer.sku,
                "channel": ProductStockAlert.Channel.SMS,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ProductStockAlert.objects.count(),
            0,
        )

    def test_email_alert_requires_verified_email(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.sold_out_offer.sku,
                "channel": ProductStockAlert.Channel.EMAIL,
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_customer_can_cancel_stock_alert(self):
        self.client.force_login(self.user)

        create_response = self.client.post(
            reverse("catalog:stock_alert_create"),
            {
                "sku": self.sold_out_offer.sku,
                "channel": ProductStockAlert.Channel.SMS,
            },
        )
        alert_id = create_response.json()["alert"]["id"]

        cancel_response = self.client.post(
            reverse(
                "catalog:stock_alert_cancel",
                kwargs={"alert_id": alert_id},
            )
        )

        self.assertEqual(cancel_response.status_code, 200)

        alert = ProductStockAlert.objects.get(pk=alert_id)

        self.assertEqual(
            alert.status,
            ProductStockAlert.Status.CANCELLED,
        )
        self.assertIsNotNone(alert.cancelled_at)

    def test_alert_list_only_contains_current_users_alerts(self):
        ProductStockAlert.objects.create(
            user=self.user,
            offer=self.sold_out_offer,
            channel=ProductStockAlert.Channel.SMS,
        )

        other_user = User.objects.create_user(
            username="other-alert-user",
            phone_number="+919876543211",
            phone_verified=True,
        )
        ProductStockAlert.objects.create(
            user=other_user,
            offer=self.sold_out_offer,
            channel=ProductStockAlert.Channel.SMS,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("catalog:stock_alert_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()["alerts"]),
            1,
        )
