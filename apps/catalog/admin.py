from django.contrib import admin

from .models import (
    Brand,
    Category,
    Colour,
    FrameShape,
    FrameType,
    Material,
    ProductDesign,
    ProductImage,
    ProductOffer,
    ProductStockAlert,
    ProductVariant,
)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "code")
    readonly_fields = ("slug",)


@admin.register(Colour)
class ColourAdmin(admin.ModelAdmin):
    list_display = ("name", "hex_value", "is_active")
    list_editable = ("hex_value", "is_active")
    search_fields = ("name",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)


@admin.register(FrameShape)
class FrameShapeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)


@admin.register(FrameType)
class FrameTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = (
        "colour",
        "size_label",
        "supplier_variant_code",
        "stock_mode",
        "stock_quantity",
        "manual_stock_status",
        "is_active",
    )


@admin.register(ProductDesign)
class ProductDesignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "supplier_model_number",
        "brand",
        "kind",
        "gender",
        "status",
        "updated_at",
    )
    list_filter = (
        "kind",
        "gender",
        "status",
        "brand",
        "material",
        "frame_shape",
        "frame_type",
    )
    search_fields = (
        "name",
        "supplier_model_number",
        "brand__name",
    )
    autocomplete_fields = (
        "brand",
        "material",
        "frame_shape",
        "frame_type",
    )
    filter_horizontal = ("categories",)
    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
    )
    inlines = (ProductVariantInline,)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "physical_sku",
        "design",
        "colour",
        "size_label",
        "stock_mode",
        "stock_quantity",
        "display_effective_stock_status",
        "is_active",
    )
    list_filter = (
        "stock_mode",
        "manual_stock_status",
        "is_active",
        "colour",
    )
    search_fields = (
        "physical_sku",
        "supplier_variant_code",
        "design__name",
        "design__supplier_model_number",
        "colour__name",
    )
    autocomplete_fields = (
        "design",
        "colour",
    )
    readonly_fields = (
        "physical_sku",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Effective stock status")
    def display_effective_stock_status(self, obj):
        return obj.effective_stock_status


@admin.register(ProductOffer)
class ProductOfferAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "variant",
        "offer_type",
        "selling_price_including_gst",
        "gst_rate",
        "display_effective_status",
        "price_visible",
        "is_active",
    )
    list_filter = (
        "offer_type",
        "status",
        "requires_prescription",
        "supports_powered_lenses",
        "is_active",
    )
    search_fields = (
        "sku",
        "variant__physical_sku",
        "variant__design__name",
        "variant__design__supplier_model_number",
    )
    autocomplete_fields = ("variant",)
    readonly_fields = (
        "sku",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Effective status")
    def display_effective_status(self, obj):
        return obj.effective_status


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "offer",
        "display_order",
        "is_primary",
        "created_at",
    )
    list_filter = (
        "is_primary",
        "created_at",
    )
    search_fields = (
        "variant__physical_sku",
        "variant__design__name",
        "offer__sku",
        "alt_text",
    )
    autocomplete_fields = (
        "variant",
        "offer",
    )
    readonly_fields = ("created_at",)


@admin.register(ProductStockAlert)
class ProductStockAlertAdmin(admin.ModelAdmin):
    list_display = (
        "offer",
        "user",
        "channel",
        "destination",
        "status",
        "created_at",
        "notified_at",
    )
    list_filter = (
        "channel",
        "status",
        "created_at",
    )
    search_fields = (
        "offer__sku",
        "offer__variant__design__name",
        "user__username",
        "user__email",
        "user__phone_number",
        "destination",
    )
    autocomplete_fields = (
        "user",
        "offer",
    )
    readonly_fields = (
        "destination",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
