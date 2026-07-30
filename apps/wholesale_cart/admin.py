from django.contrib import admin

from .models import WholesaleCart, WholesaleCartItem


class WholesaleCartItemInline(admin.TabularInline):
    model = WholesaleCartItem
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "variant",
        "prescription",
        "eye",
        "boxes",
        "applied_box_price_including_gst",
        "subtotal_including_gst",
        "validation_status",
        "validation_code",
        "validated_at",
    )


@admin.register(WholesaleCart)
class WholesaleCartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wholesale_account",
        "status",
        "pricing_updated_at",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "created_at",
    )
    search_fields = (
        "wholesale_account__reference_id",
        "wholesale_account__business_name",
        "wholesale_account__user__phone_number",
    )
    readonly_fields = (
        "wholesale_account",
        "status",
        "pricing_updated_at",
        "created_at",
        "updated_at",
    )
    inlines = (WholesaleCartItemInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(WholesaleCartItem)
class WholesaleCartItemAdmin(admin.ModelAdmin):
    list_display = (
        "cart",
        "variant",
        "eye",
        "boxes",
        "applied_box_price_including_gst",
        "subtotal_including_gst",
        "validation_status",
        "updated_at",
    )
    list_filter = (
        "eye",
        "validation_status",
        "created_at",
    )
    search_fields = (
        "cart__wholesale_account__reference_id",
        "variant__sku",
        "variant__listing__catalogue_code",
    )
    readonly_fields = (
        "cart",
        "variant",
        "prescription",
        "eye",
        "boxes",
        "base_box_price_including_gst",
        "applied_box_price_including_gst",
        "discount_per_box_including_gst",
        "subtotal_including_gst",
        "bulk_price_tier_id_snapshot",
        "variant_snapshot",
        "prescription_snapshot",
        "pricing_snapshot",
        "validation_status",
        "validation_code",
        "validation_message",
        "validated_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
