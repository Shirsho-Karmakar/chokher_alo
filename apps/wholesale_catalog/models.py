from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.lenses.models import (
    LensCoating,
    LensPrescriptionRule,
    LensSpecification,
)


class WholesaleLensListing(models.Model):
    """
    A powered lens family offered through the wholesale portal.

    Examples of catalogue codes include SV.CR, KT.CR, and PROG.
    Their meanings remain administrator-managed rather than hard-coded.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMING_SOON = "coming_soon", "Coming soon"
        ACTIVE = "active", "Active"
        DISCONTINUED = "discontinued", "Discontinued"

    class BoxContentsUnit(models.TextChoices):
        INDIVIDUAL_LENS = (
            "individual_lens",
            "Individual lenses",
        )
        PAIR = "pair", "Pairs of lenses"

    lens = models.OneToOneField(
        LensSpecification,
        on_delete=models.PROTECT,
        related_name="wholesale_listing",
    )

    catalogue_code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Editable code such as SV.CR or PROG.",
    )
    name = models.CharField(max_length=150)

    box_contents_unit = models.CharField(
        max_length=30,
        choices=BoxContentsUnit.choices,
        default=BoxContentsUnit.INDIVIDUAL_LENS,
    )
    units_per_box = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text=(
            "Number of individual lenses or pairs contained "
            "in one wholesale box."
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)

    public_notes = models.TextField(blank=True)
    internal_notes = models.TextField(
        blank=True,
        help_text="Visible only to authorized staff.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["catalogue_code"]
        verbose_name = "Wholesale lens listing"
        verbose_name_plural = "Wholesale lens listings"

    def clean(self):
        super().clean()

        self.catalogue_code = self.catalogue_code.strip().upper()
        self.name = self.name.strip()
        self.public_notes = self.public_notes.strip()
        self.internal_notes = self.internal_notes.strip()

        if self.lens_id and not self.lens.is_powered:
            raise ValidationError(
                {
                    "lens": (
                        "Only powered lenses may be added to "
                        "the wholesale catalogue."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.catalogue_code} — {self.name}"


class WholesaleLensVariant(models.Model):
    """
    One exact wholesale product row.

    A row combines:
    - lens family
    - prescription range
    - coating/business code
    - box price
    - wholesale box inventory
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AVAILABLE = "available", "Available"
        SOLD_OUT = "sold_out", "Sold out"
        COMING_SOON = "coming_soon", "Coming soon"
        DISCONTINUED = "discontinued", "Discontinued"

    listing = models.ForeignKey(
        WholesaleLensListing,
        on_delete=models.PROTECT,
        related_name="variants",
    )
    prescription_rule = models.ForeignKey(
        LensPrescriptionRule,
        on_delete=models.PROTECT,
        related_name="wholesale_variants",
    )
    coating = models.ForeignKey(
        LensCoating,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wholesale_variants",
        help_text=(
            "Leave empty for a plain or uncoated catalogue column."
        ),
    )

    sku = models.CharField(
        max_length=24,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    supplier_code = models.CharField(
        max_length=100,
        blank=True,
    )

    base_box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    boxes_in_stock = models.PositiveIntegerField(default=0)

    minimum_order_boxes = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    order_multiple_boxes = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text=(
            "Orders must use this box multiple. "
            "For example, 5 permits 5, 10, 15, and so on."
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)

    public_notes = models.TextField(blank=True)
    internal_notes = models.TextField(
        blank=True,
        help_text="Visible only to authorized staff.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "listing",
            "prescription_rule",
            "coating",
        ]
        verbose_name = "Wholesale lens variant"
        verbose_name_plural = "Wholesale lens variants"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "listing",
                    "prescription_rule",
                    "coating",
                ],
                name="uniq_wholesale_lens_rule_coating",
                nulls_distinct=False,
            ),
        ]

    def clean(self):
        super().clean()

        self.supplier_code = self.supplier_code.strip()
        self.public_notes = self.public_notes.strip()
        self.internal_notes = self.internal_notes.strip()

        errors = {}

        if self.listing_id and self.prescription_rule_id:
            if (
                self.prescription_rule.lens_id
                != self.listing.lens_id
            ):
                errors["prescription_rule"] = (
                    "The prescription rule must belong to "
                    "the listing's lens specification."
                )

        if self.coating_id and self.listing_id:
            coating_is_available = (
                self.listing.lens.coatings
                .filter(pk=self.coating_id)
                .exists()
            )

            if not coating_is_available:
                errors["coating"] = (
                    "The coating must be enabled for the "
                    "listing's lens specification."
                )

        price_required_statuses = {
            self.Status.AVAILABLE,
            self.Status.SOLD_OUT,
        }

        if (
            self.status in price_required_statuses
            and self.base_box_price_including_gst is None
        ):
            errors["base_box_price_including_gst"] = (
                "A box price is required for available and "
                "sold-out wholesale products."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["sku"])
        super().save(*args, **kwargs)

        if not self.sku:
            generated_sku = f"CHA-WHL-{self.pk:06d}"

            type(self).objects.filter(pk=self.pk).update(
                sku=generated_sku
            )
            self.sku = generated_sku

    @property
    def effective_status(self) -> str:
        if not self.is_active or not self.listing.is_active:
            return self.Status.DISCONTINUED

        if (
            self.listing.status
            == WholesaleLensListing.Status.DISCONTINUED
            or self.status == self.Status.DISCONTINUED
        ):
            return self.Status.DISCONTINUED

        if (
            self.listing.status
            == WholesaleLensListing.Status.DRAFT
            or self.status == self.Status.DRAFT
        ):
            return self.Status.DRAFT

        if (
            self.listing.status
            == WholesaleLensListing.Status.COMING_SOON
            or self.status == self.Status.COMING_SOON
        ):
            return self.Status.COMING_SOON

        if (
            self.status == self.Status.SOLD_OUT
            or self.boxes_in_stock == 0
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
            and self.base_box_price_including_gst is not None
        )

    def __str__(self):
        coating = self.coating.code if self.coating_id else "PLAIN"

        return (
            f"{self.listing.catalogue_code} / "
            f"{self.prescription_rule.name} / {coating}"
        )


