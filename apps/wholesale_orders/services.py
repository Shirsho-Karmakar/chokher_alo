from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.retail_orders.razorpay_gateway import (
    RazorpayGateway,
    RazorpayGatewayError,
    RazorpayPaymentSession,
    amount_to_subunits,
)
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
    WholesaleOrderNotificationEvent,
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

    supported_payment_methods = {
        WholesalePaymentAttempt.Method.RAZORPAY,
        WholesalePaymentAttempt.Method.BANK_TRANSFER,
    }

    if payment_method not in supported_payment_methods:
        raise WholesaleCheckoutError(
            "invalid_payment_method",
            (
                "Wholesale checkout supports Razorpay "
                "and bank transfer."
            ),
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


def _audit_payload(existing, event, **details):
    payload = (
        dict(existing)
        if isinstance(existing, dict)
        else {}
    )
    history = list(payload.get("history") or [])
    history.append(
        {
            "event": event,
            **details,
        }
    )
    payload["history"] = history
    return payload


def _queue_wholesale_event(
    *,
    order,
    event_type,
    payload=None,
):
    from .notifications import (
        queue_wholesale_order_notification,
    )

    return queue_wholesale_order_notification(
        order=order,
        event_type=event_type,
        payload=payload,
    )


def _issue_wholesale_invoice(*, order):
    from .invoices import issue_wholesale_invoice

    return issue_wholesale_invoice(order=order)


def _locked_payment_context(payment_attempt):
    attempt = (
        WholesalePaymentAttempt.objects
        .select_for_update(of=("self",))
        .get(pk=payment_attempt.pk)
    )
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .get(pk=attempt.order_id)
    )
    cart = (
        WholesaleCart.objects
        .select_for_update(of=("self",))
        .get(pk=order.source_cart_id)
    )

    return attempt, order, cart


def _lock_order_reservations(*, order, statuses):
    return list(
        WholesaleStockReservation.objects
        .select_for_update(of=("self",))
        .filter(
            order=order,
            status__in=statuses,
        )
        .order_by("pk")
    )


def _lock_reservation_inventory(reservations):
    wholesale_ids = {
        reservation.wholesale_variant_id
        for reservation in reservations
    }
    physical_ids = {
        reservation.physical_variant_id
        for reservation in reservations
    }

    wholesale_variants = {
        variant.pk: variant
        for variant in (
            WholesaleLensVariant.objects
            .select_for_update(of=("self",))
            .filter(pk__in=wholesale_ids)
        )
    }
    physical_variants = {
        variant.pk: variant
        for variant in (
            ProductVariant.objects
            .select_for_update(of=("self",))
            .filter(pk__in=physical_ids)
        )
    }

    return wholesale_variants, physical_variants


