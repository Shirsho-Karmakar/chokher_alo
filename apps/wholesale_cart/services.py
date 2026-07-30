from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.prescriptions.models import (
    Prescription,
    PrescriptionEyeValue,
)
from apps.wholesale.models import WholesaleAccount
from apps.wholesale_catalog.matching import (
    matching_eyes_for_variant,
)
from apps.wholesale_catalog.models import (
    WholesaleLensListing,
    WholesaleLensVariant,
)
from apps.wholesale_catalog.pricing import (
    WholesalePricingError,
    quote_wholesale_boxes,
)

from .models import WholesaleCart, WholesaleCartItem


MONEY_PLACES = Decimal("0.01")


class WholesaleCartError(Exception):
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
class WholesaleCartReadiness:
    ready: bool
    subtotal_including_gst: Decimal
    total_boxes: int
    missing_checkout_details: tuple[str, ...]
    errors: tuple[str, ...]
    invalid_item_ids: tuple[int, ...]

    def as_dict(self):
        return {
            "ready": self.ready,
            "subtotal_including_gst": str(
                self.subtotal_including_gst
            ),
            "total_boxes": self.total_boxes,
            "missing_checkout_details": list(
                self.missing_checkout_details
            ),
            "errors": list(self.errors),
            "invalid_item_ids": list(
                self.invalid_item_ids
            ),
        }


def _money(value):
    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def _account_has_access(account):
    user = account.user

    return (
        user.is_active
        and user.phone_verified
        and account.status
        == WholesaleAccount.Status.APPROVED
    )


def _approved_account(*, user, lock=False):
    if (
        not getattr(user, "is_authenticated", False)
        or not user.is_active
        or not user.phone_verified
    ):
        raise WholesaleCartError(
            "wholesale_access_required",
            "An approved wholesale account is required.",
        )

    queryset = WholesaleAccount.objects.select_related(
        "user"
    )

    if lock:
        queryset = queryset.select_for_update(
            of=("self",)
        )

    try:
        account = queryset.get(user=user)
    except WholesaleAccount.DoesNotExist as exc:
        raise WholesaleCartError(
            "wholesale_account_missing",
            "A wholesale account has not been created.",
        ) from exc

    if not _account_has_access(account):
        raise WholesaleCartError(
            "wholesale_access_required",
            "An approved wholesale account is required.",
        )

    return account


def _variant_queryset(*, lock=False):
    queryset = (
        WholesaleLensVariant.objects
        .select_related(
            "listing",
            "listing__lens",
            "listing__lens__offer",
            "listing__lens__offer__variant",
            "listing__lens__offer__variant__design",
            "prescription_rule",
            "coating",
        )
        .prefetch_related(
            "prescription_rule__allowed_axes",
            "bulk_price_tiers",
        )
    )

    if lock:
        queryset = queryset.select_for_update(
            of=("self",)
        )

    return queryset


def _prescription_queryset():
    return Prescription.objects.prefetch_related(
        "eye_values"
    )


def _cart_item_queryset(*, lock=False):
    queryset = (
        WholesaleCartItem.objects
        .select_related(
            "cart",
            "cart__wholesale_account",
            "cart__wholesale_account__user",
            "variant",
            "variant__listing",
            "variant__listing__lens",
            "variant__listing__lens__offer",
            "variant__listing__lens__offer__variant",
            "variant__listing__lens__offer__variant__design",
            "variant__prescription_rule",
            "variant__coating",
            "prescription",
        )
        .prefetch_related(
            "variant__prescription_rule__allowed_axes",
            "variant__bulk_price_tiers",
            "prescription__eye_values",
        )
    )

    if lock:
        queryset = queryset.select_for_update(
            of=("self",)
        )

    return queryset


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


