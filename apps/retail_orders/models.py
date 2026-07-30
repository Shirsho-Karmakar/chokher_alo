import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.utils import timezone

from apps.catalog.models import ProductOffer, ProductVariant
from apps.lenses.models import LensSpecification
from apps.prescriptions.models import Prescription
from apps.retail_cart.models import RetailCart, RetailCartItem


MONEY_PLACES = Decimal("0.01")

INDIAN_PIN_CODE_VALIDATOR = RegexValidator(
    regex=r"^[1-9][0-9]{5}$",
    message="Enter a valid six-digit Indian PIN code.",
)


def default_cancellable_until():
    return timezone.now() + timedelta(hours=24)


def default_razorpay_payment_methods():
    """
    Business-level method names.

    Provider-specific Razorpay options will be mapped during integration.
    Credit cards are deliberately excluded.
    """
    return [
        "upi",
        "debit_card",
        "netbanking",
        "wallet",
    ]


def _money(value):
    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


class StoreLocation(models.Model):
    code = models.CharField(
        max_length=30,
        unique=True,
        help_text="Internal code such as MAIN.",
    )
    name = models.CharField(max_length=150)

    phone_number = models.CharField(
        max_length=20,
        blank=True,
    )
    email = models.EmailField(blank=True)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )
    locality = models.CharField(
        max_length=150,
        blank=True,
    )
    landmark = models.CharField(
        max_length=150,
        blank=True,
    )
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(
        max_length=6,
        validators=[INDIAN_PIN_CODE_VALIDATOR],
    )
    country = models.CharField(
        max_length=100,
        default="India",
    )

    is_active = models.BooleanField(default=True)
    is_default_pickup = models.BooleanField(default=False)

    pickup_instructions = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default_pickup"],
                condition=models.Q(is_default_pickup=True),
                name="uniq_default_pickup_store",
            ),
        ]

    def clean(self):
        super().clean()

        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.phone_number = self.phone_number.strip()
        self.address_line_1 = self.address_line_1.strip()
        self.address_line_2 = self.address_line_2.strip()
        self.locality = self.locality.strip()
        self.landmark = self.landmark.strip()
        self.city = self.city.strip()
        self.state = self.state.strip()
        self.country = self.country.strip()
        self.pickup_instructions = (
            self.pickup_instructions.strip()
        )

        if self.is_default_pickup and not self.is_active:
            raise ValidationError(
                {
                    "is_default_pickup": (
                        "The default pickup store must be active."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.name}"


class RetailCheckoutPolicy(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    delivery_fee_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    free_delivery_threshold_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    payment_reservation_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(120),
        ],
    )
    cancellation_window_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(168),
        ],
    )

    pay_at_store_enabled = models.BooleanField(default=True)

    currency = models.CharField(
        max_length=3,
        default="INR",
        editable=False,
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        verbose_name = "Retail checkout policy"
        verbose_name_plural = "Retail checkout policies"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="uniq_active_retail_checkout_policy",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delivery_fee_for(self, subtotal):
        subtotal = _money(subtotal)

        if (
            subtotal
            >= self.free_delivery_threshold_including_gst
        ):
            return Decimal("0.00")

        return _money(self.delivery_fee_including_gst)

    def __str__(self):
        return self.name


class RetailOrder(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = (
            "awaiting_payment",
            "Awaiting payment",
        )
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        PRODUCTION = (
            "production",
            "Prescription/lens production",
        )
        READY_FOR_PICKUP = (
            "ready_for_pickup",
            "Ready for pickup",
        )
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        PAYMENT_FAILED = (
            "payment_failed",
            "Payment failed",
        )

    class PaymentMethod(models.TextChoices):
        RAZORPAY = "razorpay", "Online payment"
        PAY_AT_STORE = "pay_at_store", "Pay at store"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        REFUND_PENDING = (
            "refund_pending",
            "Refund pending",
        )
        REFUNDED = "refunded", "Refunded"

    class FulfillmentMethod(models.TextChoices):
        DELIVERY = "delivery", "Delivery"
        STORE_PICKUP = "store_pickup", "Store pickup"

    order_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="retail_orders",
    )
    source_cart = models.ForeignKey(
        RetailCart,
        on_delete=models.PROTECT,
        related_name="retail_orders",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.AWAITING_PAYMENT,
        db_index=True,
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )

    fulfillment_method = models.CharField(
        max_length=20,
        choices=FulfillmentMethod.choices,
    )
    store_location = models.ForeignKey(
        StoreLocation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_orders",
    )

    billing_same_as_shipping = models.BooleanField(
        default=True
    )

    subtotal_including_gst = models.DecimalField(
        max_digits=12,
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
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(
        max_length=3,
        default="INR",
        editable=False,
    )

    checkout_policy_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )
    customer_notes = models.TextField(blank=True)

    cancellable_until = models.DateTimeField(
        default=default_cancellable_until,
    )

    payment_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    processing_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    production_started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    ready_for_pickup_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    packed_at = models.DateTimeField(
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

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_retail_orders",
    )
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="retail_order_user_created_idx",
            ),
            models.Index(
                fields=["status", "-created_at"],
                name="retail_ord_status_idx",
            ),
        ]

    def clean(self):
        super().clean()

        self.customer_notes = self.customer_notes.strip()
        self.cancellation_reason = (
            self.cancellation_reason.strip()
        )

        errors = {}

        if self.user_id and not self.user.is_active:
            errors["user"] = (
                "An active customer account is required."
            )

        if (
            self.source_cart_id
            and self.user_id
            and self.source_cart.user_id != self.user_id
        ):
            errors["source_cart"] = (
                "The source cart must belong to the order customer."
            )

        if (
            self.fulfillment_method
            == self.FulfillmentMethod.STORE_PICKUP
        ):
            if self.store_location_id is None:
                errors["store_location"] = (
                    "Store pickup requires a store location."
                )
            elif not self.store_location.is_active:
                errors["store_location"] = (
                    "The selected pickup store is inactive."
                )

        if (
            self.fulfillment_method
            == self.FulfillmentMethod.DELIVERY
            and self.store_location_id is not None
        ):
            errors["store_location"] = (
                "Delivery orders must not use a pickup store."
            )

        if (
            self.payment_method
            == self.PaymentMethod.PAY_AT_STORE
            and self.fulfillment_method
            != self.FulfillmentMethod.STORE_PICKUP
        ):
            errors["payment_method"] = (
                "Pay at store is only available for store pickup."
            )

        expected_total = _money(
            self.subtotal_including_gst
            + self.delivery_fee_including_gst
        )

        if _money(self.grand_total_including_gst) != expected_total:
            errors["grand_total_including_gst"] = (
                "Grand total must equal subtotal plus delivery fee."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["order_number"])
        super().save(*args, **kwargs)

        if not self.order_number:
            local_date = timezone.localtime(
                self.created_at
            ).strftime("%Y%m%d")

            generated_number = (
                f"CHA-R-{local_date}-{self.pk:06d}"
            )

            type(self).objects.filter(pk=self.pk).update(
                order_number=generated_number
            )
            self.order_number = generated_number

    @property
    def cancellation_block_reason(self):
        if self.status == self.Status.CANCELLED:
            return "already_cancelled"

        if self.status not in {
            self.Status.AWAITING_PAYMENT,
            self.Status.CONFIRMED,
        }:
            return "order_processing_started"

        if timezone.now() > self.cancellable_until:
            return "cancellation_window_expired"

        if any(
            timestamp is not None
            for timestamp in (
                self.processing_started_at,
                self.production_started_at,
                self.packed_at,
                self.shipped_at,
                self.delivered_at,
            )
        ):
            return "order_processing_started"

        return None

    @property
    def can_customer_cancel(self):
        return self.cancellation_block_reason is None

    def __str__(self):
        return self.order_number or f"Retail order #{self.pk}"