def _consume_active_reservations(*, order, now):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            WholesaleStockReservation.Status.ACTIVE,
        ],
    )

    if not reservations:
        consumed = _lock_order_reservations(
            order=order,
            statuses=[
                WholesaleStockReservation.Status.CONSUMED,
            ],
        )

        if consumed:
            return tuple(consumed)

        raise WholesaleCheckoutError(
            "active_reservation_missing",
            "No active stock reservation exists.",
        )

    if any(now >= item.expires_at for item in reservations):
        raise WholesaleCheckoutError(
            "payment_reservation_expired",
            "The wholesale stock reservation has expired.",
        )

    wholesale_variants, physical_variants = (
        _lock_reservation_inventory(reservations)
    )

    boxes_by_variant = defaultdict(int)
    units_by_variant = defaultdict(int)

    for reservation in reservations:
        boxes_by_variant[
            reservation.wholesale_variant_id
        ] += reservation.boxes_reserved
        units_by_variant[
            reservation.physical_variant_id
        ] += reservation.physical_units_reserved

    wholesale_before = {}
    physical_before = {}

    for variant_id, boxes in boxes_by_variant.items():
        variant = wholesale_variants[variant_id]
        wholesale_before[variant_id] = (
            variant.boxes_in_stock
        )

        if variant.boxes_in_stock < boxes:
            raise WholesaleCheckoutError(
                "wholesale_stock_changed",
                (
                    "Wholesale stock is no longer sufficient "
                    "to confirm this order."
                ),
                details={
                    "variant_id": variant_id,
                    "available_boxes": variant.boxes_in_stock,
                    "required_boxes": boxes,
                },
            )

    for variant_id, units in units_by_variant.items():
        variant = physical_variants[variant_id]
        physical_before[variant_id] = (
            variant.stock_quantity
        )

        if (
            variant.stock_mode
            == ProductVariant.StockMode.QUANTITY
            and variant.stock_quantity < units
        ):
            raise WholesaleCheckoutError(
                "shared_stock_changed",
                (
                    "Shared physical stock is no longer "
                    "sufficient to confirm this order."
                ),
                details={
                    "physical_variant_id": variant_id,
                    "available_units": variant.stock_quantity,
                    "required_units": units,
                },
            )

        if (
            variant.stock_mode
            == ProductVariant.StockMode.STATUS_ONLY
            and variant.effective_stock_status
            != ProductVariant.StockStatus.AVAILABLE
        ):
            raise WholesaleCheckoutError(
                "shared_stock_unavailable",
                "The shared physical stock is unavailable.",
            )

    for variant_id, boxes in boxes_by_variant.items():
        variant = wholesale_variants[variant_id]
        variant.boxes_in_stock -= boxes
        variant.save(
            update_fields=[
                "boxes_in_stock",
                "updated_at",
            ]
        )

    for variant_id, units in units_by_variant.items():
        variant = physical_variants[variant_id]

        if (
            variant.stock_mode
            == ProductVariant.StockMode.QUANTITY
        ):
            variant.stock_quantity -= units
            variant.save(
                update_fields=[
                    "stock_quantity",
                    "updated_at",
                ]
            )

    for reservation in reservations:
        wholesale_variant = wholesale_variants[
            reservation.wholesale_variant_id
        ]
        physical_variant = physical_variants[
            reservation.physical_variant_id
        ]

        reservation.status = (
            WholesaleStockReservation.Status.CONSUMED
        )
        reservation.consumed_at = now
        reservation.metadata = _audit_payload(
            reservation.metadata,
            "consumed",
            at=now.isoformat(),
            boxes=reservation.boxes_reserved,
            physical_units=(
                reservation.physical_units_reserved
            ),
            wholesale_stock_before=(
                wholesale_before[
                    reservation.wholesale_variant_id
                ]
            ),
            wholesale_stock_after=(
                wholesale_variant.boxes_in_stock
            ),
            physical_stock_before=(
                physical_before[
                    reservation.physical_variant_id
                ]
            ),
            physical_stock_after=(
                physical_variant.stock_quantity
            ),
        )
        reservation.save(
            update_fields=[
                "status",
                "consumed_at",
                "metadata",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _release_active_reservations(
    *,
    order,
    now,
    expired=False,
    reason="",
):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            WholesaleStockReservation.Status.ACTIVE,
        ],
    )

    final_status = (
        WholesaleStockReservation.Status.EXPIRED
        if expired
        else WholesaleStockReservation.Status.RELEASED
    )

    for reservation in reservations:
        reservation.status = final_status
        reservation.released_at = now
        reservation.metadata = _audit_payload(
            reservation.metadata,
            "expired" if expired else "released",
            at=now.isoformat(),
            reason=reason,
        )
        reservation.save(
            update_fields=[
                "status",
                "released_at",
                "metadata",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _restore_consumed_stock(*, order, now):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            WholesaleStockReservation.Status.CONSUMED,
        ],
    )

    if not reservations:
        return ()

    wholesale_variants, physical_variants = (
        _lock_reservation_inventory(reservations)
    )

    boxes_by_variant = defaultdict(int)
    units_by_variant = defaultdict(int)

    for reservation in reservations:
        boxes_by_variant[
            reservation.wholesale_variant_id
        ] += reservation.boxes_reserved
        units_by_variant[
            reservation.physical_variant_id
        ] += reservation.physical_units_reserved

    for variant_id, boxes in boxes_by_variant.items():
        variant = wholesale_variants[variant_id]
        variant.boxes_in_stock += boxes
        variant.save(
            update_fields=[
                "boxes_in_stock",
                "updated_at",
            ]
        )

    for variant_id, units in units_by_variant.items():
        variant = physical_variants[variant_id]

        if (
            variant.stock_mode
            == ProductVariant.StockMode.QUANTITY
        ):
            variant.stock_quantity += units
            variant.save(
                update_fields=[
                    "stock_quantity",
                    "updated_at",
                ]
            )

    for reservation in reservations:
        reservation.status = (
            WholesaleStockReservation.Status.RELEASED
        )
        reservation.released_at = now
        reservation.metadata = _audit_payload(
            reservation.metadata,
            "stock_restored",
            at=now.isoformat(),
            boxes=reservation.boxes_reserved,
            physical_units=(
                reservation.physical_units_reserved
            ),
        )
        reservation.save(
            update_fields=[
                "status",
                "released_at",
                "metadata",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _reopen_checkout_cart(*, cart):
    if cart.status == WholesaleCart.Status.OPEN:
        return cart

    if cart.status != (
        WholesaleCart.Status.CHECKOUT_STARTED
    ):
        raise WholesaleCheckoutError(
            "cart_cannot_be_reopened",
            "The wholesale cart cannot be reopened.",
        )

    cart.status = WholesaleCart.Status.OPEN
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )
    return cart


def _convert_checkout_cart(*, cart):
    if cart.status == WholesaleCart.Status.CONVERTED:
        return cart

    if cart.status != (
        WholesaleCart.Status.CHECKOUT_STARTED
    ):
        raise WholesaleCheckoutError(
            "cart_conversion_invalid",
            "The wholesale cart is not awaiting payment.",
        )

    cart.status = WholesaleCart.Status.CONVERTED
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )
    return cart


