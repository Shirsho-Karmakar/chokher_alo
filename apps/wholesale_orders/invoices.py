from django.conf import settings
from django.db import transaction

from .models import WholesaleInvoice, WholesaleOrder


def _address_snapshot(address):
    return {
        "recipient_name": address.recipient_name,
        "business_name": address.business_name,
        "phone_number": address.phone_number,
        "invoice_email": address.invoice_email,
        "gstin": address.gstin or None,
        "address_line_1": address.address_line_1,
        "address_line_2": address.address_line_2 or None,
        "landmark": address.landmark or None,
        "city": address.city,
        "district": address.district or None,
        "state": address.state,
        "postal_code": address.postal_code,
    }


def _item_snapshot(item):
    return {
        "order_item_id": item.pk,
        "sku": item.variant_snapshot.get("sku"),
        "catalogue_code": item.variant_snapshot.get(
            "catalogue_code"
        ),
        "name": item.variant_snapshot.get("name"),
        "eye": item.eye,
        "boxes": item.boxes,
        "physical_units": item.physical_units_reserved,
        "gst_rate": item.variant_snapshot.get("gst_rate"),
        "base_box_price_including_gst": str(
            item.base_box_price_including_gst
        ),
        "applied_box_price_including_gst": str(
            item.applied_box_price_including_gst
        ),
        "discount_per_box_including_gst": str(
            item.discount_per_box_including_gst
        ),
        "subtotal_including_gst": str(
            item.subtotal_including_gst
        ),
        "variant": item.variant_snapshot,
        "prescription": item.prescription_snapshot,
        "pricing": item.pricing_snapshot,
    }


@transaction.atomic
def issue_wholesale_invoice(*, order):
    order = (
        WholesaleOrder.objects
        .select_for_update(of=("self",))
        .select_related("billing_address")
        .prefetch_related("items")
        .get(pk=order.pk)
    )

    existing = WholesaleInvoice.objects.filter(
        order=order
    ).first()

    if existing is not None:
        return existing, False

    if (
        order.payment_status
        != WholesaleOrder.PaymentStatus.PAID
    ):
        raise ValueError(
            "A wholesale invoice requires a paid order."
        )

    invoice = WholesaleInvoice.objects.create(
        order=order,
        currency="INR",
        seller_snapshot={
            "name": settings.WHOLESALE_INVOICE_SELLER_NAME,
            "gstin": (
                settings.WHOLESALE_INVOICE_SELLER_GSTIN
                or None
            ),
            "address": (
                settings.WHOLESALE_INVOICE_SELLER_ADDRESS
                or None
            ),
            "state": (
                settings.WHOLESALE_INVOICE_SELLER_STATE
                or None
            ),
            "email": (
                settings.WHOLESALE_INVOICE_SELLER_EMAIL
                or None
            ),
        },
        business_snapshot=dict(
            order.business_snapshot or {}
        ),
        billing_address_snapshot=_address_snapshot(
            order.billing_address
        ),
        items_snapshot=[
            _item_snapshot(item)
            for item in order.items.all()
        ],
        subtotal_including_gst=(
            order.subtotal_including_gst
        ),
        delivery_fee_including_gst=(
            order.delivery_fee_including_gst
        ),
        grand_total_including_gst=(
            order.grand_total_including_gst
        ),
    )

    return invoice, True