class RetailOrderAddressSnapshot(models.Model):
    class AddressType(models.TextChoices):
        SHIPPING = "shipping", "Shipping address"
        BILLING = "billing", "Billing address"

    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.CASCADE,
        related_name="address_snapshots",
    )
    address_type = models.CharField(
        max_length=20,
        choices=AddressType.choices,
    )

    source_address_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        editable=False,
    )

    recipient_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )
    locality = models.CharField(
        max_length=150,
        blank=True,
    )
    landmark = models.CharField(
        max_length=150,
        blank=True,
    )
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(
        max_length=6,
        validators=[INDIAN_PIN_CODE_VALIDATOR],
    )
    country = models.CharField(
        max_length=100,
        default="India",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "address_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "address_type"],
                name="uniq_retail_order_address_type",
            ),
        ]

    def clean(self):
        super().clean()

        self.recipient_name = self.recipient_name.strip()
        self.phone_number = self.phone_number.strip()
        self.address_line_1 = self.address_line_1.strip()
        self.address_line_2 = self.address_line_2.strip()
        self.locality = self.locality.strip()
        self.landmark = self.landmark.strip()
        self.city = self.city.strip()
        self.state = self.state.strip()
        self.country = self.country.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.get_address_type_display()}"
        )


class RetailFulfillmentGroup(models.Model):
    class GroupType(models.TextChoices):
        MAIN_DELIVERY = "main_delivery", "Main delivery"
        MAIN_PICKUP = "main_pickup", "Main store pickup"
        POWERED_PRODUCTION = (
            "powered_production",
            "Powered-lens production",
        )
        CUSTOMER_FRAME_INBOUND = (
            "customer_frame_inbound",
            "Customer frame inbound",
        )
        CUSTOMER_FRAME_RETURN = (
            "customer_frame_return",
            "Customer frame return",
        )

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.CASCADE,
        related_name="fulfillment_groups",
    )
    group_type = models.CharField(
        max_length=40,
        choices=GroupType.choices,
    )
    title = models.CharField(max_length=150)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    store_location = models.ForeignKey(
        StoreLocation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fulfillment_groups",
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
    ready_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    shipped_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]

    def clean(self):
        super().clean()

        self.title = self.title.strip()
        self.carrier_name = self.carrier_name.strip()
        self.tracking_number = self.tracking_number.strip()

        if (
            self.group_type == self.GroupType.MAIN_PICKUP
            and self.store_location_id is None
        ):
            raise ValidationError(
                {
                    "store_location": (
                        "A main pickup group requires a store."
                    )
                }
            )

        if (
            self.group_type == self.GroupType.MAIN_DELIVERY
            and self.store_location_id is not None
        ):
            raise ValidationError(
                {
                    "store_location": (
                        "A delivery group must not use "
                        "a pickup store."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_number} — {self.title}"


class RetailOrderItem(models.Model):
    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    fulfillment_group = models.ForeignKey(
        RetailFulfillmentGroup,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="items",
    )

    source_cart_item_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        editable=False,
    )

    item_type = models.CharField(
        max_length=30,
        choices=RetailCartItem.ItemType.choices,
    )

    offer = models.ForeignKey(
        ProductOffer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_order_items",
    )
    product_variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_order_items",
    )
    prescription = models.ForeignKey(
        Prescription,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_order_items",
    )
    lens = models.ForeignKey(
        LensSpecification,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retail_order_items",
    )

    sku = models.CharField(
        max_length=30,
        blank=True,
    )
    product_name = models.CharField(max_length=255)
    variant_description = models.CharField(
        max_length=255,
        blank=True,
    )

    quantity = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10),
        ],
    )

    unit_price_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    line_total_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        editable=False,
    )
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )

    is_custom = models.BooleanField(
        default=False,
        editable=False,
    )
    is_non_refundable = models.BooleanField(
        default=False,
        editable=False,
    )
    non_cancellable_after_production = models.BooleanField(
        default=False,
        editable=False,
    )

    product_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )
    configuration_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(quantity__gte=1)
                    & models.Q(quantity__lte=10)
                ),
                name="retail_order_item_quantity_1_to_10",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        item_type=(
                            RetailCartItem.ItemType.STANDARD
                        ),
                    )
                    | models.Q(quantity=1)
                ),
                name="retail_order_custom_quantity_one",
            ),
            models.UniqueConstraint(
                fields=["order", "source_cart_item_id"],
                condition=models.Q(
                    source_cart_item_id__isnull=False
                ),
                name="uniq_order_source_cart_item",
            ),
        ]

    def clean(self):
        super().clean()

        self.sku = self.sku.strip()
        self.product_name = self.product_name.strip()
        self.variant_description = (
            self.variant_description.strip()
        )

        errors = {}

        if (
            self.fulfillment_group_id
            and self.fulfillment_group.order_id
            != self.order_id
        ):
            errors["fulfillment_group"] = (
                "The fulfillment group must belong "
                "to this order."
            )

        if self.item_type == RetailCartItem.ItemType.STANDARD:
            if self.offer_id is None:
                errors["offer"] = (
                    "A standard order item requires an offer."
                )

            if self.product_variant_id is None:
                errors["product_variant"] = (
                    "A standard order item requires "
                    "a product variant."
                )

            if self.prescription_id or self.lens_id:
                errors["item_type"] = (
                    "A standard item must not contain "
                    "prescription-lens configuration."
                )

        elif (
            self.item_type
            == RetailCartItem.ItemType.POWERED_EYEWEAR
        ):
            if self.offer_id is None:
                errors["offer"] = (
                    "Powered eyewear requires a frame offer."
                )

            if self.product_variant_id is None:
                errors["product_variant"] = (
                    "Powered eyewear requires a frame variant."
                )

            if self.prescription_id is None:
                errors["prescription"] = (
                    "Powered eyewear requires a prescription."
                )

            if self.lens_id is None:
                errors["lens"] = (
                    "Powered eyewear requires a lens."
                )

            if self.quantity != 1:
                errors["quantity"] = (
                    "Powered eyewear must have quantity one."
                )

        elif (
            self.item_type
            == RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
        ):
            if self.offer_id or self.product_variant_id:
                errors["item_type"] = (
                    "A customer-owned frame service must not "
                    "reference store frame stock."
                )

            if self.prescription_id is None:
                errors["prescription"] = (
                    "The service requires a prescription."
                )

            if self.lens_id is None:
                errors["lens"] = (
                    "The service requires a configured lens."
                )

            if self.quantity != 1:
                errors["quantity"] = (
                    "The service must have quantity one."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        is_custom = self.item_type in {
            RetailCartItem.ItemType.POWERED_EYEWEAR,
            RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME,
        }

        self.is_custom = is_custom
        self.is_non_refundable = is_custom
        self.non_cancellable_after_production = is_custom

        self.line_total_including_gst = _money(
            self.unit_price_including_gst * self.quantity
        )

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.product_name}"
        )


