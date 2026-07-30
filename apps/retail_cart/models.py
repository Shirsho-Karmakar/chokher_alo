from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models

from apps.catalog.models import ProductOffer
from apps.lenses.models import LensCoating, LensSpecification
from apps.prescriptions.models import Prescription


class RetailCart(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CHECKOUT_STARTED = "checkout_started", "Checkout started"
        CONVERTED = "converted", "Converted to order"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="retail_carts",
    )
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    currency = models.CharField(
        max_length=3,
        default="INR",
        editable=False,
    )

    last_validated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="open"),
                name="uniq_open_retail_cart_user",
            ),
        ]

    def clean(self):
        super().clean()

        if self.user_id and not self.user.is_active:
            raise ValidationError(
                {"user": "An active customer account is required."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Retail cart #{self.pk or 'new'} — {self.user}"


class RetailCartItem(models.Model):
    class ItemType(models.TextChoices):
        STANDARD = "standard", "Standard retail product"
        POWERED_EYEWEAR = (
            "powered_eyewear",
            "Prescription-powered eyewear",
        )
        CUSTOMER_OWNED_FRAME = (
            "customer_owned_frame",
            "Customer-owned frame service",
        )

    cart = models.ForeignKey(
        RetailCart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item_type = models.CharField(
        max_length=30,
        choices=ItemType.choices,
    )

    # Required for standard and powered-eyewear items.
    # Customer-owned-frame services have no product offer.
    offer = models.ForeignKey(
        ProductOffer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_cart_items",
    )

    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10),
        ],
    )

    current_unit_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    current_total_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    price_refreshed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_non_refundable = models.BooleanField(
        default=False,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(quantity__gte=1)
                    & models.Q(quantity__lte=10)
                ),
                name="retail_item_quantity_1_to_10",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        item_type="customer_owned_frame",
                        offer__isnull=True,
                    )
                    | models.Q(
                        item_type__in=[
                            "standard",
                            "powered_eyewear",
                        ],
                        offer__isnull=False,
                    )
                ),
                name="retail_item_offer_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(item_type="standard")
                    | models.Q(quantity=1)
                ),
                name="retail_custom_item_quantity_one",
            ),
            models.UniqueConstraint(
                fields=["cart", "offer"],
                condition=models.Q(item_type="standard"),
                name="uniq_standard_offer_per_retail_cart",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.item_type == self.ItemType.STANDARD:
            if self.offer_id is None:
                errors["offer"] = (
                    "A product offer is required for a standard item."
                )
            elif self.offer.requires_prescription:
                errors["offer"] = (
                    "Prescription products require a configured "
                    "powered-eyewear cart item."
                )

        elif self.item_type == self.ItemType.POWERED_EYEWEAR:
            if self.offer_id is None:
                errors["offer"] = (
                    "A base eyewear offer is required."
                )
            elif not self.offer.supports_powered_lenses:
                errors["offer"] = (
                    "This eyewear offer does not support "
                    "prescription-powered lenses."
                )

            if self.quantity != 1:
                errors["quantity"] = (
                    "Powered-eyewear items must have quantity one."
                )

        elif self.item_type == self.ItemType.CUSTOMER_OWNED_FRAME:
            if self.offer_id is not None:
                errors["offer"] = (
                    "A customer-owned frame service must not "
                    "reference a store product offer."
                )

            if self.quantity != 1:
                errors["quantity"] = (
                    "Customer-owned frame services must have "
                    "quantity one."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.is_non_refundable = self.item_type in {
            self.ItemType.POWERED_EYEWEAR,
            self.ItemType.CUSTOMER_OWNED_FRAME,
        }

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.offer_id:
            return f"{self.cart} — {self.offer.sku}"

        return f"{self.cart} — Customer-owned frame service"


class PoweredEyewearConfiguration(models.Model):
    cart_item = models.OneToOneField(
        RetailCartItem,
        on_delete=models.CASCADE,
        related_name="powered_configuration",
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        related_name="powered_cart_configurations",
    )

    lens = models.ForeignKey(
        LensSpecification,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="powered_cart_configurations",
    )
    selected_coatings = models.ManyToManyField(
        LensCoating,
        related_name="powered_cart_configurations",
        blank=True,
    )

    lens_quote_breakdown = models.JSONField(
        default=list,
        blank=True,
    )
    lens_quote_total_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    configured_unit_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quote_refreshed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Powered-eyewear configuration"
        verbose_name_plural = "Powered-eyewear configurations"

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.cart_item_id
            and self.cart_item.item_type
            != RetailCartItem.ItemType.POWERED_EYEWEAR
        ):
            errors["cart_item"] = (
                "The cart item must be a powered-eyewear item."
            )

        if (
            self.cart_item_id
            and self.prescription_id
            and self.prescription.user_id
            != self.cart_item.cart.user_id
        ):
            errors["prescription"] = (
                "The prescription must belong to the cart owner."
            )

        if self.lens_id:
            if not self.lens.is_powered:
                errors["lens"] = (
                    "A powered lens specification is required."
                )

            if not self.prescription.is_approved:
                errors["lens"] = (
                    "A lens may only be selected after the "
                    "prescription is approved."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_configured(self):
        return (
            self.prescription.is_approved
            and self.lens_id is not None
            and self.configured_unit_price_including_gst
            is not None
        )

    def __str__(self):
        return f"Powered configuration for item #{self.cart_item_id}"


class CustomerOwnedFrameService(models.Model):
    class CompletionChoice(models.TextChoices):
        FIT_AND_RETURN = (
            "fit_and_return",
            "Fit lenses and return complete eyewear",
        )
        SEND_LENSES_ONLY = (
            "send_lenses_only",
            "Send lenses only",
        )

    class FrameHandling(models.TextChoices):
        NOT_REQUIRED = (
            "not_required",
            "Frame not required",
        )
        BRING_TO_STORE = (
            "bring_to_store",
            "Bring frame to store",
        )
        SEND_TO_STORE = (
            "send_to_store",
            "Send frame to store",
        )

    cart_item = models.OneToOneField(
        RetailCartItem,
        on_delete=models.CASCADE,
        related_name="owned_frame_service",
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        related_name="owned_frame_cart_services",
    )

    completion_choice = models.CharField(
        max_length=30,
        choices=CompletionChoice.choices,
    )
    frame_handling = models.CharField(
        max_length=30,
        choices=FrameHandling.choices,
        default=FrameHandling.NOT_REQUIRED,
    )
    customer_notes = models.TextField(blank=True)

    lens = models.ForeignKey(
        LensSpecification,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_frame_cart_services",
    )
    selected_coatings = models.ManyToManyField(
        LensCoating,
        related_name="owned_frame_cart_services",
        blank=True,
    )

    lens_quote_breakdown = models.JSONField(
        default=list,
        blank=True,
    )
    lens_quote_total_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    configured_unit_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quote_refreshed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer-owned frame service"
        verbose_name_plural = "Customer-owned frame services"

    def clean(self):
        super().clean()

        self.customer_notes = self.customer_notes.strip()
        errors = {}

        if (
            self.cart_item_id
            and self.cart_item.item_type
            != RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
        ):
            errors["cart_item"] = (
                "The cart item must be a customer-owned frame service."
            )

        if (
            self.cart_item_id
            and self.prescription_id
            and self.prescription.user_id
            != self.cart_item.cart.user_id
        ):
            errors["prescription"] = (
                "The prescription must belong to the cart owner."
            )

        if (
            self.completion_choice
            == self.CompletionChoice.FIT_AND_RETURN
            and self.frame_handling
            not in {
                self.FrameHandling.BRING_TO_STORE,
                self.FrameHandling.SEND_TO_STORE,
            }
        ):
            errors["frame_handling"] = (
                "Choose how the frame will reach the store."
            )

        if (
            self.completion_choice
            == self.CompletionChoice.SEND_LENSES_ONLY
            and self.frame_handling
            != self.FrameHandling.NOT_REQUIRED
        ):
            errors["frame_handling"] = (
                "Frame handling must be 'Frame not required' "
                "when only lenses will be sent."
            )

        if self.lens_id:
            if not self.lens.is_powered:
                errors["lens"] = (
                    "A powered lens specification is required."
                )

            if not self.prescription.is_approved:
                errors["lens"] = (
                    "A lens may only be selected after the "
                    "prescription is approved."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_configured(self):
        return (
            self.prescription.is_approved
            and self.lens_id is not None
            and self.configured_unit_price_including_gst
            is not None
        )

    def __str__(self):
        return f"Customer-owned frame service #{self.cart_item_id}"