def _cancel_pending_payment_attempts(
    *,
    order,
    now,
    exclude_attempt_id=None,
    reason="",
):
    attempts = list(
        WholesalePaymentAttempt.objects
        .select_for_update(of=("self",))
        .filter(
            order=order,
            status=WholesalePaymentAttempt.Status.PENDING,
        )
        .exclude(
            pk=exclude_attempt_id
            if exclude_attempt_id is not None
            else 0
        )
    )

    for attempt in attempts:
        attempt.status = (
            WholesalePaymentAttempt.Status.CANCELLED
        )
        attempt.failed_at = now
        attempt.provider_payload = _audit_payload(
            attempt.provider_payload,
            "cancelled",
            at=now.isoformat(),
            reason=reason,
        )
        attempt.save(
            update_fields=[
                "status",
                "failed_at",
                "provider_payload",
                "updated_at",
            ]
        )

    return tuple(attempts)


def _cancel_fulfillment(*, order, now, reason):
    fulfillment = (
        WholesaleFulfillment.objects
        .select_for_update(of=("self",))
        .get(order=order)
    )
    fulfillment.status = (
        WholesaleFulfillment.Status.CANCELLED
    )
    fulfillment.metadata = _audit_payload(
        fulfillment.metadata,
        "cancelled",
        at=now.isoformat(),
        reason=reason,
    )
    fulfillment.save(
        update_fields=[
            "status",
            "metadata",
            "updated_at",
        ]
    )
    return fulfillment


def _confirm_attempt(
    *,
    attempt,
    order,
    cart,
    provider_payment_id,
    provider_signature="",
    signature_verified=False,
    response_payload=None,
):
    now = timezone.now()

    _consume_active_reservations(
        order=order,
        now=now,
    )

    attempt.status = WholesalePaymentAttempt.Status.PAID
    attempt.provider_payment_id = (
        provider_payment_id.strip()
    )
    attempt.provider_signature = (
        provider_signature.strip()
    )
    attempt.signature_verified = signature_verified
    attempt.provider_payload = _audit_payload(
        attempt.provider_payload,
        "payment_confirmed",
        at=now.isoformat(),
        method=attempt.method,
        response=response_payload or {},
    )
    attempt.paid_at = now
    attempt.failed_at = None
    attempt.save(
        update_fields=[
            "status",
            "provider_payment_id",
            "provider_signature",
            "signature_verified",
            "provider_payload",
            "paid_at",
            "failed_at",
            "updated_at",
        ]
    )

    order.status = WholesaleOrder.Status.CONFIRMED
    order.payment_status = (
        WholesaleOrder.PaymentStatus.PAID
    )
    order.confirmed_at = now
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "confirmed_at",
            "updated_at",
        ]
    )

    _cancel_pending_payment_attempts(
        order=order,
        now=now,
        exclude_attempt_id=attempt.pk,
        reason="Another payment attempt was confirmed.",
    )
    _convert_checkout_cart(cart=cart)

    invoice, _created = _issue_wholesale_invoice(
        order=order
    )
    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.PAYMENT_CONFIRMED
        ),
        payload={
            "invoice_number": invoice.invoice_number,
        },
    )
    return order


