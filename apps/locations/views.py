from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .constants import IndianState
from .models import Address, ServiceablePincode
from .validators import normalize_indian_pin_code


def _validation_payload(exc):
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return {"__all__": exc.messages}


def _error(code, message, *, status=400, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JsonResponse({"ok": False, "error": error}, status=status)


def _bool(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _serialize_address(address):
    return {
        "id": address.pk,
        "label": address.label,
        "recipient_name": address.recipient_name,
        "phone_number": address.phone_number,
        "address_line_1": address.address_line_1,
        "address_line_2": address.address_line_2,
        "landmark": address.landmark,
        "city": address.city,
        "district": address.district,
        "state": address.state,
        "state_label": address.get_state_display(),
        "postal_code": address.postal_code,
        "is_default_delivery": address.is_default_delivery,
        "is_default_billing": address.is_default_billing,
        "is_active": address.is_active,
        "updated_at": address.updated_at.isoformat(),
    }


def _apply_address_fields(address, post):
    fields = (
        "label",
        "recipient_name",
        "phone_number",
        "address_line_1",
        "address_line_2",
        "landmark",
        "city",
        "district",
        "state",
        "postal_code",
    )
    for field in fields:
        if field in post:
            setattr(address, field, post.get(field, ""))

    if "is_default_delivery" in post:
        address.is_default_delivery = _bool(post.get("is_default_delivery"))
    if "is_default_billing" in post:
        address.is_default_billing = _bool(post.get("is_default_billing"))


@require_GET
def serviceability(request):
    raw = request.GET.get("postal_code", "")
    try:
        postal_code = normalize_indian_pin_code(raw)
    except ValidationError as exc:
        return _error(
            "invalid_postal_code",
            "Enter a valid six-digit Indian PIN code.",
            fields={"postal_code": exc.messages},
        )

    record = ServiceablePincode.objects.filter(postal_code=postal_code).first()
    if record is None:
        return JsonResponse({
            "ok": True,
            "postal_code": postal_code,
            "serviceable": False,
            "status": "inactive",
            "status_label": "Delivery unavailable",
            "message": "We do not deliver to this PIN code yet.",
        })

    in_launch_state = record.state == IndianState.WEST_BENGAL
    serviceable = record.delivery_available and in_launch_state
    if serviceable:
        message = "Delivery is available to this PIN code in West Bengal."
    elif record.status == ServiceablePincode.Status.COMING_SOON and in_launch_state:
        message = "Delivery to this PIN code is coming soon."
    else:
        message = "We do not deliver to this PIN code yet."

    return JsonResponse({
        "ok": True,
        "postal_code": postal_code,
        "serviceable": serviceable,
        "status": record.status,
        "status_label": record.get_status_display(),
        "city": record.city or None,
        "district": record.district or None,
        "state": record.state,
        "state_label": record.get_state_display(),
        "message": message,
    })


@login_required
@require_http_methods(["GET", "POST"])
def address_list_create(request):
    if request.method == "GET":
        addresses = Address.objects.filter(user=request.user, is_active=True)
        return JsonResponse({
            "ok": True,
            "addresses": [_serialize_address(address) for address in addresses],
        })

    address = Address(user=request.user, state=IndianState.WEST_BENGAL)
    _apply_address_fields(address, request.POST)
    if not address.state:
        address.state = IndianState.WEST_BENGAL

    if address.state != IndianState.WEST_BENGAL:
        return _error(
            "launch_region_only",
            "Chokher Alo currently delivers only within West Bengal.",
            fields={"state": ["Select West Bengal."]},
        )

    try:
        address.save()
    except ValidationError as exc:
        return _error(
            "invalid_address",
            "Correct the address details.",
            fields=_validation_payload(exc),
        )

    return JsonResponse({"ok": True, "address": _serialize_address(address)}, status=201)


@login_required
@require_POST
def address_update(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user, is_active=True)
    _apply_address_fields(address, request.POST)

    if address.state != IndianState.WEST_BENGAL:
        return _error(
            "launch_region_only",
            "Chokher Alo currently delivers only within West Bengal.",
            fields={"state": ["Select West Bengal."]},
        )

    try:
        address.save()
    except ValidationError as exc:
        return _error(
            "invalid_address",
            "Correct the address details.",
            fields=_validation_payload(exc),
        )

    return JsonResponse({"ok": True, "address": _serialize_address(address)})


@login_required
@require_POST
def address_deactivate(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user, is_active=True)
    address.is_active = False
    address.is_default_delivery = False
    address.is_default_billing = False
    try:
        address.save()
    except ValidationError as exc:
        return _error("invalid_address", "The address could not be removed.", fields=_validation_payload(exc))
    return JsonResponse({"ok": True})
