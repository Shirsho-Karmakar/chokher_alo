import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.locations.models import Address
from apps.retail_cart.services import (
    RetailCartError,
    get_or_create_open_retail_cart,
)

from .forms import (
    RazorpaySuccessForm,
    RetailCheckoutForm,
    RetailOrderCancellationForm,
    RetailOrderListForm,
    StaffCustomerFrameReceivedForm,
    StaffOrderNoteForm,
    StaffPayAtStorePaymentForm,
    StaffRetailOrderListForm,
    StaffShipmentForm,
)
from .models import (
    RetailFulfillmentGroup,
    RetailOrder,
    RetailPaymentAttempt,
    RetailPaymentWebhookEvent,
)
from .razorpay_gateway import (
    RazorpayGateway,
    RazorpayGatewayError,
    amount_to_subunits,
)
from .services import (
    RetailCheckoutError,
    cancel_retail_order,
    confirm_online_payment,
    create_retail_checkout,
    fail_online_payment,
    prepare_razorpay_payment,
    preview_retail_checkout,
    RetailOrderOperationError,
    mark_order_delivered,
    mark_order_packed,
    mark_order_ready_for_pickup,
    mark_order_shipped,
    mark_pay_at_store_paid,
    record_customer_frame_received,
    start_order_processing,
    start_order_production,
)


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return str(value)


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True,
    )


def _error_response(
    *,
    code,
    message,
    status,
    **extra,
):
    error = {
        "code": code,
        "message": message,
    }
    error.update(extra)

    return JsonResponse(
        {
            "ok": False,
            "error": error,
        },
        status=status,
    )


def _checkout_error_response(exc):
    conflict_codes = {
        "cart_not_open",
        "cart_not_ready",
        "checkout_in_progress",
        "insufficient_stock",
        "delivery_not_serviceable",
        "pay_at_store_disabled",
        "pay_at_store_requires_pickup",
        "payment_attempt_not_preparable",
        "payment_attempt_not_payable",
        "payment_attempt_expired",
        "payment_not_captured",
        "order_processing_started",
        "cancellation_window_expired",
        "already_cancelled",
    }

    return _error_response(
        code=exc.code,
        message=str(exc),
        status=409 if exc.code in conflict_codes else 400,
        details=exc.details,
    )


def _gateway_error_response(exc):
    return _error_response(
        code=exc.code,
        message=str(exc),
        status=502,
        provider_status_code=exc.status_code,
    )


def _owned_address(*, user, address_id):
    if address_id is None:
        return None

    return get_object_or_404(
        Address,
        pk=address_id,
        user=user,
        is_active=True,
    )


def _billing_same_as_shipping(request, form):
    if "billing_same_as_shipping" not in request.POST:
        return True

    return form.cleaned_data["billing_same_as_shipping"]


def _serialize_address(address):
    return {
        "id": address.pk,
        "label": address.label or None,
        "recipient_name": address.recipient_name,
        "phone_number": address.phone_number,
        "address_line_1": address.address_line_1,
        "address_line_2": address.address_line_2,
        "landmark": address.landmark,
        "city": address.city,
        "district": address.district,
        "state": address.get_state_display(),
        "state_code": address.state,
        "postal_code": address.postal_code,
    }


def _serialize_store(store):
    if store is None:
        return None

    return {
        "id": store.pk,
        "code": store.code,
        "name": store.name,
        "phone_number": store.phone_number or None,
        "email": store.email or None,
        "address_line_1": store.address_line_1,
        "address_line_2": store.address_line_2,
        "locality": store.locality,
        "landmark": store.landmark,
        "city": store.city,
        "state": store.state,
        "postal_code": store.postal_code,
        "country": store.country,
        "pickup_instructions": (
            store.pickup_instructions
        ),
    }