@transaction.atomic
def prepare_wholesale_razorpay_payment(
    *,
    payment_attempt,
    gateway=None,
):
    attempt, order, _cart = _locked_payment_context(
        payment_attempt
    )
    now = timezone.now()

    if (
        attempt.method
        != WholesalePaymentAttempt.Method.RAZORPAY
    ):
        raise WholesaleCheckoutError(
            "invalid_payment_method",
            "This is not a Razorpay payment attempt.",
        )

    if attempt.status != WholesalePaymentAttempt.Status.PENDING:
        raise WholesaleCheckoutError(
            "payment_attempt_not_preparable",
            "This payment attempt cannot be prepared.",
        )

    if (
        attempt.expires_at is not None
        and now >= attempt.expires_at
    ):
        raise WholesaleCheckoutError(
            "payment_attempt_expired",
            "The payment attempt has expired.",
        )

    allowed_methods = ("upi", "netbanking")
    gateway = gateway or RazorpayGateway()

    if attempt.provider_order_id:
        return RazorpayPaymentSession(
            key_id=gateway.key_id,
            provider_order_id=attempt.provider_order_id,
            amount_subunits=amount_to_subunits(
                attempt.amount_including_gst
            ),
            currency=attempt.currency,
            receipt=order.order_number,
            allowed_payment_methods=allowed_methods,
            expires_at=attempt.expires_at,
        )

    payload = gateway.create_order(
        amount_including_gst=(
            attempt.amount_including_gst
        ),
        currency=attempt.currency,
        receipt=order.order_number,
        notes={
            "order_type": "wholesale",
            "wholesale_order_id": order.pk,
            "wholesale_order_number": (
                order.order_number
            ),
            "wholesale_account_id": (
                order.wholesale_account_id
            ),
        },
    )

    provider_order_id = str(
        payload.get("id") or ""
    ).strip()

    if not provider_order_id:
        raise RazorpayGatewayError(
            "razorpay_order_id_missing",
            "Razorpay did not return an order ID.",
            payload=payload,
        )

    if (
        payload.get("amount")
        != amount_to_subunits(
            attempt.amount_including_gst
        )
    ):
        raise RazorpayGatewayError(
            "razorpay_order_amount_mismatch",
            "The Razorpay order amount did not match checkout.",
            payload=payload,
        )

    if payload.get("currency") != attempt.currency:
        raise RazorpayGatewayError(
            "razorpay_order_currency_mismatch",
            (
                "The Razorpay order currency did not "
                "match checkout."
            ),
            payload=payload,
        )

    attempt.provider_order_id = provider_order_id
    attempt.provider_payload = _audit_payload(
        attempt.provider_payload,
        "razorpay_order_created",
        at=now.isoformat(),
        response=payload,
    )
    attempt.save(
        update_fields=[
            "provider_order_id",
            "provider_payload",
            "updated_at",
        ]
    )

    return RazorpayPaymentSession(
        key_id=gateway.key_id,
        provider_order_id=provider_order_id,
        amount_subunits=amount_to_subunits(
            attempt.amount_including_gst
        ),
        currency=attempt.currency,
        receipt=order.order_number,
        allowed_payment_methods=allowed_methods,
        expires_at=attempt.expires_at,
    )


@transaction.atomic
def confirm_wholesale_online_payment(
    *,
    payment_attempt,
    provider_payment_id,
    provider_signature,
    signature_verified,
    response_payload=None,
):
    attempt, order, cart = _locked_payment_context(
        payment_attempt
    )
    now = timezone.now()
    provider_payment_id = provider_payment_id.strip()

    if (
        attempt.method
        != WholesalePaymentAttempt.Method.RAZORPAY
    ):
        raise WholesaleCheckoutError(
            "invalid_payment_method",
            "This is not a Razorpay payment attempt.",
        )

    if attempt.status == WholesalePaymentAttempt.Status.PAID:
        if (
            attempt.provider_payment_id
            == provider_payment_id
        ):
            return order

        raise WholesaleCheckoutError(
            "payment_already_confirmed",
            (
                "This payment attempt was already "
                "confirmed with another payment ID."
            ),
        )

    if attempt.status != WholesalePaymentAttempt.Status.PENDING:
        raise WholesaleCheckoutError(
            "payment_attempt_not_payable",
            "This payment attempt cannot be confirmed.",
        )

    if (
        attempt.expires_at is not None
        and now >= attempt.expires_at
    ):
        raise WholesaleCheckoutError(
            "payment_attempt_expired",
            "The payment attempt has expired.",
        )

    if not signature_verified:
        raise WholesaleCheckoutError(
            "payment_signature_invalid",
            "The payment signature could not be verified.",
        )

    if not provider_payment_id:
        raise WholesaleCheckoutError(
            "provider_payment_id_missing",
            "The provider payment ID is required.",
        )

    return _confirm_attempt(
        attempt=attempt,
        order=order,
        cart=cart,
        provider_payment_id=provider_payment_id,
        provider_signature=provider_signature,
        signature_verified=True,
        response_payload=response_payload,
    )


