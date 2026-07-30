from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)
from apps.wholesale.models import WholesaleAccount
from apps.wholesale_catalog.models import WholesaleLensVariant


class WholesaleCart(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CHECKOUT_STARTED = (
            "checkout_started",
            "Checkout started",
        )
        CONVERTED = "converted", "Converted to order"
        ABANDONED = "abandoned", "Abandoned"

    wholesale_account = models.ForeignKey(
        WholesaleAccount,
        on_delete=models.PROTECT,
        related_name="wholesale_carts",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )

    pricing_updated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wholesale_account"],
                condition=models.Q(
                    status__in=[
                        "open",
                        "checkout_started",
                    ]
                ),
                name="uniq_active_wholesale_cart",
            ),
        ]
        indexes = [
            models.Index(
                fields=["wholesale_account", "status"],
                name="wh_cart_account_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.wholesale_account.reference_id} — "
            f"{self.get_status_display()}"
        )


class WholesaleCartItem(models.Model):
    class ValidationStatus(models.TextChoices):
        VALID = "valid", "Valid"
        INVALID = "invalid", "Invalid"

    cart = models.ForeignKey(
        WholesaleCart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        WholesaleLensVariant,
        on_delete=models.PROTECT,
        related_name="wholesale_cart_items",
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        related_name="wholesale_cart_items",
    )

    eye = models.CharField(
        max_length=10,
        choices=PrescriptionEyeValue.Eye.choices,
    )
    boxes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    base_box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    applied_box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_per_box_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    subtotal_including_gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    bulk_price_tier_id_snapshot = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    variant_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )
    prescription_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )
    pricing_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.INVALID,
        db_index=True,
    )
    validation_code = models.CharField(
        max_length=80,
        blank=True,
    )
    validation_message = models.TextField(blank=True)
    validated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "cart",
                    "variant",
                    "prescription",
                    "eye",
                ],
                name="uniq_wh_cart_line",
            ),
            models.CheckConstraint(
                condition=models.Q(boxes__gte=1),
                name="wh_cart_boxes_gte_1",
            ),
        ]
        indexes = [
            models.Index(
                fields=["cart", "validation_status"],
                name="wh_cart_item_status_idx",
            ),
        ]

    def clean(self):
        super().clean()

        self.validation_code = self.validation_code.strip()
        self.validation_message = (
            self.validation_message.strip()
        )

        if (
            self.cart_id
            and self.prescription_id
            and self.prescription.user_id
            != self.cart.wholesale_account.user_id
        ):
            raise ValidationError(
                {
                    "prescription": (
                        "The prescription must belong to the "
                        "wholesale account user."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.variant.sku} / {self.eye} / "
            f"{self.boxes} box(es)"
        )
