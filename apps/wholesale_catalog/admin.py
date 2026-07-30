from django.contrib import admin

from .models import (
    WholesaleBulkPriceTier,
    WholesaleLensListing,
    WholesaleLensVariant,
)


@admin.register(WholesaleLensListing)
class WholesaleLensListingAdmin(admin.ModelAdmin):
    list_display = (
        "catalogue_code",
        "name",
        "lens",
        "box_contents_unit",
        "units_per_box",
        "status",
        "is_active",
    )
    list_filter = (
        "status",
        "box_contents_unit",
        "is_active",
        "lens__vision_type",
        "lens__refractive_index",
    )
    search_fields = (
        "catalogue_code",
        "name",
        "lens__offer__sku",
        "lens__offer__variant__design__name",
    )
    autocomplete_fields = ("lens",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )


class WholesaleBulkPriceTierInline(admin.TabularInline):
    model = WholesaleBulkPriceTier
    extra = 0
    fields = (
        "minimum_boxes",
        "maximum_boxes",
        "box_price_including_gst",
        "is_active",
    )


@admin.register(WholesaleLensVariant)
class WholesaleLensVariantAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "listing",
        "prescription_rule",
        "coating",
        "base_box_price_including_gst",
        "boxes_in_stock",
        "display_effective_status",
        "price_visible",
    )
    list_filter = (
        "status",
        "is_active",
        "listing",
        "coating",
    )
    search_fields = (
        "sku",
        "supplier_code",
        "listing__catalogue_code",
        "listing__name",
        "prescription_rule__name",
        "coating__code",
        "coating__name",
    )
    autocomplete_fields = (
        "listing",
        "prescription_rule",
        "coating",
    )
    readonly_fields = (
        "sku",
        "created_at",
        "updated_at",
    )
    inlines = (WholesaleBulkPriceTierInline,)

    @admin.display(description="Effective status")
    def display_effective_status(self, obj):
        return obj.effective_status

    def get_readonly_fields(self, request, obj=None):
        base_readonly = (
            "sku",
            "created_at",
            "updated_at",
        )

        if (
            request.user.is_superuser
            or request.user.has_perm(
                "wholesale_catalog."
                "change_wholesalelenslisting"
            )
        ):
            return base_readonly

        # Inventory managers may update stock and availability,
        # but not catalogue identity or wholesale pricing.
        return base_readonly + (
            "listing",
            "prescription_rule",
            "coating",
            "supplier_code",
            "base_box_price_including_gst",
            "minimum_order_boxes",
            "order_multiple_boxes",
            "public_notes",
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.has_perm(
                "wholesale_catalog."
                "add_wholesalelensvariant"
            )
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(WholesaleBulkPriceTier)
class WholesaleBulkPriceTierAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "minimum_boxes",
        "maximum_boxes",
        "box_price_including_gst",
        "is_active",
    )
    list_filter = (
        "is_active",
        "variant__listing",
    )
    search_fields = (
        "variant__sku",
        "variant__listing__catalogue_code",
        "variant__prescription_rule__name",
    )
    autocomplete_fields = ("variant",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )
