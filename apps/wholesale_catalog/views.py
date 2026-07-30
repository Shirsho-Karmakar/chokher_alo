from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.prescriptions.models import Prescription
from apps.wholesale.permissions import approved_wholesale_required

from .forms import (
    WholesaleBoxQuoteForm,
    WholesaleCatalogueQueryForm,
)
from .matching import (
    compatible_wholesale_variants_for_prescription,
    matching_eyes_for_variant,
)
from .models import WholesaleLensVariant
from .pricing import (
    WholesalePricingError,
    quote_wholesale_boxes,
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


def _serialize_prescription_rule(rule):
    return {
        "id": rule.pk,
        "name": rule.name,
        "minimum_sphere": _money(rule.minimum_sphere),
        "maximum_sphere": _money(rule.maximum_sphere),
        "minimum_cylinder": _money(rule.minimum_cylinder),
        "maximum_cylinder": _money(rule.maximum_cylinder),
        "minimum_add_power": _money(
            rule.minimum_add_power
        ),
        "maximum_add_power": _money(
            rule.maximum_add_power
        ),
        "axis_mode": rule.axis_mode,
        "axis_mode_label": rule.get_axis_mode_display(),
        "axis_tolerance_degrees": (
            rule.axis_tolerance_degrees
        ),
        "allowed_axes": [
            allowed_axis.axis
            for allowed_axis in rule.allowed_axes.all()
        ],
        "supports_prism": rule.supports_prism,
    }


def _serialize_bulk_tiers(variant):
    if not variant.price_visible:
        return []

    tiers = getattr(
        variant,
        "active_bulk_price_tiers",
        (),
    )

    return [
        {
            "id": tier.pk,
            "minimum_boxes": tier.minimum_boxes,
            "maximum_boxes": tier.maximum_boxes,
            "box_price_including_gst": _money(
                tier.box_price_including_gst
            ),
        }
        for tier in tiers
    ]


def _serialize_variant(match):
    variant = match.variant
    listing = variant.listing
    lens = listing.lens
    offer = lens.offer
    design = offer.variant.design
    effective_status = variant.effective_status

    return {
        "variant_id": variant.pk,
        "sku": variant.sku,
        "supplier_code": variant.supplier_code or None,
        "catalogue_code": listing.catalogue_code,
        "name": listing.name,
        "product_name": design.name,
        "brand": (
            design.brand.name
            if design.brand_id
            else None
        ),
        "vision_type": {
            "id": lens.vision_type_id,
            "code": lens.vision_type.code,
            "name": lens.vision_type.name,
        },
        "refractive_index": {
            "id": lens.refractive_index_id,
            "value": str(lens.refractive_index.value),
            "display_name": (
                lens.refractive_index.display_name
                or None
            ),
        },
        "coating": (
            {
                "id": variant.coating_id,
                "code": variant.coating.code,
                "name": variant.coating.name,
            }
            if variant.coating_id
            else None
        ),
        "matching_eyes": list(match.matching_eyes),
        "prescription_rule": _serialize_prescription_rule(
            variant.prescription_rule
        ),
        "box": {
            "contents_unit": listing.box_contents_unit,
            "contents_unit_label": (
                listing.get_box_contents_unit_display()
            ),
            "units_per_box": listing.units_per_box,
        },
        "minimum_order_boxes": variant.minimum_order_boxes,
        "order_multiple_boxes": variant.order_multiple_boxes,
        "status": effective_status,
        "status_label": WholesaleLensVariant.Status(
            effective_status
        ).label,
        "price_visible": variant.price_visible,
        "base_box_price_including_gst": (
            _money(
                variant.base_box_price_including_gst
            )
            if variant.price_visible
            else None
        ),
        "bulk_price_tiers": _serialize_bulk_tiers(
            variant
        ),
        "public_notes": variant.public_notes,
    }


def _serialize_quote(quote, *, eye):
    return {
        "variant_id": quote.variant_id,
        "sku": quote.sku,
        "eye": eye,
        "boxes": quote.boxes,
        "base_box_price_including_gst": _money(
            quote.base_box_price_including_gst
        ),
        "applied_box_price_including_gst": _money(
            quote.applied_box_price_including_gst
        ),
        "discount_per_box_including_gst": _money(
            quote.discount_per_box_including_gst
        ),
        "subtotal_including_gst": _money(
            quote.subtotal_including_gst
        ),
        "bulk_tier_id": quote.bulk_tier_id,
    }


@approved_wholesale_required
@require_GET
def compatible_lens_catalogue(request):
    form = WholesaleCatalogueQueryForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="A valid prescription ID is required.",
            status=400,
            fields=_form_errors(form),
        )

    prescription = get_object_or_404(
        Prescription.objects.prefetch_related(
            "eye_values"
        ),
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    if prescription.status != Prescription.Status.APPROVED:
        return _error_response(
            code="prescription_not_approved",
            message=(
                "The prescription must be approved before "
                "wholesale products can be displayed."
            ),
            status=409,
            prescription_status=prescription.status,
        )

    matches = compatible_wholesale_variants_for_prescription(
        prescription
    )

    wholesale_account = request.user.wholesale_account

    return JsonResponse(
        {
            "ok": True,
            "wholesale_account": {
                "reference_id": (
                    wholesale_account.reference_id
                ),
                "status": wholesale_account.status,
                "checkout_ready": (
                    wholesale_account.is_checkout_ready
                ),
                "missing_checkout_details": list(
                    wholesale_account
                    .missing_checkout_details()
                ),
            },
            "prescription": {
                "id": prescription.pk,
                "status": prescription.status,
                "status_label": (
                    prescription.get_status_display()
                ),
            },
            "count": len(matches),
            "variants": [
                _serialize_variant(match)
                for match in matches
            ],
        }
    )


@approved_wholesale_required
@require_POST
def box_quote(request):
    form = WholesaleBoxQuoteForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the quotation request and try again.",
            status=400,
            fields=_form_errors(form),
        )

    prescription = get_object_or_404(
        Prescription.objects.prefetch_related(
            "eye_values"
        ),
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    if prescription.status != Prescription.Status.APPROVED:
        return _error_response(
            code="prescription_not_approved",
            message="An approved prescription is required.",
            status=409,
        )

    variant = get_object_or_404(
        (
            WholesaleLensVariant.objects
            .select_related(
                "listing",
                "listing__lens",
                "listing__lens__offer",
                "prescription_rule",
                "coating",
            )
            .prefetch_related(
                "prescription_rule__allowed_axes",
                "bulk_price_tiers",
            )
        ),
        pk=form.cleaned_data["variant_id"],
    )

    matching_eyes = matching_eyes_for_variant(
        prescription=prescription,
        variant=variant,
    )
    requested_eye = form.cleaned_data["eye"]

    if requested_eye not in matching_eyes:
        return _error_response(
            code="prescription_range_mismatch",
            message=(
                "The selected wholesale row does not match "
                "the requested prescription eye."
            ),
            status=400,
        )

    try:
        quote = quote_wholesale_boxes(
            variant=variant,
            boxes=form.cleaned_data["boxes"],
            enforce_stock=True,
        )
    except WholesalePricingError as exc:
        return _error_response(
            code="wholesale_quote_unavailable",
            message=str(exc),
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "quote": _serialize_quote(
                quote,
                eye=requested_eye,
            ),
        }
    )