def _ensure_payment_operator(actor):
    if (
        actor is None
        or not getattr(actor, "is_authenticated", False)
        or not actor.is_active
        or not actor.is_staff
    ):
        raise WholesaleCheckoutError(
            "staff_payment_access_required",
            "An active staff account is required.",
        )

    if (
        not actor.is_superuser
        and not actor.has_perm(
            "wholesale_orders."
            "change_wholesalepaymentattempt"
        )
    ):
        raise WholesaleCheckoutError(
            "staff_payment_permission_required",
            (
                "Wholesale payment-management "
                "permission is required."
            ),
        )


@transaction.atomic
def confirm_wholesale_bank_transfer(
    *,
    payment_attempt,
    actor,
    transfer_reference,
    response_payload=None,
):
    _ensure_payment_operator(actor)

    reference = transfer_reference.strip()

    if not reference:
        raise WholesaleCheckoutError(
            "transfer_reference_required",
            "A bank-transfer reference is required.",
        )

    attempt, order, cart = _locked_payment_context(
        payment_attempt
    )
    now = timezone.now()

    if (
        attempt.method
        != WholesalePaymentAttempt.Method.BANK_TRANSFER
    ):
        raise WholesaleCheckoutError(
            "invalid_payment_method",
            "This is not a bank-transfer payment.",
        )

    if attempt.status == WholesalePaymentAttempt.Status.PAID:
        if attempt.provider_payment_id == reference:
            return order

        raise WholesaleCheckoutError(
            "payment_already_confirmed",
            (
                "This bank transfer was already confirmed "
                "with another reference."
            ),
        )

    if attempt.status != WholesalePaymentAttempt.Status.PENDING:
        raise WholesaleCheckoutError(
            "payment_attempt_not_payable",
            "This payment attempt cannot be confirmed.",
        )

    if (
        attempt.expires_at is not None
        and now >= attempt.expires_at
    ):
        raise WholesaleCheckoutError(
            "payment_attempt_expired",
            "The bank-transfer reservation has expired.",
        )

    return _confirm_attempt(
        attempt=attempt,
        order=order,
        cart=cart,
        provider_payment_id=reference,
        response_payload={
            "bank_transfer": {
                "reference": reference,
                "confirmed_by_id": actor.pk,
                "confirmed_by": (
                    actor.get_username()
                ),
            },
            "provider_response": response_payload or {},
        },
    )


@transaction.atomic
def fail_wholesale_payment(
    *,
    payment_attempt,
    response_payload=None,
):
    attempt, order, cart = _locked_payment_context(
        payment_attempt
    )
    now = timezone.now()

    if attempt.status == WholesalePaymentAttempt.Status.FAILED:
        return order

    if attempt.status in {
        WholesalePaymentAttempt.Status.PAID,
        WholesalePaymentAttempt.Status.REFUNDED,
    }:
        raise WholesaleCheckoutError(
            "paid_payment_cannot_fail",
            "A paid wholesale payment cannot be failed.",
        )

    if attempt.status != WholesalePaymentAttempt.Status.PENDING:
        raise WholesaleCheckoutError(
            "payment_attempt_cannot_fail",
            "This payment attempt cannot be failed.",
        )

    _release_active_reservations(
        order=order,
        now=now,
        reason="Payment failed.",
    )

    attempt.status = WholesalePaymentAttempt.Status.FAILED
    attempt.failed_at = now
    attempt.provider_payload = _audit_payload(
        attempt.provider_payload,
        "payment_failed",
        at=now.isoformat(),
        response=response_payload or {},
    )
    attempt.save(
        update_fields=[
            "status",
            "failed_at",
            "provider_payload",
            "updated_at",
        ]
    )

    order.status = WholesaleOrder.Status.PAYMENT_FAILED
    order.payment_status = (
        WholesaleOrder.PaymentStatus.FAILED
    )
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.CANCELLED
    )
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "fulfillment_status",
            "updated_at",
        ]
    )

    _cancel_fulfillment(
        order=order,
        now=now,
        reason="Payment failed.",
    )
    _reopen_checkout_cart(cart=cart)

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.PAYMENT_FAILED
        ),
        payload={"reason": "Payment failed."},
    )
    return order


