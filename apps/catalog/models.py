from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.utils.text import slugify


HEX_COLOUR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Enter a hexadecimal colour such as #000000.",
)


class Brand(models.Model):
    name = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(
        max_length=130,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    code = models.CharField(
        max_length=3,
        unique=True,
        help_text="Three-letter internal code, such as FRM or SUN.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.code = self.code.strip().upper()

        if len(self.code) != 3 or not self.code.isalnum():
            raise ValidationError(
                {
                    "code": (
                        "The category code must contain exactly "
                        "three letters or numbers."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["slug"])
        super().save(*args, **kwargs)

        if not self.slug:
            generated_slug = slugify(f"{self.name}-{self.pk}")
            type(self).objects.filter(pk=self.pk).update(
                slug=generated_slug
            )
            self.slug = generated_slug

    def __str__(self):
        return self.name


class Colour(models.Model):
    name = models.CharField(max_length=100, unique=True)
    hex_value = models.CharField(
        max_length=7,
        blank=True,
        validators=[HEX_COLOUR_VALIDATOR],
        help_text="Optional display colour such as #000000.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

        if self.hex_value:
            self.hex_value = self.hex_value.upper()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Material(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class FrameShape(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class FrameType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductDesign(models.Model):
    class Kind(models.TextChoices):
        FRAME = "frame", "Frame design"
        LENS = "lens", "Lens"
        ACCESSORY = "accessory", "Accessory"

    class Gender(models.TextChoices):
        MEN = "men", "Men"
        WOMEN = "women", "Women"
        UNISEX = "unisex", "Unisex"
        KIDS = "kids", "Kids"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMING_SOON = "coming_soon", "Coming soon"
        ACTIVE = "active", "Active"
        DISCONTINUED = "discontinued", "Discontinued"

    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=280,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    supplier_model_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )

    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.FRAME,
    )

    brand = models.ForeignKey(
        Brand,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="product_designs",
    )
    categories = models.ManyToManyField(
        Category,
        related_name="product_designs",
        blank=True,
    )

    gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
        default=Gender.UNISEX,
    )

    material = models.ForeignKey(
        Material,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="product_designs",
    )
    frame_shape = models.ForeignKey(
        FrameShape,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="product_designs",
    )
    frame_type = models.ForeignKey(
        FrameType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="product_designs",
    )

    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "supplier_model_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["brand", "supplier_model_number"],
                condition=~models.Q(supplier_model_number=""),
                name="uniq_brand_supplier_model",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.supplier_model_number = (
            self.supplier_model_number.strip()
        )
        self.description = self.description.strip()

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["slug"])
        super().save(*args, **kwargs)

        if not self.slug:
            generated_slug = slugify(f"{self.name}-{self.pk}")
            type(self).objects.filter(pk=self.pk).update(
                slug=generated_slug
            )
            self.slug = generated_slug

    def __str__(self):
        if self.supplier_model_number:
            return f"{self.name} ({self.supplier_model_number})"

        return self.name


class ProductVariant(models.Model):
    class StockMode(models.TextChoices):
        QUANTITY = "quantity", "Track exact quantity"
        STATUS_ONLY = "status_only", "Status only"

    class StockStatus(models.TextChoices):
        AVAILABLE = "available", "Available"
        SOLD_OUT = "sold_out", "Sold out"
        COMING_SOON = "coming_soon", "Coming soon"

    design = models.ForeignKey(
        ProductDesign,
        on_delete=models.PROTECT,
        related_name="variants",
    )
    colour = models.ForeignKey(
        Colour,
        on_delete=models.PROTECT,
        related_name="product_variants",
    )

    size_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Examples: Small, Medium, Large, Free Size.",
    )
    supplier_variant_code = models.CharField(
        max_length=100,
        blank=True,
    )

    physical_sku = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )

    lens_width_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    lens_height_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    frame_width_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    stock_mode = models.CharField(
        max_length=20,
        choices=StockMode.choices,
        default=StockMode.STATUS_ONLY,
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    manual_stock_status = models.CharField(
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.AVAILABLE,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["design", "colour", "size_label"]
        constraints = [
            models.UniqueConstraint(
                fields=["design", "colour", "size_label"],
                name="uniq_design_colour_size",
            ),
        ]

    def clean(self):
        super().clean()
        self.size_label = self.size_label.strip()
        self.supplier_variant_code = (
            self.supplier_variant_code.strip()
        )

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["physical_sku"])
        super().save(*args, **kwargs)

        if not self.physical_sku:
            generated_sku = f"CHA-STK-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                physical_sku=generated_sku
            )
            self.physical_sku = generated_sku

    @property
    def effective_stock_status(self) -> str:
        if (
            not self.is_active
            or self.design.status
            in {
                ProductDesign.Status.DRAFT,
                ProductDesign.Status.DISCONTINUED,
            }
        ):
            return self.StockStatus.SOLD_OUT

        if (
            self.design.status == ProductDesign.Status.COMING_SOON
            or self.manual_stock_status
            == self.StockStatus.COMING_SOON
        ):
            return self.StockStatus.COMING_SOON

        if self.stock_mode == self.StockMode.QUANTITY:
            if self.stock_quantity > 0:
                return self.StockStatus.AVAILABLE

            return self.StockStatus.SOLD_OUT

        return self.manual_stock_status

    def __str__(self):
        details = [str(self.design), str(self.colour)]

        if self.size_label:
            details.append(self.size_label)

        return " / ".join(details)


class ProductOffer(models.Model):
    class OfferType(models.TextChoices):
        FRAME_ONLY = "frame_only", "Frame only"
        ZERO_POWER = "zero_power", "Zero-power eyewear"
        SUNGLASSES = "sunglasses", "Sunglasses"
        ACCESSORY = "accessory", "Accessory"
        LENS = "lens", "Lens"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMING_SOON = "coming_soon", "Coming soon"
        AVAILABLE = "available", "Available"
        SOLD_OUT = "sold_out", "Sold out"
        DISCONTINUED = "discontinued", "Discontinued"

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="offers",
    )
    offer_type = models.CharField(
        max_length=30,
        choices=OfferType.choices,
    )

    sku = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )

    mrp_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    selling_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        help_text="Enter the applicable GST percentage.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    requires_prescription = models.BooleanField(default=False)
    supports_powered_lenses = models.BooleanField(
        default=False,
        help_text=(
            "Allow the customer to combine this eyewear offer "
            "with prescription-powered lenses."
        ),
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["variant", "offer_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "offer_type"],
                name="uniq_variant_offer_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(mrp_including_gst__isnull=True)
                    | models.Q(
                        selling_price_including_gst__isnull=True
                    )
                    | models.Q(
                        selling_price_including_gst__lte=models.F(
                            "mrp_including_gst"
                        )
                    )
                ),
                name="offer_selling_price_not_above_mrp",
            ),
        ]

    def clean(self):
        super().clean()

        price_required_statuses = {
            self.Status.AVAILABLE,
            self.Status.SOLD_OUT,
        }

        errors = {}

        if self.status in price_required_statuses:
            if self.mrp_including_gst is None:
                errors["mrp_including_gst"] = (
                    "MRP is required for available and sold-out offers."
                )

            if self.selling_price_including_gst is None:
                errors["selling_price_including_gst"] = (
                    "Selling price is required for available and "
                    "sold-out offers."
                )

        if (
            self.mrp_including_gst is not None
            and self.selling_price_including_gst is not None
            and self.selling_price_including_gst
            > self.mrp_including_gst
        ):
            errors["selling_price_including_gst"] = (
                "Selling price cannot exceed MRP."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["sku"])
        super().save(*args, **kwargs)

        if not self.sku:
            prefix_by_type = {
                self.OfferType.FRAME_ONLY: "FRM",
                self.OfferType.ZERO_POWER: "ZPW",
                self.OfferType.SUNGLASSES: "SUN",
                self.OfferType.ACCESSORY: "ACC",
                self.OfferType.LENS: "LEN",
            }

            prefix = prefix_by_type[self.offer_type]
            generated_sku = f"CHA-{prefix}-{self.pk:06d}"

            type(self).objects.filter(pk=self.pk).update(
                sku=generated_sku
            )
            self.sku = generated_sku

    @property
    def effective_status(self) -> str:
        if not self.is_active:
            return self.Status.DISCONTINUED

        if self.status in {
            self.Status.DRAFT,
            self.Status.DISCONTINUED,
        }:
            return self.status

        if self.status == self.Status.COMING_SOON:
            return self.Status.COMING_SOON

        variant_status = self.variant.effective_stock_status

        if (
            variant_status
            == ProductVariant.StockStatus.COMING_SOON
        ):
            return self.Status.COMING_SOON

        if (
            self.status == self.Status.SOLD_OUT
            or variant_status == ProductVariant.StockStatus.SOLD_OUT
        ):
            return self.Status.SOLD_OUT

        return self.Status.AVAILABLE

    @property
    def price_visible(self) -> bool:
        return (
            self.effective_status
            in {
                self.Status.AVAILABLE,
                self.Status.SOLD_OUT,
            }
            and self.mrp_including_gst is not None
            and self.selling_price_including_gst is not None
        )

    def __str__(self):
        return (
            f"{self.variant} — "
            f"{self.get_offer_type_display()}"
        )


