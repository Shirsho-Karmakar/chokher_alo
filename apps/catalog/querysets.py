from django.db.models import (
    Case,
    CharField,
    Prefetch,
    Value,
    When,
)

from .models import (
    ProductDesign,
    ProductImage,
    ProductOffer,
    ProductVariant,
)


def public_product_offers():
    """
    Return retail offers that may be displayed publicly.

    Exact inventory quantities remain private. The public status is annotated
    in the database so it can be filtered and paginated efficiently.
    """

    image_queryset = (
        ProductImage.objects
        .select_related("offer")
        .order_by(
            "display_order",
            "created_at",
        )
    )

    return (
        ProductOffer.objects
        .filter(
            is_active=True,
            variant__is_active=True,
            variant__design__status__in=[
                ProductDesign.Status.ACTIVE,
                ProductDesign.Status.COMING_SOON,
            ],
        )
        .exclude(
            status__in=[
                ProductOffer.Status.DRAFT,
                ProductOffer.Status.DISCONTINUED,
            ]
        )
        .annotate(
            public_status=Case(
                When(
                    status=ProductOffer.Status.COMING_SOON,
                    then=Value(ProductOffer.Status.COMING_SOON),
                ),
                When(
                    variant__design__status=(
                        ProductDesign.Status.COMING_SOON
                    ),
                    then=Value(ProductOffer.Status.COMING_SOON),
                ),
                When(
                    variant__manual_stock_status=(
                        ProductVariant.StockStatus.COMING_SOON
                    ),
                    then=Value(ProductOffer.Status.COMING_SOON),
                ),
                When(
                    status=ProductOffer.Status.SOLD_OUT,
                    then=Value(ProductOffer.Status.SOLD_OUT),
                ),
                When(
                    variant__stock_mode=(
                        ProductVariant.StockMode.QUANTITY
                    ),
                    variant__stock_quantity__lte=0,
                    then=Value(ProductOffer.Status.SOLD_OUT),
                ),
                When(
                    variant__stock_mode=(
                        ProductVariant.StockMode.STATUS_ONLY
                    ),
                    variant__manual_stock_status=(
                        ProductVariant.StockStatus.SOLD_OUT
                    ),
                    then=Value(ProductOffer.Status.SOLD_OUT),
                ),
                default=Value(ProductOffer.Status.AVAILABLE),
                output_field=CharField(max_length=20),
            )
        )
        .select_related(
            "variant",
            "variant__colour",
            "variant__design",
            "variant__design__brand",
            "variant__design__material",
            "variant__design__frame_shape",
            "variant__design__frame_type",
        )
        .prefetch_related(
            "variant__design__categories",
            Prefetch(
                "variant__images",
                queryset=image_queryset,
                to_attr="catalog_images",
            ),
        )
    )
