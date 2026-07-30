from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.locations.models import Address, ServiceablePincode
from apps.retail_cart.models import (
    CustomerOwnedFrameService,
    RetailCart,
    RetailCartItem,
)
from apps.retail_cart.services import (
    RetailCartError,
    refresh_retail_cart,
)

from .models import (
    RetailCheckoutPolicy,
    RetailFulfillmentGroup,
    RetailOrder,
    RetailOrderAddressSnapshot,
    RetailOrderItem,
    RetailOrderNotificationEvent,
    RetailPaymentAttempt,
    RetailStockReservation,
    StoreLocation,
)


MONEY_PLACES = Decimal("0.01")


class RetailCheckoutError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details=None,
    ):
        self.code = code
        self.details = details
        super().__init__(message)


@dataclass(frozen=True)
class CheckoutCreationResult:
    order: RetailOrder
    payment_attempt: RetailPaymentAttempt
    reservation_expires_at: object | None


def _money(value) -> Decimal:
    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def _active_policy() -> RetailCheckoutPolicy:
    policy = (
        RetailCheckoutPolicy.objects
        .select_for_update()
        .filter(is_active=True)
        .first()
    )

    if policy is None:
        raise RetailCheckoutError(
            "checkout_policy_missing",
            "An active retail checkout policy is required.",
        )

    return policy


def _default_store() -> StoreLocation:
    store = (
        StoreLocation.objects
        .select_for_update()
        .filter(
            is_active=True,
            is_default_pickup=True,
        )
        .first()
    )

    if store is None:
        raise RetailCheckoutError(
            "default_store_missing",
            "An active default store must be configured.",
        )

    return store


def _owned_active_address(
    *,
    user,
    address,
    default_field: str,
    required_message: str,
) -> Address:
    queryset = (
        Address.objects
        .select_for_update()
        .filter(
            user=user,
            is_active=True,
        )
    )

    if address is not None:
        resolved = queryset.filter(pk=address.pk).first()
    else:
        resolved = queryset.filter(
            **{default_field: True}
        ).first()

    if resolved is None:
        raise RetailCheckoutError(
            "address_required",
            required_message,
        )

    return resolved


def _resolve_addresses(
    *,
    user,
    fulfillment_method,
    shipping_address,
    billing_address,
    billing_same_as_shipping,
):
    if (
        fulfillment_method
        == RetailOrder.FulfillmentMethod.DELIVERY
    ):
        shipping = _owned_active_address(
            user=user,
            address=shipping_address,
            default_field="is_default_delivery",
            required_message=(
                "An active delivery address is required."
            ),
        )

        serviceable = ServiceablePincode.objects.filter(
            postal_code=shipping.postal_code,
            status=ServiceablePincode.Status.ACTIVE,
        ).exists()

        if not serviceable:
            raise RetailCheckoutError(
                "delivery_not_serviceable",
                "Delivery is not currently available for this PIN code.",
            )

        if billing_same_as_shipping:
            billing = shipping
        else:
            billing = _owned_active_address(
                user=user,
                address=billing_address,
                default_field="is_default_billing",
                required_message=(
                    "An active billing address is required."
                ),
            )

        return shipping, billing, billing_same_as_shipping

    billing = _owned_active_address(
        user=user,
        address=billing_address,
        default_field="is_default_billing",
        required_message=(
            "A billing address is required for store pickup."
        ),
    )

    return None, billing, False


def _policy_snapshot(policy):
    return {
        "policy_id": policy.pk,
        "name": policy.name,
        "delivery_fee_including_gst": str(
            policy.delivery_fee_including_gst
        ),
        "free_delivery_threshold_including_gst": str(
            policy.free_delivery_threshold_including_gst
        ),
        "payment_reservation_minutes": (
            policy.payment_reservation_minutes
        ),
        "cancellation_window_hours": (
            policy.cancellation_window_hours
        ),
        "pay_at_store_enabled": policy.pay_at_store_enabled,
        "currency": policy.currency,
    }


def _create_address_snapshot(
    *,
    order,
    address,
    address_type,
):
    return RetailOrderAddressSnapshot.objects.create(
        order=order,
        address_type=address_type,
        source_address_id=address.pk,
        recipient_name=address.recipient_name,
        phone_number=address.phone_number,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        locality="",
        landmark=address.landmark,
        city=address.city,
        district=address.district,
        state=address.get_state_display(),
        postal_code=address.postal_code,
        country="India",
    )


def _variant_description(variant) -> str:
    values = []

    if variant.colour_id:
        values.append(f"Colour: {variant.colour.name}")

    if variant.size_label:
        values.append(f"Size: {variant.size_label}")

    return "; ".join(values)