def _serialize_order_summary(order):
    return {
        "order_number": order.order_number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "payment_method": order.payment_method,
        "payment_method_label": (
            order.get_payment_method_display()
        ),
        "payment_status": order.payment_status,
        "payment_status_label": (
            order.get_payment_status_display()
        ),
        "fulfillment_method": order.fulfillment_method,
        "fulfillment_method_label": (
            order.get_fulfillment_method_display()
        ),
        "subtotal_including_gst": _money(
            order.subtotal_including_gst
        ),
        "delivery_fee_including_gst": _money(
            order.delivery_fee_including_gst
        ),
        "grand_total_including_gst": _money(
            order.grand_total_including_gst
        ),
        "currency": order.currency,
        "can_customer_cancel": order.can_customer_cancel,
        "cancellation_block_reason": (
            order.cancellation_block_reason
        ),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _serialize_order_detail(order):
    data = _serialize_order_summary(order)

    data.update(
        {
            "billing_same_as_shipping": (
                order.billing_same_as_shipping
            ),
            "store_location": _serialize_store(
                order.store_location
            ),
            "customer_notes": order.customer_notes,
            "cancellable_until": (
                order.cancellable_until.isoformat()
            ),
            "payment_confirmed_at": (
                order.payment_confirmed_at.isoformat()
                if order.payment_confirmed_at
                else None
            ),
            "cancelled_at": (
                order.cancelled_at.isoformat()
                if order.cancelled_at
                else None
            ),
            "cancellation_reason": (
                order.cancellation_reason or None
            ),
            "addresses": [
                {
                    "address_type": snapshot.address_type,
                    "address_type_label": (
                        snapshot.get_address_type_display()
                    ),
                    "recipient_name": (
                        snapshot.recipient_name
                    ),
                    "phone_number": snapshot.phone_number,
                    "address_line_1": (
                        snapshot.address_line_1
                    ),
                    "address_line_2": (
                        snapshot.address_line_2
                    ),
                    "locality": snapshot.locality,
                    "landmark": snapshot.landmark,
                    "city": snapshot.city,
                    "district": snapshot.district,
                    "state": snapshot.state,
                    "postal_code": snapshot.postal_code,
                    "country": snapshot.country,
                }
                for snapshot
                in order.address_snapshots.all()
            ],
            "items": [
                {
                    "id": item.pk,
                    "item_type": item.item_type,
                    "item_type_label": (
                        item.get_item_type_display()
                    ),
                    "sku": item.sku,
                    "product_name": item.product_name,
                    "variant_description": (
                        item.variant_description or None
                    ),
                    "quantity": item.quantity,
                    "unit_price_including_gst": _money(
                        item.unit_price_including_gst
                    ),
                    "line_total_including_gst": _money(
                        item.line_total_including_gst
                    ),
                    "gst_rate": _money(item.gst_rate),
                    "is_custom": item.is_custom,
                    "is_non_refundable": (
                        item.is_non_refundable
                    ),
                    "non_cancellable_after_production": (
                        item
                        .non_cancellable_after_production
                    ),
                    "product_snapshot": (
                        item.product_snapshot
                    ),
                    "configuration_snapshot": (
                        item.configuration_snapshot
                    ),
                    "fulfillment_group_id": (
                        item.fulfillment_group_id
                    ),
                }
                for item in order.items.all()
            ],
            "fulfillment_groups": [
                {
                    "id": group.pk,
                    "group_type": group.group_type,
                    "group_type_label": (
                        group.get_group_type_display()
                    ),
                    "title": group.title,
                    "status": group.status,
                    "status_label": (
                        group.get_status_display()
                    ),
                    "store_location": _serialize_store(
                        group.store_location
                    ),
                    "carrier_name": (
                        group.carrier_name or None
                    ),
                    "tracking_number": (
                        group.tracking_number or None
                    ),
                    "metadata": group.metadata,
                }
                for group
                in order.fulfillment_groups.all()
            ],
            "payment_attempts": [
                {
                    "id": attempt.pk,
                    "payment_method": (
                        attempt.payment_method
                    ),
                    "status": attempt.status,
                    "status_label": (
                        attempt.get_status_display()
                    ),
                    "amount_including_gst": _money(
                        attempt.amount_including_gst
                    ),
                    "currency": attempt.currency,
                    "allowed_payment_methods": (
                        attempt.allowed_payment_methods
                    ),
                    "provider_order_id": (
                        attempt.provider_order_id
                    ),
                    "provider_payment_id": (
                        attempt.provider_payment_id
                    ),
                    "signature_verified": (
                        attempt.signature_verified
                    ),
                    "expires_at": (
                        attempt.expires_at.isoformat()
                        if attempt.expires_at
                        else None
                    ),
                    "paid_at": (
                        attempt.paid_at.isoformat()
                        if attempt.paid_at
                        else None
                    ),
                }
                for attempt
                in order.payment_attempts.all()
            ],
        }
    )

    return data


def _load_order_detail_queryset():
    return (
        RetailOrder.objects
        .select_related(
            "store_location",
            "user",
            "source_cart",
        )
        .prefetch_related(
            "address_snapshots",
            "items",
            "fulfillment_groups",
            "fulfillment_groups__store_location",
            "payment_attempts",
        )
    )


def _serialize_payment_session(session):
    return {
        "provider": "razorpay",
        "key_id": session.key_id,
        "provider_order_id": session.provider_order_id,
        "amount_subunits": session.amount_subunits,
        "currency": session.currency,
        "receipt": session.receipt,
        "allowed_payment_methods": list(
            session.allowed_payment_methods
        ),
        "expires_at": (
            session.expires_at.isoformat()
            if session.expires_at
            else None
        ),
    }


@login_required
@require_POST
def checkout_preview(request):
    form = RetailCheckoutForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the checkout request.",
            status=400,
            fields=_form_errors(form),
        )

    shipping = _owned_address(
        user=request.user,
        address_id=form.cleaned_data.get(
            "shipping_address_id"
        ),
    )
    billing = _owned_address(
        user=request.user,
        address_id=form.cleaned_data.get(
            "billing_address_id"
        ),
    )

    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
        preview = preview_retail_checkout(
            cart=cart,
            fulfillment_method=(
                form.cleaned_data["fulfillment_method"]
            ),
            payment_method=(
                form.cleaned_data["payment_method"]
            ),
            shipping_address=shipping,
            billing_address=billing,
            billing_same_as_shipping=(
                _billing_same_as_shipping(
                    request,
                    form,
                )
            ),
        )
    except RetailCartError as exc:
        return _error_response(
            code=exc.code,
            message=str(exc),
            status=409,
        )
    except RetailCheckoutError as exc:
        return _checkout_error_response(exc)

    return JsonResponse(
        {
            "ok": True,
            "preview": {
                "cart_id": preview.cart_id,
                "fulfillment_method": (
                    preview.fulfillment_method
                ),
                "payment_method": preview.payment_method,
                "shipping_address": (
                    _serialize_address(
                        preview.shipping_address
                    )
                    if preview.shipping_address
                    else None
                ),
                "billing_address": _serialize_address(
                    preview.billing_address
                ),
                "billing_same_as_shipping": (
                    preview.billing_same_as_shipping
                ),
                "store_location": _serialize_store(
                    preview.store_location
                ),
                "subtotal_including_gst": _money(
                    preview.subtotal_including_gst
                ),
                "delivery_fee_including_gst": _money(
                    preview.delivery_fee_including_gst
                ),
                "grand_total_including_gst": _money(
                    preview.grand_total_including_gst
                ),
                "currency": preview.currency,
                "policy": preview.policy_snapshot,
            },
        }
    )