class RetailStockReservation(models.Model):
    class Reason(models.TextChoices):
        ONLINE_PAYMENT = (
            "online_payment",
            "Online payment attempt",
        )
        PAY_AT_STORE = (
            "pay_at_store",
            "Pay-at-store order",
        )
        MANUAL = "manual", "Manual reservation"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"
        EXPIRED = "expired", "Expired"

    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.CASCADE,
        related_name="stock_reservations",
    )
    order_item = models.ForeignKey(
        RetailOrderItem,
        on_delete=models.CASCADE,
        related_name="stock_reservations",
    )
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="retail_stock_reservations",
    )

    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
    )
    reason = models.CharField(
        max_length=20,
        choices=Reason.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    released_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "order_item",
                    "product_variant",
                ],
                condition=models.Q(status="active"),
                name="uniq_active_retail_stock_reservation",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.order_item_id
            and self.order_item.order_id != self.order_id
        ):
            errors["order_item"] = (
                "The order item must belong to this order."
            )

        if (
            self.order_item_id
            and self.order_item.product_variant_id
            != self.product_variant_id
        ):
            errors["product_variant"] = (
                "The reserved variant must match "
                "the order item variant."
            )

        if (
            self.order_item_id
            and self.quantity > self.order_item.quantity
        ):
            errors["quantity"] = (
                "Reservation quantity cannot exceed "
                "the order-item quantity."
            )

        if (
            self.status == self.Status.ACTIVE
            and self.reason == self.Reason.ONLINE_PAYMENT
            and self.expires_at is None
        ):
            errors["expires_at"] = (
                "Online-payment reservations require "
                "an expiry time."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return (
            self.status == self.Status.ACTIVE
            and self.expires_at is not None
            and timezone.now() >= self.expires_at
        )

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.product_variant.physical_sku}"
        )