def _product_snapshot(cart_item):
    if cart_item.offer_id is None:
        return {
            "service_type": "customer_owned_frame",
        }

    offer = cart_item.offer
    variant = offer.variant
    design = variant.design

    return {
        "offer_id": offer.pk,
        "sku": offer.sku,
        "offer_type": offer.offer_type,
        "offer_type_label": offer.get_offer_type_display(),
        "product_variant_id": variant.pk,
        "physical_sku": variant.physical_sku,
        "product_name": design.name,
        "supplier_model_number": (
            design.supplier_model_number or None
        ),
        "colour": (
            {
                "id": variant.colour_id,
                "name": variant.colour.name,
            }
            if variant.colour_id
            else None
        ),
        "size": variant.size_label or None,
        "mrp_including_gst": str(
            offer.mrp_including_gst
        ),
        "selling_price_including_gst": str(
            offer.selling_price_including_gst
        ),
        "gst_rate": str(offer.gst_rate),
    }


def _lens_snapshot(lens):
    return {
        "lens_id": lens.pk,
        "offer_id": lens.offer_id,
        "sku": lens.offer.sku,
        "name": lens.offer.variant.design.name,
        "vision_type": {
            "code": lens.vision_type.code,
            "name": lens.vision_type.name,
        },
        "refractive_index": str(
            lens.refractive_index.value
        ),
        "selling_unit": lens.selling_unit,
        "gst_rate": str(lens.offer.gst_rate),
    }


def _coating_snapshot(configuration):
    return [
        {
            "id": coating.pk,
            "code": coating.code,
            "name": coating.name,
        }
        for coating in configuration.selected_coatings.all()
    ]


def _configuration_snapshot(cart_item):
    if (
        cart_item.item_type
        == RetailCartItem.ItemType.STANDARD
    ):
        return {}

    if (
        cart_item.item_type
        == RetailCartItem.ItemType.POWERED_EYEWEAR
    ):
        configuration = cart_item.powered_configuration

        return {
            "prescription_id": configuration.prescription_id,
            "prescription_status": (
                configuration.prescription.status
            ),
            "lens": _lens_snapshot(configuration.lens),
            "selected_coatings": _coating_snapshot(
                configuration
            ),
            "lens_quote_breakdown": (
                configuration.lens_quote_breakdown
            ),
            "lens_quote_total_including_gst": str(
                configuration
                .lens_quote_total_including_gst
            ),
            "configured_unit_price_including_gst": str(
                configuration
                .configured_unit_price_including_gst
            ),
        }

    service = cart_item.owned_frame_service

    return {
        "prescription_id": service.prescription_id,
        "prescription_status": service.prescription.status,
        "completion_choice": service.completion_choice,
        "completion_choice_label": (
            service.get_completion_choice_display()
        ),
        "frame_handling": service.frame_handling,
        "frame_handling_label": (
            service.get_frame_handling_display()
        ),
        "customer_notes": service.customer_notes,
        "lens": _lens_snapshot(service.lens),
        "selected_coatings": _coating_snapshot(service),
        "lens_quote_breakdown": (
            service.lens_quote_breakdown
        ),
        "lens_quote_total_including_gst": str(
            service.lens_quote_total_including_gst
        ),
        "configured_unit_price_including_gst": str(
            service.configured_unit_price_including_gst
        ),
    }


def _load_cart_items(cart):
    return list(
        RetailCartItem.objects
        .select_for_update(of=("self",))
        .filter(cart=cart)
        .select_related(
            "offer",
            "offer__variant",
            "offer__variant__colour",
            "offer__variant__design",
            "powered_configuration",
            "powered_configuration__prescription",
            "powered_configuration__lens",
            "powered_configuration__lens__offer",
            "powered_configuration__lens__offer__variant",
            "powered_configuration__lens__offer__variant__design",
            "powered_configuration__lens__vision_type",
            "powered_configuration__lens__refractive_index",
            "owned_frame_service",
            "owned_frame_service__prescription",
            "owned_frame_service__lens",
            "owned_frame_service__lens__offer",
            "owned_frame_service__lens__offer__variant",
            "owned_frame_service__lens__offer__variant__design",
            "owned_frame_service__lens__vision_type",
            "owned_frame_service__lens__refractive_index",
        )
        .prefetch_related(
            "powered_configuration__selected_coatings",
            "owned_frame_service__selected_coatings",
        )
        .order_by("created_at", "pk")
    )


def _needs_operational_store(
    *,
    cart_items,
    fulfillment_method,
) -> bool:
    if (
        fulfillment_method
        == RetailOrder.FulfillmentMethod.STORE_PICKUP
    ):
        return True

    for item in cart_items:
        if (
            item.item_type
            != RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
        ):
            continue

        service = item.owned_frame_service

        if (
            service.completion_choice
            == CustomerOwnedFrameService
            .CompletionChoice.FIT_AND_RETURN
        ):
            return True

    return False


