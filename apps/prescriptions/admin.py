from django.contrib import admin
from django.utils import timezone

from .models import (
    Prescription,
    PrescriptionEyeValue,
    PrescriptionNotificationEvent,
)
from .notifications import (
    queue_prescription_review_notifications,
)


class PrescriptionEyeValueInline(admin.StackedInline):
    model = PrescriptionEyeValue
    extra = 0
    max_num = 2

    fields = (
        "eye",
        "sphere",
        "cylinder",
        "axis",
        "add_power",
        "distance_pd_mm",
        "near_pd_mm",
        "prism_diopters",
        "prism_base",
    )


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_filter = (
        "status",
        "created_at",
        "reviewed_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__phone_number",
        "customer_notes",
        "customer_review_message",
                    "admin_notes",
    )
    autocomplete_fields = ("user",)
    readonly_fields = (
        "reviewed_by",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    inlines = (PrescriptionEyeValueInline,)

    fieldsets = (
        (
            "Customer prescription",
            {
                "fields": (
                    "user",
                    "prescription_file",
                    "customer_notes",
                )
            },
        ),
        (
            "Review",
            {
                "fields": (
                    "status",
                    "admin_notes",
                    "reviewed_by",
                    "reviewed_at",
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

    def save_model(self, request, obj, form, change):
        previous_status = None

        if change and obj.pk:
            previous_status = (
                Prescription.objects
                .only("status")
                .get(pk=obj.pk)
                .status
            )

        status_changed = previous_status != obj.status

        reviewed_statuses = {
            Prescription.Status.APPROVED,
            Prescription.Status.CLARIFICATION_REQUIRED,
            Prescription.Status.REJECTED,
        }

        if status_changed and obj.status in reviewed_statuses:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()

        elif status_changed and obj.status in {
            Prescription.Status.PENDING,
            Prescription.Status.UNDER_REVIEW,
        }:
            obj.reviewed_by = None
            obj.reviewed_at = None

        super().save_model(request, obj, form, change)

        if status_changed:
            queue_prescription_review_notifications(
                prescription=obj,
                previous_status=previous_status,
            )


@admin.register(PrescriptionNotificationEvent)
class PrescriptionNotificationEventAdmin(admin.ModelAdmin):
    list_display = (
        "prescription",
        "event_type",
        "channel",
        "recipient",
        "status",
        "attempt_count",
        "sent_at",
        "created_at",
    )
    list_filter = (
        "event_type",
        "channel",
        "status",
        "created_at",
    )
    search_fields = (
        "prescription__id",
        "recipient",
        "deduplication_key",
    )
    readonly_fields = (
        "prescription",
        "recipient_user",
        "event_type",
        "channel",
        "recipient",
        "deduplication_key",
        "status",
        "payload",
        "attempt_count",
        "last_error",
        "sent_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
