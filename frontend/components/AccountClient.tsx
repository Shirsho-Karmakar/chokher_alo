"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getSession, logoutSession } from "@/lib/api";
import type { SessionStatus } from "@/lib/api-types";
import AddressBook from "./AddressBook";
import StockAlertsClient from "./StockAlertsClient";

export default function AccountClient() {
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => { getSession().then(setSession).catch((e) => setMessage(e instanceof ApiError ? e.message : "Could not load account.")).finally(() => setLoading(false)); }, []);

  async function signOut() {
    try { await logoutSession(); window.location.href = "/"; } catch (e) { setMessage(e instanceof ApiError ? e.message : "Could not sign out."); }
  }

  if (loading) return <div className="skeleton" style={{minHeight: 380}}/>;
  if (!session?.authenticated) return <div className="empty-state">Sign in to manage your Chokher Alo account.<div className="form-actions" style={{justifyContent:"center"}}><Link className="btn primary" href="/login?next=/account">Sign in with phone</Link></div></div>;

  return <div className="account-stack">
    <div className="account-welcome">
      <div><div className="eyebrow">Signed in</div><h2>{session.user?.phone_number || "Your account"}</h2><p>Orders, prescriptions and delivery addresses in one place.</p></div>
      <button className="btn ghost" onClick={() => void signOut()}>Sign out</button>
    </div>
    <div className="dashboard-grid">
      <Link href="/account/orders" className="dashboard-card"><div className="category-kicker">Orders</div><div className="metric">Track</div><p>Order status, payment and delivery tracking.</p></Link>
      <Link href="/prescription" className="dashboard-card"><div className="category-kicker">Prescriptions</div><div className="metric">Manage</div><p>Upload prescriptions and see approved compatible lenses.</p></Link>
      <Link href="/wishlist" className="dashboard-card"><div className="category-kicker">Wishlist</div><div className="metric">Saved</div><p>Return to frames you liked.</p></Link>
    </div>
    <section className="account-section"><div className="section-heading simple"><div><div className="eyebrow">Delivery</div><h2>Saved addresses</h2><p>West Bengal addresses used during checkout.</p></div></div><AddressBook/></section>
    <section className="account-section"><div className="section-heading simple"><div><div className="eyebrow">Availability</div><h2>Stock alerts</h2><p>Active SMS/email notifications for products you are waiting for.</p></div></div><StockAlertsClient/></section>
    {message && <div className="form-message">{message}</div>}
  </div>;
}
