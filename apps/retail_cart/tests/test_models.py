from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import (
    Colour,
    ProductDesign,
    ProductOffer,
    ProductVariant,
)
from apps.retail_cart.models import (
    RetailCart,
    RetailCartItem,
)


User = get_user_model()


class RetailCartModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="retail-cart-model-user",
            phone_number="+919876543210",
            phone_verified=True,
        )
        self.cart = RetailCart.objects.create(user=self.user)

        colour = Colour.objects.create(name="Cart Model Black")
        design = ProductDesign.objects.create(
            name="Cart Model Frame",
            kind=ProductDesign.Kind.FRAME,
            status=ProductDesign.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(
            design=design,
            colour=colour,
            stock_mode=ProductVariant.StockMode.QUANTITY,
            stock_quantity=10,
        )
        self.offer = ProductOffer.objects.create(
            variant=variant,
            offer_type=ProductOffer.OfferType.FRAME_ONLY,
            mrp_including_gst=Decimal("1500.00"),
            selling_price_including_gst=Decimal("1200.00"),
            gst_rate=Decimal("18.00"),
            status=ProductOffer.Status.AVAILABLE,
            supports_powered_lenses=True,
        )

    def test_only_one_open_cart_is_allowed_per_user(self):
        duplicate = RetailCart(
            user=self.user,
            status=RetailCart.Status.OPEN,
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_powered_item_is_automatically_non_refundable(self):
        item = RetailCartItem.objects.create(
            cart=self.cart,
            item_type=(
                RetailCartItem.ItemType.POWERED_EYEWEAR
            ),
            offer=self.offer,
            quantity=1,
        )

        self.assertTrue(item.is_non_refundable)

    def test_powered_item_quantity_must_be_one(self):
        item = RetailCartItem(
            cart=self.cart,
            item_type=(
                RetailCartItem.ItemType.POWERED_EYEWEAR
            ),
            offer=self.offer,
            quantity=2,
        )

        with self.assertRaises(ValidationError):
            item.save()

    def test_customer_owned_service_cannot_have_offer(self):
        item = RetailCartItem(
            cart=self.cart,
            item_type=(
                RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
            ),
            offer=self.offer,
            quantity=1,
        )

        with self.assertRaises(ValidationError):
            item.save()
