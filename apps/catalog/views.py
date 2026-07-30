import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    CatalogueFilterForm,
    ProductStockAlertRequestForm,
)
from .models import (
    Brand,
    Category,
    Colour,
    FrameShape,
    FrameType,
    Material,
    ProductImage,
    ProductOffer,
    ProductStockAlert,
)
from .querysets import public_product_offers


def _money(value):
    if value is None:
        return None

    return str(value)


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True,
    )


def _error_response(
    *,
    code,
    message,
    status,
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


def _public_status(offer):
    return getattr(
        offer,
        "public_status",
        offer.effective_status,
    )


def _price_visible(offer):
    return (
        _public_status(offer)
        in {
            ProductOffer.Status.AVAILABLE,
            ProductOffer.Status.SOLD_OUT,
        }
        and offer.mrp_including_gst is not None
        and offer.selling_price_including_gst is not None
    )


def _selected_images(offer):
    images = getattr(
        offer.variant,
        "catalog_images",
        (),
    )

    offer_images = [
        image
        for image in images
        if image.offer_id == offer.pk
    ]
    general_images = [
        image
        for image in images
        if image.offer_id is None
    ]

    selected = offer_images or general_images

    return sorted(
        selected,
        key=lambda image: (
            not image.is_primary,
            image.display_order,
            image.pk,
        ),
    )


def _serialize_image(request, image):
    return {
        "id": image.pk,
        "url": request.build_absolute_uri(
            reverse(
                "catalog:product_image",
                kwargs={"image_id": image.pk},
            )
        ),
        "alt_text": image.alt_text,
        "is_primary": image.is_primary,
        "display_order": image.display_order,
    }


def _serialize_offer_summary(request, offer):
    design = offer.variant.design
    status = _public_status(offer)
    price_visible = _price_visible(offer)
    images = _selected_images(offer)

    return {
        "sku": offer.sku,
        "name": design.name,
        "supplier_model_number": (
            design.supplier_model_number or None
        ),
        "brand": (
            design.brand.name
            if design.brand_id
            else None
        ),
        "offer_type": offer.offer_type,
        "offer_type_label": offer.get_offer_type_display(),
        "colour": {
            "id": offer.variant.colour_id,
            "name": offer.variant.colour.name,
            "hex_value": (
                offer.variant.colour.hex_value or None
            ),
        },
        "size": offer.variant.size_label or None,
        "gender": design.gender,
        "gender_label": design.get_gender_display(),
        "status": status,
        "status_label": ProductOffer.Status(status).label,
        "price_visible": price_visible,
        "mrp_including_gst": (
            _money(offer.mrp_including_gst)
            if price_visible
            else None
        ),
        "selling_price_including_gst": (
            _money(offer.selling_price_including_gst)
            if price_visible
            else None
        ),
        "gst_rate": (
            _money(offer.gst_rate)
            if price_visible
            else None
        ),
        "requires_prescription": offer.requires_prescription,
        "supports_powered_lenses": (
            offer.supports_powered_lenses
        ),
        "primary_image": (
            _serialize_image(request, images[0])
            if images
            else None
        ),
        "detail_url": request.build_absolute_uri(
            reverse(
                "catalog:product_detail",
                kwargs={"sku": offer.sku},
            )
        ),
    }


def _serialize_offer_detail(request, offer):
    summary = _serialize_offer_summary(
        request,
        offer,
    )
    design = offer.variant.design

    sibling_offers = (
        public_product_offers()
        .filter(variant_id=offer.variant_id)
        .exclude(pk=offer.pk)
        .order_by("offer_type")
    )

    summary.update(
        {
            "description": design.description,
            "categories": [
                {
                    "id": category.pk,
                    "name": category.name,
                    "slug": category.slug,
                }
                for category in design.categories.all()
            ],
            "attributes": {
                "material": (
                    {
                        "id": design.material_id,
                        "name": design.material.name,
                    }
                    if design.material_id
                    else None
                ),
                "frame_shape": (
                    {
                        "id": design.frame_shape_id,
                        "name": design.frame_shape.name,
                    }
                    if design.frame_shape_id
                    else None
                ),
                "frame_type": (
                    {
                        "id": design.frame_type_id,
                        "name": design.frame_type.name,
                    }
                    if design.frame_type_id
                    else None
                ),
            },
            "measurements_mm": {
                "lens_width": _money(
                    offer.variant.lens_width_mm
                ),
                "lens_height": _money(
                    offer.variant.lens_height_mm
                ),
                "frame_width": _money(
                    offer.variant.frame_width_mm
                ),
            },
            "physical_sku": offer.variant.physical_sku,
            "supplier_variant_code": (
                offer.variant.supplier_variant_code or None
            ),
            "images": [
                _serialize_image(request, image)
                for image in _selected_images(offer)
            ],
            "purchase_options": {
                "direct_purchase_allowed": (
                    not offer.requires_prescription
                ),
                "requires_prescription": (
                    offer.requires_prescription
                ),
                "supports_powered_lenses": (
                    offer.supports_powered_lenses
                ),
                "compatible_lens_endpoint": (
                    request.build_absolute_uri(
                        reverse("lenses:compatible")
                    )
                    if offer.supports_powered_lenses
                    else None
                ),
            },
            "other_offers_for_variant": [
                _serialize_offer_summary(
                    request,
                    sibling,
                )
                for sibling in sibling_offers
            ],
        }
    )

    return summary


def _serialize_alert(alert):
    return {
        "id": alert.pk,
        "sku": alert.offer.sku,
        "channel": alert.channel,
        "channel_label": alert.get_channel_display(),
        "destination": alert.destination,
        "status": alert.status,
        "created_at": alert.created_at.isoformat(),
    }


@require_GET
def catalogue_filters(request):
    return JsonResponse(
        {
            "ok": True,
            "filters": {
                "categories": list(
                    Category.objects
                    .filter(
                        is_active=True,
                        slug__isnull=False,
                    )
                    .order_by("name")
                    .values("id", "name", "slug")
                ),
                "brands": list(
                    Brand.objects
                    .filter(is_active=True)
                    .order_by("name")
                    .values("id", "name")
                ),
                "colours": list(
                    Colour.objects
                    .filter(is_active=True)
                    .order_by("name")
                    .values(
                        "id",
                        "name",
                        "hex_value",
                    )
                ),
                "materials": list(
                    Material.objects
                    .filter(is_active=True)
                    .order_by("name")
                    .values("id", "name")
                ),
                "frame_shapes": list(
                    FrameShape.objects
                    .filter(is_active=True)
                    .order_by("name")
                    .values("id", "name")
                ),
                "frame_types": list(
                    FrameType.objects
                    .filter(is_active=True)
                    .order_by("name")
                    .values("id", "name")
                ),
                "genders": [
                    {
                        "value": value,
                        "label": label,
                    }
                    for value, label in (
                        ("men", "Men"),
                        ("women", "Women"),
                        ("unisex", "Unisex"),
                        ("kids", "Kids"),
                    )
                ],
                "offer_types": [
                    {
                        "value": value,
                        "label": label,
                    }
                    for value, label
                    in ProductOffer.OfferType.choices
                ],
            },
        }
    )


@require_GET
def product_list(request):
    form = CatalogueFilterForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_filters",
            message="Correct the catalogue filters and try again.",
            status=400,
            fields=_form_errors(form),
        )

    data = form.cleaned_data
    queryset = public_product_offers()

    if data.get("q"):
        search = data["q"].strip()

        queryset = queryset.filter(
            Q(variant__design__name__icontains=search)
            | Q(
                variant__design__supplier_model_number__icontains=(
                    search
                )
            )
            | Q(variant__design__brand__name__icontains=search)
            | Q(sku__icontains=search)
        )

    if data.get("category"):
        queryset = queryset.filter(
            variant__design__categories=data["category"]
        )

    if data.get("brand"):
        queryset = queryset.filter(
            variant__design__brand=data["brand"]
        )

    if data.get("gender"):
        queryset = queryset.filter(
            variant__design__gender=data["gender"]
        )

    if data.get("frame_shape"):
        queryset = queryset.filter(
            variant__design__frame_shape=data["frame_shape"]
        )

    if data.get("frame_type"):
        queryset = queryset.filter(
            variant__design__frame_type=data["frame_type"]
        )

    if data.get("material"):
        queryset = queryset.filter(
            variant__design__material=data["material"]
        )

    if data.get("colour"):
        queryset = queryset.filter(
            variant__colour=data["colour"]
        )

    if data.get("size"):
        queryset = queryset.filter(
            variant__size_label__iexact=data["size"].strip()
        )

    if data.get("offer_type"):
        queryset = queryset.filter(
            offer_type=data["offer_type"]
        )

    if data.get("availability"):
        queryset = queryset.filter(
            public_status=data["availability"]
        )

    price_statuses = [
        ProductOffer.Status.AVAILABLE,
        ProductOffer.Status.SOLD_OUT,
    ]

    if data.get("minimum_price") is not None:
        queryset = queryset.filter(
            public_status__in=price_statuses,
            selling_price_including_gst__gte=(
                data["minimum_price"]
            ),
        )

    if data.get("maximum_price") is not None:
        queryset = queryset.filter(
            public_status__in=price_statuses,
            selling_price_including_gst__lte=(
                data["maximum_price"]
            ),
        )

    ordering = data.get("ordering") or "newest"

    if ordering == "name":
        queryset = queryset.order_by(
            "variant__design__name",
            "sku",
        )
    elif ordering == "price_asc":
        queryset = queryset.order_by(
            F("selling_price_including_gst").asc(
                nulls_last=True
            ),
            "sku",
        )
    elif ordering == "price_desc":
        queryset = queryset.order_by(
            F("selling_price_including_gst").desc(
                nulls_last=True
            ),
            "sku",
        )
    else:
        queryset = queryset.order_by(
            "-created_at",
            "-pk",
        )

    queryset = queryset.distinct()

    page_number = data.get("page") or 1
    page_size = data.get("page_size") or 24
    paginator = Paginator(queryset, page_size)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        return _error_response(
            code="page_not_found",
            message="The requested catalogue page does not exist.",
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "products": [
                _serialize_offer_summary(
                    request,
                    offer,
                )
                for offer in page.object_list
            ],
        }
    )


