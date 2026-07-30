from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductOffer, ProductVariant
from apps.lenses.models import LensCoating, LensSpecification
from apps.lenses.pricing import LensPricingError, quote_lens
from apps.prescriptions.models import Prescription

from .models import (
    CustomerOwnedFrameService,
    PoweredEyewearConfiguration,
    RetailCart,
    RetailCartItem,
)


User = get_user_model()
MONEY_PLACES = Decimal("0.01")


class RetailCartError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class CartValidationIssue:
    code: str
    message: str
    item_id: int | None
    blocking: bool


@dataclass(frozen=True)
class CartValidationResult:
    cart_id: int
    issues: tuple[CartValidationIssue, ...]
    removed_item_ids: tuple[int, ...]
    subtotal_including_gst: Decimal
    checkout_ready: bool
    has_unpriced_items: bool


def _money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def _ensure_open_cart(cart: RetailCart) -> None:
    if cart.status != RetailCart.Status.OPEN:
        raise RetailCartError(
            "cart_not_open",
            "This retail cart is no longer open.",
        )


def _ensure_quantity(quantity: int) -> None:
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise RetailCartError(
            "invalid_quantity",
            "Quantity must be a whole number.",
        )

    if quantity < 1 or quantity > 10:
        raise RetailCartError(
            "invalid_quantity",
            "Retail quantities must be between 1 and 10.",
        )


def _ensure_offer_available(
    offer: ProductOffer,
    *,
    quantity: int,
) -> None:
    if offer.effective_status != ProductOffer.Status.AVAILABLE:
        raise RetailCartError(
            "offer_unavailable",
            "This product is not currently available.",
        )

    if offer.selling_price_including_gst is None:
        raise RetailCartError(
            "price_unavailable",
            "This product does not have a configured selling price.",
        )

    variant = offer.variant

    if (
        variant.stock_mode == ProductVariant.StockMode.QUANTITY
        and variant.stock_quantity < quantity
    ):
        raise RetailCartError(
            "insufficient_stock",
            "The requested quantity is not currently available.",
        )


def _ensure_lens_available(lens: LensSpecification) -> None:
    if not lens.is_active:
        raise RetailCartError(
            "lens_unavailable",
            "The selected lens is not currently available.",
        )

    if (
        lens.offer.effective_status
        != ProductOffer.Status.AVAILABLE
    ):
        raise RetailCartError(
            "lens_unavailable",
            "The selected lens is not currently available.",
        )


def _quote_lines(quote) -> list[dict]:
    return [
        {
            "code": line.code,
            "name": line.name,
            "amount_including_gst": str(
                line.amount_including_gst
            ),
            "rule_id": line.rule_id,
        }
        for line in quote.lines
    ]


def _set_item_price(
    item: RetailCartItem,
    unit_price: Decimal,
) -> bool:
    unit_price = _money(unit_price)
    total = _money(unit_price * item.quantity)

    price_changed = (
        item.current_unit_price_including_gst is not None
        and item.current_unit_price_including_gst
        != unit_price
    )

    item.current_unit_price_including_gst = unit_price
    item.current_total_including_gst = total
    item.price_refreshed_at = timezone.now()
    item.save(
        update_fields=[
            "current_unit_price_including_gst",
            "current_total_including_gst",
            "price_refreshed_at",
            "is_non_refundable",
            "updated_at",
        ]
    )

    return price_changed


def _clear_item_price(item: RetailCartItem) -> None:
    item.current_unit_price_including_gst = None
    item.current_total_including_gst = None
    item.price_refreshed_at = timezone.now()
    item.save(
        update_fields=[
            "current_unit_price_including_gst",
            "current_total_including_gst",
            "price_refreshed_at",
            "is_non_refundable",
            "updated_at",
        ]
    )


def _clear_quote_only(configuration) -> None:
    configuration.lens_quote_breakdown = []
    configuration.lens_quote_total_including_gst = None
    configuration.configured_unit_price_including_gst = None
    configuration.quote_refreshed_at = None
    configuration.save(
        update_fields=[
            "lens_quote_breakdown",
            "lens_quote_total_including_gst",
            "configured_unit_price_including_gst",
            "quote_refreshed_at",
            "updated_at",
        ]
    )


def _reset_configuration(configuration) -> None:
    configuration.lens = None
    configuration.lens_quote_breakdown = []
    configuration.lens_quote_total_including_gst = None
    configuration.configured_unit_price_including_gst = None
    configuration.quote_refreshed_at = None
    configuration.save(
        update_fields=[
            "lens",
            "lens_quote_breakdown",
            "lens_quote_total_including_gst",
            "configured_unit_price_including_gst",
            "quote_refreshed_at",
            "updated_at",
        ]
    )
    configuration.selected_coatings.clear()


