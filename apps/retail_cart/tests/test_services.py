import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

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
from apps.retail_cart.services import (
    RetailCartError,
    add_customer_owned_frame_service,
    add_powered_eyewear,
    add_standard_offer,
    configure_customer_owned_frame_service,
    configure_powered_eyewear,
    get_or_create_open_retail_cart,
    refresh_retail_cart,
)
from apps.wholesale.models import WholesaleAccount


User = get_user_model()


class RetailCartServiceTests(TestCase):
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
            username="retail-cart-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.cart = get_or_create_open_retail_cart(
            user=self.user
        )

        brand = Brand.objects.create(name="Cart Test Brand")
        black = Colour.objects.create(name="Cart Test Black")
        clear = Colour.objects.create(name="Cart Test Clear")

        standard_design = ProductDesign.objects.create(
            name="Cart Accessory",
            kind=ProductDesign.Kind.ACCESSORY,
            brand=brand,
            status=ProductDesign.Status.ACTIVE,
        )
        self.standard_variant = ProductVariant.objects.create(
            design=standard_design,
            colour=black,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=20,
        )
        self.standard_offer = ProductOffer.objects.create(
            variant=self.standard_variant,
            offer_type=ProductOffer.OfferType.ACCESSORY,
            mrp_including_gst=Decimal("700.00"),
            selling_price_including_gst=Decimal("500.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
        )

        frame_design = ProductDesign.objects.create(
            name="Cart Powered Frame",
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
            name="Cart Powered Lens",
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
            code="CSV",
            name="Cart Single Vision",
        )
        index = LensRefractiveIndex.objects.create(
            value=Decimal("1.62"),
        )

        self.lens = LensSpecification.objects.create(
            offer=lens_offer,
            vision_type=vision_type,
            refractive_index=index,
            is_powered=True,
            require_both_eyes=True,
        )
        LensPrescriptionRule.objects.create(
            lens=self.lens,
            name="Cart supported range",
            minimum_sphere=Decimal("-10.00"),
            maximum_sphere=Decimal("10.00"),
            minimum_cylinder=Decimal("-4.00"),
            maximum_cylinder=Decimal("4.00"),
        )

        self.coating = LensCoating.objects.create(
            code="CBL",
            name="Cart Blue Coating",
        )
        self.lens.coatings.add(self.coating)

        LensPriceRule.objects.create(
            lens=self.lens,
            rule_type=LensPriceRule.RuleType.COATING,
            name="Cart coating charge",
            coating=self.coating,
            amount_including_gst=Decimal("200.00"),
        )

        self.approved_prescription = self.create_prescription(
            Prescription.Status.APPROVED
        )
        self.pending_prescription = self.create_prescription(
            Prescription.Status.PENDING
        )

    def create_prescription(self, status):
        prescription = Prescription.objects.create(
            user=self.user,
            prescription_file=SimpleUploadedFile(
                f"{status}.jpg",
                b"cart-prescription",
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

    def test_open_cart_is_reused(self):
        second = get_or_create_open_retail_cart(
            user=self.user
        )

        self.assertEqual(second.pk, self.cart.pk)

    def test_standard_items_merge_without_reserving_stock(self):
        first = add_standard_offer(
            cart=self.cart,
            offer=self.standard_offer,
            quantity=2,
        )
        second = add_standard_offer(
            cart=self.cart,
            offer=self.standard_offer,
            quantity=1,
        )

        second.refresh_from_db()
        self.standard_variant.refresh_from_db()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.quantity, 3)
        self.assertEqual(
            self.standard_variant.stock_quantity,
            20,
        )

    def test_standard_quantity_cannot_exceed_ten(self):
        add_standard_offer(
            cart=self.cart,
            offer=self.standard_offer,
            quantity=10,
        )

        with self.assertRaises(RetailCartError):
            add_standard_offer(
                cart=self.cart,
                offer=self.standard_offer,
                quantity=1,
            )

    def test_sold_out_standard_item_is_removed_on_refresh(self):
        item = add_standard_offer(
            cart=self.cart,
            offer=self.standard_offer,
            quantity=1,
        )

        self.standard_variant.stock_quantity = 0
        self.standard_variant.save()

        result = refresh_retail_cart(cart=self.cart)

        self.assertFalse(
            RetailCartItem.objects.filter(pk=item.pk).exists()
        )
        self.assertIn(item.pk, result.removed_item_ids)
        self.assertTrue(
            any(
                issue.code == "item_removed_unavailable"
                for issue in result.issues
            )
        )

    def test_price_change_is_refreshed_and_reported(self):
        item = add_standard_offer(
            cart=self.cart,
            offer=self.standard_offer,
            quantity=2,
        )

        self.standard_offer.selling_price_including_gst = (
            Decimal("550.00")
        )
        self.standard_offer.save()

        result = refresh_retail_cart(cart=self.cart)
        item.refresh_from_db()

        self.assertEqual(
            item.current_unit_price_including_gst,
            Decimal("550.00"),
        )
        self.assertEqual(
            item.current_total_including_gst,
            Decimal("1100.00"),
        )
        self.assertTrue(
            any(
                issue.code == "price_updated"
                for issue in result.issues
            )
        )

    def test_pending_powered_item_remains_but_blocks_checkout(self):
        item = add_powered_eyewear(
            cart=self.cart,
            offer=self.frame_offer,
            prescription=self.pending_prescription,
        )

        result = refresh_retail_cart(cart=self.cart)

        self.assertTrue(
            RetailCartItem.objects.filter(pk=item.pk).exists()
        )
        self.assertFalse(result.checkout_ready)
        self.assertTrue(item.is_non_refundable)
        self.assertTrue(
            any(
                issue.code == "prescription_pending"
                for issue in result.issues
            )
        )

    def test_powered_configuration_calculates_final_price(self):
        item = add_powered_eyewear(
            cart=self.cart,
            offer=self.frame_offer,
            prescription=self.approved_prescription,
        )

        configure_powered_eyewear(
            item=item,
            lens=self.lens,
            coatings=[self.coating],
        )

        item.refresh_from_db()
        configuration = item.powered_configuration

        self.assertEqual(
            configuration.lens_quote_total_including_gst,
            Decimal("1000.00"),
        )
        self.assertEqual(
            item.current_unit_price_including_gst,
            Decimal("2000.00"),
        )
        self.assertTrue(item.is_non_refundable)

    def test_same_prescription_can_be_used_for_multiple_items(self):
        add_powered_eyewear(
            cart=self.cart,
            offer=self.frame_offer,
            prescription=self.approved_prescription,
        )
        add_powered_eyewear(
            cart=self.cart,
            offer=self.frame_offer,
            prescription=self.approved_prescription,
        )

        self.assertEqual(
            self.cart.items.filter(
                item_type=(
                    RetailCartItem.ItemType.POWERED_EYEWEAR
                )
            ).count(),
            2,
        )

    def test_customer_owned_frame_service_is_non_refundable(self):
        item = add_customer_owned_frame_service(
            cart=self.cart,
            prescription=self.approved_prescription,
            completion_choice=(
                CustomerOwnedFrameService
                .CompletionChoice.SEND_LENSES_ONLY
            ),
            frame_handling=(
                CustomerOwnedFrameService
                .FrameHandling.NOT_REQUIRED
            ),
        )

        configure_customer_owned_frame_service(
            item=item,
            lens=self.lens,
            coatings=[self.coating],
        )

        item.refresh_from_db()

        self.assertTrue(item.is_non_refundable)
        self.assertEqual(
            item.current_unit_price_including_gst,
            Decimal("1000.00"),
        )

    def test_invalid_frame_handling_is_rejected(self):
        with self.assertRaises(ValidationError):
            add_customer_owned_frame_service(
                cart=self.cart,
                prescription=self.approved_prescription,
                completion_choice=(
                    CustomerOwnedFrameService
                    .CompletionChoice.FIT_AND_RETURN
                ),
                frame_handling=(
                    CustomerOwnedFrameService
                    .FrameHandling.NOT_REQUIRED
                ),
            )

    def test_approved_wholesale_user_can_have_retail_cart(self):
        wholesale_user = User.objects.create_user(
            username="wholesale-retail-shopper",
            phone_number="+919876543211",
            phone_verified=True,
        )
        WholesaleAccount.objects.create(
            user=wholesale_user,
            status=WholesaleAccount.Status.APPROVED,
        )

        retail_cart = get_or_create_open_retail_cart(
            user=wholesale_user
        )

        self.assertEqual(retail_cart.user, wholesale_user)
        self.assertEqual(
            retail_cart.status,
            retail_cart.Status.OPEN,
        )
