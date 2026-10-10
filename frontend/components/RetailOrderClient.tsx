"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, cancelRetailOrder, getRetailOrder } from "@/lib/api";
import type { RetailOrderDetail } from "@/lib/api-types";
import { compactDate, money } from "@/lib/format";


function firstValue(...values: any[]) {
  return values.find(
    (value) =>
      value !== undefined &&
      value !== null &&
      value !== ""
  );
}

function snapshotValue(source: any, ...keys: string[]) {
  if (!source || typeof source !== "object") return undefined;

  for (const key of keys) {
    const value = source[key];
    if (
      value !== undefined &&
      value !== null &&
      value !== ""
    ) {
      return value;
    }
  }

  return undefined;
}

function displayMoney(value: any) {
  if (
    value === undefined ||
    value === null ||
    value === ""
  ) {
    return null;
  }

  const amount = Number(value);

  if (!Number.isFinite(amount)) {
    return null;
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

function displayLabel(value: any) {
  if (
    value === undefined ||
    value === null ||
    value === ""
  ) {
    return null;
  }

  if (typeof value === "string") {
    return value
      .replace(/_/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  return String(value);
}

function PoweredOrderConfiguration({ item }: { item: any }) {
  const config =
    item?.configuration_snapshot &&
    typeof item.configuration_snapshot === "object"
      ? item.configuration_snapshot
      : {};

  if (!Object.keys(config).length) {
    return null;
  }

  const lens =
    config?.lens && typeof config.lens === "object"
      ? config.lens
      : {};

  const visionType =
    lens?.vision_type && typeof lens.vision_type === "object"
      ? lens.vision_type?.name || lens.vision_type?.code
      : lens?.vision_type;

  const prescriptionId =
    config?.prescription_id ?? null;

  const prescriptionStatus =
    config?.prescription_status ?? null;

  const lensName =
    lens?.name || lens?.title || null;

  const refractiveIndex =
    lens?.refractive_index || null;

  const selectedCoatings = Array.isArray(
    config?.selected_coatings
  )
    ? config.selected_coatings
    : [];

  const quoteBreakdown = Array.isArray(
    config?.lens_quote_breakdown
  )
    ? config.lens_quote_breakdown
    : [];

  const coatingNames = selectedCoatings
    .map((coating: any) => {
      if (typeof coating === "string") return coating;

      if (typeof coating === "number") {
        const quote = quoteBreakdown.find(
          (row: any) =>
            row?.rule_id === coating ||
            row?.coating_id === coating
        );
        return quote?.name || `Coating #${coating}`;
      }

      return (
        coating?.name ||
        coating?.title ||
        coating?.label ||
        null
      );
    })
    .filter(Boolean);

  const lensTotal = Number(
    config?.lens_quote_total_including_gst || 0
  );

  const configuredTotal = Number(
    config?.configured_unit_price_including_gst || 0
  );

  const frameTotal =
    configuredTotal > 0 && lensTotal >= 0
      ? configuredTotal - lensTotal
      : 0;

  const money = (value: number) =>
    new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(value);

  const cleanStatus = prescriptionStatus
    ? String(prescriptionStatus)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (letter) =>
          letter.toUpperCase()
        )
    : null;

  return (
    <span
      style={{
        display: "grid",
        gap: 7,
        marginTop: 8,
        color: "var(--ink-soft)",
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {prescriptionId && (
        <span>
          <strong style={{ color: "var(--ink)" }}>
            Prescription
          </strong>
          {` #${prescriptionId}`}
          {cleanStatus ? ` · ${cleanStatus}` : ""}
        </span>
      )}

      {lensName && (
        <span>
          <strong style={{ color: "var(--ink)" }}>
            Lens
          </strong>
          {` · ${lensName}`}
          {visionType ? ` · ${visionType}` : ""}
          {refractiveIndex
            ? ` · Index ${refractiveIndex}`
            : ""}
        </span>
      )}

      {coatingNames.length > 0 && (
        <span>
          <strong style={{ color: "var(--ink)" }}>
            Coatings
          </strong>
          {` · ${coatingNames.join(", ")}`}
        </span>
      )}

      {(frameTotal > 0 ||
        lensTotal > 0 ||
        configuredTotal > 0) && (
        <span
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 14,
          }}
        >
          {frameTotal > 0 && (
            <span>Frame {money(frameTotal)}</span>
          )}

          {lensTotal > 0 && (
            <span>Lens {money(lensTotal)}</span>
          )}

          {configuredTotal > 0 && (
            <span>
              <strong style={{ color: "var(--ink)" }}>
                Configured {money(configuredTotal)}
              </strong>
            </span>
          )}
        </span>
      )}

      <span>
        Prescription/custom eyewear is non-refundable.
      </span>
    </span>
  );
}


export default function RetailOrderClient({ orderNumber }: { orderNumber: string }) {
  const [order, setOrder] = useState<RetailOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    getRetailOrder(orderNumber)
      .then(setOrder)
      .catch((e) => setMessage(e instanceof ApiError ? e.message : "Could not load order."))
      .finally(() => setLoading(false));
  }, [orderNumber]);

  async function cancel() {
    const reason = cancelReason.trim();
    if (!reason) { setMessage("Please enter a cancellation reason."); return; }
    setCancelling(true); setMessage(null);
    try {
      setOrder(await cancelRetailOrder(orderNumber, reason));
      setCancelOpen(false); setCancelReason("");
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not cancel order.");
    } finally { setCancelling(false); }
  }

  if (loading) return <div className="skeleton" style={{minHeight: 420}}/>;
  if (!order) return <div className="empty-state">{message || "Order not found."}</div>;
  const shipping = order.addresses?.find((a: any) => a.address_type === "shipping");

  return <div className="order-detail-layout">
    <div>
      <div className="order-detail-head"><div><div className="eyebrow">Order {order.order_number}</div><h2>{order.status_label}</h2><p>Placed {compactDate(order.created_at)} · {order.payment_method_label} · {order.payment_status_label}</p></div><span className={`status-pill ${order.status}`}>{order.status_label}</span></div>
      <div className="timeline-card">
        {order.fulfillment_groups?.map((g) => <div className="timeline-row" key={g.id}><span className={`timeline-dot ${g.status}`}/><div><strong>{g.title}</strong><p>{g.status_label}{g.carrier_name ? ` · ${g.carrier_name}` : ""}{g.tracking_number ? ` · Tracking ${g.tracking_number}` : ""}</p></div></div>)}
      </div>
      <div className="order-items-card"><h3>Items</h3>{order.items.map((item) => <div className="order-line" key={item.id}><div><strong>{item.product_name}</strong><p>{item.variant_description || item.sku}{item.configuration_snapshot ? <PoweredOrderConfiguration item={item} /> : null}</p>{item.is_non_refundable && <span className="tag">Non-refundable</span>}</div><div><span>× {item.quantity}</span><strong>{money(item.line_total_including_gst)}</strong></div></div>)}</div>
    </div>
    <aside className="summary-card">
      <h3>Order summary</h3>
      <div className="summary-row"><span>Subtotal</span><strong>{money(order.subtotal_including_gst)}</strong></div>
      <div className="summary-row"><span>Delivery</span><span>{money(order.delivery_fee_including_gst)}</span></div>
      <div className="summary-row total"><span>Total</span><span>{money(order.grand_total_including_gst)}</span></div>
      {shipping && <div className="delivery-mini"><strong>Delivery address</strong><span>{String(shipping.recipient_name)}<br/>{String(shipping.address_line_1)}<br/>{String(shipping.city)}, {String(shipping.postal_code)}</span></div>}
      {order.can_customer_cancel && !cancelOpen && <button className="btn ghost block" onClick={() => setCancelOpen(true)}>Cancel order</button>}
      {cancelOpen && <div className="cancel-panel"><label>Cancellation reason</label><textarea rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Tell us why you need to cancel"/><div className="cancel-actions"><button type="button" className="text-button" onClick={() => {setCancelOpen(false);setCancelReason("");}}>Keep order</button><button type="button" className="btn danger-button" disabled={cancelling || !cancelReason.trim()} onClick={() => void cancel()}>{cancelling ? "Cancelling…" : "Confirm cancellation"}</button></div></div>}
      
      <div className="form-message">
        Cancellation is unavailable during the initial launch phase.
      </div>

      {message && <div className="form-message">{message}</div>}

        <a
          className="btn ghost block"
          href={`/backend/retail/orders/${encodeURIComponent(
            orderNumber
          )}/invoice/`}
          download={`Chokher-Alo-Invoice-${orderNumber}.pdf`}
        >
          Download invoice
        </a>


      <Link href="/account/orders" className="text-button">← Back to orders</Link>
    </aside>
  </div>;
}