def _store_quote(
    configuration,
    *,
    quote,
    configured_price: Decimal,
) -> None:
    configuration.lens_quote_breakdown = _quote_lines(quote)
    configuration.lens_quote_total_including_gst = (
        quote.total_including_gst
    )
    configuration.configured_unit_price_including_gst = (
        _money(configured_price)
    )
    configuration.quote_refreshed_at = timezone.now()
    configuration.save(
        update_fields=[
            "lens_quote_breakdown",
            "lens_quote_total_including_gst",
            "configured_unit_price_including_gst",
            "quote_refreshed_at",
            "updated_at",
        ]
    )


@transaction.atomic
def get_or_create_open_retail_cart(*, user) -> RetailCart:
    if not user.is_authenticated or not user.is_active:
        raise RetailCartError(
            "login_required",
            "An active customer login is required.",
        )

    # Locking the user serializes simultaneous open-cart creation attempts.
    User.objects.select_for_update().get(pk=user.pk)

    cart, _ = RetailCart.objects.get_or_create(
        user=user,
        status=RetailCart.Status.OPEN,
    )

    return cart


@transaction.atomic
def add_standard_offer(
    *,
    cart: RetailCart,
    offer: ProductOffer,
    quantity: int = 1,
) -> RetailCartItem:
    _ensure_quantity(quantity)

    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=cart.pk)
    )
    _ensure_open_cart(cart)

    offer = (
        ProductOffer.objects
        .select_related(
            "variant",
            "variant__design",
        )
        .get(pk=offer.pk)
    )

    if offer.requires_prescription:
        raise RetailCartError(
            "configuration_required",
            "This product requires a prescription configuration.",
        )

    existing = (
        RetailCartItem.objects
        .select_for_update()
        .filter(
            cart=cart,
            item_type=RetailCartItem.ItemType.STANDARD,
            offer=offer,
        )
        .first()
    )

    new_quantity = quantity

    if existing is not None:
        new_quantity += existing.quantity

    _ensure_quantity(new_quantity)
    _ensure_offer_available(
        offer,
        quantity=new_quantity,
    )

    if existing is None:
        item = RetailCartItem.objects.create(
            cart=cart,
            item_type=RetailCartItem.ItemType.STANDARD,
            offer=offer,
            quantity=new_quantity,
        )
    else:
        item = existing
        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])

    _set_item_price(
        item,
        offer.selling_price_including_gst,
    )

    return item


@transaction.atomic
def add_powered_eyewear(
    *,
    cart: RetailCart,
    offer: ProductOffer,
    prescription: Prescription,
) -> RetailCartItem:
    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=cart.pk)
    )
    _ensure_open_cart(cart)

    offer = (
        ProductOffer.objects
        .select_related(
            "variant",
            "variant__design",
        )
        .get(pk=offer.pk)
    )

    if not offer.supports_powered_lenses:
        raise RetailCartError(
            "powered_lenses_not_supported",
            "This eyewear offer does not support powered lenses.",
        )

    _ensure_offer_available(offer, quantity=1)

    if prescription.user_id != cart.user_id:
        raise RetailCartError(
            "invalid_prescription",
            "The prescription must belong to the cart owner.",
        )

    item = RetailCartItem.objects.create(
        cart=cart,
        item_type=RetailCartItem.ItemType.POWERED_EYEWEAR,
        offer=offer,
        quantity=1,
    )
    PoweredEyewearConfiguration.objects.create(
        cart_item=item,
        prescription=prescription,
    )

    _set_item_price(
        item,
        offer.selling_price_including_gst,
    )

    return item


