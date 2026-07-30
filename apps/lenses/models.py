from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models

from apps.catalog.models import ProductDesign, ProductOffer


class LensVisionType(models.Model):
    code = models.CharField(
        max_length=30,
        unique=True,
        help_text="Internal code such as SV, BF, or PROG.",
    )
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.code = self.code.strip().upper()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class LensRefractiveIndex(models.Model):
    value = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        unique=True,
        validators=[
            MinValueValidator(Decimal("1.00")),
            MaxValueValidator(Decimal("2.50")),
        ],
    )
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional name such as Standard, Thin, or Ultra Thin.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["value"]
        verbose_name = "Lens refractive index"
        verbose_name_plural = "Lens refractive indices"

    def clean(self):
        super().clean()
        self.display_name = self.display_name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.display_name:
            return f"{self.value} — {self.display_name}"

        return str(self.value)


class LensCoating(models.Model):
    code = models.CharField(
        max_length=30,
        unique=True,
        help_text="Editable business code such as HC, PG, or BRC.",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        super().clean()
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.description = self.description.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.name}"


class LensSpecification(models.Model):
    class SellingUnit(models.TextChoices):
        INDIVIDUAL = "individual", "Individual lens"
        PAIR = "pair", "Pair of lenses"
        BOX = "box", "Box"

    offer = models.OneToOneField(
        ProductOffer,
        on_delete=models.PROTECT,
        related_name="lens_specification",
    )

    vision_type = models.ForeignKey(
        LensVisionType,
        on_delete=models.PROTECT,
        related_name="lens_specifications",
    )
    refractive_index = models.ForeignKey(
        LensRefractiveIndex,
        on_delete=models.PROTECT,
        related_name="lens_specifications",
    )
    coatings = models.ManyToManyField(
        LensCoating,
        related_name="lens_specifications",
        blank=True,
    )

    is_powered = models.BooleanField(default=True)
    require_both_eyes = models.BooleanField(
        default=True,
        help_text=(
            "Require compatible right-eye and left-eye values "
            "before showing this lens."
        ),
    )

    selling_unit = models.CharField(
        max_length=20,
        choices=SellingUnit.choices,
        default=SellingUnit.PAIR,
    )
    units_per_box = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Required only when the selling unit is Box.",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "vision_type",
            "refractive_index",
            "offer",
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.offer_id:
            if self.offer.offer_type != ProductOffer.OfferType.LENS:
                errors["offer"] = (
                    "A lens specification must use a Lens offer."
                )

            if (
                self.offer.variant.design.kind
                != ProductDesign.Kind.LENS
            ):
                errors["offer"] = (
                    "The selected offer must belong to a lens design."
                )

            if (
                self.is_powered
                and not self.offer.requires_prescription
            ):
                errors["offer"] = (
                    "Powered lens offers must require a prescription."
                )

            if (
                not self.is_powered
                and self.offer.requires_prescription
            ):
                errors["offer"] = (
                    "Zero-power lens offers must not require "
                    "a prescription."
                )

        if self.selling_unit == self.SellingUnit.BOX:
            if not self.units_per_box:
                errors["units_per_box"] = (
                    "Enter the number of units contained in one box."
                )
        elif self.units_per_box is not None:
            errors["units_per_box"] = (
                "Units per box may only be entered for Box products."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.offer} — "
            f"{self.vision_type} / {self.refractive_index}"
        )


class LensPrescriptionRule(models.Model):
    class AxisMode(models.TextChoices):
        ANY = "any", "Any axis"
        EXACT = "exact", "Configured exact axes"
        NOT_REQUIRED = "not_required", "Axis not required"

    lens = models.ForeignKey(
        LensSpecification,
        on_delete=models.CASCADE,
        related_name="prescription_rules",
    )

    name = models.CharField(
        max_length=150,
        help_text="Administrative label describing this range.",
    )

    minimum_sphere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    maximum_sphere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    minimum_cylinder = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    maximum_cylinder = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    minimum_add_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    maximum_add_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    axis_mode = models.CharField(
        max_length=20,
        choices=AxisMode.choices,
        default=AxisMode.ANY,
    )
    axis_tolerance_degrees = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(20)],
        help_text=(
            "Zero means an exact match. Used only with configured axes."
        ),
    )

    supports_prism = models.BooleanField(default=False)
    priority = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "lens",
            "priority",
            "name",
        ]

    def clean(self):
        super().clean()

        self.name = self.name.strip()
        errors = {}

        range_fields = (
            (
                "minimum_sphere",
                "maximum_sphere",
                "sphere",
            ),
            (
                "minimum_cylinder",
                "maximum_cylinder",
                "cylinder",
            ),
            (
                "minimum_add_power",
                "maximum_add_power",
                "ADD power",
            ),
        )

        for minimum_field, maximum_field, label in range_fields:
            minimum_value = getattr(self, minimum_field)
            maximum_value = getattr(self, maximum_field)

            if (
                minimum_value is not None
                and maximum_value is not None
                and minimum_value > maximum_value
            ):
                errors[maximum_field] = (
                    f"Maximum {label} must be greater than "
                    f"or equal to minimum {label}."
                )

        if (
            self.axis_mode != self.AxisMode.EXACT
            and self.axis_tolerance_degrees != 0
        ):
            errors["axis_tolerance_degrees"] = (
                "Axis tolerance is only supported for exact-axis rules."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lens} — {self.name}"


