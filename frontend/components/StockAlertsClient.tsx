"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, cancelStockAlert, getStockAlerts } from "@/lib/api";
import type { ProductStockAlert } from "@/lib/api-types";
import { compactDate } from "@/lib/format";

export default function StockAlertsClient() {
  const [alerts, setAlerts] = useState<ProductStockAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getStockAlerts()
      .then(setAlerts)
      .catch((error) => setMessage(error instanceof ApiError ? error.message : "Could not load stock alerts."))
      .finally(() => setLoading(false));
  }, []);

  async function cancel(id: number) {
    setBusyId(id);
    setMessage(null);
    try {
      await cancelStockAlert(id);
      setAlerts((items) => items.filter((item) => item.id !== id));
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not cancel this alert.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="skeleton" style={{ minHeight: 110 }} />;

  return (
    <div>
      {alerts.length === 0 ? <div className="account-inline-empty">No active stock alerts.</div> : (
        <div className="stock-alert-list">
          {alerts.map((alert) => (
            <div className="stock-alert-row" key={alert.id}>
              <div><Link className="stock-alert-sku" href={`/product/${encodeURIComponent(alert.sku)}`}>{alert.sku}</Link><span>{alert.channel_label} · {alert.destination} · added {compactDate(alert.created_at)}</span></div>
              <button type="button" className="text-button" disabled={busyId === alert.id} onClick={() => void cancel(alert.id)}>{busyId === alert.id ? "Cancelling…" : "Cancel alert"}</button>
            </div>
          ))}
        </div>
      )}
      {message && <div className="form-message">{message}</div>}
    </div>
  );
}