class ProductImage(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="images",
    )
    offer = models.ForeignKey(
        ProductOffer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="images",
        help_text=(
            "Leave empty for a general variant image. "
            "Select an offer for an offer-specific image."
        ),
    )

    image = models.ImageField(
        upload_to="catalog/products/%Y/%m/",
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant"],
                condition=(
                    models.Q(is_primary=True)
                    & models.Q(offer__isnull=True)
                ),
                name="uniq_primary_general_variant_image",
            ),
            models.UniqueConstraint(
                fields=["offer"],
                condition=(
                    models.Q(is_primary=True)
                    & models.Q(offer__isnull=False)
                ),
                name="uniq_primary_offer_image",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.offer_id
            and self.offer.variant_id != self.variant_id
        ):
            raise ValidationError(
                {
                    "offer": (
                        "The selected offer must belong to the "
                        "selected product variant."
                    )
                }
            )

        self.alt_text = self.alt_text.strip()

    def save(self, *args, **kwargs):
        self.full_clean(validate_constraints=False)

        with transaction.atomic():
            if self.is_primary:
                existing_images = ProductImage.objects.filter(
                    variant=self.variant,
                    is_primary=True,
                ).exclude(pk=self.pk)

                if self.offer_id:
                    existing_images = existing_images.filter(
                        offer=self.offer
                    )
                else:
                    existing_images = existing_images.filter(
                        offer__isnull=True
                    )

                existing_images.update(is_primary=False)

            return super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.offer or self.variant}"


