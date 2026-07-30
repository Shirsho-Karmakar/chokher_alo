from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.wholesale.models import WholesaleAccount
from apps.wholesale_catalog.models import WholesaleLensVariant
from apps.wholesale_cart.models import (
    WholesaleCart,
    WholesaleCartItem,
)
from apps.wholesale_cart.services import (
    physical_units_per_wholesale_box,
    revalidate_wholesale_cart,
)

from .models import (
    WholesaleFulfillment,
    WholesaleOrder,
    WholesaleOrderAddressSnapshot,
    WholesaleOrderItem,
    WholesalePaymentAttempt,
    WholesaleStockReservation,
)


MONEY_PLACES = Decimal("0.01")


class WholesaleCheckoutError(Exception):
    def __init__(
        self,
        code,
        message,
        *,
        details=None,
    ):
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class WholesaleCheckoutResult:
    order: WholesaleOrder
    payment_attempt: WholesalePaymentAttempt
    fulfillment: WholesaleFulfillment
    created: bool


def _money(value):
    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def _active_order_statuses():
    return (
        WholesaleOrder.Status.PAYMENT_PENDING,
        WholesaleOrder.Status.CONFIRMED,
        WholesaleOrder.Status.PROCESSING,
        WholesaleOrder.Status.SHIPPED,
    )


def _locked_cart(cart):
    return (
        WholesaleCart.objects
        .select_for_update(of=("self",))
        .select_related(
            "wholesale_account",
            "wholesale_account__user",
        )
        .get(pk=cart.pk)
    )


def _existing_checkout(cart):
    return (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .filter(
            source_cart=cart,
            status__in=_active_order_statuses(),
        )
        .order_by("pk")
        .first()
    )


def _existing_checkout_result(order):
    payment_attempt = (
        order.payment_attempts
        .order_by("-created_at")
        .first()
    )

    if payment_attempt is None:
        raise WholesaleCheckoutError(
            "payment_attempt_missing",
            "The wholesale checkout has no payment attempt.",
        )

    return WholesaleCheckoutResult(
        order=order,
        payment_attempt=payment_attempt,
        fulfillment=order.fulfillment,
        created=False,
    )


def _default_billing_address(account):
    return (
        account.user.addresses
        .filter(
            is_active=True,
            is_default_billing=True,
        )
        .order_by("pk")
        .first()
    )


def _create_address_snapshot(
    *,
    order,
    account,
    address,
):
    return WholesaleOrderAddressSnapshot.objects.create(
        order=order,
        recipient_name=(
            getattr(address, "recipient_name", "")
            or account.contact_person_name
        ),
        business_name=account.business_name,
        phone_number=(
            getattr(address, "phone_number", "")
            or account.user.phone_number
            or ""
        ),
        invoice_email=account.invoice_email,
        gstin=account.gstin,
        address_line_1=getattr(
            address,
            "address_line_1",
            "",
        ),
        address_line_2=getattr(
            address,
            "address_line_2",
            "",
        ),
        landmark=getattr(
            address,
            "landmark",
            "",
        ),
        city=getattr(address, "city", ""),
        district=getattr(
            address,
            "district",
            "",
        ),
        state=str(getattr(address, "state", "")),
        postal_code=getattr(
            address,
            "postal_code",
            "",
        ),
    )


def _reserved_wholesale_boxes(*, now):
    return {
        row["wholesale_variant_id"]: row["total"]
        for row in (
            WholesaleStockReservation.objects
            .filter(
                status=WholesaleStockReservation.Status.ACTIVE,
                expires_at__gt=now,
            )
            .values("wholesale_variant_id")
            .annotate(total=Sum("boxes_reserved"))
        )
    }


def _reserved_physical_units(*, now):
    return {
        row["physical_variant_id"]: row["total"]
        for row in (
            WholesaleStockReservation.objects
            .filter(
                status=WholesaleStockReservation.Status.ACTIVE,
                expires_at__gt=now,
            )
            .values("physical_variant_id")
            .annotate(
                total=Sum("physical_units_reserved")
            )
        )
    }