@login_required
@require_POST
def create_checkout(request):
    form = RetailCheckoutForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the checkout request.",
            status=400,
            fields=_form_errors(form),
        )

    shipping = _owned_address(
        user=request.user,
        address_id=form.cleaned_data.get(
            "shipping_address_id"
        ),
    )
    billing = _owned_address(
        user=request.user,
        address_id=form.cleaned_data.get(
            "billing_address_id"
        ),
    )

    try:
        cart = get_or_create_open_retail_cart(
            user=request.user
        )
        result = create_retail_checkout(
            cart=cart,
            fulfillment_method=(
                form.cleaned_data["fulfillment_method"]
            ),
            payment_method=(
                form.cleaned_data["payment_method"]
            ),
            shipping_address=shipping,
            billing_address=billing,
            billing_same_as_shipping=(
                _billing_same_as_shipping(
                    request,
                    form,
                )
            ),
            customer_notes=(
                form.cleaned_data.get("customer_notes")
                or ""
            ),
        )
    except RetailCartError as exc:
        return _error_response(
            code=exc.code,
            message=str(exc),
            status=409,
        )
    except RetailCheckoutError as exc:
        return _checkout_error_response(exc)

    payment_session = None

    if (
        result.order.payment_method
        == RetailOrder.PaymentMethod.RAZORPAY
    ):
        try:
            payment_session = prepare_razorpay_payment(
                payment_attempt=result.payment_attempt
            )
        except (
            RazorpayGatewayError,
            RetailCheckoutError,
        ) as exc:
            try:
                fail_online_payment(
                    payment_attempt=result.payment_attempt,
                    response_payload={
                        "preparation_error": str(exc),
                    },
                )
            except RetailCheckoutError:
                pass

            if isinstance(exc, RazorpayGatewayError):
                return _gateway_error_response(exc)

            return _checkout_error_response(exc)

    order = get_object_or_404(
        _load_order_detail_queryset(),
        pk=result.order.pk,
        user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
            "payment_session": (
                _serialize_payment_session(
                    payment_session
                )
                if payment_session
                else None
            ),
        },
        status=201,
    )


