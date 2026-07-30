from django.contrib import admin

from .models import (
    RetailCheckoutPolicy,
    RetailFulfillmentGroup,
    RetailFulfillmentStatusHistory,
    RetailOrder,
    RetailOrderStatusHistory,
    RetailOrderAddressSnapshot,
    RetailOrderItem,
    RetailOrderNotificationEvent,
    RetailPaymentAttempt,
    RetailPaymentWebhookEvent,
    RetailStockReservation,
    StoreLocation,
)


@admin.register(StoreLocation)
class StoreLocationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "city",
        "postal_code",
        "is_default_pickup",
        "is_active",
    )
    list_filter = (
        "is_default_pickup",
        "is_active",
        "state",
        "city",
    )
    search_fields = (
        "code",
        "name",
        "phone_number",
        "city",
        "postal_code",
    )


@admin.register(RetailCheckoutPolicy)
class RetailCheckoutPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "delivery_fee_including_gst",
        "free_delivery_threshold_including_gst",
        "payment_reservation_minutes",
        "cancellation_window_hours",
        "pay_at_store_enabled",
        "is_active",
    )
    list_filter = (
        "is_active",
        "pay_at_store_enabled",
    )


class RetailOrderItemInline(admin.TabularInline):
    model = RetailOrderItem
    extra = 0
    can_delete = False
    fields = (
        "item_type",
        "sku",
        "product_name",
        "quantity",
        "unit_price_including_gst",
        "line_total_including_gst",
        "is_custom",
        "is_non_refundable",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class RetailFulfillmentGroupInline(admin.TabularInline):
    model = RetailFulfillmentGroup
    extra = 0
    can_delete = False
    fields = (
        "group_type",
        "title",
        "status",
        "store_location",
        "tracking_number",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RetailOrder)
class RetailOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status",
        "payment_method",
        "payment_status",
        "fulfillment_method",
        "grand_total_including_gst",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_method",
        "payment_status",
        "fulfillment_method",
        "created_at",
    )
    search_fields = (
        "order_number",
        "user__username",
        "user__email",
        "user__phone_number",
    )
    autocomplete_fields = ()
    readonly_fields = (
        "order_number",
        "user",
        "source_cart",
        "status",
        "payment_method",
        "payment_status",
        "fulfillment_method",
        "store_location",
        "billing_same_as_shipping",
        "subtotal_including_gst",
        "delivery_fee_including_gst",
        "grand_total_including_gst",
        "currency",
        "checkout_policy_snapshot",
        "cancellable_until",
        "payment_confirmed_at",
        "processing_started_at",
        "production_started_at",
        "ready_for_pickup_at",
        "packed_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "cancelled_by",
        "cancellation_reason",
        "customer_notes",
        "created_at",
        "updated_at",
    )
    inlines = (
        RetailOrderItemInline,
        RetailFulfillmentGroupInline,
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailOrderAddressSnapshot)
class RetailOrderAddressSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "address_type",
        "recipient_name",
        "city",
        "postal_code",
    )
    list_filter = (
        "address_type",
        "state",
        "city",
    )
    search_fields = (
        "order__order_number",
        "recipient_name",
        "phone_number",
        "postal_code",
    )
    readonly_fields = (
        "order",
        "address_type",
        "source_address_id",
        "recipient_name",
        "phone_number",
        "address_line_1",
        "address_line_2",
        "locality",
        "landmark",
        "city",
        "district",
        "state",
        "postal_code",
        "country",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailFulfillmentGroup)
class RetailFulfillmentGroupAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "group_type",
        "title",
        "status",
        "store_location",
        "tracking_number",
    )
    list_filter = (
        "group_type",
        "status",
        "store_location",
    )
    search_fields = (
        "order__order_number",
        "title",
        "tracking_number",
    )
    autocomplete_fields = ()
    readonly_fields = (
        "order",
        "group_type",
        "title",
        "status",
        "store_location",
        "carrier_name",
        "tracking_number",
        "metadata",
        "processing_started_at",
        "ready_at",
        "shipped_at",
        "completed_at",
        "created_at",
        "updated_at",
    )


