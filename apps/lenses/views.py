from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import ProductDesign, ProductOffer, ProductVariant
from apps.prescriptions.models import Prescription

from .forms import CompatibleLensQueryForm, LensQuoteRequestForm
from .matching import compatible_lenses_for_prescription
from .models import LensSpecification
from .pricing import LensPricingError, quote_lens


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True,
    )


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return str(value)


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


def _serialize_lens(specification):
    offer = specification.offer
    variant = offer.variant
    design = variant.design
    effective_status = offer.effective_status

    price_visible = offer.price_visible

    return {
        "lens_id": specification.pk,
        "offer_id": offer.pk,
        "sku": offer.sku,
        "physical_sku": variant.physical_sku,
        "name": design.name,
        "supplier_model_number": (
            design.supplier_model_number or None
        ),
        "brand": (
            design.brand.name
            if design.brand_id
            else None
        ),
        "vision_type": {
            "id": specification.vision_type_id,
            "code": specification.vision_type.code,
            "name": specification.vision_type.name,
        },
        "refractive_index": {
            "id": specification.refractive_index_id,
            "value": str(specification.refractive_index.value),
            "display_name": (
                specification.refractive_index.display_name
                or None
            ),
        },
        "coatings": [
            {
                "id": coating.pk,
                "code": coating.code,
                "name": coating.name,
            }
            for coating in specification.coatings.all()
            if coating.is_active
        ],
        "selling_unit": specification.selling_unit,
        "selling_unit_label": (
            specification.get_selling_unit_display()
        ),
        "units_per_box": specification.units_per_box,
        "requires_both_eyes": specification.require_both_eyes,
        "status": effective_status,
        "status_label": ProductOffer.Status(
            effective_status
        ).label,
        "price_visible": price_visible,
        "mrp_including_gst": (
            _money(offer.mrp_including_gst)
            if price_visible
            else None
        ),
        "base_price_including_gst": (
            _money(offer.selling_price_including_gst)
            if price_visible
            else None
        ),
        "gst_rate": (
            _money(offer.gst_rate)
            if price_visible
            else None
        ),
    }


def _serialize_quote(quote):
    return {
        "lens_id": quote.lens_id,
        "offer_id": quote.offer_id,
        "prescription_id": quote.prescription_id,
        "selling_unit": quote.selling_unit,
        "gst_rate": _money(quote.gst_rate),
        "lines": [
            {
                "code": line.code,
                "name": line.name,
                "amount_including_gst": _money(
                    line.amount_including_gst
                ),
                "rule_id": line.rule_id,
            }
            for line in quote.lines
        ],
        "total_including_gst": _money(
            quote.total_including_gst
        ),
    }


@login_required
@require_GET
def compatible_lens_catalogue(request):
    form = CompatibleLensQueryForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="A valid prescription ID is required.",
            status=400,
            fields=_form_errors(form),
        )

    prescription = get_object_or_404(
        Prescription.objects.prefetch_related("eye_values"),
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    if prescription.status != Prescription.Status.APPROVED:
        return _error_response(
            code="prescription_not_approved",
            message=(
                "The prescription must be approved before "
                "compatible lenses can be displayed."
            ),
            status=409,
            prescription_status=prescription.status,
        )

    compatible_lenses = compatible_lenses_for_prescription(
        prescription
    )

    return JsonResponse(
        {
            "ok": True,
            "prescription": {
                "id": prescription.pk,
                "status": prescription.status,
                "status_label": (
                    prescription.get_status_display()
                ),
            },
            "count": len(compatible_lenses),
            "lenses": [
                _serialize_lens(specification)
                for specification in compatible_lenses
            ],
        }
    )


@login_required
@require_POST
def lens_quote(request):
    form = LensQuoteRequestForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the quotation request and try again.",
            status=400,
            fields=_form_errors(form),
        )

    prescription = get_object_or_404(
        Prescription.objects.prefetch_related("eye_values"),
        pk=form.cleaned_data["prescription_id"],
        user=request.user,
    )

    lens = get_object_or_404(
        (
            LensSpecification.objects
            .select_related(
                "offer",
                "offer__variant",
                "offer__variant__design",
                "offer__variant__design__brand",
                "vision_type",
                "refractive_index",
            )
            .prefetch_related(
                "coatings",
                "prescription_rules__allowed_axes",
                "price_rules",
            )
        ),
        pk=form.cleaned_data["lens_id"],
    )

    frame_variant = None
    frame_variant_id = form.cleaned_data.get(
        "frame_variant_id"
    )

    if frame_variant_id is not None:
        frame_variant = get_object_or_404(
            (
                ProductVariant.objects
                .select_related(
                    "design",
                    "design__frame_type",
                    "design__frame_shape",
                    "design__material",
                )
            ),
            pk=frame_variant_id,
        )

        if frame_variant.design.kind != ProductDesign.Kind.FRAME:
            return _error_response(
                code="invalid_frame_variant",
                message=(
                    "The selected product variant is not "
                    "an eyewear frame."
                ),
                status=400,
            )

        if (
            frame_variant.effective_stock_status
            != ProductVariant.StockStatus.AVAILABLE
        ):
            return _error_response(
                code="frame_unavailable",
                message=(
                    "The selected frame is not currently available."
                ),
                status=409,
            )

    try:
        quote = quote_lens(
            lens=lens,
            prescription=prescription,
            selected_coatings=form.cleaned_data[
                "coating_ids"
            ],
            frame_variant=frame_variant,
        )
    except LensPricingError as exc:
        return _error_response(
            code="quotation_unavailable",
            message=str(exc),
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "quote": _serialize_quote(quote),
        }
    )
