from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _value(obj: Any, *names: str, default=None):
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)

        if value not in (None, ""):
            return value

    return default


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value) -> str:
    return f"INR {_decimal(value):,.2f}"


def _display(obj: Any, field: str, fallback=""):
    method = getattr(obj, f"get_{field}_display", None)
    if callable(method):
        try:
            return method()
        except Exception:
            pass

    value = getattr(obj, field, None)
    return str(value if value not in (None, "") else fallback)


def _user_name(user) -> str:
    if user is None:
        return ""

    get_full_name = getattr(user, "get_full_name", None)
    if callable(get_full_name):
        name = (get_full_name() or "").strip()
        if name:
            return name

    for field in ("name", "full_name", "email", "username"):
        value = getattr(user, field, None)
        if value:
            return str(value)

    return ""


def _address_snapshot(order) -> dict:
    for name in (
        "shipping_address_snapshot",
        "delivery_address_snapshot",
        "address_snapshot",
        "billing_address_snapshot",
    ):
        value = getattr(order, name, None)
        if isinstance(value, dict) and value:
            return value

    address_obj = None
    for name in (
        "shipping_address",
        "delivery_address",
        "address",
        "billing_address",
    ):
        value = getattr(order, name, None)
        if value is not None:
            address_obj = value
            break

    if address_obj is None:
        return {}

    result = {}
    for field in (
        "recipient_name",
        "name",
        "phone",
        "address_line_1",
        "address_line_2",
        "locality",
        "city",
        "district",
        "state",
        "postal_code",
        "pincode",
        "landmark",
    ):
        value = getattr(address_obj, field, None)
        if value not in (None, ""):
            result[field] = value

    return result


def _address_lines(snapshot: dict) -> list[str]:
    if not snapshot:
        return []

    lines = []

    recipient = _value(
        snapshot,
        "recipient_name",
        "name",
        "full_name",
    )
    if recipient:
        lines.append(str(recipient))

    line1 = _value(
        snapshot,
        "address_line_1",
        "line1",
        "address1",
        "street",
    )
    line2 = _value(
        snapshot,
        "address_line_2",
        "line2",
        "address2",
    )

    if line1:
        lines.append(str(line1))
    if line2:
        lines.append(str(line2))

    place_parts = [
        _value(snapshot, "locality"),
        _value(snapshot, "city"),
        _value(snapshot, "district"),
    ]
    place = ", ".join(str(v) for v in place_parts if v)
    if place:
        lines.append(place)

    state = _value(snapshot, "state")
    postal = _value(snapshot, "postal_code", "pincode", "pin_code")
    state_postal = " ".join(str(v) for v in (state, postal) if v)
    if state_postal:
        lines.append(state_postal)

    phone = _value(snapshot, "phone", "phone_number", "mobile")
    if phone:
        lines.append(f"Phone: {phone}")

    return lines


def _item_name(item) -> str:
    direct = _value(
        item,
        "product_name",
        "name",
        "title",
        "sku",
    )
    if direct:
        return str(direct)

    snapshot = _value(
        item,
        "product_snapshot",
        "offer_snapshot",
        "variant_snapshot",
        default={},
    )
    if isinstance(snapshot, dict):
        return str(
            _value(
                snapshot,
                "name",
                "title",
                "product_name",
                "sku",
                default="Item",
            )
        )

    return "Item"


def _item_sku(item) -> str:
    direct = _value(item, "sku", "product_sku", default="")
    if direct:
        return str(direct)

    for snap_name in (
        "product_snapshot",
        "offer_snapshot",
        "variant_snapshot",
    ):
        snapshot = getattr(item, snap_name, None)
        if isinstance(snapshot, dict):
            value = _value(snapshot, "sku", "product_sku")
            if value:
                return str(value)

    return ""


