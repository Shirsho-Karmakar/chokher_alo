from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.prescriptions.models import Prescription
from apps.wholesale.permissions import approved_wholesale_required
from apps.wholesale_catalog.models import WholesaleLensVariant

from .models import WholesaleCartItem
from .services import (
    WholesaleCartError,
    get_or_create_open_wholesale_cart,
    revalidate_wholesale_cart,
    remove_wholesale_cart_item,
    set_wholesale_cart_item,
)


def _money(value):
    return str(value) if value is not None else None


def _error(exc, status=409):
    payload = {"code": exc.code, "message": str(exc)}
    if getattr(exc, "details", None):
        payload["details"] = exc.details
    return JsonResponse({"ok": False, "error": payload}, status=status)


def _serialize_item(item):
    variant = item.variant
    listing = variant.listing
    return {
        "id": item.pk,
        "variant_id": variant.pk,
        "sku": variant.sku,
        "name": listing.name,
        "prescription_id": item.prescription_id,
        "eye": item.eye,
        "eye_label": item.get_eye_display(),
        "power_label": variant.prescription_rule.name,
        "units_per_box": listing.units_per_box,
        "boxes": item.boxes,
        "minimum_order_boxes": variant.minimum_order_boxes,
        "order_multiple_boxes": variant.order_multiple_boxes,
        "base_box_price_including_gst": _money(item.base_box_price_including_gst),
        "applied_box_price_including_gst": _money(item.applied_box_price_including_gst),
        "discount_per_box_including_gst": _money(item.discount_per_box_including_gst),
        "subtotal_including_gst": _money(item.subtotal_including_gst),
        "validation_status": item.validation_status,
        "validation_code": item.validation_code or None,
        "validation_message": item.validation_message or None,
        "variant_snapshot": item.variant_snapshot,
        "prescription_snapshot": item.prescription_snapshot,
        "pricing_snapshot": item.pricing_snapshot,
    }


def _load_items(cart):
    return (
        cart.items.select_related(
            "variant",
            "variant__listing",
            "prescription",
        ).order_by("created_at", "pk")
    )


def _serialize_cart(cart, readiness=None):
    if readiness is None:
        readiness = revalidate_wholesale_cart(cart=cart)
    return {
        "id": cart.pk,
        "status": cart.status,
        "status_label": cart.get_status_display(),
        "items": [_serialize_item(item) for item in _load_items(cart)],
        "readiness": readiness.as_dict(),
    }


@approved_wholesale_required
@require_GET
def current_cart(request):
    try:
        cart = get_or_create_open_wholesale_cart(user=request.user)
        readiness = revalidate_wholesale_cart(cart=cart)
    except WholesaleCartError as exc:
        return _error(exc)
    return JsonResponse({"ok": True, "cart": _serialize_cart(cart, readiness)})


@approved_wholesale_required
@require_POST
def set_item(request):
    try:
        variant_id = int(request.POST.get("variant_id", ""))
        prescription_id = int(request.POST.get("prescription_id", ""))
        boxes = int(request.POST.get("boxes", ""))
    except (TypeError, ValueError):
        return JsonResponse({
            "ok": False,
            "error": {"code": "invalid_request", "message": "Variant, prescription, and box quantity are required."},
        }, status=400)

    eye = request.POST.get("eye", "")
    variant = get_object_or_404(WholesaleLensVariant, pk=variant_id)
    prescription = get_object_or_404(Prescription, pk=prescription_id, user=request.user)

    try:
        cart = get_or_create_open_wholesale_cart(user=request.user)
        item = set_wholesale_cart_item(
            cart=cart,
            variant=variant,
            prescription=prescription,
            eye=eye,
            boxes=boxes,
        )
        cart = item.cart
        readiness = revalidate_wholesale_cart(cart=cart)
    except WholesaleCartError as exc:
        return _error(exc)

    return JsonResponse({"ok": True, "item": _serialize_item(item), "cart": _serialize_cart(cart, readiness)})


@approved_wholesale_required
@require_POST
def remove_item(request, item_id):
    try:
        cart = get_or_create_open_wholesale_cart(user=request.user)
    except WholesaleCartError as exc:
        return _error(exc)

    item = get_object_or_404(WholesaleCartItem, pk=item_id, cart=cart)
    try:
        readiness = remove_wholesale_cart_item(item=item)
    except WholesaleCartError as exc:
        return _error(exc)

    cart.refresh_from_db()
    return JsonResponse({"ok": True, "cart": _serialize_cart(cart, readiness)})


# Stock-box cart endpoint: wholesale users select exact power variants directly.
@approved_wholesale_required
@require_POST
def set_item(request):
    try:
        variant_id = int(request.POST.get("variant_id", ""))
        boxes = int(request.POST.get("boxes", ""))
    except (TypeError, ValueError):
        return JsonResponse({
            "ok": False,
            "error": {"code": "invalid_request", "message": "Variant and box quantity are required."},
        }, status=400)

    variant = get_object_or_404(WholesaleLensVariant, pk=variant_id)
    try:
        cart = get_or_create_open_wholesale_cart(user=request.user)
        item = set_wholesale_cart_item(
            cart=cart,
            variant=variant,
            prescription=None,
            eye="",
            boxes=boxes,
        )
        cart = item.cart
        readiness = revalidate_wholesale_cart(cart=cart)
    except WholesaleCartError as exc:
        return _error(exc)

    return JsonResponse({"ok": True, "item": _serialize_item(item), "cart": _serialize_cart(cart, readiness)})
