from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .models import WholesaleLensVariant


MONEY_PLACES = Decimal("0.01")


class WholesalePricingError(Exception):
    """Raised when a valid wholesale box quotation cannot be produced."""


@dataclass(frozen=True)
class WholesaleBoxQuote:
    variant_id: int
    sku: str
    boxes: int
    base_box_price_including_gst: Decimal
    applied_box_price_including_gst: Decimal
    discount_per_box_including_gst: Decimal
    subtotal_including_gst: Decimal
    bulk_tier_id: int | None


def _money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def quote_wholesale_boxes(
    *,
    variant: WholesaleLensVariant,
    boxes: int,
    enforce_stock: bool = True,
) -> WholesaleBoxQuote:
    if isinstance(boxes, bool) or not isinstance(boxes, int):
        raise WholesalePricingError(
            "Box quantity must be a whole number."
        )

    if boxes < 1:
        raise WholesalePricingError(
            "At least one box must be requested."
        )

    if (
        variant.effective_status
        != WholesaleLensVariant.Status.AVAILABLE
    ):
        raise WholesalePricingError(
            "This wholesale lens is not currently available."
        )

    if variant.base_box_price_including_gst is None:
        raise WholesalePricingError(
            "The wholesale box price is not configured."
        )

    if boxes < variant.minimum_order_boxes:
        raise WholesalePricingError(
            f"The minimum order is "
            f"{variant.minimum_order_boxes} boxes."
        )

    if boxes % variant.order_multiple_boxes != 0:
        raise WholesalePricingError(
            "The requested quantity does not match the "
            "required box multiple."
        )

    if enforce_stock and boxes > variant.boxes_in_stock:
        raise WholesalePricingError(
            "The requested quantity exceeds available stock."
        )

    matching_tier = None

    tiers = (
        variant.bulk_price_tiers
        .filter(is_active=True)
        .order_by("-minimum_boxes")
    )

    for tier in tiers:
        if tier.matches_quantity(boxes):
            matching_tier = tier
            break

    base_price = _money(
        variant.base_box_price_including_gst
    )

    applied_price = (
        _money(matching_tier.box_price_including_gst)
        if matching_tier is not None
        else base_price
    )

    discount_per_box = _money(
        base_price - applied_price
    )
    subtotal = _money(
        applied_price * boxes
    )

    return WholesaleBoxQuote(
        variant_id=variant.pk,
        sku=variant.sku,
        boxes=boxes,
        base_box_price_including_gst=base_price,
        applied_box_price_including_gst=applied_price,
        discount_per_box_including_gst=discount_per_box,
        subtotal_including_gst=subtotal,
        bulk_tier_id=(
            matching_tier.pk
            if matching_tier is not None
            else None
        ),
    )