def _item_qty(item) -> int:
    value = _value(item, "quantity", "qty", default=1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _item_total(item) -> Decimal:
    return _decimal(
        _value(
            item,
            "line_total_including_gst",
            "subtotal_including_gst",
            "total_including_gst",
            "line_total",
            "subtotal",
            default=0,
        )
    )


def _item_unit(item, qty: int, total: Decimal) -> Decimal:
    explicit = _value(
        item,
        "configured_unit_price_including_gst",
        "unit_price_including_gst",
        "unit_price",
        default=None,
    )
    if explicit is not None:
        return _decimal(explicit)

    if qty:
        return total / Decimal(qty)

    return total




def _configuration_lines(item) -> list[str]:
    config = _value(
        item,
        "configuration_snapshot",
        "configuration",
        "config_snapshot",
        default={},
    )

    if not isinstance(config, dict) or not config:
        return []

    lines = []

    prescription_id = config.get("prescription_id")
    prescription_status = config.get("prescription_status")

    if prescription_id:
        prescription_text = f"Prescription #{prescription_id}"

        if prescription_status:
            status = (
                str(prescription_status)
                .replace("_", " ")
                .title()
            )
            prescription_text += f" - {status}"

        lines.append(prescription_text)

    lens = config.get("lens")
    if not isinstance(lens, dict):
        lens = {}

    lens_name = lens.get("name") or lens.get("title")

    vision = lens.get("vision_type")
    if isinstance(vision, dict):
        vision_name = vision.get("name") or vision.get("code")
    else:
        vision_name = vision

    refractive_index = lens.get("refractive_index")

    if lens_name:
        lens_text = f"Lens: {lens_name}"

        if vision_name:
            lens_text += f" - {vision_name}"

        if refractive_index:
            lens_text += f" - Index {refractive_index}"

        lines.append(lens_text)

    selected_coatings = config.get("selected_coatings") or []
    quote_breakdown = config.get("lens_quote_breakdown") or []

    coating_names = []

    if isinstance(selected_coatings, list):
        for coating in selected_coatings:
            if isinstance(coating, str):
                coating_names.append(coating)

            elif isinstance(coating, dict):
                name = (
                    coating.get("name")
                    or coating.get("title")
                    or coating.get("label")
                )
                if name:
                    coating_names.append(str(name))

            elif isinstance(coating, int):
                match = next(
                    (
                        row
                        for row in quote_breakdown
                        if isinstance(row, dict)
                        and (
                            row.get("rule_id") == coating
                            or row.get("coating_id") == coating
                        )
                    ),
                    None,
                )

                if match and match.get("name"):
                    coating_names.append(str(match["name"]))
                else:
                    coating_names.append(f"Coating #{coating}")

    if coating_names:
        lines.append(
            "Coatings: " + ", ".join(coating_names)
        )

    lens_total = _decimal(
        config.get("lens_quote_total_including_gst")
    )
    configured_total = _decimal(
        config.get("configured_unit_price_including_gst")
    )

    frame_total = configured_total - lens_total

    price_parts = []

    if frame_total > 0:
        price_parts.append(f"Frame {_money(frame_total)}")

    if lens_total > 0:
        price_parts.append(f"Lens {_money(lens_total)}")

    if configured_total > 0:
        price_parts.append(
            f"Configured total {_money(configured_total)}"
        )

    if price_parts:
        lines.append(" | ".join(price_parts))

    if prescription_id or lens_name:
        lines.append(
            "Prescription/custom eyewear is non-refundable."
        )

    return lines


def build_retail_invoice_pdf(order) -> bytes:
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {order.order_number}",
        author="Chokher Alo",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceBrand",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=24,
        textColor=colors.HexColor("#0b1f2a"),
        spaceAfter=4,
    )

    invoice_title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#0b1f2a"),
        alignment=TA_RIGHT,
        spaceAfter=3,
    )

    small = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#57616a"),
    )

    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1a252d"),
    )

    body_right = ParagraphStyle(
        "BodyRight",
        parent=body,
        alignment=TA_RIGHT,
    )

    section = ParagraphStyle(
        "Section",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#0b1f2a"),
        spaceAfter=5,
    )

    seller_name = getattr(settings, "INVOICE_SELLER_NAME", "Chokher Alo")
    seller_address = getattr(settings, "INVOICE_SELLER_ADDRESS", "")
    seller_gstin = getattr(settings, "INVOICE_SELLER_GSTIN", "")
    seller_email = getattr(settings, "INVOICE_SELLER_EMAIL", "")
    seller_phone = getattr(settings, "INVOICE_SELLER_PHONE", "")

    created = getattr(order, "created_at", None)
    if created:
        try:
            created = timezone.localtime(created)
        except Exception:
            pass
        invoice_date = created.strftime("%d %b %Y")
    else:
        invoice_date = timezone.localdate().strftime("%d %b %Y")

    header_left = [
        Paragraph(str(seller_name).upper(), title_style),
        Paragraph("Eyewear and prescription lenses", small),
    ]

    seller_extra = [
        value
        for value in (
            seller_address,
            f"GSTIN: {seller_gstin}" if seller_gstin else "",
            seller_email,
            seller_phone,
        )
        if value
    ]

    if seller_extra:
        header_left.append(
            Paragraph("<br/>".join(map(str, seller_extra)), small)
        )

    header_right = [
        Paragraph("INVOICE", invoice_title_style),
        Paragraph(
            f"<b>Order:</b> {order.order_number}<br/>"
            f"<b>Date:</b> {invoice_date}",
            body_right,
        ),
    ]

    header = Table(
        [[header_left, header_right]],
        colWidths=[112 * mm, 50 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -1),
                    0.7,
                    colors.HexColor("#d8dde1"),
                ),
            ]
        )
    )

    story = [header, Spacer(1, 9 * mm)]

    user = getattr(order, "user", None)
    customer_name = _user_name(user)
    customer_email = getattr(user, "email", "") if user else ""

    address = _address_snapshot(order)
    address_lines = _address_lines(address)

    bill_to = [
        Paragraph("BILL TO", section),
        Paragraph(
            "<br/>".join(
                [
                    value
                    for value in (
                        customer_name,
                        customer_email,
                        *address_lines,
                    )
                    if value
                ]
            )
            or "-",
            body,
        ),
    ]

    payment_method = _display(order, "payment_method", fallback="")
    payment_status = _display(order, "payment_status", fallback="")
    order_status = _display(order, "status", fallback="")

    order_info = [
        Paragraph("ORDER DETAILS", section),
        Paragraph(
            f"<b>Status:</b> {order_status}<br/>"
            f"<b>Payment:</b> {payment_method or '-'}"
            f"{' - ' + payment_status if payment_status else ''}<br/>"
            f"<b>Currency:</b> {getattr(order, 'currency', 'INR') or 'INR'}",
            body,
        ),
    ]

    info_table = Table(
        [[bill_to, order_info]],
        colWidths=[100 * mm, 62 * mm],
    )
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#e1e5e8"),
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor("#edf0f2"),
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 8 * mm)])

    item_rows = [
        [
            Paragraph("<b>Item</b>", body),
            Paragraph("<b>Qty</b>", body_right),
            Paragraph("<b>Unit price</b>", body_right),
            Paragraph("<b>Total</b>", body_right),
        ]
    ]

    try:
        items = list(order.items.all())
    except Exception:
        items = []

    for item in items:
        qty = _item_qty(item)
        total = _item_total(item)
        unit = _item_unit(item, qty, total)
        sku = _item_sku(item)

        description = _item_name(item)
        if sku:
            description = (
                f"{description}<br/>"
                f"<font size='7.5' color='#6b747b'>{sku}</font>"
            )

        configuration_lines = _configuration_lines(item)
        if configuration_lines:
            description += (
                "<br/><font size='7.5' color='#4f5d66'>"
                + "<br/>".join(configuration_lines)
                + "</font>"
            )

        item_rows.append(
            [
                Paragraph(description, body),
                Paragraph(str(qty), body_right),
                Paragraph(_money(unit), body_right),
                Paragraph(_money(total), body_right),
            ]
        )

    if len(item_rows) == 1:
        fallback_subtotal = _value(
            order,
            "subtotal_including_gst",
            default=0,
        )
        item_rows.append(
            [
                Paragraph("Order item", body),
                Paragraph("1", body_right),
                Paragraph(_money(fallback_subtotal), body_right),
                Paragraph(_money(fallback_subtotal), body_right),
            ]
        )

    items_table = Table(
        item_rows,
        colWidths=[82 * mm, 20 * mm, 30 * mm, 30 * mm],
        repeatRows=1,
    )

    items_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#f1f4f5"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#0b1f2a"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.45,
                    colors.HexColor("#dfe4e7"),
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.extend([items_table, Spacer(1, 7 * mm)])

    subtotal = _value(
        order,
        "subtotal_including_gst",
        "subtotal",
        default=0,
    )
    delivery = _value(
        order,
        "delivery_fee_including_gst",
        "delivery_fee",
        default=0,
    )
    grand_total = _value(
        order,
        "grand_total_including_gst",
        "grand_total",
        "total_including_gst",
        default=0,
    )

    totals = Table(
        [
            ["Subtotal", _money(subtotal)],
            ["Delivery", _money(delivery)],
            ["Total", _money(grand_total)],
        ],
        colWidths=[42 * mm, 38 * mm],
        hAlign="RIGHT",
    )

    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                (
                    "LINEABOVE",
                    (0, -1),
                    (-1, -1),
                    0.8,
                    colors.HexColor("#0b1f2a"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(totals)
    story.append(Spacer(1, 10 * mm))

    story.append(
        KeepTogether(
            [
                Paragraph(
                    "Prices shown are inclusive of applicable GST. "
                    "This invoice was generated electronically from "
                    "the Chokher Alo order record.",
                    small,
                ),
                Spacer(1, 3 * mm),
                Paragraph(
                    "Thank you for shopping with Chokher Alo.",
                    body,
                ),
            ]
        )
    )

    document.build(story)
    return buffer.getvalue()