@require_GET
def product_detail(request, sku):
    offer = get_object_or_404(
        public_product_offers(),
        sku=sku,
    )

    return JsonResponse(
        {
            "ok": True,
            "product": _serialize_offer_detail(
                request,
                offer,
            ),
        }
    )


@require_GET
def product_image(request, image_id):
    image = get_object_or_404(
        ProductImage.objects.select_related(
            "variant",
            "offer",
        ),
        pk=image_id,
    )

    if image.offer_id:
        image_is_public = public_product_offers().filter(
            pk=image.offer_id
        ).exists()
    else:
        image_is_public = public_product_offers().filter(
            variant_id=image.variant_id
        ).exists()

    if not image_is_public:
        raise Http404("Product image not found.")

    content_type, _ = mimetypes.guess_type(
        image.image.name
    )

    response = FileResponse(
        image.image.open("rb"),
        as_attachment=False,
        filename=Path(image.image.name).name,
        content_type=(
            content_type or "application/octet-stream"
        ),
    )

    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = (
        "public, max-age=86400"
    )

    return response


@login_required
@require_GET
def stock_alert_list(request):
    alerts = (
        ProductStockAlert.objects
        .filter(
            user=request.user,
            status=ProductStockAlert.Status.ACTIVE,
        )
        .select_related("offer")
        .order_by("-created_at")
    )

    return JsonResponse(
        {
            "ok": True,
            "alerts": [
                _serialize_alert(alert)
                for alert in alerts
            ],
        }
    )