def _ensure_open_cart(*, cart, account):
    if cart.wholesale_account_id != account.pk:
        raise WholesaleCartError(
            "cart_not_owned",
            "This wholesale cart belongs to another account.",
        )

    if cart.status != WholesaleCart.Status.OPEN:
        raise WholesaleCartError(
            "cart_not_open",
            "The wholesale cart is not open for changes.",
        )


def physical_units_per_wholesale_box(variant):
    unit_multiplier = 1

    if (
        variant.listing.box_contents_unit
        == WholesaleLensListing.BoxContentsUnit.PAIR
    ):
        unit_multiplier = 2

    return (
        variant.listing.units_per_box
        * unit_multiplier
    )


def _validate_group_quantity(
    *,
    variant,
    total_boxes,
):
    if (
        variant.effective_status
        != WholesaleLensVariant.Status.AVAILABLE
    ):
        raise WholesaleCartError(
            "wholesale_variant_unavailable",
            "This wholesale lens is not currently available.",
        )

    if total_boxes < variant.minimum_order_boxes:
        raise WholesaleCartError(
            "minimum_order_not_met",
            (
                "The requested quantity is below the "
                "minimum order quantity."
            ),
            details={
                "minimum_order_boxes": (
                    variant.minimum_order_boxes
                ),
            },
        )

    if (
        total_boxes
        % variant.order_multiple_boxes
        != 0
    ):
        raise WholesaleCartError(
            "invalid_order_multiple",
            (
                "The requested quantity does not match "
                "the required box multiple."
            ),
            details={
                "order_multiple_boxes": (
                    variant.order_multiple_boxes
                ),
            },
        )

    if variant.boxes_in_stock < total_boxes:
        raise WholesaleCartError(
            "insufficient_wholesale_stock",
            "The requested boxes exceed wholesale stock.",
            details={
                "available_boxes": variant.boxes_in_stock,
                "requested_boxes": total_boxes,
            },
        )

    physical_variant = (
        variant.listing.lens.offer.variant
    )
    required_physical_units = (
        total_boxes
        * physical_units_per_wholesale_box(variant)
    )

    if (
        physical_variant.effective_stock_status
        != ProductVariant.StockStatus.AVAILABLE
    ):
        raise WholesaleCartError(
            "shared_stock_unavailable",
            (
                "The underlying shared physical stock "
                "is unavailable."
            ),
        )

    if (
        physical_variant.stock_mode
        == ProductVariant.StockMode.QUANTITY
        and physical_variant.stock_quantity
        < required_physical_units
    ):
        raise WholesaleCartError(
            "insufficient_shared_stock",
            (
                "The requested boxes exceed the shared "
                "physical stock."
            ),
            details={
                "available_physical_units": (
                    physical_variant.stock_quantity
                ),
                "required_physical_units": (
                    required_physical_units
                ),
            },
        )

    try:
        return quote_wholesale_boxes(
            variant=variant,
            boxes=total_boxes,
            enforce_stock=False,
        )
    except WholesalePricingError as exc:
        raise WholesaleCartError(
            "wholesale_quote_unavailable",
            str(exc),
        ) from exc


def _prescription_eye(
    *,
    account,
    prescription,
    variant,
    eye,
):
    if prescription.user_id != account.user_id:
        raise WholesaleCartError(
            "prescription_not_owned",
            (
                "The prescription does not belong to "
                "this wholesale account."
            ),
        )

    if prescription.status != Prescription.Status.APPROVED:
        raise WholesaleCartError(
            "prescription_not_approved",
            "An approved prescription is required.",
        )

    if eye not in PrescriptionEyeValue.Eye.values:
        raise WholesaleCartError(
            "invalid_eye",
            "The requested prescription eye is invalid.",
        )

    matching_eyes = matching_eyes_for_variant(
        prescription=prescription,
        variant=variant,
    )

    if eye not in matching_eyes:
        raise WholesaleCartError(
            "prescription_range_mismatch",
            (
                "The selected wholesale lens does not "
                "match this prescription eye."
            ),
        )

    for eye_value in prescription.eye_values.all():
        if eye_value.eye == eye:
            return eye_value

    raise WholesaleCartError(
        "prescription_eye_missing",
        "The requested eye values are missing.",
    )