@login_required
@require_POST
def confirm_razorpay_payment(request):
    form = RazorpaySuccessForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the payment response.",
            status=400,
            fields=_form_errors(form),
        )

    attempt = get_object_or_404(
        RetailPaymentAttempt.objects.select_related(
            "order"
        ),
        provider_order_id=form.cleaned_data[
            "razorpay_order_id"
        ],
        order__user=request.user,
    )

    gateway = RazorpayGateway()

    try:
        signature_verified = (
            gateway.verify_checkout_signature(
                provider_order_id=(
                    form.cleaned_data[
                        "razorpay_order_id"
                    ]
                ),
                provider_payment_id=(
                    form.cleaned_data[
                        "razorpay_payment_id"
                    ]
                ),
                signature=form.cleaned_data[
                    "razorpay_signature"
                ],
            )
        )
    except RazorpayGatewayError as exc:
        return _gateway_error_response(exc)

    if not signature_verified:
        return _error_response(
            code="payment_signature_invalid",
            message=(
                "The payment signature could not be verified."
            ),
            status=400,
        )

    try:
        provider_payment = gateway.fetch_payment(
            form.cleaned_data["razorpay_payment_id"]
        )
    except RazorpayGatewayError as exc:
        return _gateway_error_response(exc)

    expected_amount = amount_to_subunits(
        attempt.amount_including_gst
    )

    payment_is_valid = (
        provider_payment.get("id")
        == form.cleaned_data["razorpay_payment_id"]
        and provider_payment.get("order_id")
        == attempt.provider_order_id
        and provider_payment.get("amount")
        == expected_amount
        and provider_payment.get("currency")
        == attempt.currency
    )

    if not payment_is_valid:
        return _error_response(
            code="payment_details_mismatch",
            message=(
                "The provider payment did not match the order."
            ),
            status=409,
        )

    if (
        provider_payment.get("status") != "captured"
        and provider_payment.get("captured") is not True
    ):
        return _error_response(
            code="payment_not_captured",
            message=(
                "The payment has not yet been captured."
            ),
            status=409,
        )

    try:
        order = confirm_online_payment(
            payment_attempt=attempt,
            provider_payment_id=form.cleaned_data[
                "razorpay_payment_id"
            ],
            provider_signature=form.cleaned_data[
                "razorpay_signature"
            ],
            signature_verified=True,
            response_payload=provider_payment,
        )
    except RetailCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _load_order_detail_queryset(),
        pk=order.pk,
        user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_GET
