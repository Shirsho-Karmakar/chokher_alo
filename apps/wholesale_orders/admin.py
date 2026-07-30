from django.contrib import admin

from .models import (
    WholesaleFulfillment,
    WholesaleInvoice,
    WholesaleOrder,
    WholesaleOrderNotificationEvent,
    WholesaleOrderAddressSnapshot,
    WholesaleOrderItem,
    WholesalePaymentAttempt,
    WholesalePaymentWebhookEvent,
    WholesaleStockReservation,
)


class WholesaleOrderItemInline(admin.TabularInline):
    model = WholesaleOrderItem
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "variant",
        "physical_variant",
        "prescription",
        "eye",
        "boxes",
        "physical_units_reserved",
        "applied_box_price_including_gst",
        "subtotal_including_gst",
    )


class WholesalePaymentAttemptInline(admin.TabularInline):
    model = WholesalePaymentAttempt
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "method",
        "status",
        "amount_including_gst",
        "currency",
        "provider_order_id",
        "provider_payment_id",
        "signature_verified",
        "expires_at",
        "paid_at",
        "failed_at",
        "created_at",
        "updated_at",
    )


class WholesaleStockReservationInline(admin.TabularInline):
    model = WholesaleStockReservation
    extra = 0
    can_delete = False
    show_change_link = True

    readonly_fields = (
        "order_item",
        "wholesale_variant",
        "physical_variant",
        "boxes_reserved",
        "physical_units_reserved",
        "status",
        "metadata",
        "expires_at",
        "consumed_at",
        "released_at",
    )


@admin.register(WholesaleOrder)
class WholesaleOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "wholesale_account",
        "status",
        "payment_status",
        "fulfillment_status",
        "total_boxes",
        "grand_total_including_gst",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_status",
        "fulfillment_status",
        "created_at",
    )
    search_fields = (
        "order_number",
        "wholesale_account__reference_id",
        "wholesale_account__business_name",
        "wholesale_account__user__phone_number",
    )
    readonly_fields = (
        "order_number",
        "wholesale_account",
        "source_cart",
        "status",
        "payment_status",
        "fulfillment_status",
        "business_snapshot",
        "subtotal_including_gst",
        "delivery_fee_including_gst",
        "grand_total_including_gst",
        "total_boxes",
        "customer_notes",
        "placed_at",
        "confirmed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    )
    inlines = (
        WholesaleOrderItemInline,
        WholesalePaymentAttemptInline,
        WholesaleStockReservationInline,
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(WholesaleOrderAddressSnapshot)
class WholesaleOrderAddressSnapshotAdmin(
    admin.ModelAdmin
):
    list_display = (
        "order",
        "business_name",
        "city",
        "state",
        "postal_code",
    )
    search_fields = (
        "order__order_number",
        "business_name",
        "phone_number",
        "invoice_email",
        "postal_code",
    )
    readonly_fields = (
        "order",
        "recipient_name",
        "business_name",
        "phone_number",
        "invoice_email",
        "gstin",
        "address_line_1",
        "address_line_2",
        "landmark",
        "city",
        "district",
        "state",
        "postal_code",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WholesaleOrderItem)
class WholesaleOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "variant",
        "eye",
        "boxes",
        "applied_box_price_including_gst",
        "subtotal_including_gst",
    )
    search_fields = (
        "order__order_number",
        "variant__sku",
        "variant__listing__catalogue_code",
    )
    readonly_fields = (
        "order",
        "variant",
        "physical_variant",
        "prescription",
        "eye",
        "boxes",
        "physical_units_reserved",
        "base_box_price_including_gst",
        "applied_box_price_including_gst",
        "discount_per_box_including_gst",
        "subtotal_including_gst",
        "bulk_price_tier_id_snapshot",
        "variant_snapshot",
        "prescription_snapshot",
        "pricing_snapshot",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WholesalePaymentAttempt)
class WholesalePaymentAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "method",
        "status",
        "amount_including_gst",
        "expires_at",
        "created_at",
    )
    list_filter = (
        "method",
        "status",
        "created_at",
    )
    search_fields = (
        "order__order_number",
        "provider_order_id",
        "provider_payment_id",
        "idempotency_key",
    )
    readonly_fields = (
        "order",
        "method",
        "status",
        "amount_including_gst",
        "currency",
        "idempotency_key",
        "provider_order_id",
        "provider_payment_id",
        "provider_signature",
        "signature_verified",
        "provider_payload",
        "expires_at",
        "paid_at",
        "failed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(WholesaleFulfillment)
class WholesaleFulfillmentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "status",
        "carrier_name",
        "tracking_number",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = (
        "order__order_number",
        "carrier_name",
        "tracking_number",
    )
    readonly_fields = (
        "order",
        "status",
        "carrier_name",
        "tracking_number",
        "metadata",
        "processing_started_at",
        "shipped_at",
        "delivered_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(WholesaleStockReservation)
class WholesaleStockReservationAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "wholesale_variant",
        "boxes_reserved",
        "physical_units_reserved",
        "status",
        "expires_at",
    )
    list_filter = (
        "status",
        "expires_at",
    )
    search_fields = (
        "order__order_number",
        "wholesale_variant__sku",
        "physical_variant__physical_sku",
    )
    readonly_fields = (
        "order",
        "order_item",
        "wholesale_variant",
        "physical_variant",
        "boxes_reserved",
        "physical_units_reserved",
        "status",
        "metadata",
        "expires_at",
        "consumed_at",
        "released_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

@admin.register(WholesalePaymentWebhookEvent)
class WholesalePaymentWebhookEventAdmin(
    admin.ModelAdmin
):
    list_display = (
        "event_id",
        "event_type",
        "status",
        "order",
        "created_at",
        "processed_at",
    )
    list_filter = (
        "status",
        "event_type",
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
        "status",
        "order",
        "payment_attempt",
        "signature",
        "payload",
        "error_message",
        "processed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser


@admin.register(WholesaleOrderNotificationEvent)
class WholesaleOrderNotificationEventAdmin(
    admin.ModelAdmin
):
    list_display = (
        "order",
        "event_type",
        "channel",
        "recipient",
        "status",
        "attempt_count",
        "created_at",
    )
    list_filter = (
        "event_type",
        "channel",
        "status",
        "created_at",
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
        "status",
        "attempt_count",
        "last_error",
        "payload",
        "sent_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WholesaleInvoice)
class WholesaleInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "order",
        "status",
        "grand_total_including_gst",
        "issued_at",
    )
    list_filter = (
        "status",
        "issued_at",
    )
    search_fields = (
        "invoice_number",
        "order__order_number",
        "business_snapshot__business_name",
    )
    readonly_fields = (
        "invoice_number",
        "order",
        "status",
        "currency",
        "seller_snapshot",
        "business_snapshot",
        "billing_address_snapshot",
        "items_snapshot",
        "subtotal_including_gst",
        "delivery_fee_including_gst",
        "grand_total_including_gst",
        "issued_at",
        "voided_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