class ProductStockAlert(models.Model):
    """
    A customer's request to be notified when an unavailable retail offer
    becomes available.

    Actual email and SMS delivery will be added in the notification stage.
    """

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        NOTIFIED = "notified", "Notified"
        CANCELLED = "cancelled", "Cancelled"

        FAILED = "failed", "Failed"
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_stock_alerts",
    )
    offer = models.ForeignKey(
        ProductOffer,
        on_delete=models.PROTECT,
        related_name="stock_alerts",
    )
    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
    )
    destination = models.CharField(
        max_length=254,
        editable=False,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    attempt_count = models.PositiveSmallIntegerField(
        default=0,
    )
    last_error = models.TextField(blank=True)
    delivery_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    notified_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Product stock alert"
        verbose_name_plural = "Product stock alerts"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "offer", "channel"],
                condition=models.Q(status="active"),
                name="uniq_active_product_stock_alert",
            ),
        ]

    def clean(self):
        super().clean()

        if self.status != self.Status.ACTIVE:
            return

        errors = {}

        if not self.user_id or not self.user.is_active:
            errors["user"] = "An active customer account is required."

        if self.offer_id:
            offer_status = self.offer.effective_status

            if offer_status not in {
                ProductOffer.Status.SOLD_OUT,
                ProductOffer.Status.COMING_SOON,
            }:
                errors["offer"] = (
                    "Stock alerts are only available for sold-out "
                    "or coming-soon products."
                )

        if self.channel == self.Channel.SMS:
            if (
                not self.user.phone_number
                or not self.user.phone_verified
            ):
                errors["channel"] = (
                    "A verified phone number is required for SMS alerts."
                )
            else:
                self.destination = self.user.phone_number

        elif self.channel == self.Channel.EMAIL:
            if not self.user.email or not self.user.email_verified:
                errors["channel"] = (
                    "A verified email address is required "
                    "for email alerts."
                )
            else:
                self.destination = self.user.email

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.user} — {self.offer.sku} — "
            f"{self.get_channel_display()}"
        )