def order_list(request):
    form = RetailOrderListForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the order-list request.",
            status=400,
            fields=_form_errors(form),
        )

    queryset = (
        RetailOrder.objects
        .filter(user=request.user)
        .select_related("store_location")
        .order_by("-created_at")
    )

    page_number = form.cleaned_data.get("page") or 1
    page_size = form.cleaned_data.get("page_size") or 20
    paginator = Paginator(queryset, page_size)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        return _error_response(
            code="page_not_found",
            message="The requested order page does not exist.",
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "orders": [
                _serialize_order_summary(order)
                for order in page.object_list
            ],
        }
    )


@login_required
@require_GET
def order_detail(request, order_number):
    order = get_object_or_404(
        _load_order_detail_queryset(),
        order_number=order_number,
        user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def cancel_order(request, order_number):
    form = RetailOrderCancellationForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Enter a cancellation reason.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        RetailOrder,
        order_number=order_number,
        user=request.user,
    )

    try:
        cancel_retail_order(
            order=order,
            cancelled_by=request.user,
            reason=form.cleaned_data["reason"],
        )
    except RetailCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _load_order_detail_queryset(),
        pk=order.pk,
        user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


def _payment_entity(payload):
    return (
        payload
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )


def _order_entity(payload):
    return (
        payload
        .get("payload", {})
        .get("order", {})
        .get("entity", {})
    )


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    raw_body = request.body
    signature = request.headers.get(
        "X-Razorpay-Signature",
        "",
    )
    event_id = request.headers.get(
        "X-Razorpay-Event-Id",
        "",
    ).strip()

    if not signature or not event_id:
        return _error_response(
            code="webhook_headers_missing",
            message=(
                "Required Razorpay webhook headers are missing."
            ),
            status=400,
        )

    gateway = RazorpayGateway()

    try:
        verified = gateway.verify_webhook_signature(
            raw_body=raw_body,
            signature=signature,
        )
    except RazorpayGatewayError as exc:
        return _gateway_error_response(exc)

    if not verified:
        return _error_response(
            code="webhook_signature_invalid",
            message="The webhook signature is invalid.",
            status=400,
        )

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return _error_response(
            code="webhook_payload_invalid",
            message="The webhook payload is not valid JSON.",
            status=400,
        )

    event_type = str(payload.get("event") or "").strip()

    if not event_type:
        return _error_response(
            code="webhook_event_missing",
            message="The webhook event type is missing.",
            status=400,
        )

    with transaction.atomic():
        event, created = (
            RetailPaymentWebhookEvent.objects
            .select_for_update()
            .get_or_create(
                event_id=event_id,
                defaults={
                    "event_type": event_type,
                    "signature": signature,
                    "payload": payload,
                },
            )
        )

        if (
            not created
            and event.status
            in {
                RetailPaymentWebhookEvent
                .Status.PROCESSED,
                RetailPaymentWebhookEvent
                .Status.IGNORED,
            }
        ):
            return JsonResponse(
                {
                    "ok": True,
                    "duplicate": True,
                    "event_id": event.event_id,
                    "status": event.status,
                }
            )

        event.event_type = event_type
        event.signature = signature
        event.payload = payload
        event.status = (
            RetailPaymentWebhookEvent.Status.RECEIVED
        )
        event.error_message = ""
        event.save()

    payment = _payment_entity(payload)
    provider_order = _order_entity(payload)

    provider_order_id = (
        payment.get("order_id")
        or provider_order.get("id")
    )
    provider_payment_id = payment.get("id")

    attempt = None

    if provider_order_id:
        attempt = (
            RetailPaymentAttempt.objects
            .select_related("order")
            .filter(
                provider_order_id=provider_order_id
            )
            .first()
        )

    if attempt is None:
        event.status = (
            RetailPaymentWebhookEvent.Status.IGNORED
        )
        event.error_message = (
            "No local payment attempt matched the provider order."
        )
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                "status",
                "error_message",
                "processed_at",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "ok": True,
                "ignored": True,
                "event_id": event.event_id,
            }
        )

    event.order = attempt.order
    event.payment_attempt = attempt
    event.save(
        update_fields=[
            "order",
            "payment_attempt",
            "updated_at",
        ]
    )

    try:
        if event_type in {
            "payment.captured",
            "order.paid",
        }:
            if not provider_payment_id:
                raise RetailCheckoutError(
                    "provider_payment_id_missing",
                    "The captured-payment event has no payment ID.",
                )

            expected_amount = amount_to_subunits(
                attempt.amount_including_gst
            )

            payment_matches_attempt = (
                payment.get("order_id")
                == attempt.provider_order_id
                and payment.get("amount")
                == expected_amount
                and payment.get("currency")
                == attempt.currency
            )

            if not payment_matches_attempt:
                raise RetailCheckoutError(
                    "webhook_payment_mismatch",
                    (
                        "The webhook payment did not match "
                        "the local payment attempt."
                    ),
                )

            payment_is_captured = (
                payment.get("status") == "captured"
                or payment.get("captured") is True
            )

            if not payment_is_captured:
                raise RetailCheckoutError(
                    "webhook_payment_not_captured",
                    (
                        "The webhook payment is not in "
                        "the captured state."
                    ),
                )

            confirm_online_payment(
                payment_attempt=attempt,
                provider_payment_id=provider_payment_id,
                provider_signature=signature,
                signature_verified=True,
                response_payload=payload,
            )

        elif event_type == "payment.failed":
            fail_online_payment(
                payment_attempt=attempt,
                response_payload=payload,
            )

        else:
            event.status = (
                RetailPaymentWebhookEvent.Status.IGNORED
            )
            event.processed_at = timezone.now()
            event.save(
                update_fields=[
                    "status",
                    "processed_at",
                    "updated_at",
                ]
            )

            return JsonResponse(
                {
                    "ok": True,
                    "ignored": True,
                    "event_id": event.event_id,
                }
            )

    except RetailCheckoutError as exc:
        event.status = (
            RetailPaymentWebhookEvent.Status.FAILED
        )
        event.error_message = (
            f"{exc.code}: {exc}"
        )
        event.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        return _error_response(
            code="webhook_processing_failed",
            message=str(exc),
            status=500,
            event_id=event.event_id,
        )

    event.status = (
        RetailPaymentWebhookEvent.Status.PROCESSED
    )
    event.processed_at = timezone.now()
    event.save(
        update_fields=[
            "status",
            "processed_at",
            "updated_at",
        ]
    )

    return JsonResponse(
        {
            "ok": True,
            "event_id": event.event_id,
            "status": event.status,
        }
    )


