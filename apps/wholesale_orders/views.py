import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.retail_orders.razorpay_gateway import (
    RazorpayGateway,
    RazorpayGatewayError,
    amount_to_subunits,
)
from apps.wholesale_cart.services import (
    WholesaleCartError,
    get_or_create_open_wholesale_cart,
)

from .forms import (
    StaffBankTransferConfirmationForm,
    StaffWholesaleOrderListForm,
    StaffWholesaleOrderNoteForm,
    StaffWholesaleShipmentForm,
    WholesaleCheckoutForm,
    WholesaleOrderCancellationForm,
    WholesaleOrderListForm,
    WholesaleRazorpaySuccessForm,
)
from .models import (
    WholesaleOrder,
    WholesaleInvoice,
    WholesalePaymentAttempt,
    WholesalePaymentWebhookEvent,
)
from .services import (
    WholesaleCheckoutError,
    cancel_wholesale_checkout,
    confirm_wholesale_bank_transfer,
    confirm_wholesale_online_payment,
    fail_wholesale_payment,
    mark_wholesale_order_delivered,
    mark_wholesale_order_shipped,
    prepare_wholesale_razorpay_payment,
    start_wholesale_checkout,
    start_wholesale_order_processing,
)


def _money(value: Decimal | None):
    return str(value) if value is not None else None


def _form_errors(form):
    return form.errors.get_json_data(
        escape_html=True
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
        "cart_not_checkout_ready",
        "payment_attempt_not_preparable",
        "payment_attempt_not_payable",
        "payment_attempt_expired",
        "payment_reservation_expired",
        "payment_already_confirmed",
        "order_not_ready_for_processing",
        "order_not_ready_to_ship",
        "order_not_ready_for_delivery",
        "checkout_cannot_be_cancelled",
        "insufficient_available_wholesale_stock",
        "insufficient_available_shared_stock",
        "wholesale_stock_changed",
        "shared_stock_changed",
    }

    return _error_response(
        code=exc.code,
        message=str(exc),
        status=(
            409
            if exc.code in conflict_codes
            else 400
        ),
        details=exc.details,
    )