@transaction.atomic
def expire_wholesale_payment_attempt(
    *,
    payment_attempt,
):
    attempt, order, cart = _locked_payment_context(
        payment_attempt
    )
    now = timezone.now()

    if attempt.status == WholesalePaymentAttempt.Status.EXPIRED:
        return order

    if attempt.status in {
        WholesalePaymentAttempt.Status.PAID,
        WholesalePaymentAttempt.Status.REFUNDED,
    }:
        raise WholesaleCheckoutError(
            "paid_payment_cannot_expire",
            "A paid wholesale payment cannot expire.",
        )

    if attempt.status != WholesalePaymentAttempt.Status.PENDING:
        raise WholesaleCheckoutError(
            "payment_attempt_cannot_expire",
            "This payment attempt cannot be expired.",
        )

    if (
        attempt.expires_at is not None
        and now < attempt.expires_at
    ):
        raise WholesaleCheckoutError(
            "payment_not_expired",
            "This payment attempt has not expired.",
        )

    _release_active_reservations(
        order=order,
        now=now,
        expired=True,
        reason="Payment reservation expired.",
    )

    attempt.status = WholesalePaymentAttempt.Status.EXPIRED
    attempt.failed_at = now
    attempt.provider_payload = _audit_payload(
        attempt.provider_payload,
        "payment_expired",
        at=now.isoformat(),
    )
    attempt.save(
        update_fields=[
            "status",
            "failed_at",
            "provider_payload",
            "updated_at",
        ]
    )

    order.status = WholesaleOrder.Status.PAYMENT_FAILED
    order.payment_status = (
        WholesaleOrder.PaymentStatus.FAILED
    )
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.CANCELLED
    )
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "fulfillment_status",
            "updated_at",
        ]
    )

    _cancel_fulfillment(
        order=order,
        now=now,
        reason="Payment reservation expired.",
    )
    _reopen_checkout_cart(cart=cart)

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.PAYMENT_FAILED
        ),
        payload={
            "reason": "Payment reservation expired.",
        },
    )
    return order


def expire_due_wholesale_payment_attempts():
    attempt_ids = list(
        WholesalePaymentAttempt.objects
        .filter(
            status=WholesalePaymentAttempt.Status.PENDING,
            expires_at__lte=timezone.now(),
        )
        .values_list("pk", flat=True)
    )

    expired_count = 0

    for attempt_id in attempt_ids:
        attempt = WholesalePaymentAttempt.objects.get(
            pk=attempt_id
        )

        try:
            expire_wholesale_payment_attempt(
                payment_attempt=attempt
            )
        except WholesaleCheckoutError:
            continue

        expired_count += 1

    return expired_count