@transaction.atomic
def configure_powered_eyewear(
    *,
    item: RetailCartItem,
    lens: LensSpecification,
    coatings: Iterable[LensCoating] = (),
) -> RetailCartItem:
    item = (
        RetailCartItem.objects
        .select_for_update(of=("self",))
        .select_related(
            "cart",
            "offer",
            "offer__variant",
            "powered_configuration",
            "powered_configuration__prescription",
        )
        .get(pk=item.pk)
    )
    _ensure_open_cart(item.cart)

    if item.item_type != RetailCartItem.ItemType.POWERED_EYEWEAR:
        raise RetailCartError(
            "invalid_item_type",
            "This cart item is not powered eyewear.",
        )

    _ensure_offer_available(item.offer, quantity=1)

    lens = (
        LensSpecification.objects
        .select_related(
            "offer",
            "offer__variant",
            "offer__variant__design",
        )
        .prefetch_related(
            "coatings",
            "prescription_rules__allowed_axes",
            "price_rules",
        )
        .get(pk=lens.pk)
    )
    _ensure_lens_available(lens)

    configuration = item.powered_configuration
    prescription = configuration.prescription

    if not prescription.is_approved:
        raise RetailCartError(
            "prescription_not_approved",
            "The prescription must be approved before "
            "a powered lens is selected.",
        )

    coatings = tuple(coatings)

    if any(not coating.is_active for coating in coatings):
        raise RetailCartError(
            "coating_unavailable",
            "One or more selected coatings are unavailable.",
        )

    try:
        quote = quote_lens(
            lens=lens,
            prescription=prescription,
            selected_coatings=coatings,
            frame_variant=item.offer.variant,
        )
    except LensPricingError as exc:
        raise RetailCartError(
            "lens_quote_unavailable",
            str(exc),
        ) from exc

    frame_price = item.offer.selling_price_including_gst
    configured_price = _money(
        frame_price + quote.total_including_gst
    )

    configuration.lens = lens
    configuration.save(update_fields=["lens", "updated_at"])
    configuration.selected_coatings.set(coatings)

    _store_quote(
        configuration,
        quote=quote,
        configured_price=configured_price,
    )
    _set_item_price(item, configured_price)

    return item


@transaction.atomic
def add_customer_owned_frame_service(
    *,
    cart: RetailCart,
    prescription: Prescription,
    completion_choice: str,
    frame_handling: str,
    customer_notes: str = "",
) -> RetailCartItem:
    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=cart.pk)
    )
    _ensure_open_cart(cart)

    if prescription.user_id != cart.user_id:
        raise RetailCartError(
            "invalid_prescription",
            "The prescription must belong to the cart owner.",
        )

    item = RetailCartItem.objects.create(
        cart=cart,
        item_type=(
            RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
        ),
        quantity=1,
    )

    CustomerOwnedFrameService.objects.create(
        cart_item=item,
        prescription=prescription,
        completion_choice=completion_choice,
        frame_handling=frame_handling,
        customer_notes=customer_notes,
    )

    _clear_item_price(item)

    return item


@transaction.atomic
def configure_customer_owned_frame_service(
    *,
    item: RetailCartItem,
    lens: LensSpecification,
    coatings: Iterable[LensCoating] = (),
) -> RetailCartItem:
    item = (
        RetailCartItem.objects
        .select_for_update(of=("self",))
        .select_related(
            "cart",
            "owned_frame_service",
            "owned_frame_service__prescription",
        )
        .get(pk=item.pk)
    )
    _ensure_open_cart(item.cart)

    if (
        item.item_type
        != RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
    ):
        raise RetailCartError(
            "invalid_item_type",
            "This cart item is not a customer-owned frame service.",
        )

    lens = (
        LensSpecification.objects
        .select_related(
            "offer",
            "offer__variant",
            "offer__variant__design",
        )
        .prefetch_related(
            "coatings",
            "prescription_rules__allowed_axes",
            "price_rules",
        )
        .get(pk=lens.pk)
    )
    _ensure_lens_available(lens)

    service = item.owned_frame_service
    prescription = service.prescription

    if not prescription.is_approved:
        raise RetailCartError(
            "prescription_not_approved",
            "The prescription must be approved before "
            "a powered lens is selected.",
        )

    coatings = tuple(coatings)

    if any(not coating.is_active for coating in coatings):
        raise RetailCartError(
            "coating_unavailable",
            "One or more selected coatings are unavailable.",
        )

    try:
        quote = quote_lens(
            lens=lens,
            prescription=prescription,
            selected_coatings=coatings,
            frame_variant=None,
        )
    except LensPricingError as exc:
        raise RetailCartError(
            "lens_quote_unavailable",
            str(exc),
        ) from exc

    configured_price = quote.total_including_gst

    service.lens = lens
    service.save(update_fields=["lens", "updated_at"])
    service.selected_coatings.set(coatings)

    _store_quote(
        service,
        quote=quote,
        configured_price=configured_price,
    )
    _set_item_price(item, configured_price)

    return item


def _item_issue(
    *,
    code: str,
    message: str,
    item_id: int | None,
    blocking: bool,
) -> CartValidationIssue:
    return CartValidationIssue(
        code=code,
        message=message,
        item_id=item_id,
        blocking=blocking,
    )