def _create_fulfillment_groups(
    *,
    order,
    cart_items,
    operational_store,
):
    if (
        order.fulfillment_method
        == RetailOrder.FulfillmentMethod.DELIVERY
    ):
        main_group = RetailFulfillmentGroup.objects.create(
            order=order,
            group_type=(
                RetailFulfillmentGroup
                .GroupType.MAIN_DELIVERY
            ),
            title="Main order delivery",
        )
    else:
        main_group = RetailFulfillmentGroup.objects.create(
            order=order,
            group_type=(
                RetailFulfillmentGroup
                .GroupType.MAIN_PICKUP
            ),
            title="Main store pickup",
            store_location=operational_store,
        )

    custom_items = [
        item
        for item in cart_items
        if item.item_type
        in {
            RetailCartItem.ItemType.POWERED_EYEWEAR,
            RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME,
        }
    ]

    production_group = None

    if custom_items:
        production_group = (
            RetailFulfillmentGroup.objects.create(
                order=order,
                group_type=(
                    RetailFulfillmentGroup
                    .GroupType.POWERED_PRODUCTION
                ),
                title="Prescription-lens production",
                metadata={
                    "final_fulfillment_group_id": (
                        main_group.pk
                    ),
                },
            )
        )

    owned_frame_groups = {}

    for item in cart_items:
        if (
            item.item_type
            != RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
        ):
            continue

        service = item.owned_frame_service

        if (
            service.completion_choice
            != CustomerOwnedFrameService
            .CompletionChoice.FIT_AND_RETURN
        ):
            continue

        inbound = RetailFulfillmentGroup.objects.create(
            order=order,
            group_type=(
                RetailFulfillmentGroup
                .GroupType.CUSTOMER_FRAME_INBOUND
            ),
            title="Customer frame inbound",
            store_location=operational_store,
            metadata={
                "source_cart_item_id": item.pk,
                "frame_handling": service.frame_handling,
            },
        )
        return_group = (
            RetailFulfillmentGroup.objects.create(
                order=order,
                group_type=(
                    RetailFulfillmentGroup
                    .GroupType.CUSTOMER_FRAME_RETURN
                ),
                title="Completed eyewear return",
                store_location=operational_store,
                metadata={
                    "source_cart_item_id": item.pk,
                    "final_fulfillment_group_id": (
                        main_group.pk
                    ),
                },
            )
        )

        owned_frame_groups[item.pk] = (
            inbound,
            return_group,
        )

    return {
        "main": main_group,
        "production": production_group,
        "owned_frame": owned_frame_groups,
    }


def _fulfillment_group_for_item(
    *,
    cart_item,
    groups,
):
    if (
        cart_item.item_type
        == RetailCartItem.ItemType.STANDARD
    ):
        return groups["main"]

    if (
        cart_item.item_type
        == RetailCartItem.ItemType.POWERED_EYEWEAR
    ):
        return groups["production"]

    service = cart_item.owned_frame_service

    if (
        service.completion_choice
        == CustomerOwnedFrameService
        .CompletionChoice.FIT_AND_RETURN
    ):
        return groups["owned_frame"][cart_item.pk][0]

    return groups["production"]


def _create_order_item(
    *,
    order,
    cart_item,
    groups,
):
    offer = cart_item.offer
    variant = offer.variant if offer else None
    prescription = None
    lens = None

    if (
        cart_item.item_type
        == RetailCartItem.ItemType.POWERED_EYEWEAR
    ):
        configuration = cart_item.powered_configuration
        prescription = configuration.prescription
        lens = configuration.lens
        product_name = offer.variant.design.name
        sku = offer.sku
        gst_rate = offer.gst_rate

    elif (
        cart_item.item_type
        == RetailCartItem.ItemType.CUSTOMER_OWNED_FRAME
    ):
        service = cart_item.owned_frame_service
        prescription = service.prescription
        lens = service.lens
        product_name = "Customer-owned frame lens service"
        sku = lens.offer.sku
        gst_rate = lens.offer.gst_rate

    else:
        product_name = offer.variant.design.name
        sku = offer.sku
        gst_rate = offer.gst_rate

    order_item = RetailOrderItem.objects.create(
        order=order,
        fulfillment_group=_fulfillment_group_for_item(
            cart_item=cart_item,
            groups=groups,
        ),
        source_cart_item_id=cart_item.pk,
        item_type=cart_item.item_type,
        offer=offer,
        product_variant=variant,
        prescription=prescription,
        lens=lens,
        sku=sku,
        product_name=product_name,
        variant_description=(
            _variant_description(variant)
            if variant is not None
            else ""
        ),
        quantity=cart_item.quantity,
        unit_price_including_gst=(
            cart_item.current_unit_price_including_gst
        ),
        gst_rate=gst_rate,
        product_snapshot=_product_snapshot(cart_item),
        configuration_snapshot=(
            _configuration_snapshot(cart_item)
        ),
    )

    owned_groups = groups["owned_frame"].get(
        cart_item.pk
    )

    if owned_groups is not None:
        inbound, return_group = owned_groups

        inbound.metadata = {
            **inbound.metadata,
            "order_item_id": order_item.pk,
        }
        inbound.save(
            update_fields=["metadata", "updated_at"]
        )

        return_group.metadata = {
            **return_group.metadata,
            "order_item_id": order_item.pk,
        }
        return_group.save(
            update_fields=["metadata", "updated_at"]
        )

    return order_item