def _staff_order_access_error(request):
    user = request.user

    if not user.is_active or not user.is_staff:
        return _error_response(
            code="staff_access_required",
            message="An active staff account is required.",
            status=403,
        )

    if (
        not user.is_superuser
        and not user.has_perm(
            "retail_orders.change_retailorder"
        )
    ):
        return _error_response(
            code="order_permission_required",
            message="Order Manager permission is required.",
            status=403,
        )

    return None


def _operation_error_response(exc):
    permission_codes = {
        "staff_access_required",
        "order_permission_required",
    }
    conflict_codes = {
        "invalid_status_transition",
        "managed_status_required",
        "production_not_required",
        "customer_frame_not_received",
        "packing_not_applicable",
        "pickup_not_applicable",
        "shipping_not_applicable",
        "carrier_required",
        "tracking_number_required",
        "pay_at_store_payment_required",
        "not_pay_at_store",
        "order_cancelled",
        "payment_attempt_missing",
        "invalid_fulfillment_group",
        "frame_receipt_not_allowed",
    }

    if exc.code in permission_codes:
        status = 403
    elif exc.code in conflict_codes:
        status = 409
    else:
        status = 400

    return _error_response(
        code=exc.code,
        message=str(exc),
        status=status,
        details=exc.details,
    )