@transaction.atomic
def cancel_wholesale_checkout(
    *,
    order,
    reason="",
):
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .get(pk=order.pk)
    )
    cart = (
        WholesaleCart.objects
        .select_for_update(of=("self",))
        .get(pk=order.source_cart_id)
    )
    now = timezone.now()
    reason = reason.strip()

    if order.status == WholesaleOrder.Status.CANCELLED:
        return order

    if order.status == WholesaleOrder.Status.PAYMENT_PENDING:
        _release_active_reservations(
            order=order,
            now=now,
            reason=reason or "Checkout cancelled.",
        )
        _cancel_pending_payment_attempts(
            order=order,
            now=now,
            reason=reason or "Checkout cancelled.",
        )
        order.payment_status = (
            WholesaleOrder.PaymentStatus.CANCELLED
        )
        _reopen_checkout_cart(cart=cart)

    elif order.status == WholesaleOrder.Status.CONFIRMED:
        if (
            order.payment_status
            != WholesaleOrder.PaymentStatus.PAID
        ):
            raise WholesaleCheckoutError(
                "confirmed_payment_missing",
                "The confirmed order has no paid payment.",
            )

        _restore_consumed_stock(
            order=order,
            now=now,
        )
        order.payment_status = (
            WholesaleOrder.PaymentStatus.REFUND_PENDING
        )

    else:
        raise WholesaleCheckoutError(
            "checkout_cannot_be_cancelled",
            (
                "Only payment-pending or confirmed "
                "wholesale orders may be cancelled."
            ),
        )

    _cancel_fulfillment(
        order=order,
        now=now,
        reason=reason or "Wholesale order cancelled.",
    )

    order.status = WholesaleOrder.Status.CANCELLED
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.CANCELLED
    )
    order.internal_notes = reason
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

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.CANCELLED
        ),
        payload={
            "reason": reason,
            "refund_pending": (
                order.payment_status
                == WholesaleOrder
                .PaymentStatus.REFUND_PENDING
            ),
        },
    )
    return order


@transaction.atomic
def mark_wholesale_order_refunded(
    *,
    order,
    refund_payload=None,
):
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .get(pk=order.pk)
    )

    if (
        order.payment_status
        == WholesaleOrder.PaymentStatus.REFUNDED
    ):
        return order

    if (
        order.status != WholesaleOrder.Status.CANCELLED
        or order.payment_status
        != WholesaleOrder.PaymentStatus.REFUND_PENDING
    ):
        raise WholesaleCheckoutError(
            "refund_not_pending",
            "This wholesale order is not awaiting a refund.",
        )

    attempt = (
        WholesalePaymentAttempt.objects
        .select_for_update(of=("self",))
        .filter(
            order=order,
            status=WholesalePaymentAttempt.Status.PAID,
        )
        .order_by("-created_at")
        .first()
    )

    if attempt is None:
        raise WholesaleCheckoutError(
            "paid_payment_missing",
            "No paid payment exists for this order.",
        )

    now = timezone.now()

    attempt.status = WholesalePaymentAttempt.Status.REFUNDED
    attempt.provider_payload = _audit_payload(
        attempt.provider_payload,
        "refunded",
        at=now.isoformat(),
        response=refund_payload or {},
    )
    attempt.save(
        update_fields=[
            "status",
            "provider_payload",
            "updated_at",
        ]
    )

    order.payment_status = (
        WholesaleOrder.PaymentStatus.REFUNDED
    )
    order.save(
        update_fields=[
            "payment_status",
            "updated_at",
        ]
    )

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.REFUNDED
        ),
        payload={
            "refund": refund_payload or {},
        },
    )
    return order


def _ensure_wholesale_order_operator(actor):
    if (
        actor is None
        or not getattr(actor, "is_authenticated", False)
        or not actor.is_active
        or not actor.is_staff
    ):
        raise WholesaleCheckoutError(
            "staff_order_access_required",
            "An active staff account is required.",
        )

    if (
        not actor.is_superuser
        and not actor.has_perm(
            "wholesale_orders.change_wholesaleorder"
        )
    ):
        raise WholesaleCheckoutError(
            "staff_order_permission_required",
            "Wholesale order-management permission is required.",
        )


def _locked_wholesale_order_and_fulfillment(order):
    locked_order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .get(pk=order.pk)
    )
    fulfillment = (
        WholesaleFulfillment.objects
        .select_for_update(of=("self",))
        .get(order=locked_order)
    )

    return locked_order, fulfillment


@transaction.atomic
def start_wholesale_order_processing(
    *,
    order,
    actor,
    note="",
):
    _ensure_wholesale_order_operator(actor)
    order, fulfillment = (
        _locked_wholesale_order_and_fulfillment(order)
    )

    if order.status == WholesaleOrder.Status.PROCESSING:
        return order

    if (
        order.status != WholesaleOrder.Status.CONFIRMED
        or order.payment_status
        != WholesaleOrder.PaymentStatus.PAID
    ):
        raise WholesaleCheckoutError(
            "order_not_ready_for_processing",
            (
                "Only a confirmed and paid wholesale "
                "order can enter processing."
            ),
        )

    now = timezone.now()
    order.status = WholesaleOrder.Status.PROCESSING
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.PROCESSING
    )
    order.save(
        update_fields=[
            "status",
            "fulfillment_status",
            "updated_at",
        ]
    )

    fulfillment.status = (
        WholesaleFulfillment.Status.PROCESSING
    )
    fulfillment.processing_started_at = now
    fulfillment.metadata = _audit_payload(
        fulfillment.metadata,
        "processing_started",
        at=now.isoformat(),
        actor_id=actor.pk,
        actor=actor.get_username(),
        note=note.strip(),
    )
    fulfillment.save(
        update_fields=[
            "status",
            "processing_started_at",
            "metadata",
            "updated_at",
        ]
    )

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.PROCESSING
        ),
        payload={"note": note.strip()},
    )
    return order