def _decimal_snapshot(value):
    if value is None:
        return None

    return str(value)


def _eye_snapshot(eye_value):
    return {
        "eye": eye_value.eye,
        "sphere": _decimal_snapshot(
            eye_value.sphere
        ),
        "cylinder": _decimal_snapshot(
            eye_value.cylinder
        ),
        "axis": eye_value.axis,
        "add_power": _decimal_snapshot(
            eye_value.add_power
        ),
        "distance_pd_mm": _decimal_snapshot(
            eye_value.distance_pd_mm
        ),
        "near_pd_mm": _decimal_snapshot(
            eye_value.near_pd_mm
        ),
        "prism_diopters": _decimal_snapshot(
            eye_value.prism_diopters
        ),
        "prism_base": eye_value.prism_base or None,
    }


def _variant_snapshot(variant):
    listing = variant.listing
    lens = listing.lens
    physical_variant = lens.offer.variant

    return {
        "variant_id": variant.pk,
        "sku": variant.sku,
        "supplier_code": variant.supplier_code or None,
        "catalogue_code": listing.catalogue_code,
        "name": listing.name,
        "prescription_rule_id": (
            variant.prescription_rule_id
        ),
        "prescription_rule_name": (
            variant.prescription_rule.name
        ),
        "coating": (
            {
                "id": variant.coating_id,
                "code": variant.coating.code,
                "name": variant.coating.name,
            }
            if variant.coating_id
            else None
        ),
        "box_contents_unit": listing.box_contents_unit,
        "units_per_box": listing.units_per_box,
        "physical_units_per_box": (
            physical_units_per_wholesale_box(variant)
        ),
        "physical_variant_id": physical_variant.pk,
        "physical_sku": physical_variant.physical_sku,
    }


def _set_valid_item(
    *,
    item,
    quote,
    eye_value,
    aggregate_boxes,
    validated_at,
):
    base_price = _money(
        quote.base_box_price_including_gst
    )
    applied_price = _money(
        quote.applied_box_price_including_gst
    )
    discount = _money(
        quote.discount_per_box_including_gst
    )
    subtotal = _money(
        applied_price * item.boxes
    )

    item.base_box_price_including_gst = base_price
    item.applied_box_price_including_gst = (
        applied_price
    )
    item.discount_per_box_including_gst = discount
    item.subtotal_including_gst = subtotal
    item.bulk_price_tier_id_snapshot = (
        quote.bulk_tier_id
    )
    item.variant_snapshot = _variant_snapshot(
        item.variant
    )
    item.prescription_snapshot = _eye_snapshot(
        eye_value
    )
    item.pricing_snapshot = {
        "aggregate_variant_boxes": aggregate_boxes,
        "base_box_price_including_gst": str(
            base_price
        ),
        "applied_box_price_including_gst": str(
            applied_price
        ),
        "discount_per_box_including_gst": str(
            discount
        ),
        "bulk_price_tier_id": quote.bulk_tier_id,
    }
    item.validation_status = (
        WholesaleCartItem.ValidationStatus.VALID
    )
    item.validation_code = ""
    item.validation_message = ""
    item.validated_at = validated_at

    item.save(
        update_fields=[
            "base_box_price_including_gst",
            "applied_box_price_including_gst",
            "discount_per_box_including_gst",
            "subtotal_including_gst",
            "bulk_price_tier_id_snapshot",
            "variant_snapshot",
            "prescription_snapshot",
            "pricing_snapshot",
            "validation_status",
            "validation_code",
            "validation_message",
            "validated_at",
            "updated_at",
        ]
    )