def _allocate_stock(
    *,
    order,
    order_items,
    payment_method,
    reservation_minutes,
):
    quantity_items = [
        item
        for item in order_items
        if (
            item.product_variant_id is not None
            and item.product_variant.stock_mode
            == ProductVariant.StockMode.QUANTITY
        )
    ]

    if not quantity_items:
        return None

    variant_ids = sorted(
        {
            item.product_variant_id
            for item in quantity_items
        }
    )

    variants = {
        variant.pk: variant
        for variant in (
            ProductVariant.objects
            .select_for_update()
            .filter(pk__in=variant_ids)
            .order_by("pk")
        )
    }

    now = timezone.now()

    (
        RetailStockReservation.objects
        .filter(
            product_variant_id__in=variant_ids,
            status=RetailStockReservation.Status.ACTIVE,
            expires_at__lte=now,
        )
        .update(
            status=RetailStockReservation.Status.EXPIRED,
            released_at=now,
            updated_at=now,
        )
    )

    active_reserved = {
        row["product_variant_id"]: (
            row["reserved_quantity"] or 0
        )
        for row in (
            RetailStockReservation.objects
            .filter(
                product_variant_id__in=variant_ids,
                status=(
                    RetailStockReservation.Status.ACTIVE
                ),
            )
            .values("product_variant_id")
            .annotate(
                reserved_quantity=Sum("quantity")
            )
        )
    }

    required = defaultdict(int)

    for item in quantity_items:
        required[item.product_variant_id] += item.quantity

    for variant_id, requested_quantity in required.items():
        variant = variants[variant_id]
        reserved_quantity = active_reserved.get(
            variant_id,
            0,
        )
        available_quantity = (
            variant.stock_quantity - reserved_quantity
        )

        if requested_quantity > available_quantity:
            raise RetailCheckoutError(
                "insufficient_stock",
                (
                    "One or more products no longer have "
                    "enough available stock."
                ),
                details={
                    "product_variant_id": variant_id,
                    "requested_quantity": requested_quantity,
                },
            )

    if (
        payment_method
        == RetailOrder.PaymentMethod.RAZORPAY
    ):
        expires_at = now + timedelta(
            minutes=reservation_minutes
        )

        for item in quantity_items:
            RetailStockReservation.objects.create(
                order=order,
                order_item=item,
                product_variant=variants[
                    item.product_variant_id
                ],
                quantity=item.quantity,
                reason=(
                    RetailStockReservation
                    .Reason.ONLINE_PAYMENT
                ),
                status=(
                    RetailStockReservation.Status.ACTIVE
                ),
                expires_at=expires_at,
            )

        return expires_at

    for variant_id, requested_quantity in required.items():
        variant = variants[variant_id]
        variant.stock_quantity -= requested_quantity
        variant.save(
            update_fields=[
                "stock_quantity",
                "updated_at",
            ]
        )

    for item in quantity_items:
        RetailStockReservation.objects.create(
            order=order,
            order_item=item,
            product_variant=variants[
                item.product_variant_id
            ],
            quantity=item.quantity,
            reason=RetailStockReservation.Reason.PAY_AT_STORE,
            status=RetailStockReservation.Status.CONSUMED,
            consumed_at=now,
        )

    return None