@transaction.atomic
def mark_wholesale_order_shipped(
    *,
    order,
    actor,
    carrier_name,
    tracking_number,
    note="",
):
    _ensure_wholesale_order_operator(actor)

    carrier_name = carrier_name.strip()
    tracking_number = tracking_number.strip()

    if not carrier_name or not tracking_number:
        raise WholesaleCheckoutError(
            "shipment_details_required",
            (
                "Carrier name and tracking number "
                "are required."
            ),
        )

    order, fulfillment = (
        _locked_wholesale_order_and_fulfillment(order)
    )

    if order.status == WholesaleOrder.Status.SHIPPED:
        if (
            fulfillment.carrier_name == carrier_name
            and fulfillment.tracking_number
            == tracking_number
        ):
            return order

        raise WholesaleCheckoutError(
            "order_already_shipped",
            (
                "This order was already shipped with "
                "different tracking details."
            ),
        )

    if order.status != WholesaleOrder.Status.PROCESSING:
        raise WholesaleCheckoutError(
            "order_not_ready_to_ship",
            "Only a processing order can be shipped.",
        )

    now = timezone.now()
    order.status = WholesaleOrder.Status.SHIPPED
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.SHIPPED
    )
    order.save(
        update_fields=[
            "status",
            "fulfillment_status",
            "updated_at",
        ]
    )

    fulfillment.status = WholesaleFulfillment.Status.SHIPPED
    fulfillment.carrier_name = carrier_name
    fulfillment.tracking_number = tracking_number
    fulfillment.shipped_at = now
    fulfillment.metadata = _audit_payload(
        fulfillment.metadata,
        "shipped",
        at=now.isoformat(),
        actor_id=actor.pk,
        actor=actor.get_username(),
        carrier_name=carrier_name,
        tracking_number=tracking_number,
        note=note.strip(),
    )
    fulfillment.save(
        update_fields=[
            "status",
            "carrier_name",
            "tracking_number",
            "shipped_at",
            "metadata",
            "updated_at",
        ]
    )

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.SHIPPED
        ),
        payload={
            "carrier_name": carrier_name,
            "tracking_number": tracking_number,
            "note": note.strip(),
        },
    )
    return order


@transaction.atomic
def mark_wholesale_order_delivered(
    *,
    order,
    actor,
    note="",
):
    _ensure_wholesale_order_operator(actor)
    order, fulfillment = (
        _locked_wholesale_order_and_fulfillment(order)
    )

    if order.status == WholesaleOrder.Status.DELIVERED:
        return order

    if order.status != WholesaleOrder.Status.SHIPPED:
        raise WholesaleCheckoutError(
            "order_not_ready_for_delivery",
            "Only a shipped order can be marked delivered.",
        )

    now = timezone.now()
    order.status = WholesaleOrder.Status.DELIVERED
    order.fulfillment_status = (
        WholesaleOrder.FulfillmentStatus.DELIVERED
    )
    order.save(
        update_fields=[
            "status",
            "fulfillment_status",
            "updated_at",
        ]
    )

    fulfillment.status = (
        WholesaleFulfillment.Status.DELIVERED
    )
    fulfillment.delivered_at = now
    fulfillment.metadata = _audit_payload(
        fulfillment.metadata,
        "delivered",
        at=now.isoformat(),
        actor_id=actor.pk,
        actor=actor.get_username(),
        note=note.strip(),
    )
    fulfillment.save(
        update_fields=[
            "status",
            "delivered_at",
            "metadata",
            "updated_at",
        ]
    )

    _queue_wholesale_event(
        order=order,
        event_type=(
            WholesaleOrderNotificationEvent
            .EventType.DELIVERED
        ),
        payload={"note": note.strip()},
    )
    return order