def _set_invalid_item(
    *,
    item,
    code,
    message,
    validated_at,
):
    item.validation_status = (
        WholesaleCartItem.ValidationStatus.INVALID
    )
    item.validation_code = code
    item.validation_message = message
    item.validated_at = validated_at

    item.save(
        update_fields=[
            "validation_status",
            "validation_code",
            "validation_message",
            "validated_at",
            "updated_at",
        ]
    )


def _revalidate_locked_cart(cart):
    account = cart.wholesale_account
    validated_at = timezone.now()

    items = list(
        _cart_item_queryset(lock=True)
        .filter(cart=cart)
        .order_by("pk")
    )

    if not _account_has_access(account):
        for item in items:
            _set_invalid_item(
                item=item,
                code="wholesale_access_required",
                message=(
                    "The wholesale account is not "
                    "currently approved."
                ),
                validated_at=validated_at,
            )

        cart.pricing_updated_at = validated_at
        cart.save(
            update_fields=[
                "pricing_updated_at",
                "updated_at",
            ]
        )

        return WholesaleCartReadiness(
            ready=False,
            subtotal_including_gst=_money("0.00"),
            total_boxes=sum(
                item.boxes
                for item in items
            ),
            missing_checkout_details=(
                account.missing_checkout_details()
            ),
            errors=("wholesale_access_required",),
            invalid_item_ids=tuple(
                item.pk
                for item in items
            ),
        )

    grouped_items = defaultdict(list)

    for item in items:
        grouped_items[item.variant_id].append(item)

    errors = []
    invalid_item_ids = []

    for variant_id, variant_items in grouped_items.items():
        variant = _variant_queryset(lock=True).get(
            pk=variant_id
        )
        total_boxes = sum(
            item.boxes
            for item in variant_items
        )

        try:
            quote = _validate_group_quantity(
                variant=variant,
                total_boxes=total_boxes,
            )
        except WholesaleCartError as exc:
            errors.append(exc.code)

            for item in variant_items:
                _set_invalid_item(
                    item=item,
                    code=exc.code,
                    message=str(exc),
                    validated_at=validated_at,
                )
                invalid_item_ids.append(item.pk)

            continue

        for item in variant_items:
            item.variant = variant

            try:
                eye_value = _prescription_eye(
                    account=account,
                    prescription=item.prescription,
                    variant=variant,
                    eye=item.eye,
                )
            except WholesaleCartError as exc:
                errors.append(exc.code)
                invalid_item_ids.append(item.pk)

                _set_invalid_item(
                    item=item,
                    code=exc.code,
                    message=str(exc),
                    validated_at=validated_at,
                )
                continue

            _set_valid_item(
                item=item,
                quote=quote,
                eye_value=eye_value,
                aggregate_boxes=total_boxes,
                validated_at=validated_at,
            )

    cart.pricing_updated_at = validated_at
    cart.save(
        update_fields=[
            "pricing_updated_at",
            "updated_at",
        ]
    )

    subtotal = _money(
        sum(
            (
                item.subtotal_including_gst
                for item in items
                if item.validation_status
                == WholesaleCartItem
                .ValidationStatus.VALID
            ),
            start=Decimal("0.00"),
        )
    )

    missing_details = (
        account.missing_checkout_details()
    )

    if not items:
        errors.append("empty_cart")

    if missing_details:
        errors.append("checkout_details_incomplete")

    unique_errors = tuple(dict.fromkeys(errors))

    return WholesaleCartReadiness(
        ready=(
            bool(items)
            and not invalid_item_ids
            and not missing_details
            and not unique_errors
        ),
        subtotal_including_gst=subtotal,
        total_boxes=sum(
            item.boxes
            for item in items
        ),
        missing_checkout_details=missing_details,
        errors=unique_errors,
        invalid_item_ids=tuple(invalid_item_ids),
    )


