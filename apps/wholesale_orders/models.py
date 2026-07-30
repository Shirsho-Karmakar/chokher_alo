import secrets
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import ProductVariant
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)
from apps.wholesale.models import WholesaleAccount
from apps.wholesale_catalog.models import WholesaleLensVariant
from apps.wholesale_cart.models import WholesaleCart


ORDER_NUMBER_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_wholesale_order_number():
    random_part = "".join(
        secrets.choice(ORDER_NUMBER_ALPHABET)
        for _ in range(12)
    )
    return f"CHA-WO-{random_part}"


def generate_payment_idempotency_key():
    return f"wh-pay-{secrets.token_urlsafe(24)}"


class WholesaleOrder(models.Model):
    class Status(models.TextChoices):
        PAYMENT_PENDING = (
            "payment_pending",
            "Payment pending",
        )
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        default=generate_wholesale_order_number,
    )

    wholesale_account = models.ForeignKey(
        WholesaleAccount,
        on_delete=models.PROTECT,
        related_name="wholesale_orders",
    )
    source_cart = models.ForeignKey(
        WholesaleCart,
        on_delete=models.PROTECT,
        related_name="wholesale_orders",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PAYMENT_PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
        db_index=True,
    )

    business_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    subtotal_including_gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    delivery_fee_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    grand_total_including_gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_boxes = models.PositiveIntegerField(default=0)

    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    placed_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_cart"],
                condition=models.Q(
                    status__in=[
                        "payment_pending",
                        "confirmed",
                        "processing",
                        "shipped",
                    ]
                ),
                name="uniq_active_wh_order_per_cart",
            ),
        ]
        indexes = [
            models.Index(
                fields=["wholesale_account", "status"],
                name="wh_order_account_status_idx",
            ),
            models.Index(
                fields=["status", "created_at"],
                name="wh_order_status_created_idx",
            ),
        ]

    def __str__(self):
        return self.order_number


class WholesaleOrderAddressSnapshot(models.Model):
    order = models.OneToOneField(
        WholesaleOrder,
        on_delete=models.CASCADE,
        related_name="billing_address",
    )

    recipient_name = models.CharField(max_length=255)
    business_name = models.CharField(
        max_length=255,
        blank=True,
    )
    phone_number = models.CharField(max_length=30)
    invoice_email = models.EmailField()
    gstin = models.CharField(max_length=15, blank=True)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )
    landmark = models.CharField(
        max_length=255,
        blank=True,
    )
    city = models.CharField(max_length=150)
    district = models.CharField(
        max_length=150,
        blank=True,
    )
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Wholesale billing-address snapshot"
        verbose_name_plural = (
            "Wholesale billing-address snapshots"
        )

    def __str__(self):
        return f"{self.order.order_number} — billing"


class WholesaleOrderItem(models.Model):
    order = models.ForeignKey(
        WholesaleOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        WholesaleLensVariant,
        on_delete=models.PROTECT,
        related_name="wholesale_order_items",
    )
    physical_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="wholesale_order_items",
    )
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.PROTECT,
        related_name="wholesale_order_items",
    )

    eye = models.CharField(
        max_length=10,
        choices=PrescriptionEyeValue.Eye.choices,
    )
    boxes = models.PositiveIntegerField()
    physical_units_reserved = models.PositiveIntegerField()

    base_box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    applied_box_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    discount_per_box_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    subtotal_including_gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
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

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(boxes__gte=1),
                name="wh_order_item_boxes_gte_1",
            ),
        ]

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.variant.sku} — {self.eye}"
        )


class WholesalePaymentAttempt(models.Model):
    class Method(models.TextChoices):
        RAZORPAY = "razorpay", "Razorpay"
        BANK_TRANSFER = (
            "bank_transfer",
            "Bank transfer",
        )
        PAY_AT_STORE = (
            "pay_at_store",
            "Pay at store",
        )

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey(
        WholesaleOrder,
        on_delete=models.CASCADE,
        related_name="payment_attempts",
    )

    method = models.CharField(
        max_length=30,
        choices=Method.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    amount_including_gst = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
        default=generate_payment_idempotency_key,
    )

    provider_order_id = models.CharField(
        max_length=150,
        blank=True,
    )
    provider_payment_id = models.CharField(
        max_length=150,
        blank=True,
    )
    provider_signature = models.CharField(
        max_length=255,
        blank=True,
    )
    provider_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="wh_pay_status_created_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.get_method_display()}"
        )


class WholesaleFulfillment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.OneToOneField(
        WholesaleOrder,
        on_delete=models.CASCADE,
        related_name="fulfillment",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    carrier_name = models.CharField(
        max_length=100,
        blank=True,
    )
    tracking_number = models.CharField(
        max_length=150,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    processing_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    shipped_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.get_status_display()}"
        )


class WholesaleStockReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"
        EXPIRED = "expired", "Expired"

    order = models.ForeignKey(
        WholesaleOrder,
        on_delete=models.CASCADE,
        related_name="stock_reservations",
    )
    order_item = models.OneToOneField(
        WholesaleOrderItem,
        on_delete=models.CASCADE,
        related_name="stock_reservation",
    )

    wholesale_variant = models.ForeignKey(
        WholesaleLensVariant,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    physical_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="wholesale_stock_reservations",
    )

    boxes_reserved = models.PositiveIntegerField()
    physical_units_reserved = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(
                fields=["status", "expires_at"],
                name="wh_res_status_expiry_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.wholesale_variant.sku}"
        )