@transaction.atomic
def create_retail_checkout(
    *,
    cart,
    fulfillment_method,
    payment_method,
    shipping_address=None,
    billing_address=None,
    billing_same_as_shipping=True,
    customer_notes="",
) -> CheckoutCreationResult:
    cart = (
        RetailCart.objects
        .select_for_update()
        .select_related("user")
        .get(pk=cart.pk)
    )

    if cart.status != RetailCart.Status.OPEN:
        raise RetailCheckoutError(
            "cart_not_open",
            "The retail cart is not open.",
        )

    if not cart.user.is_active:
        raise RetailCheckoutError(
            "inactive_customer",
            "An active customer account is required.",
        )

    if (
        fulfillment_method
        not in RetailOrder.FulfillmentMethod.values
    ):
        raise RetailCheckoutError(
            "invalid_fulfillment_method",
            "Select delivery or store pickup.",
        )

    if payment_method not in RetailOrder.PaymentMethod.values:
        raise RetailCheckoutError(
            "invalid_payment_method",
            "Select a supported payment method.",
        )

    policy = _active_policy()

    if (
        payment_method
        == RetailOrder.PaymentMethod.PAY_AT_STORE
    ):
        if not policy.pay_at_store_enabled:
            raise RetailCheckoutError(
                "pay_at_store_disabled",
                "Pay at store is currently unavailable.",
            )

        if (
            fulfillment_method
            != RetailOrder.FulfillmentMethod.STORE_PICKUP
        ):
            raise RetailCheckoutError(
                "pay_at_store_requires_pickup",
                "Pay at store is only available for store pickup.",
            )

    try:
        validation = refresh_retail_cart(cart=cart)
    except RetailCartError as exc:
        raise RetailCheckoutError(
            exc.code,
            str(exc),
        ) from exc

    if not validation.checkout_ready:
        raise RetailCheckoutError(
            "cart_not_ready",
            "The cart is not ready for checkout.",
            details={
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "item_id": issue.item_id,
                        "blocking": issue.blocking,
                    }
                    for issue in validation.issues
                ]
            },
        )

    cart_items = _load_cart_items(cart)

    if not cart_items:
        raise RetailCheckoutError(
            "empty_cart",
            "The cart does not contain any purchasable items.",
        )

    shipping, billing, billing_same = _resolve_addresses(
        user=cart.user,
        fulfillment_method=fulfillment_method,
        shipping_address=shipping_address,
        billing_address=billing_address,
        billing_same_as_shipping=billing_same_as_shipping,
    )

    operational_store = None

    if _needs_operational_store(
        cart_items=cart_items,
        fulfillment_method=fulfillment_method,
    ):
        operational_store = _default_store()

    subtotal = _money(
        validation.subtotal_including_gst
    )

    if subtotal <= Decimal("0.00"):
        raise RetailCheckoutError(
            "invalid_order_total",
            "The order total must be greater than zero.",
        )

    delivery_fee = Decimal("0.00")

    if (
        fulfillment_method
        == RetailOrder.FulfillmentMethod.DELIVERY
    ):
        delivery_fee = policy.delivery_fee_for(
            subtotal
        )

    grand_total = _money(subtotal + delivery_fee)
    now = timezone.now()

    is_online = (
        payment_method
        == RetailOrder.PaymentMethod.RAZORPAY
    )

    order = RetailOrder.objects.create(
        user=cart.user,
        source_cart=cart,
        status=(
            RetailOrder.Status.AWAITING_PAYMENT
            if is_online
            else RetailOrder.Status.CONFIRMED
        ),
        payment_method=payment_method,
        payment_status=(
            RetailOrder.PaymentStatus.PENDING
            if is_online
            else RetailOrder.PaymentStatus.UNPAID
        ),
        fulfillment_method=fulfillment_method,
        store_location=(
            operational_store
            if fulfillment_method
            == RetailOrder.FulfillmentMethod.STORE_PICKUP
            else None
        ),
        billing_same_as_shipping=billing_same,
        subtotal_including_gst=subtotal,
        delivery_fee_including_gst=delivery_fee,
        grand_total_including_gst=grand_total,
        checkout_policy_snapshot=(
            _policy_snapshot(policy)
        ),
        customer_notes=customer_notes,
        cancellable_until=(
            now
            + timedelta(
                hours=policy.cancellation_window_hours
            )
        ),
    )

    if shipping is not None:
        _create_address_snapshot(
            order=order,
            address=shipping,
            address_type=(
                RetailOrderAddressSnapshot
                .AddressType.SHIPPING
            ),
        )

    _create_address_snapshot(
        order=order,
        address=billing,
        address_type=(
            RetailOrderAddressSnapshot.AddressType.BILLING
        ),
    )

    groups = _create_fulfillment_groups(
        order=order,
        cart_items=cart_items,
        operational_store=operational_store,
    )

    order_items = [
        _create_order_item(
            order=order,
            cart_item=cart_item,
            groups=groups,
        )
        for cart_item in cart_items
    ]

    reservation_expires_at = _allocate_stock(
        order=order,
        order_items=order_items,
        payment_method=payment_method,
        reservation_minutes=(
            policy.payment_reservation_minutes
        ),
    )

    payment_attempt = RetailPaymentAttempt.objects.create(
        order=order,
        payment_method=payment_method,
        status=(
            RetailPaymentAttempt.Status.CREATED
            if is_online
            else RetailPaymentAttempt.Status.PENDING
        ),
        amount_including_gst=grand_total,
        allowed_payment_methods=(
            [
                "upi",
                "debit_card",
                "netbanking",
                "wallet",
            ]
            if is_online
            else []
        ),
        expires_at=reservation_expires_at,
    )

    cart.status = (
        RetailCart.Status.CHECKOUT_STARTED
        if is_online
        else RetailCart.Status.CONVERTED
    )
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return CheckoutCreationResult(
        order=order,
        payment_attempt=payment_attempt,
        reservation_expires_at=reservation_expires_at,
    )


def _queue_order_notification(
    *,
    order,
    event_type,
    payload=None,
):
    """
    Create idempotent email/SMS events for verified destinations.

    Actual message delivery will be implemented in the notification stage.
    """
    payload = {
        "order_number": order.order_number,
        "order_status": order.status,
        "payment_status": order.payment_status,
        **(payload or {}),
    }

    user = order.user
    events = []

    if user.email and getattr(user, "email_verified", False):
        event, _ = (
            RetailOrderNotificationEvent.objects
            .get_or_create(
                order=order,
                event_type=event_type,
                channel=(
                    RetailOrderNotificationEvent
                    .Channel.EMAIL
                ),
                defaults={
                    "recipient": user.email,
                    "payload": payload,
                },
            )
        )
        events.append(event)

    if (
        user.phone_number
        and getattr(user, "phone_verified", False)
    ):
        event, _ = (
            RetailOrderNotificationEvent.objects
            .get_or_create(
                order=order,
                event_type=event_type,
                channel=(
                    RetailOrderNotificationEvent
                    .Channel.SMS
                ),
                defaults={
                    "recipient": user.phone_number,
                    "payload": payload,
                },
            )
        )
        events.append(event)

    return tuple(events)


