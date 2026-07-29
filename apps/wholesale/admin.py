from django.contrib import admin
from django.utils import timezone

from .models import (
    WholesaleAccount,
    WholesaleVerificationContact,
)


@admin.register(WholesaleAccount)
class WholesaleAccountAdmin(admin.ModelAdmin):
    list_display = (
        "reference_id",
        "phone_number",
        "business_name",
        "status",
        "approved_at",
        "created_at",
    )
    list_filter = ("status", "created_at", "approved_at")
    search_fields = (
        "reference_id",
        "user__phone_number",
        "business_name",
        "contact_person_name",
        "gstin",
    )
    readonly_fields = (
        "reference_id",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    )
    list_select_related = ("user", "approved_by")

    fieldsets = (
        (
            "Wholesale identity",
            {
                "fields": (
                    "user",
                    "reference_id",
                    "status",
                )
            },
        ),
        (
            "Business details",
            {
                "fields": (
                    "business_name",
                    "contact_person_name",
                    "gstin",
                    "invoice_email",
                )
            },
        ),
        (
            "Administrative review",
            {
                "fields": (
                    "internal_notes",
                    "approved_by",
                    "approved_at",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(
        description="Phone number",
        ordering="user__phone_number",
    )
    def phone_number(self, obj):
        return obj.user.phone_number

    def has_add_permission(self, request):
        # Wholesale accounts will be created by the phone-login workflow.
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        # Preserve wholesale records unless the site owner deliberately
        # deletes one.
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        return (
            request.user.has_perm(
                "wholesale.change_wholesaleaccount"
            )
            and request.user.has_perm(
                "wholesale.review_wholesale_account"
            )
        )

    def save_model(self, request, obj, form, change):
        previous_status = None

        if change and obj.pk:
            previous_status = (
                WholesaleAccount.objects
                .only("status")
                .get(pk=obj.pk)
                .status
            )

        changed_to_approved = (
            obj.status == WholesaleAccount.Status.APPROVED
            and previous_status != WholesaleAccount.Status.APPROVED
        )

        if changed_to_approved:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()

        super().save_model(request, obj, form, change)


@admin.register(WholesaleVerificationContact)
class WholesaleVerificationContactAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "phone_number",
        "is_active",
        "display_order",
        "updated_at",
    )
    list_editable = (
        "is_active",
        "display_order",
    )
    list_filter = ("is_active",)
    search_fields = (
        "label",
        "phone_number",
    )
    ordering = (
        "display_order",
        "created_at",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