class WholesaleBulkPriceTier(models.Model):
    """
    Product-specific wholesale box price for a quantity range.

    Prices are final per-box amounts including GST. Tiers do not stack.
    """

    variant = models.ForeignKey(
        WholesaleLensVariant,
        on_delete=models.CASCADE,
        related_name="bulk_price_tiers",
    )

    minimum_boxes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    maximum_boxes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Leave empty for an open-ended final tier.",
    )

    box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "variant",
            "minimum_boxes",
        ]
        verbose_name = "Wholesale bulk-price tier"
        verbose_name_plural = "Wholesale bulk-price tiers"
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "minimum_boxes"],
                name="uniq_wholesale_tier_minimum",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.maximum_boxes is not None
            and self.maximum_boxes < self.minimum_boxes
        ):
            errors["maximum_boxes"] = (
                "Maximum boxes must be greater than or "
                "equal to minimum boxes."
            )

        if (
            self.variant_id
            and self.variant.base_box_price_including_gst
            is not None
            and self.box_price_including_gst
            > self.variant.base_box_price_including_gst
        ):
            errors["box_price_including_gst"] = (
                "A bulk price cannot exceed the normal box price."
            )

        if self.variant_id and self.minimum_boxes:
            current_maximum = (
                self.maximum_boxes
                if self.maximum_boxes is not None
                else float("inf")
            )

            other_tiers = (
                type(self).objects
                .filter(variant_id=self.variant_id)
                .exclude(pk=self.pk)
            )

            for other_tier in other_tiers:
                other_maximum = (
                    other_tier.maximum_boxes
                    if other_tier.maximum_boxes is not None
                    else float("inf")
                )

                ranges_overlap = (
                    self.minimum_boxes <= other_maximum
                    and other_tier.minimum_boxes
                    <= current_maximum
                )

                if ranges_overlap:
                    errors["minimum_boxes"] = (
                        "This quantity range overlaps an "
                        "existing bulk-price tier."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def matches_quantity(self, boxes: int) -> bool:
        if boxes < self.minimum_boxes:
            return False

        if (
            self.maximum_boxes is not None
            and boxes > self.maximum_boxes
        ):
            return False

        return True

    def __str__(self):
        maximum = (
            str(self.maximum_boxes)
            if self.maximum_boxes is not None
            else "and above"
        )

        return (
            f"{self.variant.sku}: "
            f"{self.minimum_boxes}–{maximum} boxes"
        )
