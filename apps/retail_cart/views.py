from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import ProductOffer
from apps.catalog.querysets import public_product_offers
from apps.lenses.models import LensSpecification
from apps.prescriptions.models import Prescription

from .forms import (
    AddCustomerOwnedFrameServiceForm,
    AddPoweredEyewearForm,
    AddStandardItemForm,
    LensConfigurationForm,
    UpdateCartItemQuantityForm,
)
from .models import (
    CustomerOwnedFrameService,
    PoweredEyewearConfiguration,
    RetailCart,
    RetailCartItem,
)
from .services import (
    RetailCartError,
    add_customer_owned_frame_service,
    add_powered_eyewear,
    add_standard_offer,
    configure_customer_owned_frame_service,
    configure_powered_eyewear,
    get_or_create_open_retail_cart,
    refresh_retail_cart,
    remove_retail_cart_item,
    update_standard_item_quantity,
)


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return str(value)


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True,
    )


def _error_response(
    *,
    code: str,
    message: str,
    status: int,
    **extra,
):
    error = {
        "code": code,
        "message": message,
    }
    error.update(extra)

    return JsonResponse(
        {
            "ok": False,
            "error": error,
        },
        status=status,
    )


def _validation_error_response(exc):
    fields = (
        exc.message_dict
        if hasattr(exc, "message_dict")
        else {"__all__": exc.messages}
    )

    return _error_response(
        code="invalid_cart_configuration",
        message="Correct the cart configuration and try again.",
        status=400,
        fields=fields,
    )


def _cart_error_response(exc):
    conflict_codes = {
        "cart_not_open",
        "offer_unavailable",
        "insufficient_stock",
        "price_unavailable",
        "lens_unavailable",
        "prescription_not_approved",
        "lens_quote_unavailable",
    }

    status = 409 if exc.code in conflict_codes else 400

    return _error_response(
        code=exc.code,
        message=str(exc),
        status=status,
    )


def _prescription_summary(prescription):
    return {
        "id": prescription.pk,
        "status": prescription.status,
        "status_label": prescription.get_status_display(),
        "is_approved": prescription.is_approved,
    }


def _lens_summary(lens):
    if lens is None:
        return None

    return {
        "id": lens.pk,
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
        "selling_unit_label": (
            lens.get_selling_unit_display()
        ),
    }


def _coating_summaries(configuration):
    return [
        {
            "id": coating.pk,
            "code": coating.code,
            "name": coating.name,
        }
        for coating in configuration.selected_coatings.all()
    ]


def _configuration_state(configuration):
    if configuration.prescription.status in {
        Prescription.Status.PENDING,
        Prescription.Status.UNDER_REVIEW,
    }:
        return "prescription_pending"

    if not configuration.prescription.is_approved:
        return "prescription_not_approved"

    if configuration.lens_id is None:
        return "lens_selection_required"

    if not configuration.is_configured:
        return "configuration_incomplete"

    return "configured"


def _serialize_powered_configuration(configuration):
    return {
        "state": _configuration_state(configuration),
        "prescription": _prescription_summary(
            configuration.prescription
        ),
        "lens": _lens_summary(configuration.lens),
        "selected_coatings": _coating_summaries(
            configuration
        ),
        "lens_quote_breakdown": (
            configuration.lens_quote_breakdown
        ),
        "lens_quote_total_including_gst": _money(
            configuration.lens_quote_total_including_gst
        ),
        "configured_unit_price_including_gst": _money(
            configuration.configured_unit_price_including_gst
        ),
        "quote_refreshed_at": (
            configuration.quote_refreshed_at.isoformat()
            if configuration.quote_refreshed_at
            else None
        ),
    }


def _serialize_owned_frame_service(service):
    return {
        "state": _configuration_state(service),
        "prescription": _prescription_summary(
            service.prescription
        ),
        "completion_choice": service.completion_choice,
        "completion_choice_label": (
            service.get_completion_choice_display()
        ),
        "frame_handling": service.frame_handling,
        "frame_handling_label": (
            service.get_frame_handling_display()
        ),
        "customer_notes": service.customer_notes,
        "lens": _lens_summary(service.lens),
        "selected_coatings": _coating_summaries(service),
        "lens_quote_breakdown": (
            service.lens_quote_breakdown
        ),
        "lens_quote_total_including_gst": _money(
            service.lens_quote_total_including_gst
        ),
        "configured_unit_price_including_gst": _money(
            service.configured_unit_price_including_gst
        ),
        "quote_refreshed_at": (
            service.quote_refreshed_at.isoformat()
            if service.quote_refreshed_at
            else None
        ),
    }


