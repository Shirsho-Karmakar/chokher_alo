"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError, cancelWholesaleOrder, getWholesaleOrder } from "@/lib/api";
import type { WholesaleOrderDetail } from "@/lib/api-types";
import { compactDate, money } from "@/lib/format";

export default function WholesaleOrderClient({ orderNumber }: { orderNumber: string }) {
  const [order, setOrder] = useState<WholesaleOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    getWholesaleOrder(orderNumber)
      .then(setOrder)
      .catch((error) => {
        setMessage(
          error instanceof ApiError
            ? error.message
            : "Could not load trade order."
        );
      })
      .finally(() => setLoading(false));
  }, [orderNumber]);

  const latestPayment = useMemo(() => {
    if (!order?.payment_attempts?.length) return null;
    return [...order.payment_attempts].sort((a, b) => b.id - a.id)[0];
  }, [order]);

  async function cancel() {
    const reason = cancelReason.trim();
    if (!reason) return;

    setCancelling(true);
    setMessage(null);

    try {
      setOrder(await cancelWholesaleOrder(orderNumber, reason));
      setCancelOpen(false);
      setCancelReason("");
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not cancel order."
      );
    } finally {
      setCancelling(false);
    }
  }

  if (loading) {
    return <div className="skeleton" style={{ minHeight: 400 }} />;
  }

  if (!order) {
    return <div className="empty-state">{message || "Trade order not found."}</div>;
  }

  return (
    <div className="order-detail-layout">
      <div>
        <div className="order-detail-head">
          <div>
            <div className="eyebrow">Trade order {order.order_number}</div>
            <h2>{order.status_label}</h2>
            <p>
              Placed {compactDate(order.created_at)} - {order.payment_status_label}
            </p>
          </div>
          <span className={`status-pill ${order.status}`}>
            {order.status_label}
          </span>
        </div>

        <div className="timeline-card">
          <div className="timeline-row">
            <span className={`timeline-dot ${order.fulfillment?.status || ""}`} />
            <div>
              <strong>Fulfilment</strong>
              <p>
                {order.fulfillment?.status_label || order.fulfillment_status_label}
                {order.fulfillment?.carrier_name
                  ? ` - ${order.fulfillment.carrier_name}`
                  : ""}
                {order.fulfillment?.tracking_number
                  ? ` - Tracking ${order.fulfillment.tracking_number}`
                  : ""}
              </p>
            </div>
          </div>
        </div>

        <div className="order-items-card">
          <h3>Lens boxes</h3>

          {order.items.map((item) => {
            const unitsPerBox =
              item.boxes > 0
                ? Math.round(item.physical_units / item.boxes)
                : 0;

            return (
              <div
                className="order-line"
                key={item.id}
                style={{ alignItems: "flex-start" }}
              >
                <div style={{ display: "grid", gap: 7 }}>
                  <strong>{item.name || item.sku}</strong>

                  <p style={{ margin: 0 }}>
                    {item.sku}
                    {item.eye ? ` - ${item.eye}` : ""}
                  </p>

                  <div
                    style={{
                      display: "flex",
                      gap: 18,
                      flexWrap: "wrap",
                      color: "var(--ink-soft)",
                      fontSize: 12
                    }}
                  >
                    <span>
                      <strong>{item.boxes}</strong>{" "}
                      {item.boxes === 1 ? "box" : "boxes"}
                    </span>

                    <span>
                      <strong>{unitsPerBox}</strong> lenses / box
                    </span>

                    <span>
                      <strong>{item.physical_units}</strong> total lenses
                    </span>

                    <span>
                      {money(item.box_price_including_gst)} / box
                    </span>
                  </div>
                </div>

                <strong>{money(item.subtotal_including_gst)}</strong>
              </div>
            );
          })}
        </div>

        <div className="order-items-card" style={{ marginTop: 16 }}>
          <h3>Payment</h3>

          <div className="spec-row">
            <span>Status</span>
            <strong>{order.payment_status_label}</strong>
          </div>

          {latestPayment && (
            <>
              <div className="spec-row">
                <span>Method</span>
                <strong>{latestPayment.method_label}</strong>
              </div>

              <div className="spec-row">
                <span>Amount</span>
                <strong>{money(latestPayment.amount_including_gst)}</strong>
              </div>

              {latestPayment.paid_at && (
                <div className="spec-row">
                  <span>Paid</span>
                  <strong>{compactDate(latestPayment.paid_at)}</strong>
                </div>
              )}
            </>
          )}

          {order.payment_status === "paid" && (
            <div className="form-message" style={{ marginTop: 12 }}>
              Payment verified successfully.
            </div>
          )}
        </div>

        <div className="order-items-card" style={{ marginTop: 16 }}>
          <h3>Billing</h3>

          <div
            style={{
              display: "grid",
              gap: 5,
              color: "var(--ink-soft)",
              fontSize: 13,
              lineHeight: 1.55
            }}
          >
            <strong style={{ color: "var(--ink)" }}>
              {order.billing_address.business_name ||
                order.billing_address.recipient_name}
            </strong>

            <span>{order.billing_address.recipient_name}</span>

            <span>
              {order.billing_address.address_line_1}
              {order.billing_address.address_line_2
                ? `, ${order.billing_address.address_line_2}`
                : ""}
            </span>

            <span>
              {order.billing_address.city}
              {order.billing_address.district
                ? `, ${order.billing_address.district}`
                : ""}
              {` - ${order.billing_address.state} ${order.billing_address.postal_code}`}
            </span>

            {order.billing_address.gstin && (
              <span>GSTIN: {order.billing_address.gstin}</span>
            )}

            <span>Invoice: {order.billing_address.invoice_email}</span>
          </div>
        </div>
      </div>

      <aside className="summary-card">
        <h3>Invoice summary</h3>

        <div className="summary-row">
          <span>Boxes</span>
          <strong>{order.total_boxes}</strong>
        </div>

        <div className="summary-row">
          <span>Total lenses</span>
          <strong>
            {order.items.reduce(
              (sum, item) => sum + item.physical_units,
              0
            )}
          </strong>
        </div>

        <div className="summary-row">
          <span>Subtotal</span>
          <strong>{money(order.subtotal_including_gst)}</strong>
        </div>

        <div className="summary-row">
          <span>Delivery</span>
          <span>{money(order.delivery_fee_including_gst)}</span>
        </div>

        <div className="summary-row total">
          <span>Total</span>
          <span>{money(order.grand_total_including_gst)}</span>
        </div>

        <a
          className="btn ghost block"
          href={`/backend/api/wholesale/orders/${encodeURIComponent(
            orderNumber
          )}/invoice/`}
        
          download={`Chokher-Alo-Trade-Invoice-${orderNumber}.pdf`}>
          Download invoice
        </a>

        {false && ["payment_pending", "confirmed"].includes(order?.status || "") &&
          !cancelOpen && (
            <button
              className="btn ghost block"
              onClick={() => setCancelOpen(true)}
            >
              Cancel order
            </button>
          )}

        {cancelOpen && (
          <div className="cancel-panel">
            <label>Cancellation reason</label>

            <textarea
              rows={3}
              value={cancelReason}
              onChange={(event) => setCancelReason(event.target.value)}
              placeholder="Reason for cancelling this trade order"
            />

            <div className="cancel-actions">
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  setCancelOpen(false);
                  setCancelReason("");
                }}
              >
                Keep order
              </button>

              <button
                type="button"
                className="btn danger-button"
                disabled={cancelling || !cancelReason.trim()}
                onClick={() => void cancel()}
              >
                {cancelling ? "Cancelling..." : "Confirm cancellation"}
              </button>
            </div>
          </div>
        )}

        
        <div className="form-message">
          Cancellation is unavailable during the initial launch phase.
        </div>

        {message && <div className="form-message">{message}</div>}

        <Link className="text-button" href="/wholesale/orders">
          Back to orders
        </Link>
      </aside>
    </div>
  );
}