class LensAllowedAxis(models.Model):
    rule = models.ForeignKey(
        LensPrescriptionRule,
        on_delete=models.CASCADE,
        related_name="allowed_axes",
    )
    axis = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(180),
        ],
    )

    class Meta:
        ordering = ["axis"]
        verbose_name = "Allowed lens axis"
        verbose_name_plural = "Allowed lens axes"
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "axis"],
                name="uniq_axis_per_lens_rule",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.rule_id
            and self.rule.axis_mode
            != LensPrescriptionRule.AxisMode.EXACT
        ):
            raise ValidationError(
                {
                    "rule": (
                        "Allowed axes can only be added to an "
                        "exact-axis rule."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.axis}° — {self.rule}"


class LensPriceRule(models.Model):
    """
    Configurable GST-inclusive adjustment applied to a lens quotation.

    The base price remains on ProductOffer. These rules represent additions
    such as index, coating, prescription-power, and frame-related charges.
    """

    class RuleType(models.TextChoices):
        INDEX = "index", "Refractive-index adjustment"
        COATING = "coating", "Coating charge"
        POWER = "power", "Prescription-power surcharge"
        FRAME = "frame", "Frame-related surcharge"

    lens = models.ForeignKey(
        LensSpecification,
        on_delete=models.CASCADE,
        related_name="price_rules",
    )
    rule_type = models.CharField(
        max_length=20,
        choices=RuleType.choices,
        db_index=True,
    )
    name = models.CharField(max_length=150)

    amount_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # Used only by coating rules.
    coating = models.ForeignKey(
        LensCoating,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="price_rules",
    )

    # Used only by frame-related rules.
    frame_type = models.ForeignKey(
        "catalog.FrameType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lens_price_rules",
    )
    frame_shape = models.ForeignKey(
        "catalog.FrameShape",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lens_price_rules",
    )
    material = models.ForeignKey(
        "catalog.Material",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lens_price_rules",
    )

    # Used only by power-surcharge rules. Absolute values are evaluated.
    minimum_abs_sphere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    maximum_abs_sphere = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    minimum_abs_cylinder = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    maximum_abs_cylinder = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    minimum_add_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    maximum_add_power = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    priority = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Higher-priority non-stackable rules take precedence."
        ),
    )
    is_stackable = models.BooleanField(
        default=False,
        help_text=(
            "Stackable matching rules are all added to the quotation."
        ),
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "lens",
            "rule_type",
            "-priority",
            "name",
        ]

    def clean(self):
        super().clean()

        self.name = self.name.strip()
        errors = {}

        power_fields = (
            "minimum_abs_sphere",
            "maximum_abs_sphere",
            "minimum_abs_cylinder",
            "maximum_abs_cylinder",
            "minimum_add_power",
            "maximum_add_power",
        )

        frame_fields = (
            "frame_type",
            "frame_shape",
            "material",
        )

        if self.rule_type == self.RuleType.COATING:
            if self.coating_id is None:
                errors["coating"] = (
                    "A coating must be selected for a coating rule."
                )

            if self.coating_id and self.lens_id:
                if not self.lens.coatings.filter(
                    pk=self.coating_id
                ).exists():
                    errors["coating"] = (
                        "The coating must be enabled for this lens."
                    )
        elif self.coating_id is not None:
            errors["coating"] = (
                "A coating may only be selected for a coating rule."
            )

        has_power_condition = any(
            getattr(self, field_name) is not None
            for field_name in power_fields
        )

        if self.rule_type == self.RuleType.POWER:
            if not has_power_condition:
                errors["rule_type"] = (
                    "A power rule requires at least one power range."
                )
        elif has_power_condition:
            errors["rule_type"] = (
                "Power ranges may only be used by power rules."
            )

        has_frame_condition = any(
            getattr(self, field_name + "_id", None) is not None
            for field_name in frame_fields
        )

        if self.rule_type == self.RuleType.FRAME:
            if not has_frame_condition:
                errors["rule_type"] = (
                    "A frame rule requires a frame type, shape, "
                    "or material."
                )
        elif has_frame_condition:
            errors["rule_type"] = (
                "Frame attributes may only be used by frame rules."
            )

        ranges = (
            (
                "minimum_abs_sphere",
                "maximum_abs_sphere",
                "sphere",
            ),
            (
                "minimum_abs_cylinder",
                "maximum_abs_cylinder",
                "cylinder",
            ),
            (
                "minimum_add_power",
                "maximum_add_power",
                "ADD power",
            ),
        )

        for minimum_field, maximum_field, label in ranges:
            minimum_value = getattr(self, minimum_field)
            maximum_value = getattr(self, maximum_field)

            if (
                minimum_value is not None
                and maximum_value is not None
                and minimum_value > maximum_value
            ):
                errors[maximum_field] = (
                    f"Maximum {label} must be greater than or "
                    f"equal to minimum {label}."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.lens} — "
            f"{self.get_rule_type_display()} — {self.name}"
        )