def _serialize_offer(offer):
    if offer is None:
        return None

    design = offer.variant.design

    return {
        "sku": offer.sku,
        "name": design.name,
        "offer_type": offer.offer_type,
        "offer_type_label": offer.get_offer_type_display(),
        "colour": offer.variant.colour.name,
        "size": offer.variant.size_label or None,
        "status": offer.effective_status,
        "supports_powered_lenses": (
            offer.supports_powered_lenses
        ),
    }


def _serialize_cart_item(item):
    data = {
        "id": item.pk,
        "item_type": item.item_type,
        "item_type_label": item.get_item_type_display(),
        "offer": _serialize_offer(item.offer),
        "quantity": item.quantity,
        "quantity_editable": (
            item.item_type
            == RetailCartItem.ItemType.STANDARD
        ),
        "current_unit_price_including_gst": _money(
            item.current_unit_price_including_gst
        ),
        "current_total_including_gst": _money(
            item.current_total_including_gst
        ),
        "price_refreshed_at": (
            item.price_refreshed_at.isoformat()
            if item.price_refreshed_at
            else None
        ),
        "is_non_refundable": item.is_non_refundable,
        "powered_configuration": None,
        "customer_owned_frame_service": None,
    }

    powered_configuration = getattr(
        item,
        "powered_configuration",
        None,
    )
    owned_frame_service = getattr(
        item,
        "owned_frame_service",
        None,
    )

    if powered_configuration is not None:
        data["powered_configuration"] = (
            _serialize_powered_configuration(
                powered_configuration
            )
        )

    if owned_frame_service is not None:
        data["customer_owned_frame_service"] = (
            _serialize_owned_frame_service(
                owned_frame_service
            )
        )

    return data


def _serialize_issue(issue):
    return {
        "code": issue.code,
        "message": issue.message,
        "item_id": issue.item_id,
        "blocking": issue.blocking,
    }