@transaction.atomic
def start_wholesale_checkout(
    *,
    cart,
    payment_method,
    reservation_minutes=30,
    customer_notes="",
):
    if (
        not isinstance(reservation_minutes, int)
        or isinstance(reservation_minutes, bool)
        or reservation_minutes < 1
    ):
        raise WholesaleCheckoutError(
            "invalid_reservation_duration",
            (
                "Reservation duration must be a positive "
                "whole number of minutes."
            ),
        )

    if payment_method not in (
        WholesalePaymentAttempt.Method.values
    ):
        raise WholesaleCheckoutError(
            "invalid_payment_method",
            "The selected wholesale payment method is invalid.",
        )

    cart = _locked_cart(cart)

    existing_order = _existing_checkout(cart)

    if existing_order is not None:
        return _existing_checkout_result(existing_order)

    if cart.status != WholesaleCart.Status.OPEN:
        raise WholesaleCheckoutError(
            "cart_not_open",
            "The wholesale cart is not open for checkout.",
        )

    account = cart.wholesale_account

    if (
        not account.user.is_active
        or not account.user.phone_verified
        or account.status
        != WholesaleAccount.Status.APPROVED
    ):
        raise WholesaleCheckoutError(
            "wholesale_access_required",
            "An approved wholesale account is required.",
        )

    readiness = revalidate_wholesale_cart(
        cart=cart
    )

    if not readiness.ready:
        raise WholesaleCheckoutError(
            "cart_not_checkout_ready",
            (
                "The wholesale cart is not ready for "
                "checkout."
            ),
            details=readiness.as_dict(),
        )

    billing_address = _default_billing_address(
        account
    )

    if billing_address is None:
        raise WholesaleCheckoutError(
            "billing_address_required",
            "A default billing address is required.",
        )

    items = list(
        WholesaleCartItem.objects
        .select_for_update(of=("self",))
        .select_related(
            "variant",
            "variant__listing",
            "variant__listing__lens",
            "variant__listing__lens__offer",
            "variant__listing__lens__offer__variant",
            "prescription",
        )
        .filter(cart=cart)
        .order_by("pk")
    )

    if not items:
        raise WholesaleCheckoutError(
            "empty_cart",
            "The wholesale cart is empty.",
        )

    grouped_items = defaultdict(list)

    for item in items:
        if (
            item.validation_status
            != WholesaleCartItem.ValidationStatus.VALID
        ):
            raise WholesaleCheckoutError(
                "invalid_cart_item",
                (
                    "One or more wholesale cart items "
                    "are invalid."
                ),
                details={"item_id": item.pk},
            )

        grouped_items[item.variant_id].append(item)

    wholesale_variants = {
        variant.pk: variant
        for variant in (
            WholesaleLensVariant.objects
            .select_for_update(of=("self",))
            .select_related(
                "listing",
                "listing__lens",
                "listing__lens__offer",
                "listing__lens__offer__variant",
                "listing__lens__offer__variant__design",
            )
            .filter(pk__in=grouped_items)
        )
    }

    physical_variant_ids = {
        variant.listing.lens.offer.variant_id
        for variant in wholesale_variants.values()
    }

    physical_variants = {
        variant.pk: variant
        for variant in (
            ProductVariant.objects
            .select_for_update(of=("self",))
            .select_related("design")
            .filter(pk__in=physical_variant_ids)
        )
    }

    now = timezone.now()
    expires_at = now + timedelta(
        minutes=reservation_minutes
    )

    reserved_boxes = _reserved_wholesale_boxes(
        now=now
    )
    reserved_units = _reserved_physical_units(
        now=now
    )

    reservation_plan = []

    for variant_id, variant_items in grouped_items.items():
        variant = wholesale_variants[variant_id]
        physical_variant = physical_variants[
            variant.listing.lens.offer.variant_id
        ]

        requested_boxes = sum(
            item.boxes
            for item in variant_items
        )
        requested_units = (
            requested_boxes
            * physical_units_per_wholesale_box(variant)
        )

        already_reserved_boxes = (
            reserved_boxes.get(variant.pk, 0)
        )
        available_boxes = (
            variant.boxes_in_stock
            - already_reserved_boxes
        )

        if available_boxes < requested_boxes:
            raise WholesaleCheckoutError(
                "insufficient_available_wholesale_stock",
                (
                    "The remaining wholesale box stock "
                    "cannot satisfy this checkout."
                ),
                details={
                    "variant_id": variant.pk,
                    "available_boxes": max(
                        available_boxes,
                        0,
                    ),
                    "requested_boxes": requested_boxes,
                },
            )

        if (
            physical_variant.stock_mode
            == ProductVariant.StockMode.QUANTITY
        ):
            already_reserved_units = (
                reserved_units.get(
                    physical_variant.pk,
                    0,
                )
            )
            available_units = (
                physical_variant.stock_quantity
                - already_reserved_units
            )

            if available_units < requested_units:
                raise WholesaleCheckoutError(
                    "insufficient_available_shared_stock",
                    (
                        "The remaining shared physical "
                        "stock cannot satisfy this checkout."
                    ),
                    details={
                        "physical_variant_id": (
                            physical_variant.pk
                        ),
                        "available_physical_units": max(
                            available_units,
                            0,
                        ),
                        "required_physical_units": (
                            requested_units
                        ),
                    },
                )

        reservation_plan.append(
            (
                variant,
                physical_variant,
                variant_items,
            )
        )

    subtotal = _money(
        sum(
            (
                item.subtotal_including_gst
                for item in items
            ),
            start=Decimal("0.00"),
        )
    )
    delivery_fee = _money("0.00")
    grand_total = _money(
        subtotal + delivery_fee
    )
    total_boxes = sum(
        item.boxes
        for item in items
    )

    order = WholesaleOrder.objects.create(
        wholesale_account=account,
        source_cart=cart,
        status=WholesaleOrder.Status.PAYMENT_PENDING,
        payment_status=(
            WholesaleOrder.PaymentStatus.PENDING
        ),
        fulfillment_status=(
            WholesaleOrder.FulfillmentStatus.PENDING
        ),
        business_snapshot={
            "reference_id": account.reference_id,
            "business_name": account.business_name,
            "contact_person_name": (
                account.contact_person_name
            ),
            "gstin": account.gstin or None,
            "invoice_email": account.invoice_email,
            "user_id": account.user_id,
            "phone_number": (
                account.user.phone_number or None
            ),
        },
        subtotal_including_gst=subtotal,
        delivery_fee_including_gst=delivery_fee,
        grand_total_including_gst=grand_total,
        total_boxes=total_boxes,
        customer_notes=customer_notes.strip(),
        placed_at=now,
    )

    _create_address_snapshot(
        order=order,
        account=account,
        address=billing_address,
    )

    locked_variant_map = {
        variant.pk: (
            variant,
            physical_variant,
        )
        for (
            variant,
            physical_variant,
            _variant_items,
        ) in reservation_plan
    }

    for cart_item in items:
        variant, physical_variant = (
            locked_variant_map[
                cart_item.variant_id
            ]
        )

        physical_units = (
            cart_item.boxes
            * physical_units_per_wholesale_box(
                variant
            )
        )

        order_item = WholesaleOrderItem.objects.create(
            order=order,
            variant=variant,
            physical_variant=physical_variant,
            prescription=cart_item.prescription,
            eye=cart_item.eye,
            boxes=cart_item.boxes,
            physical_units_reserved=physical_units,
            base_box_price_including_gst=(
                cart_item
                .base_box_price_including_gst
            ),
            applied_box_price_including_gst=(
                cart_item
                .applied_box_price_including_gst
            ),
            discount_per_box_including_gst=(
                cart_item
                .discount_per_box_including_gst
            ),
            subtotal_including_gst=(
                cart_item.subtotal_including_gst
            ),
            bulk_price_tier_id_snapshot=(
                cart_item
                .bulk_price_tier_id_snapshot
            ),
            variant_snapshot=(
                cart_item.variant_snapshot
            ),
            prescription_snapshot=(
                cart_item.prescription_snapshot
            ),
            pricing_snapshot=(
                cart_item.pricing_snapshot
            ),
        )

        WholesaleStockReservation.objects.create(
            order=order,
            order_item=order_item,
            wholesale_variant=variant,
            physical_variant=physical_variant,
            boxes_reserved=cart_item.boxes,
            physical_units_reserved=physical_units,
            expires_at=expires_at,
        )

    payment_attempt = (
        WholesalePaymentAttempt.objects.create(
            order=order,
            method=payment_method,
            status=(
                WholesalePaymentAttempt.Status.PENDING
            ),
            amount_including_gst=grand_total,
            expires_at=expires_at,
        )
    )

    fulfillment = WholesaleFulfillment.objects.create(
        order=order,
    )

    cart.status = WholesaleCart.Status.CHECKOUT_STARTED
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return WholesaleCheckoutResult(
        order=order,
        payment_attempt=payment_attempt,
        fulfillment=fulfillment,
        created=True,
    )