def _locked_order_for_attempt(payment_attempt):
    attempt = (
        RetailPaymentAttempt.objects
        .select_for_update()
        .select_related(
            "order",
            "order__user",
            "order__source_cart",
        )
        .get(pk=payment_attempt.pk)
    )

    order = (
        RetailOrder.objects
        .select_for_update()
        .select_related(
            "user",
            "source_cart",
        )
        .get(pk=attempt.order_id)
    )

    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=order.source_cart_id)
    )

    return attempt, order, cart


def _lock_order_reservations(
    *,
    order,
    statuses,
):
    return list(
        RetailStockReservation.objects
        .select_for_update()
        .filter(
            order=order,
            status__in=statuses,
        )
        .select_related(
            "product_variant",
            "order_item",
        )
        .order_by(
            "product_variant_id",
            "pk",
        )
    )


def _lock_reservation_variants(reservations):
    variant_ids = sorted(
        {
            reservation.product_variant_id
            for reservation in reservations
        }
    )

    return {
        variant.pk: variant
        for variant in (
            ProductVariant.objects
            .select_for_update()
            .filter(pk__in=variant_ids)
            .order_by("pk")
        )
    }


def _consume_active_reservations(
    *,
    order,
    now,
):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            RetailStockReservation.Status.ACTIVE,
        ],
    )

    expired = [
        reservation
        for reservation in reservations
        if (
            reservation.expires_at is not None
            and now >= reservation.expires_at
        )
    ]

    if expired:
        raise RetailCheckoutError(
            "payment_reservation_expired",
            "The payment reservation has expired.",
        )

    variants = _lock_reservation_variants(
        reservations
    )
    required_by_variant = defaultdict(int)

    for reservation in reservations:
        required_by_variant[
            reservation.product_variant_id
        ] += reservation.quantity

    for variant_id, required_quantity in (
        required_by_variant.items()
    ):
        variant = variants[variant_id]

        if variant.stock_quantity < required_quantity:
            raise RetailCheckoutError(
                "reserved_stock_unavailable",
                (
                    "Reserved stock is no longer available. "
                    "Manual order review is required."
                ),
                details={
                    "product_variant_id": variant_id,
                    "required_quantity": required_quantity,
                },
            )

    for variant_id, required_quantity in (
        required_by_variant.items()
    ):
        variant = variants[variant_id]
        variant.stock_quantity -= required_quantity
        variant.save(
            update_fields=[
                "stock_quantity",
                "updated_at",
            ]
        )

    for reservation in reservations:
        reservation.status = (
            RetailStockReservation.Status.CONSUMED
        )
        reservation.consumed_at = now
        reservation.save(
            update_fields=[
                "status",
                "consumed_at",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _release_active_reservations(
    *,
    order,
    now,
    expired=False,
):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            RetailStockReservation.Status.ACTIVE,
        ],
    )

    final_status = (
        RetailStockReservation.Status.EXPIRED
        if expired
        else RetailStockReservation.Status.RELEASED
    )

    for reservation in reservations:
        reservation.status = final_status
        reservation.released_at = now
        reservation.save(
            update_fields=[
                "status",
                "released_at",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _restore_consumed_stock(
    *,
    order,
    now,
):
    reservations = _lock_order_reservations(
        order=order,
        statuses=[
            RetailStockReservation.Status.CONSUMED,
        ],
    )

    variants = _lock_reservation_variants(
        reservations
    )
    restore_by_variant = defaultdict(int)

    for reservation in reservations:
        restore_by_variant[
            reservation.product_variant_id
        ] += reservation.quantity

    for variant_id, restore_quantity in (
        restore_by_variant.items()
    ):
        variant = variants[variant_id]
        variant.stock_quantity += restore_quantity
        variant.save(
            update_fields=[
                "stock_quantity",
                "updated_at",
            ]
        )

    for reservation in reservations:
        reservation.status = (
            RetailStockReservation.Status.RELEASED
        )
        reservation.released_at = now
        reservation.save(
            update_fields=[
                "status",
                "released_at",
                "updated_at",
            ]
        )

    return tuple(reservations)


def _reopen_checkout_cart(
    *,
    cart,
):
    if cart.status == RetailCart.Status.OPEN:
        return cart

    if cart.status != RetailCart.Status.CHECKOUT_STARTED:
        raise RetailCheckoutError(
            "cart_cannot_be_reopened",
            "The source cart cannot be reopened.",
        )

    another_open_cart_exists = (
        RetailCart.objects
        .select_for_update()
        .filter(
            user_id=cart.user_id,
            status=RetailCart.Status.OPEN,
        )
        .exclude(pk=cart.pk)
        .exists()
    )

    if another_open_cart_exists:
        raise RetailCheckoutError(
            "duplicate_open_cart",
            "Another open retail cart already exists.",
        )

    cart.status = RetailCart.Status.OPEN
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return cart


def _convert_checkout_cart(
    *,
    cart,
):
    if cart.status == RetailCart.Status.CONVERTED:
        return cart

    if cart.status != RetailCart.Status.CHECKOUT_STARTED:
        raise RetailCheckoutError(
            "cart_conversion_invalid",
            "The source cart is not awaiting payment.",
        )

    cart.status = RetailCart.Status.CONVERTED
    cart.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return cart


def _cancel_open_payment_attempts(
    *,
    order,
    now,
):
    attempts = list(
        RetailPaymentAttempt.objects
        .select_for_update()
        .filter(
            order=order,
            status__in=[
                RetailPaymentAttempt.Status.CREATED,
                RetailPaymentAttempt.Status.PENDING,
                RetailPaymentAttempt.Status.AUTHORIZED,
            ],
        )
    )

    for attempt in attempts:
        attempt.status = (
            RetailPaymentAttempt.Status.CANCELLED
        )
        attempt.failed_at = now
        attempt.save(
            update_fields=[
                "status",
                "failed_at",
                "updated_at",
            ]
        )

    return tuple(attempts)


@transaction.atomic
def confirm_online_payment(
    *,
    payment_attempt,
    provider_payment_id,
    provider_signature,
    signature_verified,
    response_payload=None,
):
    """
    Confirm a verified Razorpay payment and permanently consume stock.

    Signature verification itself will be performed by the Razorpay
    integration layer before this service is called.
    """
    attempt, order, cart = _locked_order_for_attempt(
        payment_attempt
    )
    now = timezone.now()

    if (
        attempt.payment_method
        != RetailOrder.PaymentMethod.RAZORPAY
    ):
        raise RetailCheckoutError(
            "invalid_payment_method",
            "This payment attempt is not an online payment.",
        )

    if attempt.status == RetailPaymentAttempt.Status.CAPTURED:
        if attempt.provider_payment_id == provider_payment_id:
            return order

        raise RetailCheckoutError(
            "payment_already_captured",
            "This payment attempt was already captured.",
        )

    if attempt.status not in {
        RetailPaymentAttempt.Status.CREATED,
        RetailPaymentAttempt.Status.PENDING,
        RetailPaymentAttempt.Status.AUTHORIZED,
    }:
        raise RetailCheckoutError(
            "payment_attempt_not_payable",
            "This payment attempt cannot be captured.",
        )

    if (
        attempt.expires_at is not None
        and now >= attempt.expires_at
    ):
        raise RetailCheckoutError(
            "payment_attempt_expired",
            "The payment attempt has expired.",
        )

    if not signature_verified:
        raise RetailCheckoutError(
            "payment_signature_invalid",
            "The payment signature could not be verified.",
        )

    _consume_active_reservations(
        order=order,
        now=now,
    )

    attempt.status = RetailPaymentAttempt.Status.CAPTURED
    attempt.provider_payment_id = provider_payment_id
    attempt.provider_signature = provider_signature
    attempt.signature_verified = True
    attempt.response_payload = response_payload or {}
    attempt.paid_at = now
    attempt.save(
        update_fields=[
            "status",
            "provider_payment_id",
            "provider_signature",
            "signature_verified",
            "response_payload",
            "paid_at",
            "updated_at",
        ]
    )

    order.status = RetailOrder.Status.CONFIRMED
    order.payment_status = RetailOrder.PaymentStatus.PAID
    order.payment_confirmed_at = now
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "payment_confirmed_at",
            "updated_at",
        ]
    )

    _convert_checkout_cart(cart=cart)

    _queue_order_notification(
        order=order,
        event_type=(
            RetailOrderNotificationEvent
            .EventType.PAYMENT_CONFIRMED
        ),
    )

    return order