@transaction.atomic
def get_or_create_open_wholesale_cart(*, user):
    account = _approved_account(
        user=user,
        lock=True,
    )

    cart = (
        WholesaleCart.objects
        .select_for_update(of=("self",))
        .filter(
            wholesale_account=account,
            status__in=[
                WholesaleCart.Status.OPEN,
                WholesaleCart.Status.CHECKOUT_STARTED,
            ],
        )
        .order_by("pk")
        .first()
    )

    if cart is None:
        cart = WholesaleCart.objects.create(
            wholesale_account=account,
        )
    elif cart.status == (
        WholesaleCart.Status.CHECKOUT_STARTED
    ):
        from apps.wholesale_orders.models import (
            WholesaleOrder,
        )

        active_checkout_exists = (
            WholesaleOrder.objects
            .filter(
                source_cart=cart,
                status__in=[
                    WholesaleOrder.Status.PAYMENT_PENDING,
                    WholesaleOrder.Status.CONFIRMED,
                    WholesaleOrder.Status.PROCESSING,
                    WholesaleOrder.Status.SHIPPED,
                ],
            )
            .exists()
        )

        if not active_checkout_exists:
            cart.status = WholesaleCart.Status.OPEN
            cart.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    cart.wholesale_account = account
    _revalidate_locked_cart(cart)

    return (
        WholesaleCart.objects
        .select_related(
            "wholesale_account",
            "wholesale_account__user",
        )
        .prefetch_related("items")
        .get(pk=cart.pk)
    )


@transaction.atomic
def set_wholesale_cart_item(
    *,
    cart,
    variant,
    prescription,
    eye,
    boxes,
):
    if (
        not isinstance(boxes, int)
        or isinstance(boxes, bool)
        or boxes < 1
    ):
        raise WholesaleCartError(
            "invalid_box_quantity",
            "Box quantity must be a positive whole number.",
        )

    cart = _locked_cart(cart)
    account = _approved_account(
        user=cart.wholesale_account.user,
        lock=True,
    )
    _ensure_open_cart(
        cart=cart,
        account=account,
    )

    variant = _variant_queryset(lock=True).get(
        pk=variant.pk
    )
    prescription = _prescription_queryset().get(
        pk=prescription.pk
    )

    _prescription_eye(
        account=account,
        prescription=prescription,
        variant=variant,
        eye=eye,
    )

    existing_item = (
        _cart_item_queryset(lock=True)
        .filter(
            cart=cart,
            variant=variant,
            prescription=prescription,
            eye=eye,
        )
        .first()
    )

    other_boxes = (
        WholesaleCartItem.objects
        .filter(
            cart=cart,
            variant=variant,
        )
        .exclude(
            pk=(
                existing_item.pk
                if existing_item
                else None
            )
        )
        .aggregate(total=Sum("boxes"))["total"]
        or 0
    )

    _validate_group_quantity(
        variant=variant,
        total_boxes=other_boxes + boxes,
    )

    if existing_item is None:
        item = WholesaleCartItem.objects.create(
            cart=cart,
            variant=variant,
            prescription=prescription,
            eye=eye,
            boxes=boxes,
        )
    else:
        item = existing_item
        item.boxes = boxes
        item.save(
            update_fields=[
                "boxes",
                "updated_at",
            ]
        )

    _revalidate_locked_cart(cart)

    return _cart_item_queryset().get(pk=item.pk)


@transaction.atomic
def remove_wholesale_cart_item(*, item):
    cart = _locked_cart(item.cart)
    account = _approved_account(
        user=cart.wholesale_account.user,
        lock=True,
    )
    _ensure_open_cart(
        cart=cart,
        account=account,
    )

    locked_item = (
        WholesaleCartItem.objects
        .select_for_update(of=("self",))
        .get(
            pk=item.pk,
            cart=cart,
        )
    )
    locked_item.delete()

    return _revalidate_locked_cart(cart)


@transaction.atomic
def revalidate_wholesale_cart(*, cart):
    cart = _locked_cart(cart)

    return _revalidate_locked_cart(cart)