class RetailPaymentAttempt(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=RetailOrder.PaymentMethod.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        db_index=True,
    )

    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    amount_including_gst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(
        max_length=3,
        default="INR",
        editable=False,
    )

    allowed_payment_methods = models.JSONField(
        default=default_razorpay_payment_methods,
        blank=True,
    )

    provider_order_id = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
    )
    provider_payment_id = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
    )
    provider_signature = models.TextField(blank=True)
    signature_verified = models.BooleanField(default=False)

    request_payload = models.JSONField(
        default=dict,
        blank=True,
    )
    response_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    failed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.order_id
            and self.payment_method
            != self.order.payment_method
        ):
            errors["payment_method"] = (
                "The payment attempt method must match "
                "the order payment method."
            )

        if (
            self.order_id
            and _money(self.amount_including_gst)
            != _money(self.order.grand_total_including_gst)
        ):
            errors["amount_including_gst"] = (
                "The payment amount must equal "
                "the order grand total."
            )

        forbidden_methods = {
            "credit_card",
            "credit-card",
            "creditcard",
        }

        if forbidden_methods.intersection(
            set(self.allowed_payment_methods)
        ):
            errors["allowed_payment_methods"] = (
                "Credit-card payments are not enabled."
            )

        if (
            self.payment_method
            == RetailOrder.PaymentMethod.PAY_AT_STORE
            and self.allowed_payment_methods
        ):
            errors["allowed_payment_methods"] = (
                "Pay-at-store attempts must not contain "
                "online payment methods."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.get_status_display()}"
        )


class RetailOrderNotificationEvent(models.Model):
    class EventType(models.TextChoices):
        PAYMENT_CONFIRMED = (
            "payment_confirmed",
            "Payment confirmed",
        )
        PROCESSING = "processing", "Order processing"
        SHIPPED = "shipped", "Order shipped"
        READY_FOR_PICKUP = (
            "ready_for_pickup",
            "Ready for pickup",
        )
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        RetailOrder,
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
    )
    channel = models.CharField(
        max_length=10,
        choices=Channel.choices,
    )
    recipient = models.CharField(max_length=254)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "order",
                    "event_type",
                    "channel",
                ],
                name="uniq_retail_order_notification_event",
            ),
        ]

    def clean(self):
        super().clean()
        self.recipient = self.recipient.strip()
        self.last_error = self.last_error.strip()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.order.order_number} — "
            f"{self.get_event_type_display()} — "
            f"{self.get_channel_display()}"
        )