def _serialize_staff_actor(user):
    if user is None:
        return None

    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email or None,
    }


def _serialize_order_status_history(history):
    return {
        "id": history.pk,
        "previous_status": history.previous_status,
        "previous_status_label": (
            history.get_previous_status_display()
        ),
        "new_status": history.new_status,
        "new_status_label": (
            history.get_new_status_display()
        ),
        "changed_by": _serialize_staff_actor(
            history.changed_by
        ),
        "note": history.note or None,
        "metadata": history.metadata,
        "created_at": history.created_at.isoformat(),
    }


def _serialize_fulfillment_status_history(history):
    return {
        "id": history.pk,
        "fulfillment_group_id": (
            history.fulfillment_group_id
        ),
        "previous_status": history.previous_status,
        "previous_status_label": (
            history.get_previous_status_display()
        ),
        "new_status": history.new_status,
        "new_status_label": (
            history.get_new_status_display()
        ),
        "changed_by": _serialize_staff_actor(
            history.changed_by
        ),
        "note": history.note or None,
        "metadata": history.metadata,
        "created_at": history.created_at.isoformat(),
    }


def _staff_allowed_actions(order):
    actions = []
    status = order.status

    if status == RetailOrder.Status.CONFIRMED:
        actions.append("start_processing")

    elif status == RetailOrder.Status.PROCESSING:
        has_custom_items = order.items.filter(
            is_custom=True
        ).exists()

        inbound_pending = (
            order.fulfillment_groups
            .filter(
                group_type=(
                    RetailFulfillmentGroup
                    .GroupType.CUSTOMER_FRAME_INBOUND
                ),
            )
            .exclude(
                status=(
                    RetailFulfillmentGroup.Status.COMPLETED
                )
            )
            .exists()
        )

        if has_custom_items and not inbound_pending:
            actions.append("start_production")

        if not has_custom_items:
            if (
                order.fulfillment_method
                == RetailOrder.FulfillmentMethod.DELIVERY
            ):
                actions.append("mark_packed")
            else:
                actions.append("mark_ready_for_pickup")

    elif status == RetailOrder.Status.PRODUCTION:
        if (
            order.fulfillment_method
            == RetailOrder.FulfillmentMethod.DELIVERY
        ):
            actions.append("mark_packed")
        else:
            actions.append("mark_ready_for_pickup")

    elif status == RetailOrder.Status.PACKED:
        actions.append("mark_shipped")

    elif status == RetailOrder.Status.SHIPPED:
        actions.append("mark_delivered")

    elif status == RetailOrder.Status.READY_FOR_PICKUP:
        if (
            order.payment_method
            == RetailOrder.PaymentMethod.PAY_AT_STORE
            and order.payment_status
            != RetailOrder.PaymentStatus.PAID
        ):
            actions.append("record_store_payment")
        else:
            actions.append("mark_delivered")

    pending_frame_groups = list(
        order.fulfillment_groups
        .filter(
            group_type=(
                RetailFulfillmentGroup
                .GroupType.CUSTOMER_FRAME_INBOUND
            ),
        )
        .exclude(
            status=RetailFulfillmentGroup.Status.COMPLETED
        )
        .values_list("pk", flat=True)
    )

    return {
        "order_actions": actions,
        "customer_frame_receipt_group_ids": (
            pending_frame_groups
        ),
    }


def _load_staff_order_detail_queryset():
    return (
        _load_order_detail_queryset()
        .prefetch_related(
            "status_history__changed_by",
            (
                "fulfillment_groups__"
                "status_history__changed_by"
            ),
        )
    )


def _serialize_staff_order_detail(order):
    data = _serialize_order_detail(order)

    fulfillment_histories = []

    for group in order.fulfillment_groups.all():
        fulfillment_histories.extend(
            _serialize_fulfillment_status_history(history)
            for history in group.status_history.all()
        )

    fulfillment_histories.sort(
        key=lambda item: (item["created_at"], item["id"])
    )

    data["staff_operations"] = _staff_allowed_actions(order)
    data["status_history"] = [
        _serialize_order_status_history(history)
        for history in order.status_history.all()
    ]
    data["fulfillment_status_history"] = (
        fulfillment_histories
    )

    return data