@transaction.atomic
def fail_online_payment(
    *,
    payment_attempt,
    response_payload=None,
):
    """
    Mark an online payment as failed, release stock, and reopen the cart.
    """
    attempt, order, cart = _locked_order_for_attempt(
        payment_attempt
    )
    now = timezone.now()

    if attempt.status == RetailPaymentAttempt.Status.FAILED:
        return order

    if attempt.status in {
        RetailPaymentAttempt.Status.CAPTURED,
        RetailPaymentAttempt.Status.REFUNDED,
    }:
        raise RetailCheckoutError(
            "captured_payment_cannot_fail",
            "A captured payment cannot be marked as failed.",
        )

    _release_active_reservations(
        order=order,
        now=now,
    )

    attempt.status = RetailPaymentAttempt.Status.FAILED
    attempt.response_payload = response_payload or {}
    attempt.failed_at = now
    attempt.save(
        update_fields=[
            "status",
            "response_payload",
            "failed_at",
            "updated_at",
        ]
    )

    order.status = RetailOrder.Status.PAYMENT_FAILED
    order.payment_status = RetailOrder.PaymentStatus.FAILED
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "updated_at",
        ]
    )

    _reopen_checkout_cart(cart=cart)

    return order


@transaction.atomic
def expire_online_payment_attempt(
    *,
    payment_attempt,
):
    """
    Expire an unpaid payment attempt and reopen its source cart.
    """
    attempt, order, cart = _locked_order_for_attempt(
        payment_attempt
    )
    now = timezone.now()

    if attempt.status == RetailPaymentAttempt.Status.EXPIRED:
        return order

    if attempt.status in {
        RetailPaymentAttempt.Status.CAPTURED,
        RetailPaymentAttempt.Status.REFUNDED,
    }:
        raise RetailCheckoutError(
            "captured_payment_cannot_expire",
            "A captured payment cannot be expired.",
        )

    if (
        attempt.expires_at is not None
        and now < attempt.expires_at
    ):
        raise RetailCheckoutError(
            "payment_not_expired",
            "This payment attempt has not expired.",
        )

    _release_active_reservations(
        order=order,
        now=now,
        expired=True,
    )

    attempt.status = RetailPaymentAttempt.Status.EXPIRED
    attempt.failed_at = now
    attempt.save(
        update_fields=[
            "status",
            "failed_at",
            "updated_at",
        ]
    )

    order.status = RetailOrder.Status.PAYMENT_FAILED
    order.payment_status = RetailOrder.PaymentStatus.FAILED
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "updated_at",
        ]
    )

    _reopen_checkout_cart(cart=cart)

    return order