@login_required
@require_POST
def create_stock_alert(request):
    form = ProductStockAlertRequestForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the stock-alert request.",
            status=400,
            fields=_form_errors(form),
        )

    offer = get_object_or_404(
        public_product_offers(),
        sku=form.cleaned_data["sku"],
    )
    channel = form.cleaned_data["channel"]

    existing_alert = (
        ProductStockAlert.objects
        .filter(
            user=request.user,
            offer=offer,
            channel=channel,
            status=ProductStockAlert.Status.ACTIVE,
        )
        .first()
    )

    if existing_alert is not None:
        return JsonResponse(
            {
                "ok": True,
                "created": False,
                "alert": _serialize_alert(existing_alert),
            }
        )

    try:
        with transaction.atomic():
            alert = ProductStockAlert.objects.create(
                user=request.user,
                offer=offer,
                channel=channel,
            )
    except IntegrityError:
        alert = ProductStockAlert.objects.get(
            user=request.user,
            offer=offer,
            channel=channel,
            status=ProductStockAlert.Status.ACTIVE,
        )

        return JsonResponse(
            {
                "ok": True,
                "created": False,
                "alert": _serialize_alert(alert),
            }
        )
    except ValidationError as exc:
        fields = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"__all__": exc.messages}
        )

        return _error_response(
            code="stock_alert_unavailable",
            message=(
                "A stock alert could not be created."
            ),
            status=400,
            fields=fields,
        )

    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "alert": _serialize_alert(alert),
        },
        status=201,
    )


@login_required
@require_POST
def cancel_stock_alert(request, alert_id):
    alert = get_object_or_404(
        ProductStockAlert.objects.select_related("offer"),
        pk=alert_id,
        user=request.user,
        status=ProductStockAlert.Status.ACTIVE,
    )

    alert.status = ProductStockAlert.Status.CANCELLED
    alert.cancelled_at = timezone.now()
    alert.save()

    return JsonResponse(
        {
            "ok": True,
            "alert_id": alert.pk,
            "status": alert.status,
        }
    )
