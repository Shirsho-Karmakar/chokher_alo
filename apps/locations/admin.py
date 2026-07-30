from django.contrib import admin

from .models import Address, ServiceablePincode


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_name",
        "user",
        "city",
        "state",
        "postal_code",
        "is_default_delivery",
        "is_default_billing",
        "is_active",
    )
    list_filter = (
        "state",
        "is_default_delivery",
        "is_default_billing",
        "is_active",
    )
    search_fields = (
        "recipient_name",
        "phone_number",
        "address_line_1",
        "city",
        "district",
        "postal_code",
        "user__username",
        "user__email",
        "user__phone_number",
    )
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(ServiceablePincode)
class ServiceablePincodeAdmin(admin.ModelAdmin):
    list_display = (
        "postal_code",
        "city",
        "district",
        "state",
        "status",
        "updated_at",
    )
    list_display_links = ("postal_code",)
    list_editable = ("status",)
    list_filter = (
        "status",
        "state",
    )
    search_fields = (
        "postal_code",
        "city",
        "district",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
