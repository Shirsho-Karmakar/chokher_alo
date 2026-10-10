"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getRetailOrders } from "@/lib/api";
import type { RetailOrderSummary } from "@/lib/api-types";
import { compactDate, money } from "@/lib/format";
import { ArrowIcon } from "./Icons";

export default function OrdersClient() {
  const [orders, setOrders] = useState<RetailOrderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => { getRetailOrders().then(setOrders).catch((error) => setMessage(error instanceof ApiError ? error.message : "Could not load orders.")).finally(() => setLoading(false)); }, []);
  if (loading) return <div className="skeleton" style={{minHeight: 280}}/>;
  if (message) return <div className="empty-state">{message}<div className="form-actions" style={{justifyContent:"center"}}><Link className="btn primary" href="/login?next=/account/orders">Sign in</Link></div></div>;
  if (!orders.length) return <div className="empty-state">No orders yet.<div className="form-actions" style={{justifyContent:"center"}}><Link href="/shop" className="btn primary">Start shopping</Link></div></div>;
  return <div className="order-list">{orders.map((o) => <Link href={`/account/orders/${o.order_number}`} className="order-card order-link" key={o.order_number}><div><div className="order-number">{o.order_number}</div><div className="order-meta"><span>{compactDate(o.created_at)}</span><span className={`status-pill ${o.status}`}>{o.status_label}</span><span>{o.payment_status_label}</span><span>{o.fulfillment_method_label}</span></div></div><div className="order-total"><strong>{money(o.grand_total_including_gst)}</strong><ArrowIcon size={16}/></div></Link>)}</div>;
}
