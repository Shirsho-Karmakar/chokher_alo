"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, confirmWholesaleRazorpay, createWholesaleCheckout, getAddresses, getWholesaleCart, getWholesaleProfile } from "@/lib/api";
import type { Address, PaymentSession, WholesaleCart, WholesaleProfile } from "@/lib/api-types";
import { money } from "@/lib/format";

function loadRazorpay() {
  return new Promise<boolean>((resolve) => {
    if ((window as any).Razorpay) return resolve(true);
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export default function WholesaleCheckoutClient() {
  const [cart, setCart] = useState<WholesaleCart | null>(null);
  const [profile, setProfile] = useState<WholesaleProfile | null>(null);
  const [billingAddress, setBillingAddress] = useState<Address | null>(null);
  const [method, setMethod] = useState<"razorpay" | "bank_transfer">("razorpay");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    Promise.all([getWholesaleCart(), getWholesaleProfile(), getAddresses()])
      .then(([nextCart, nextProfile, addresses]) => {
        setCart(nextCart);
        setProfile(nextProfile);
        setBillingAddress(addresses.find((address) => address.is_default_billing) || null);
      })
      .catch((error) => {
        setAuthRequired(error instanceof ApiError && error.code === "authentication_required");
        setMessage(error instanceof ApiError ? error.message : "Could not prepare trade checkout.");
      })
      .finally(() => setLoading(false));
  }, []);

  async function pay(session: PaymentSession, orderNumber: string) {
    if (!await loadRazorpay()) throw new Error("Razorpay could not be loaded.");
    return new Promise<void>((resolve, reject) => {
      const Razorpay = (window as any).Razorpay;
      const checkout = new Razorpay({
        key: session.key_id,
        amount: session.amount_subunits,
        currency: session.currency,
        name: "Chokher Alo Trade",
        description: `Wholesale ${orderNumber}`,
        order_id: session.provider_order_id,
        handler: async (response: any) => {
          try {
            const result = await confirmWholesaleRazorpay({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature
            });
            window.location.href = `/wholesale/orders/${result.order.order_number}`;
            resolve();
          } catch (error) {
            reject(error);
          }
        },
        modal: { ondismiss: () => reject(new Error("Payment window closed. The order remains available in your trade account.")) }
      });
      checkout.open();
    });
  }

  async function place() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await createWholesaleCheckout(method, notes);
      const orderNumber = String(result.order.order_number);
      if (result.payment_session) await pay(result.payment_session, orderNumber);
      else window.location.href = `/wholesale/orders/${orderNumber}`;
    } catch (error) {
      if (error instanceof ApiError && error.code === "authentication_required") {
        window.location.href = `/wholesale/login?next=${encodeURIComponent("/wholesale/checkout")}`;
        return;
      }
      setMessage(error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Could not place trade order.");
      setBusy(false);
    }
  }

  if (loading) return <div className="skeleton" style={{ minHeight: 400 }} />;
  if (!cart || !profile) return <div className="empty-state">{message || "Trade checkout unavailable."}<div className="form-actions" style={{ justifyContent: "center" }}>{authRequired && <Link href="/wholesale/login?next=/wholesale/checkout" className="btn primary">Trade sign in</Link>}</div></div>;
  if (!cart.readiness.ready) return <div className="empty-state">Your trade cart is not ready for checkout.<div className="form-actions" style={{ justifyContent: "center" }}><Link href="/wholesale/profile" className="btn primary">Complete profile</Link><Link href="/wholesale/cart" className="btn ghost">Back to cart</Link></div></div>;

  return (
    <div className="checkout-layout">
      <div className="checkout-main">
        <section className="checkout-step">
          <div className="step-head"><span>1</span><div><h2>Business & billing</h2><p>These details will be captured on the wholesale order and invoice.</p></div></div>
          <div className="business-review">
            <strong>{profile.business_name}</strong>
            <span>{profile.contact_person_name}</span>
            <span>{profile.invoice_email}</span>
            {profile.gstin && <span>GSTIN {profile.gstin}</span>}
          </div>
          {billingAddress ? <div className="trade-billing-review"><strong>Default billing address</strong><span>{billingAddress.recipient_name} · {billingAddress.phone_number}</span><span>{billingAddress.address_line_1}{billingAddress.address_line_2 ? `, ${billingAddress.address_line_2}` : ""}</span><span>{billingAddress.city}, {billingAddress.district} · {billingAddress.postal_code}</span><Link href="/wholesale/profile">Change billing address →</Link></div> : <div className="form-message">No default billing address is selected. <Link href="/wholesale/profile" style={{ textDecoration: "underline" }}>Add one in your trade profile.</Link></div>}
        </section>
        <section className="checkout-step">
          <div className="step-head"><span>2</span><div><h2>Payment</h2><p>Pay online now or place a bank-transfer order.</p></div></div>
          <div className="payment-options">
            <label className={`payment-card ${method === "razorpay" ? "selected" : ""}`}><input type="radio" name="trade-payment" checked={method === "razorpay"} onChange={() => setMethod("razorpay")} /><div><strong>Razorpay</strong><small>UPI, debit card, netbanking & wallets</small></div></label>
            <label className={`payment-card ${method === "bank_transfer" ? "selected" : ""}`}><input type="radio" name="trade-payment" checked={method === "bank_transfer"} onChange={() => setMethod("bank_transfer")} /><div><strong>Bank transfer</strong><small>Order stays pending until staff verifies the transfer</small></div></label>
          </div>
          <div className="field" style={{ marginTop: 18 }}><label>Purchase note <small>(optional)</small></label><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={4} /></div>
        </section>
      </div>
      <aside className="summary-card checkout-summary">
        <h3>Trade order</h3>
        <div className="summary-row"><span>Total boxes</span><strong>{cart.readiness.total_boxes}</strong></div>
        <div className="summary-row total"><span>Subtotal</span><span>{money(cart.readiness.subtotal_including_gst)}</span></div>
        <p className="helper">Final delivery charges and invoice totals are confirmed when the trade order is placed.</p>
        {message && <div className="form-message">{message}</div>}
        <button type="button" className="btn primary block" disabled={busy || !billingAddress} onClick={() => void place()}>{busy ? "Processing…" : method === "razorpay" ? "Pay & place order" : "Place bank-transfer order"}</button>
      </aside>
    </div>
  );
}