@transaction.atomic
def refresh_retail_cart(
    *,
    cart: RetailCart,
) -> CartValidationResult:
    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=cart.pk)
    )
    _ensure_open_cart(cart)

    items = list(
        RetailCartItem.objects
        .select_for_update(of=("self",))
        .filter(cart=cart)
        .select_related(
            "offer",
            "offer__variant",
            "offer__variant__design",
            "powered_configuration",
            "powered_configuration__prescription",
            "powered_configuration__lens",
            "powered_configuration__lens__offer",
            "powered_configuration__lens__offer__variant",
            "owned_frame_service",
            "owned_frame_service__prescription",
            "owned_frame_service__lens",
            "owned_frame_service__lens__offer",
            "owned_frame_service__lens__offer__variant",
        )
        .prefetch_related(
            "powered_configuration__selected_coatings",
            "owned_frame_service__selected_coatings",
        )
        .order_by("created_at", "pk")
    )

    issues = []
    removed_item_ids = []
    remaining_items = []

    def remove_item(item, *, code, message):
        item_id = item.pk
        item.delete()
        removed_item_ids.append(item_id)
        issues.append(
            _item_issue(
                code=code,
                message=message,
                item_id=item_id,
                blocking=False,
            )
        )

    for item in items:
        if item.item_type == RetailCartItem.ItemType.STANDARD:
            try:
                _ensure_offer_available(
                    item.offer,
                    quantity=item.quantity,
                )
            except RetailCartError as exc:
                remove_item(
                    item,
                    code="item_removed_unavailable",
                    message=(
                        f"{item.offer.sku} was removed because "
                        f"it is no longer available: {exc}"
                    ),
                )
                continue

            if _set_item_price(
                item,
                item.offer.selling_price_including_gst,
            ):
                issues.append(
                    _item_issue(
                        code="price_updated",
                        message=(
                            f"The price of {item.offer.sku} "
                            "was updated."
                        ),
                        item_id=item.pk,
                        blocking=False,
                    )
                )

            remaining_items.append(item)
            continue

        if item.item_type == RetailCartItem.ItemType.POWERED_EYEWEAR:
            try:
                _ensure_offer_available(item.offer, quantity=1)
            except RetailCartError:
                remove_item(
                    item,
                    code="powered_item_removed_unavailable",
                    message=(
                        f"{item.offer.sku} was removed because "
                        "the eyewear is no longer available."
                    ),
                )
                continue

            configuration = getattr(
                item,
                "powered_configuration",
                None,
            )

            if configuration is None:
                issues.append(
                    _item_issue(
                        code="powered_configuration_missing",
                        message=(
                            "The powered-eyewear configuration "
                            "is missing."
                        ),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            prescription = configuration.prescription

            if prescription.status in {
                Prescription.Status.PENDING,
                Prescription.Status.UNDER_REVIEW,
            }:
                _reset_configuration(configuration)
                _set_item_price(
                    item,
                    item.offer.selling_price_including_gst,
                )
                issues.append(
                    _item_issue(
                        code="prescription_pending",
                        message=(
                            "The prescription is awaiting review."
                        ),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            if not prescription.is_approved:
                _reset_configuration(configuration)
                _set_item_price(
                    item,
                    item.offer.selling_price_including_gst,
                )
                issues.append(
                    _item_issue(
                        code="prescription_not_approved",
                        message=(
                            "The prescription is not approved. "
                            "The lens configuration must be updated."
                        ),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            if configuration.lens_id is None:
                _clear_quote_only(configuration)
                _set_item_price(
                    item,
                    item.offer.selling_price_including_gst,
                )
                issues.append(
                    _item_issue(
                        code="lens_selection_required",
                        message=(
                            "Select compatible powered lenses "
                            "for this eyewear."
                        ),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            try:
                _ensure_lens_available(configuration.lens)
            except RetailCartError:
                remove_item(
                    item,
                    code="powered_item_removed_lens_unavailable",
                    message=(
                        "The powered-eyewear item was removed "
                        "because its selected lens is unavailable."
                    ),
                )
                continue

            coatings = tuple(
                configuration.selected_coatings.all()
            )

            if any(not coating.is_active for coating in coatings):
                _clear_quote_only(configuration)
                issues.append(
                    _item_issue(
                        code="coating_unavailable",
                        message=(
                            "One or more selected coatings "
                            "are unavailable."
                        ),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            try:
                quote = quote_lens(
                    lens=configuration.lens,
                    prescription=prescription,
                    selected_coatings=coatings,
                    frame_variant=item.offer.variant,
                )
            except LensPricingError as exc:
                _clear_quote_only(configuration)
                issues.append(
                    _item_issue(
                        code="powered_configuration_invalid",
                        message=str(exc),
                        item_id=item.pk,
                        blocking=True,
                    )
                )
                remaining_items.append(item)
                continue

            configured_price = _money(
                item.offer.selling_price_including_gst
                + quote.total_including_gst
            )
            _store_quote(
                configuration,
                quote=quote,
                configured_price=configured_price,
            )

            if _set_item_price(item, configured_price):
                issues.append(
                    _item_issue(
                        code="price_updated",
                        message=(
                            "The configured powered-eyewear "
                            "price was updated."
                        ),
                        item_id=item.pk,
                        blocking=False,
                    )
                )

            remaining_items.append(item)
            continue

        service = getattr(
            item,
            "owned_frame_service",
            None,
        )

        if service is None:
            issues.append(
                _item_issue(
                    code="owned_frame_service_missing",
                    message=(
                        "The customer-owned frame service "
                        "configuration is missing."
                    ),
                    item_id=item.pk,
                    blocking=True,
                )
            )
            remaining_items.append(item)
            continue

        prescription = service.prescription

        if prescription.status in {
            Prescription.Status.PENDING,
            Prescription.Status.UNDER_REVIEW,
        }:
            _reset_configuration(service)
            _clear_item_price(item)
            issues.append(
                _item_issue(
                    code="prescription_pending",
                    message=(
                        "The prescription is awaiting review."
                    ),
                    item_id=item.pk,
                    blocking=True,
                )
            )
            remaining_items.append(item)
            continue

        if not prescription.is_approved:
            _reset_configuration(service)
            _clear_item_price(item)
            issues.append(
                _item_issue(
                    code="prescription_not_approved",
                    message=(
                        "The prescription is not approved."
                    ),
                    item_id=item.pk,
                    blocking=True,
                )
            )
            remaining_items.append(item)
            continue

        if service.lens_id is None:
            _clear_quote_only(service)
            _clear_item_price(item)
            issues.append(
                _item_issue(
                    code="lens_selection_required",
                    message=(
                        "Select compatible powered lenses "
                        "for the customer-owned frame service."
                    ),
                    item_id=item.pk,
                    blocking=True,
                )
            )
            remaining_items.append(item)
            continue

        try:
            _ensure_lens_available(service.lens)
        except RetailCartError:
            remove_item(
                item,
                code="owned_frame_service_removed_lens_unavailable",
                message=(
                    "The customer-owned frame service was removed "
                    "because its selected lens is unavailable."
                ),
            )
            continue

        coatings = tuple(service.selected_coatings.all())

        try:
            quote = quote_lens(
                lens=service.lens,
                prescription=prescription,
                selected_coatings=coatings,
                frame_variant=None,
            )
        except LensPricingError as exc:
            _clear_quote_only(service)
            issues.append(
                _item_issue(
                    code="owned_frame_configuration_invalid",
                    message=str(exc),
                    item_id=item.pk,
                    blocking=True,
                )
            )
            remaining_items.append(item)
            continue

        configured_price = quote.total_including_gst
        _store_quote(
            service,
            quote=quote,
            configured_price=configured_price,
        )

        if _set_item_price(item, configured_price):
            issues.append(
                _item_issue(
                    code="price_updated",
                    message=(
                        "The customer-owned frame service price "
                        "was updated."
                    ),
                    item_id=item.pk,
                    blocking=False,
                )
            )

        remaining_items.append(item)

    subtotal = _money(
        sum(
            (
                item.current_total_including_gst
                for item in remaining_items
                if item.current_total_including_gst is not None
            ),
            start=Decimal("0.00"),
        )
    )

    has_unpriced_items = any(
        item.current_total_including_gst is None
        for item in remaining_items
    )
    has_blocking_issues = any(
        issue.blocking
        for issue in issues
    )

    checkout_ready = bool(
        remaining_items
        and not has_unpriced_items
        and not has_blocking_issues
    )

    cart.last_validated_at = timezone.now()
    cart.save(
        update_fields=[
            "last_validated_at",
            "updated_at",
        ]
    )

    return CartValidationResult(
        cart_id=cart.pk,
        issues=tuple(issues),
        removed_item_ids=tuple(removed_item_ids),
        subtotal_including_gst=subtotal,
        checkout_ready=checkout_ready,
        has_unpriced_items=has_unpriced_items,
    )
