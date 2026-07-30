import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

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
    LensPriceRule,
    LensRefractiveIndex,
    LensSpecification,
    LensVisionType,
)
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)
from apps.retail_cart.models import (
    CustomerOwnedFrameService,
    RetailCartItem,
)


User = get_user_model()


class RetailCartAPIViewTests(TestCase):
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
            username="retail-cart-api-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.other_user = User.objects.create_user(
            username="other-retail-cart-user",
            phone_number="+919876543211",
            phone_verified=True,
        )

        brand = Brand.objects.create(
            name="Retail Cart API Brand"
        )
        black = Colour.objects.create(
            name="Retail Cart API Black"
        )
        clear = Colour.objects.create(
            name="Retail Cart API Clear"
        )

        accessory_design = ProductDesign.objects.create(
            name="Retail Cart API Case",
            kind=ProductDesign.Kind.ACCESSORY,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        self.accessory_variant = (
            ProductVariant.objects.create(
                design=accessory_design,
                colour=black,
                stock_mode=(
                    ProductVariant.StockMode.QUANTITY
                ),
                stock_quantity=20,
            )
        )
        self.accessory_offer = ProductOffer.objects.create(
            variant=self.accessory_variant,
            offer_type=ProductOffer.OfferType.ACCESSORY,
            mrp_including_gst=Decimal("700.00"),
            selling_price_including_gst=Decimal("500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        frame_design = ProductDesign.objects.create(
            name="Retail Cart API Frame",
            kind=ProductDesign.Kind.FRAME,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        self.frame_variant = ProductVariant.objects.create(
            design=frame_design,
            colour=black,
            size_label="Medium",
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=5,
        )
        self.frame_offer = ProductOffer.objects.create(
            variant=self.frame_variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1000.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            supports_powered_lenses=True,
        )

        lens_design = ProductDesign.objects.create(
            name="Retail Cart API Lens",
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
        lens_offer = ProductOffer.objects.create(
            variant=lens_variant,
            offer_type=ProductOffer.OfferType.LENS,
            mrp_including_gst=Decimal("1200.00"),
            selling_price_including_gst=Decimal("800.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            requires_prescription=True,
        )

        vision_type = LensVisionType.objects.create(
            code="RCA",
            name="Retail Cart API Vision",
        )
        refractive_index = LensRefractiveIndex.objects.create(
            value=Decimal("1.63"),
        )

        self.lens = LensSpecification.objects.create(
            offer=lens_offer,
            vision_type=vision_type,
            refractive_index=refractive_index,
            is_powered=True,
            require_both_eyes=True,
        )
        LensPrescriptionRule.objects.create(
            lens=self.lens,
            name="Retail cart API range",
            minimum_sphere=Decimal("-10.00"),
            maximum_sphere=Decimal("10.00"),
            minimum_cylinder=Decimal("-4.00"),
            maximum_cylinder=Decimal("4.00"),
        )

        self.coating = LensCoating.objects.create(
            code="RCC",
            name="Retail Cart API Coating",
        )
        self.lens.coatings.add(self.coating)

        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.COATING,
            name="Retail cart API coating charge",
            coating=self.coating,
            amount_including_gst=Decimal("200.00"),
        )

        self.approved_prescription = (
            self.create_prescription(
                user=self.user,
                status=Prescription.Status.APPROVED,
            )
        )
        self.pending_prescription = (
            self.create_prescription(
                user=self.user,
                status=Prescription.Status.PENDING,
            )
        )
        self.other_prescription = (
            self.create_prescription(
                user=self.other_user,
                status=Prescription.Status.APPROVED,
            )
        )

    def create_prescription(self, *, user, status):
        prescription = Prescription.objects.create(
            user=user,
            prescription_file=SimpleUploadedFile(
                f"{user.username}-{status}.jpg",
                b"retail-cart-api-prescription",
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

    def test_cart_requires_login(self):
        response = self.client.get(
            reverse("retail_cart:current")
        )

        self.assertEqual(response.status_code, 302)

    def test_current_cart_is_created_and_returned(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("retail_cart:current")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["cart"]["items"],
            [],
        )
        self.assertFalse(
            response.json()["cart"]["validation"][
                "checkout_ready"
            ]
        )

    def test_standard_items_merge(self):
        self.client.force_login(self.user)

        first = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 2,
            },
        )
        second = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 1,
            },
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        items = second.json()["cart"]["items"]

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 3)
        self.assertEqual(
            items[0]["current_total_including_gst"],
            "1500.00",
        )

    def test_standard_quantity_can_be_updated(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 1,
            },
        )
        item_id = add_response.json()["mutation"]["item_id"]

        response = self.client.post(
            reverse(
                "retail_cart:update_quantity",
                kwargs={"item_id": item_id},
            ),
            {"quantity": 4},
        )

        self.assertEqual(response.status_code, 200)

        item = response.json()["cart"]["items"][0]

        self.assertEqual(item["quantity"], 4)
        self.assertEqual(
            item["current_total_including_gst"],
            "2000.00",
        )

    def test_sold_out_item_is_removed_when_cart_is_opened(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 1,
            },
        )
        item_id = add_response.json()["mutation"]["item_id"]

        self.accessory_variant.stock_quantity = 0
        self.accessory_variant.save()

        response = self.client.get(
            reverse("retail_cart:current")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["cart"]["items"],
            [],
        )
        self.assertIn(
            item_id,
            response.json()["cart"]["validation"][
                "removed_item_ids"
            ],
        )

    def test_pending_powered_item_remains_and_blocks_checkout(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("retail_cart:add_powered"),
            {
                "sku": self.frame_offer.sku,
                "prescription_id": (
                    self.pending_prescription.pk
                ),
            },
        )

        self.assertEqual(response.status_code, 201)

        item = response.json()["cart"]["items"][0]

        self.assertEqual(
            item["powered_configuration"]["state"],
            "prescription_pending",
        )
        self.assertTrue(item["is_non_refundable"])
        self.assertFalse(
            response.json()["cart"]["validation"][
                "checkout_ready"
            ]
        )

    def test_powered_item_can_be_configured(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("retail_cart:add_powered"),
            {
                "sku": self.frame_offer.sku,
                "prescription_id": (
                    self.approved_prescription.pk
                ),
            },
        )
        item_id = add_response.json()["mutation"]["item_id"]

        response = self.client.post(
            reverse(
                "retail_cart:configure_powered",
                kwargs={"item_id": item_id},
            ),
            {
                "lens_id": self.lens.pk,
                "coating_ids": [str(self.coating.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)

        item = response.json()["cart"]["items"][0]

        self.assertEqual(
            item["powered_configuration"]["state"],
            "configured",
        )
        self.assertEqual(
            item["current_unit_price_including_gst"],
            "2000.00",
        )
        self.assertTrue(
            response.json()["cart"]["validation"][
                "checkout_ready"
            ]
        )

    def test_other_users_prescription_is_not_accessible(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("retail_cart:add_powered"),
            {
                "sku": self.frame_offer.sku,
                "prescription_id": (
                    self.other_prescription.pk
                ),
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_owned_frame_service_can_be_configured(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse(
                "retail_cart:add_customer_owned_frame"
            ),
            {
                "prescription_id": (
                    self.approved_prescription.pk
                ),
                "completion_choice": (
                    CustomerOwnedFrameService
                    .CompletionChoice.SEND_LENSES_ONLY
                ),
                "frame_handling": (
                    CustomerOwnedFrameService
                    .FrameHandling.NOT_REQUIRED
                ),
            },
        )

        self.assertEqual(add_response.status_code, 201)

        item_id = add_response.json()["mutation"]["item_id"]

        response = self.client.post(
            reverse(
                "retail_cart:configure_customer_owned_frame",
                kwargs={"item_id": item_id},
            ),
            {
                "lens_id": self.lens.pk,
                "coating_ids": [str(self.coating.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)

        item = response.json()["cart"]["items"][0]

        self.assertEqual(
            item["customer_owned_frame_service"]["state"],
            "configured",
        )
        self.assertEqual(
            item["current_unit_price_including_gst"],
            "1000.00",
        )
        self.assertTrue(item["is_non_refundable"])

    def test_nonstandard_quantity_cannot_be_updated(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("retail_cart:add_powered"),
            {
                "sku": self.frame_offer.sku,
                "prescription_id": (
                    self.pending_prescription.pk
                ),
            },
        )
        item_id = add_response.json()["mutation"]["item_id"]

        response = self.client.post(
            reverse(
                "retail_cart:update_quantity",
                kwargs={"item_id": item_id},
            ),
            {"quantity": 2},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "quantity_not_editable",
        )

    def test_customer_can_remove_own_item(self):
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 1,
            },
        )
        item_id = add_response.json()["mutation"]["item_id"]

        response = self.client.post(
            reverse(
                "retail_cart:remove_item",
                kwargs={"item_id": item_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["cart"]["items"],
            [],
        )
        self.assertEqual(
            response.json()["mutation"]["item_id"],
            item_id,
        )

    def test_customer_cannot_remove_another_users_item(self):
        self.client.force_login(self.other_user)

        other_add = self.client.post(
            reverse("retail_cart:add_standard"),
            {
                "sku": self.accessory_offer.sku,
                "quantity": 1,
            },
        )
        other_item_id = other_add.json()["mutation"]["item_id"]

        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "retail_cart:remove_item",
                kwargs={"item_id": other_item_id},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            RetailCartItem.objects.filter(
                pk=other_item_id
            ).exists()
        )