@transaction.atomic
def cancel_wholesale_checkout(
    *,
    order,
    reason="",
):
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .select_related("source_cart")
        .get(pk=order.pk)
    )

    if order.status == WholesaleOrder.Status.CANCELLED:
        return order

    if order.status != (
        WholesaleOrder.Status.PAYMENT_PENDING
    ):
        raise WholesaleCheckoutError(
            "checkout_cannot_be_cancelled",
            (
                "Only a payment-pending wholesale "
                "checkout may be cancelled."
            ),
        )

    now = timezone.now()

    WholesaleStockReservation.objects.filter(
        order=order,
        status=WholesaleStockReservation.Status.ACTIVE,
    ).update(
        status=WholesaleStockReservation.Status.RELEASED,
        released_at=now,
        updated_at=now,
    )

    WholesalePaymentAttempt.objects.filter(
        order=order,
        status=WholesalePaymentAttempt.Status.PENDING,
    ).update(
        status=WholesalePaymentAttempt.Status.CANCELLED,
        updated_at=now,
    )

    WholesaleFulfillment.objects.filter(
        order=order,
    ).update(
        status=WholesaleFulfillment.Status.CANCELLED,
        updated_at=now,
    )

    order.status = WholesaleOrder.Status.CANCELLED
    order.payment_status = (
        WholesaleOrder.PaymentStatus.CANCELLED
    )
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.CANCELLED
    )
    order.internal_notes = reason.strip()
    order.cancelled_at = now
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "fulfillment_status",
            "internal_notes",
            "cancelled_at",
            "updated_at",
        ]
    )

    cart = order.source_cart

    if cart.status == (
        WholesaleCart.Status.CHECKOUT_STARTED
    ):
        cart.status = WholesaleCart.Status.OPEN
        cart.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    return order
