"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AddressBook from "./AddressBook";
import { ApiError, checkServiceability, confirmRetailRazorpay, createCheckout, getAddresses, getCart, previewCheckout } from "@/lib/api";
import type { Address, Cart, CheckoutPreview, PaymentSession } from "@/lib/api-types";
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

export default function CheckoutClient() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState<number | null>(null);
  const [payment, setPayment] = useState<"razorpay" | "cod">("razorpay");
  const [preview, setPreview] = useState<CheckoutPreview | null>(null);
  const [serviceable, setServiceable] = useState<boolean | null>(null);
  const [codEnabled, setCodEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  async function reloadAddresses() {
    const list = await getAddresses();
    setAddresses(list);
    if (!addressId && list.length) setAddressId((list.find((a) => a.is_default_delivery) || list[0]).id);
  }

  useEffect(() => {
    Promise.all([getCart(), getAddresses()]).then(([nextCart, list]) => {
      setCart(nextCart); setAddresses(list);
      if (list.length) setAddressId((list.find((a) => a.is_default_delivery) || list[0]).id);
    }).catch((error) => setMessage(error instanceof ApiError ? error.message : "Could not prepare checkout."))
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(() => addresses.find((a) => a.id === addressId) || null, [addresses, addressId]);

  useEffect(() => {
    if (!selected) { setPreview(null); setServiceable(null); return; }
    let cancelled = false;
    setPreview(null); setMessage(null);
    Promise.all([
      checkServiceability(selected.postal_code),
      previewCheckout({
        fulfillment_method: "delivery",
        payment_method: payment,
        shipping_address_id: selected.id,
        billing_address_id: selected.id,
        billing_same_as_shipping: true
      })
    ]).then(([availability, nextPreview]) => {
      if (cancelled) return;
      setServiceable(availability.serviceable);
      setPreview(nextPreview);
      setCodEnabled(nextPreview.policy.cod_enabled);
      if (!availability.serviceable) setMessage(availability.message);
    }).catch((error) => {
      if (!cancelled) {
        if (error instanceof ApiError && error.code === "cod_disabled") {
          setCodEnabled(false);
          setPayment("razorpay");
          setMessage("Cash on Delivery is currently unavailable. Please use Razorpay.");
        } else {
          setMessage(error instanceof ApiError ? error.message : "Could not calculate checkout.");
        }
      }
    });
    return () => { cancelled = true; };
  }, [selected?.id, selected?.postal_code, payment]);

  async function openRazorpay(session: PaymentSession, orderNumber: string) {
    const loaded = await loadRazorpay();
    if (!loaded) throw new Error("Razorpay checkout could not be loaded.");

    return new Promise<void>((resolve, reject) => {
      const Razorpay = (window as any).Razorpay;
      const checkout = new Razorpay({
        key: session.key_id,
        amount: session.amount_subunits,
        currency: session.currency,
        name: "Chokher Alo",
        description: `Order ${orderNumber}`,
        order_id: session.provider_order_id,
        theme: { color: "#0b1f33" },
        handler: async (response: any) => {
          try {
            const result = await confirmRetailRazorpay({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature
            });
            window.location.href = `/account/orders/${result.order.order_number}`;
            resolve();
          } catch (error) { reject(error); }
        },
        modal: { ondismiss: () => reject(new Error("Payment window closed. Your unpaid order remains in your account.")) }
      });
      checkout.open();
    });
  }

  async function placeOrder() {
    if (!selected || !cart) return;
    setBusy(true); setMessage(null);
    try {
      const result = await createCheckout({
        fulfillment_method: "delivery",
        payment_method: payment,
        shipping_address_id: selected.id,
        billing_address_id: selected.id,
        billing_same_as_shipping: true
      });
      if (result.payment_session) {
        await openRazorpay(result.payment_session, result.order.order_number);
      } else {
        window.location.href = `/account/orders/${result.order.order_number}`;
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Could not place the order.");
      setBusy(false);
    }
  }

  if (loading) return <div className="skeleton" style={{minHeight: 520}}/>;
  if (!cart) return <div className="empty-state">{message || "Checkout is unavailable."}<div className="form-actions" style={{justifyContent:"center"}}><Link href="/login?next=/checkout" className="btn primary">Sign in</Link></div></div>;
  if (!cart.items.length) return <div className="empty-state">Your bag is empty.<div className="form-actions" style={{justifyContent:"center"}}><Link href="/shop" className="btn primary">Shop eyewear</Link></div></div>;

  return <div className="checkout-layout">
    <div className="checkout-main">
      <section className="checkout-step">
        <div className="step-head"><span>1</span><div><h2>Delivery address</h2><p>Launch delivery is currently limited to serviceable PIN codes in West Bengal.</p></div></div>
        <AddressBook selectable selectedId={addressId} onSelect={(id) => { setAddressId(id); void reloadAddresses(); }}/>
      </section>

      <section className="checkout-step">
        <div className="step-head"><span>2</span><div><h2>Payment</h2><p>Choose secure online payment or pay when the order arrives.</p></div></div>
        <div className="payment-options">
          <label className={`payment-card ${payment === "razorpay" ? "selected" : ""}`}><input type="radio" name="payment" checked={payment === "razorpay"} onChange={() => setPayment("razorpay")}/><div><strong>Razorpay</strong><small>UPI, debit card, netbanking & wallets</small></div></label>
          <label className={`payment-card ${payment === "cod" ? "selected" : ""} ${codEnabled === false ? "disabled" : ""}`}><input type="radio" name="payment" checked={payment === "cod"} disabled={codEnabled === false} onChange={() => setPayment("cod")}/><div><strong>Cash on Delivery</strong><small>{codEnabled === false ? "Currently unavailable" : "Pay when your order is delivered"}</small></div></label>
        </div>
      </section>
    </div>

    <aside className="summary-card checkout-summary">
      <h3>Order summary</h3>
      <div className="summary-row"><span>Subtotal</span><strong>{money(preview?.subtotal_including_gst || cart.totals.subtotal_including_gst)}</strong></div>
      <div className="summary-row"><span>Delivery</span><span>{preview ? money(preview.delivery_fee_including_gst) : "—"}</span></div>
      <div className="summary-row total"><span>Total</span><span>{money(preview?.grand_total_including_gst || cart.totals.subtotal_including_gst)}</span></div>
      {selected && <div className="delivery-mini"><strong>Delivering to</strong><span>{selected.city}, {selected.postal_code}</span></div>}
      {serviceable === true && <div className="success-note">✓ Delivery available</div>}
      {cart.validation.issues.length > 0 && <div className="issue-list">{cart.validation.issues.map((issue, index) => <div className="issue" key={`${issue.code}-${index}`}>{issue.message}</div>)}</div>}
      {message && <div className="form-message">{message}</div>}
      <button className="btn primary block" disabled={busy || !selected || serviceable !== true || !preview || !cart.validation.checkout_ready} onClick={() => void placeOrder()}>{busy ? "Processing…" : payment === "cod" ? "Place COD order" : "Pay securely"}</button>
      <p className="helper">Prescription/custom eyewear is non-refundable. Review your prescription and lens configuration before placing the order.</p>
    </aside>
  </div>;
}