@admin.register(RetailOrderItem)
class RetailOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "product_name",
        "item_type",
        "quantity",
        "line_total_including_gst",
        "is_custom",
        "is_non_refundable",
    )
    list_filter = (
        "item_type",
        "is_custom",
        "is_non_refundable",
    )
    search_fields = (
        "order__order_number",
        "sku",
        "product_name",
    )
    readonly_fields = (
        "order",
        "fulfillment_group",
        "source_cart_item_id",
        "item_type",
        "offer",
        "product_variant",
        "prescription",
        "lens",
        "sku",
        "product_name",
        "variant_description",
        "quantity",
        "unit_price_including_gst",
        "line_total_including_gst",
        "gst_rate",
        "is_custom",
        "is_non_refundable",
        "non_cancellable_after_production",
        "product_snapshot",
        "configuration_snapshot",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailStockReservation)
class RetailStockReservationAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "product_variant",
        "quantity",
        "reason",
        "status",
        "expires_at",
    )
    list_filter = (
        "reason",
        "status",
    )
    search_fields = (
        "order__order_number",
        "product_variant__physical_sku",
    )
    readonly_fields = (
        "order",
        "order_item",
        "product_variant",
        "quantity",
        "reason",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailPaymentAttempt)
class RetailPaymentAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "payment_method",
        "status",
        "amount_including_gst",
        "provider_order_id",
        "provider_payment_id",
        "signature_verified",
        "created_at",
    )
    list_filter = (
        "payment_method",
        "status",
        "signature_verified",
    )
    search_fields = (
        "order__order_number",
        "provider_order_id",
        "provider_payment_id",
        "idempotency_key",
    )
    readonly_fields = (
        "order",
        "payment_method",
        "idempotency_key",
        "amount_including_gst",
        "currency",
        "allowed_payment_methods",
        "provider_order_id",
        "provider_payment_id",
        "provider_signature",
        "request_payload",
        "response_payload",
        "expires_at",
        "paid_at",
        "failed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailOrderNotificationEvent)
class RetailOrderNotificationEventAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "event_type",
        "channel",
        "recipient",
        "status",
        "attempt_count",
        "sent_at",
    )
    list_filter = (
        "event_type",
        "channel",
        "status",
    )
    search_fields = (
        "order__order_number",
        "recipient",
    )
    readonly_fields = (
        "order",
        "event_type",
        "channel",
        "recipient",
        "payload",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailPaymentWebhookEvent)
class RetailPaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "event_type",
        "status",
        "order",
        "payment_attempt",
        "processed_at",
        "created_at",
    )
    list_filter = (
        "provider",
        "event_type",
        "status",
        "created_at",
    )
    search_fields = (
        "event_id",
        "event_type",
        "order__order_number",
        "payment_attempt__provider_order_id",
        "payment_attempt__provider_payment_id",
    )
    readonly_fields = (
        "provider",
        "event_id",
        "event_type",
        "order",
        "payment_attempt",
        "status",
        "signature",
        "payload",
        "error_message",
        "processed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailOrderStatusHistory)
class RetailOrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "previous_status",
        "new_status",
        "changed_by",
        "created_at",
    )
    list_filter = (
        "previous_status",
        "new_status",
        "created_at",
    )
    search_fields = (
        "order__order_number",
        "changed_by__username",
        "changed_by__email",
        "note",
    )
    readonly_fields = (
        "order",
        "previous_status",
        "new_status",
        "changed_by",
        "note",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(RetailFulfillmentStatusHistory)
class RetailFulfillmentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "fulfillment_group",
        "previous_status",
        "new_status",
        "changed_by",
        "created_at",
    )
    list_filter = (
        "previous_status",
        "new_status",
        "created_at",
    )
    search_fields = (
        "fulfillment_group__order__order_number",
        "fulfillment_group__title",
        "changed_by__username",
        "note",
    )
    readonly_fields = (
        "fulfillment_group",
        "previous_status",
        "new_status",
        "changed_by",
        "note",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