def _load_cart_items(cart):
    return (
        RetailCartItem.objects
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


def _cart_response(
    *,
    cart,
    validation,
    status=200,
    mutation=None,
):
    cart.refresh_from_db()

    items = list(_load_cart_items(cart))

    payload = {
        "ok": True,
        "cart": {
            "id": cart.pk,
            "status": cart.status,
            "status_label": cart.get_status_display(),
            "currency": cart.currency,
            "last_validated_at": (
                cart.last_validated_at.isoformat()
                if cart.last_validated_at
                else None
            ),
            "items": [
                _serialize_cart_item(item)
                for item in items
            ],
            "totals": {
                "subtotal_including_gst": _money(
                    validation.subtotal_including_gst
                ),
            },
            "validation": {
                "checkout_ready": (
                    validation.checkout_ready
                ),
                "has_unpriced_items": (
                    validation.has_unpriced_items
                ),
                "issues": [
                    _serialize_issue(issue)
                    for issue in validation.issues
                ],
                "removed_item_ids": list(
                    validation.removed_item_ids
                ),
            },
        },
    }

    if mutation is not None:
        payload["mutation"] = mutation

    return JsonResponse(payload, status=status)


def _refresh_response(
    *,
    cart,
    status=200,
    mutation=None,
):
    try:
        validation = refresh_retail_cart(cart=cart)
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _cart_response(
        cart=cart,
        validation=validation,
        status=status,
        mutation=mutation,
    )


def _owned_open_item(*, user, item_id):
    return get_object_or_404(
        RetailCartItem.objects.select_related(
            "cart",
            "offer",
            "offer__variant",
            "offer__variant__design",
        ),
        pk=item_id,
        cart__user=user,
        cart__status=RetailCart.Status.OPEN,
    )


@login_required
@require_GET
def current_cart(request):
    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _refresh_response(cart=cart)


@login_required
@require_POST
def add_standard_item(request):
    form = AddStandardItemForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the cart item and try again.",
            status=400,
            fields=_form_errors(form),
        )

    offer = get_object_or_404(
        public_product_offers(),
        sku=form.cleaned_data["sku"],
    )

    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
        item = add_standard_offer(
            cart=cart,
            offer=offer,
            quantity=form.cleaned_data["quantity"],
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _refresh_response(
        cart=cart,
        status=201,
        mutation={
            "action": "standard_item_added",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def add_powered_item(request):
    form = AddPoweredEyewearForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the powered-eyewear request.",
            status=400,
            fields=_form_errors(form),
        )

    offer = get_object_or_404(
        public_product_offers(),
        sku=form.cleaned_data["sku"],
    )
    prescription = get_object_or_404(
        Prescription,
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
        item = add_powered_eyewear(
            cart=cart,
            offer=offer,
            prescription=prescription,
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _refresh_response(
        cart=cart,
        status=201,
        mutation={
            "action": "powered_item_added",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def configure_powered_item(request, item_id):
    form = LensConfigurationForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the lens configuration.",
            status=400,
            fields=_form_errors(form),
        )

    item = _owned_open_item(
        user=request.user,
        item_id=item_id,
    )
    lens = get_object_or_404(
        LensSpecification,
        pk=form.cleaned_data["lens_id"],
    )

    try:
        configure_powered_eyewear(
            item=item,
            lens=lens,
            coatings=form.cleaned_data["coating_ids"],
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)
    except ValidationError as exc:
        return _validation_error_response(exc)

    return _refresh_response(
        cart=item.cart,
        mutation={
            "action": "powered_item_configured",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def add_customer_owned_frame(request):
    form = AddCustomerOwnedFrameServiceForm(
        request.POST
    )

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the frame-service request.",
            status=400,
            fields=_form_errors(form),
        )

    prescription = get_object_or_404(
        Prescription,
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
        item = add_customer_owned_frame_service(
            cart=cart,
            prescription=prescription,
            completion_choice=(
                form.cleaned_data["completion_choice"]
            ),
            frame_handling=(
                form.cleaned_data["frame_handling"]
            ),
            customer_notes=(
                form.cleaned_data.get("customer_notes") or ""
            ),
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)
    except ValidationError as exc:
        return _validation_error_response(exc)

    return _refresh_response(
        cart=cart,
        status=201,
        mutation={
            "action": "customer_owned_frame_added",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def configure_customer_owned_frame(
    request,
    item_id,
):
    form = LensConfigurationForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the lens configuration.",
            status=400,
            fields=_form_errors(form),
        )

    item = _owned_open_item(
        user=request.user,
        item_id=item_id,
    )
    lens = get_object_or_404(
        LensSpecification,
        pk=form.cleaned_data["lens_id"],
    )

    try:
        configure_customer_owned_frame_service(
            item=item,
            lens=lens,
            coatings=form.cleaned_data["coating_ids"],
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)
    except ValidationError as exc:
        return _validation_error_response(exc)

    return _refresh_response(
        cart=item.cart,
        mutation={
            "action": "customer_owned_frame_configured",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def update_item_quantity(request, item_id):
    form = UpdateCartItemQuantityForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Enter a valid quantity from 1 to 10.",
            status=400,
            fields=_form_errors(form),
        )

    item = _owned_open_item(
        user=request.user,
        item_id=item_id,
    )

    try:
        update_standard_item_quantity(
            item=item,
            quantity=form.cleaned_data["quantity"],
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _refresh_response(
        cart=item.cart,
        mutation={
            "action": "quantity_updated",
            "item_id": item.pk,
        },
    )


@login_required
@require_POST
def remove_item(request, item_id):
    item = _owned_open_item(
        user=request.user,
        item_id=item_id,
    )
    cart = item.cart

    try:
        removed_item_id = remove_retail_cart_item(
            item=item
        )
    except RetailCartError as exc:
        return _cart_error_response(exc)

    return _refresh_response(
        cart=cart,
        mutation={
            "action": "item_removed",
            "item_id": removed_item_id,
        },
    )