def _gateway_error_response(exc):
    return _error_response(
        code=exc.code,
        message=str(exc),
        status=502,
        provider_status_code=exc.status_code,
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


def _serialize_order_summary(order):
    return {
        "order_number": order.order_number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "payment_status": order.payment_status,
        "payment_status_label": (
            order.get_payment_status_display()
        ),
        "fulfillment_status": (
            order.fulfillment_status
        ),
        "fulfillment_status_label": (
            order.get_fulfillment_status_display()
        ),
        "total_boxes": order.total_boxes,
        "subtotal_including_gst": _money(
            order.subtotal_including_gst
        ),
        "delivery_fee_including_gst": _money(
            order.delivery_fee_including_gst
        ),
        "grand_total_including_gst": _money(
            order.grand_total_including_gst
        ),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def _serialize_order_detail(order):
    data = _serialize_order_summary(order)
    address = order.billing_address
    fulfillment = order.fulfillment

    data.update(
        {
            "business": order.business_snapshot,
            "customer_notes": order.customer_notes,
            "placed_at": (
                order.placed_at.isoformat()
                if order.placed_at
                else None
            ),
            "confirmed_at": (
                order.confirmed_at.isoformat()
                if order.confirmed_at
                else None
            ),
            "cancelled_at": (
                order.cancelled_at.isoformat()
                if order.cancelled_at
                else None
            ),
            "billing_address": {
                "recipient_name": address.recipient_name,
                "business_name": address.business_name,
                "phone_number": address.phone_number,
                "invoice_email": address.invoice_email,
                "gstin": address.gstin or None,
                "address_line_1": address.address_line_1,
                "address_line_2": (
                    address.address_line_2 or None
                ),
                "landmark": address.landmark or None,
                "city": address.city,
                "district": address.district or None,
                "state": address.state,
                "postal_code": address.postal_code,
            },
            "fulfillment": {
                "status": fulfillment.status,
                "status_label": (
                    fulfillment.get_status_display()
                ),
                "carrier_name": (
                    fulfillment.carrier_name or None
                ),
                "tracking_number": (
                    fulfillment.tracking_number or None
                ),
                "processing_started_at": (
                    fulfillment
                    .processing_started_at
                    .isoformat()
                    if fulfillment.processing_started_at
                    else None
                ),
                "shipped_at": (
                    fulfillment.shipped_at.isoformat()
                    if fulfillment.shipped_at
                    else None
                ),
                "delivered_at": (
                    fulfillment.delivered_at.isoformat()
                    if fulfillment.delivered_at
                    else None
                ),
            },
            "items": [
                {
                    "id": item.pk,
                    "sku": item.variant_snapshot.get(
                        "sku"
                    ),
                    "catalogue_code": (
                        item.variant_snapshot.get(
                            "catalogue_code"
                        )
                    ),
                    "name": item.variant_snapshot.get(
                        "name"
                    ),
                    "eye": item.eye,
                    "boxes": item.boxes,
                    "physical_units": (
                        item.physical_units_reserved
                    ),
                    "box_price_including_gst": _money(
                        item
                        .applied_box_price_including_gst
                    ),
                    "subtotal_including_gst": _money(
                        item.subtotal_including_gst
                    ),
                    "variant_snapshot": (
                        item.variant_snapshot
                    ),
                    "prescription_snapshot": (
                        item.prescription_snapshot
                    ),
                    "pricing_snapshot": (
                        item.pricing_snapshot
                    ),
                }
                for item in order.items.all()
            ],
            "payment_attempts": [
                {
                    "id": attempt.pk,
                    "method": attempt.method,
                    "method_label": (
                        attempt.get_method_display()
                    ),
                    "status": attempt.status,
                    "status_label": (
                        attempt.get_status_display()
                    ),
                    "amount_including_gst": _money(
                        attempt.amount_including_gst
                    ),
                    "currency": attempt.currency,
                    "provider_order_id": (
                        attempt.provider_order_id or None
                    ),
                    "provider_payment_id": (
                        attempt.provider_payment_id or None
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


def _order_detail_queryset():
    return (
        WholesaleOrder.objects
        .select_related(
            "wholesale_account",
            "wholesale_account__user",
            "source_cart",
            "billing_address",
            "fulfillment",
            "invoice",
        )
        .prefetch_related(
            "items",
            "payment_attempts",
            "stock_reservations",
        )
    )


@login_required
@require_POST
def checkout_create(request):
    form = WholesaleCheckoutForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the wholesale checkout request.",
            status=400,
            fields=_form_errors(form),
        )

    try:
        cart = get_or_create_open_wholesale_cart(
            user=request.user
        )
        result = start_wholesale_checkout(
            cart=cart,
            payment_method=(
                form.cleaned_data["payment_method"]
            ),
            customer_notes=(
                form.cleaned_data.get(
                    "customer_notes"
                )
                or ""
            ),
        )
    except WholesaleCartError as exc:
        return _error_response(
            code=exc.code,
            message=str(exc),
            status=403,
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    payment_session = None

    if (
        result.payment_attempt.method
        == WholesalePaymentAttempt.Method.RAZORPAY
    ):
        try:
            payment_session = (
                prepare_wholesale_razorpay_payment(
                    payment_attempt=(
                        result.payment_attempt
                    )
                )
            )
        except (
            RazorpayGatewayError,
            WholesaleCheckoutError,
        ) as exc:
            try:
                fail_wholesale_payment(
                    payment_attempt=(
                        result.payment_attempt
                    ),
                    response_payload={
                        "preparation_error": str(exc),
                    },
                )
            except WholesaleCheckoutError:
                pass

            if isinstance(exc, RazorpayGatewayError):
                return _gateway_error_response(exc)

            return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=result.order.pk,
        wholesale_account__user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "created": result.created,
            "order": _serialize_order_detail(order),
            "payment_session": (
                _serialize_payment_session(
                    payment_session
                )
                if payment_session
                else None
            ),
        },
        status=201 if result.created else 200,
    )


@login_required
@require_POST
def confirm_razorpay_payment(request):
    form = WholesaleRazorpaySuccessForm(
        request.POST
    )

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the Razorpay response.",
            status=400,
            fields=_form_errors(form),
        )

    attempt = get_object_or_404(
        WholesalePaymentAttempt.objects.select_related(
            "order",
            "order__wholesale_account",
        ),
        provider_order_id=form.cleaned_data[
            "razorpay_order_id"
        ],
        order__wholesale_account__user=request.user,
    )

    gateway = RazorpayGateway()

    try:
        verified = gateway.verify_checkout_signature(
            provider_order_id=form.cleaned_data[
                "razorpay_order_id"
            ],
            provider_payment_id=form.cleaned_data[
                "razorpay_payment_id"
            ],
            signature=form.cleaned_data[
                "razorpay_signature"
            ],
        )
    except RazorpayGatewayError as exc:
        return _gateway_error_response(exc)

    if not verified:
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

    matches = (
        provider_payment.get("id")
        == form.cleaned_data["razorpay_payment_id"]
        and provider_payment.get("order_id")
        == attempt.provider_order_id
        and provider_payment.get("amount")
        == amount_to_subunits(
            attempt.amount_including_gst
        )
        and provider_payment.get("currency")
        == attempt.currency
    )

    if not matches:
        return _error_response(
            code="payment_details_mismatch",
            message=(
                "The provider payment did not match "
                "the wholesale order."
            ),
            status=409,
        )

    captured = (
        provider_payment.get("status") == "captured"
        or provider_payment.get("captured") is True
    )

    if not captured:
        return _error_response(
            code="payment_not_captured",
            message="The payment has not been captured.",
            status=409,
        )

    try:
        order = confirm_wholesale_online_payment(
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
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
        wholesale_account__user=request.user,
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
    form = WholesaleOrderListForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the order-list request.",
            status=400,
            fields=_form_errors(form),
        )

    queryset = WholesaleOrder.objects.filter(
        wholesale_account__user=request.user
    )

    page_size = (
        form.cleaned_data.get("page_size")
        or 20
    )
    page_number = (
        form.cleaned_data.get("page")
        or 1
    )
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
        _order_detail_queryset(),
        order_number=order_number,
        wholesale_account__user=request.user,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def order_cancel(request, order_number):
    form = WholesaleOrderCancellationForm(
        request.POST
    )

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Enter a cancellation reason.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        WholesaleOrder,
        order_number=order_number,
        wholesale_account__user=request.user,
    )

    try:
        cancel_wholesale_checkout(
            order=order,
            reason=form.cleaned_data["reason"],
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
        wholesale_account__user=request.user,
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
                "Required Razorpay webhook headers "
                "are missing."
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

    event_type = str(
        payload.get("event") or ""
    ).strip()

    if not event_type:
        return _error_response(
            code="webhook_event_missing",
            message="The webhook event type is missing.",
            status=400,
        )

    with transaction.atomic():
        event, created = (
            WholesalePaymentWebhookEvent.objects
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
                WholesalePaymentWebhookEvent
                .Status.PROCESSED,
                WholesalePaymentWebhookEvent
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
            WholesalePaymentWebhookEvent
            .Status.RECEIVED
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
            WholesalePaymentAttempt.objects
            .select_related("order")
            .filter(
                provider_order_id=provider_order_id
            )
            .first()
        )

    if attempt is None:
        event.status = (
            WholesalePaymentWebhookEvent.Status.IGNORED
        )
        event.error_message = (
            "No wholesale payment attempt matched "
            "the provider order."
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
                raise WholesaleCheckoutError(
                    "provider_payment_id_missing",
                    (
                        "The captured-payment event "
                        "has no payment ID."
                    ),
                )

            matches = (
                payment.get("order_id")
                == attempt.provider_order_id
                and payment.get("amount")
                == amount_to_subunits(
                    attempt.amount_including_gst
                )
                and payment.get("currency")
                == attempt.currency
            )

            if not matches:
                raise WholesaleCheckoutError(
                    "webhook_payment_mismatch",
                    (
                        "The webhook payment did not "
                        "match the wholesale attempt."
                    ),
                )

            captured = (
                payment.get("status") == "captured"
                or payment.get("captured") is True
            )

            if not captured:
                raise WholesaleCheckoutError(
                    "webhook_payment_not_captured",
                    (
                        "The webhook payment is not "
                        "captured."
                    ),
                )

            confirm_wholesale_online_payment(
                payment_attempt=attempt,
                provider_payment_id=provider_payment_id,
                provider_signature=signature,
                signature_verified=True,
                response_payload=payload,
            )

        elif event_type == "payment.failed":
            fail_wholesale_payment(
                payment_attempt=attempt,
                response_payload=payload,
            )

        else:
            event.status = (
                WholesalePaymentWebhookEvent
                .Status.IGNORED
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

    except WholesaleCheckoutError as exc:
        event.status = (
            WholesalePaymentWebhookEvent.Status.FAILED
        )
        event.error_message = f"{exc.code}: {exc}"
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
        WholesalePaymentWebhookEvent.Status.PROCESSED
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


def _staff_access_error(request):
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
            "wholesale_orders.change_wholesaleorder"
        )
    ):
        return _error_response(
            code="order_permission_required",
            message=(
                "Wholesale Order Manager permission "
                "is required."
            ),
            status=403,
        )

    return None


@login_required
@require_GET
def staff_order_list(request):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    form = StaffWholesaleOrderListForm(request.GET)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the staff order-list request.",
            status=400,
            fields=_form_errors(form),
        )

    queryset = WholesaleOrder.objects.select_related(
        "wholesale_account",
        "wholesale_account__user",
    )

    status_value = form.cleaned_data.get("status")
    payment_status = form.cleaned_data.get(
        "payment_status"
    )
    query = form.cleaned_data.get("q")

    if status_value:
        queryset = queryset.filter(status=status_value)

    if payment_status:
        queryset = queryset.filter(
            payment_status=payment_status
        )

    if query:
        queryset = queryset.filter(
            Q(order_number__icontains=query)
            | Q(
                wholesale_account__business_name__icontains=query
            )
            | Q(
                wholesale_account__reference_id__icontains=query
            )
        )

    page_size = (
        form.cleaned_data.get("page_size")
        or 50
    )
    page_number = (
        form.cleaned_data.get("page")
        or 1
    )
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
            },
            "orders": [
                _serialize_order_summary(order)
                for order in page.object_list
            ],
        }
    )