def _staff_order(order_number):
    return get_object_or_404(
        _load_staff_order_detail_queryset(),
        order_number=order_number,
    )


def _validated_staff_form(form):
    if form.is_valid():
        return None

    return _error_response(
        code="invalid_request",
        message="Correct the staff order request.",
        status=400,
        fields=_form_errors(form),
    )


def _staff_order_response(order):
    order = get_object_or_404(
        _load_staff_order_detail_queryset(),
        pk=order.pk,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_staff_order_detail(order),
        }
    )


@login_required
@require_GET
def staff_order_list(request):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffRetailOrderListForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the staff order-list request.",
            status=400,
            fields=_form_errors(form),
        )

    queryset = (
        RetailOrder.objects
        .select_related(
            "user",
            "store_location",
        )
        .order_by("-created_at")
    )

    status = form.cleaned_data.get("status")
    payment_status = form.cleaned_data.get(
        "payment_status"
    )
    fulfillment_method = form.cleaned_data.get(
        "fulfillment_method"
    )
    search = form.cleaned_data.get("q")

    if status:
        queryset = queryset.filter(status=status)

    if payment_status:
        queryset = queryset.filter(
            payment_status=payment_status
        )

    if fulfillment_method:
        queryset = queryset.filter(
            fulfillment_method=fulfillment_method
        )

    if search:
        queryset = queryset.filter(
            Q(order_number__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__phone_number__icontains=search)
        )

    page_number = form.cleaned_data.get("page") or 1
    page_size = form.cleaned_data.get("page_size") or 25
    paginator = Paginator(queryset, page_size)

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        return _error_response(
            code="page_not_found",
            message="The requested staff order page does not exist.",
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "pagination": {
                "page": page.number,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "orders": [
                {
                    **_serialize_order_summary(order),
                    "customer": {
                        "id": order.user_id,
                        "username": order.user.username,
                        "email": order.user.email or None,
                        "phone_number": (
                            order.user.phone_number or None
                        ),
                    },
                }
                for order in page.object_list
            ],
        }
    )


@login_required
@require_GET
def staff_order_detail(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    order = _staff_order(order_number)

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_staff_order_detail(order),
        }
    )


@login_required
@require_POST
def staff_start_processing(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffOrderNoteForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = start_order_processing(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_start_production(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffOrderNoteForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = start_order_production(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_mark_packed(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffOrderNoteForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = mark_order_packed(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_mark_ready_for_pickup(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffOrderNoteForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = mark_order_ready_for_pickup(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_mark_shipped(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffShipmentForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = mark_order_shipped(
            order=order,
            actor=request.user,
            carrier_name=form.cleaned_data["carrier_name"],
            tracking_number=(
                form.cleaned_data["tracking_number"]
            ),
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_record_store_payment(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffPayAtStorePaymentForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = mark_pay_at_store_paid(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
            receipt_reference=(
                form.cleaned_data.get(
                    "receipt_reference"
                )
                or ""
            ),
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_mark_delivered(request, order_number):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffOrderNoteForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    order = _staff_order(order_number)

    try:
        order = mark_order_delivered(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(order)


@login_required
@require_POST
def staff_record_customer_frame_received(
    request,
    group_id,
):
    access_error = _staff_order_access_error(request)

    if access_error:
        return access_error

    form = StaffCustomerFrameReceivedForm(request.POST)
    form_error = _validated_staff_form(form)

    if form_error:
        return form_error

    group = get_object_or_404(
        RetailFulfillmentGroup.objects.select_related(
            "order"
        ),
        pk=group_id,
    )

    try:
        group = record_customer_frame_received(
            fulfillment_group=group,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except RetailOrderOperationError as exc:
        return _operation_error_response(exc)

    return _staff_order_response(group.order)