def expire_due_online_payment_attempts():
    """
    Expire all currently overdue online attempts.

    A scheduled management command will call this service later.
    """
    attempt_ids = list(
        RetailPaymentAttempt.objects
        .filter(
            payment_method=RetailOrder.PaymentMethod.RAZORPAY,
            status__in=[
                RetailPaymentAttempt.Status.CREATED,
                RetailPaymentAttempt.Status.PENDING,
                RetailPaymentAttempt.Status.AUTHORIZED,
            ],
            expires_at__lte=timezone.now(),
        )
        .values_list("pk", flat=True)
    )

    expired_count = 0

    for attempt_id in attempt_ids:
        attempt = RetailPaymentAttempt.objects.get(
            pk=attempt_id
        )

        try:
            expire_online_payment_attempt(
                payment_attempt=attempt
            )
        except RetailCheckoutError:
            continue

        expired_count += 1

    return expired_count


@transaction.atomic
def cancel_retail_order(
    *,
    order,
    cancelled_by,
    reason,
):
    """
    Cancel an entire eligible order and restore committed inventory.
    """
    order = (
        RetailOrder.objects
        .select_for_update()
        .select_related(
            "user",
            "source_cart",
        )
        .get(pk=order.pk)
    )
    cart = (
        RetailCart.objects
        .select_for_update()
        .get(pk=order.source_cart_id)
    )
    now = timezone.now()

    block_reason = order.cancellation_block_reason

    if block_reason is not None:
        raise RetailCheckoutError(
            block_reason,
            "This order can no longer be cancelled.",
        )

    _release_active_reservations(
        order=order,
        now=now,
    )
    _restore_consumed_stock(
        order=order,
        now=now,
    )

    if order.payment_status == RetailOrder.PaymentStatus.PAID:
        order.payment_status = (
            RetailOrder.PaymentStatus.REFUND_PENDING
        )
    elif (
        order.payment_method
        == RetailOrder.PaymentMethod.RAZORPAY
    ):
        order.payment_status = (
            RetailOrder.PaymentStatus.FAILED
        )

    if order.payment_status != RetailOrder.PaymentStatus.PAID:
        _cancel_open_payment_attempts(
            order=order,
            now=now,
        )

    order.status = RetailOrder.Status.CANCELLED
    order.cancelled_at = now
    order.cancelled_by = cancelled_by
    order.cancellation_reason = reason
    order.save(
        update_fields=[
            "status",
            "payment_status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "updated_at",
        ]
    )

    if cart.status == RetailCart.Status.CHECKOUT_STARTED:
        _reopen_checkout_cart(cart=cart)

    _queue_order_notification(
        order=order,
        event_type=(
            RetailOrderNotificationEvent
            .EventType.CANCELLED
        ),
    )

    return order


@transaction.atomic
def mark_retail_order_refunded(
    *,
    order,
    refund_payload=None,
):
    order = (
        RetailOrder.objects
        .select_for_update()
        .select_related("user")
        .get(pk=order.pk)
    )

    if order.payment_status == RetailOrder.PaymentStatus.REFUNDED:
        return order

    if (
        order.status != RetailOrder.Status.CANCELLED
        or order.payment_status
        != RetailOrder.PaymentStatus.REFUND_PENDING
    ):
        raise RetailCheckoutError(
            "refund_not_pending",
            "This order is not awaiting a refund.",
        )

    attempt = (
        RetailPaymentAttempt.objects
        .select_for_update()
        .filter(
            order=order,
            status=RetailPaymentAttempt.Status.CAPTURED,
        )
        .order_by("-created_at")
        .first()
    )

    if attempt is None:
        raise RetailCheckoutError(
            "captured_payment_missing",
            "No captured payment exists for this order.",
        )

    attempt.status = RetailPaymentAttempt.Status.REFUNDED
    attempt.response_payload = {
        **attempt.response_payload,
        "refund": refund_payload or {},
    }
    attempt.save(
        update_fields=[
            "status",
            "response_payload",
            "updated_at",
        ]
    )

    order.payment_status = RetailOrder.PaymentStatus.REFUNDED
    order.save(
        update_fields=[
            "payment_status",
            "updated_at",
        ]
    )

    _queue_order_notification(
        order=order,
        event_type=(
            RetailOrderNotificationEvent
            .EventType.REFUNDED
        ),
    )

    return order