@login_required
@require_GET
def staff_order_detail(request, order_number):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    order = get_object_or_404(
        _order_detail_queryset(),
        order_number=order_number,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def staff_confirm_bank_transfer(
    request,
    order_number,
):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    form = StaffBankTransferConfirmationForm(
        request.POST
    )

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the bank-transfer details.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        WholesaleOrder,
        order_number=order_number,
    )
    attempt = get_object_or_404(
        WholesalePaymentAttempt,
        order=order,
        method=(
            WholesalePaymentAttempt
            .Method.BANK_TRANSFER
        ),
        status=WholesalePaymentAttempt.Status.PENDING,
    )

    try:
        confirm_wholesale_bank_transfer(
            payment_attempt=attempt,
            actor=request.user,
            transfer_reference=form.cleaned_data[
                "transfer_reference"
            ],
            response_payload={
                "note": (
                    form.cleaned_data.get("note")
                    or ""
                ),
            },
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def staff_start_processing(
    request,
    order_number,
):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    form = StaffWholesaleOrderNoteForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the processing request.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        WholesaleOrder,
        order_number=order_number,
    )

    try:
        start_wholesale_order_processing(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def staff_mark_shipped(request, order_number):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    form = StaffWholesaleShipmentForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the shipment details.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        WholesaleOrder,
        order_number=order_number,
    )

    try:
        mark_wholesale_order_shipped(
            order=order,
            actor=request.user,
            carrier_name=form.cleaned_data[
                "carrier_name"
            ],
            tracking_number=form.cleaned_data[
                "tracking_number"
            ],
            note=form.cleaned_data.get("note") or "",
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_POST
def staff_mark_delivered(request, order_number):
    access_error = _staff_access_error(request)

    if access_error:
        return access_error

    form = StaffWholesaleOrderNoteForm(request.POST)

    if not form.is_valid():
        return _error_response(
            code="invalid_request",
            message="Correct the delivery request.",
            status=400,
            fields=_form_errors(form),
        )

    order = get_object_or_404(
        WholesaleOrder,
        order_number=order_number,
    )

    try:
        mark_wholesale_order_delivered(
            order=order,
            actor=request.user,
            note=form.cleaned_data.get("note") or "",
        )
    except WholesaleCheckoutError as exc:
        return _checkout_error_response(exc)

    order = get_object_or_404(
        _order_detail_queryset(),
        pk=order.pk,
    )

    return JsonResponse(
        {
            "ok": True,
            "order": _serialize_order_detail(order),
        }
    )


@login_required
@require_GET
def invoice_detail(request, order_number):
    queryset = WholesaleInvoice.objects.select_related(
        "order",
        "order__wholesale_account",
        "order__wholesale_account__user",
    )

    if (
        request.user.is_staff
        and (
            request.user.is_superuser
            or request.user.has_perm(
                "wholesale_orders.view_wholesaleinvoice"
            )
        )
    ):
        invoice = get_object_or_404(
            queryset,
            order__order_number=order_number,
        )
    else:
        invoice = get_object_or_404(
            queryset,
            order__order_number=order_number,
            order__wholesale_account__user=request.user,
        )

    response = render(
        request,
        "wholesale_orders/invoices/detail.html",
        {"invoice": invoice},
    )
    response["Content-Disposition"] = (
        f'inline; filename="{invoice.invoice_number}.html"'
    )

    return response
