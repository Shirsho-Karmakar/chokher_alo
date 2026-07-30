from django.contrib import admin

from .models import (
    CustomerOwnedFrameService,
    PoweredEyewearConfiguration,
    RetailCart,
    RetailCartItem,
)


class RetailCartItemInline(admin.TabularInline):
    model = RetailCartItem
    extra = 0
    can_delete = False

    fields = (
        "item_type",
        "offer",
        "quantity",
        "current_unit_price_including_gst",
        "current_total_including_gst",
        "is_non_refundable",
        "updated_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RetailCart)
class RetailCartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "display_item_count",
        "last_validated_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "created_at",
        "last_validated_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__phone_number",
    )
    autocomplete_fields = ("user",)
    readonly_fields = (
        "currency",
        "last_validated_at",
        "created_at",
        "updated_at",
    )
    inlines = (RetailCartItemInline,)

    @admin.display(description="Items")
    def display_item_count(self, obj):
        return obj.items.count()

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailCartItem)
class RetailCartItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cart",
        "item_type",
        "offer",
        "quantity",
        "current_total_including_gst",
        "is_non_refundable",
        "updated_at",
    )
    list_filter = (
        "item_type",
        "is_non_refundable",
        "created_at",
    )
    search_fields = (
        "offer__sku",
        "offer__variant__design__name",
        "cart__user__username",
        "cart__user__email",
        "cart__user__phone_number",
    )
    autocomplete_fields = (
        "cart",
        "offer",
    )
    readonly_fields = (
        "item_type",
        "offer",
        "quantity",
        "current_unit_price_including_gst",
        "current_total_including_gst",
        "price_refreshed_at",
        "is_non_refundable",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(PoweredEyewearConfiguration)
class PoweredEyewearConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "cart_item",
        "prescription",
        "lens",
        "configured_unit_price_including_gst",
        "quote_refreshed_at",
    )
    search_fields = (
        "cart_item__offer__sku",
        "cart_item__cart__user__username",
        "prescription__id",
        "lens__offer__sku",
    )
    autocomplete_fields = (
        "cart_item",
        "prescription",
        "lens",
    )
    filter_horizontal = ("selected_coatings",)
    readonly_fields = (
        "lens_quote_breakdown",
        "lens_quote_total_including_gst",
        "configured_unit_price_including_gst",
        "quote_refreshed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(CustomerOwnedFrameService)
class CustomerOwnedFrameServiceAdmin(admin.ModelAdmin):
    list_display = (
        "cart_item",
        "prescription",
        "completion_choice",
        "frame_handling",
        "lens",
        "configured_unit_price_including_gst",
    )
    list_filter = (
        "completion_choice",
        "frame_handling",
    )
    search_fields = (
        "cart_item__cart__user__username",
        "prescription__id",
        "lens__offer__sku",
        "customer_notes",
    )
    autocomplete_fields = (
        "cart_item",
        "prescription",
        "lens",
    )
    filter_horizontal = ("selected_coatings",)
    readonly_fields = (
        "lens_quote_breakdown",
        "lens_quote_total_including_gst",
        "configured_unit_price_including_gst",
        "quote_refreshed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
