"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, getCart, getProduct, publicCatalogueImageUrl, removeCartItem, updateCartQuantity } from "@/lib/api";
import type { Cart } from "@/lib/api-types";
import { demoProducts } from "@/lib/demo-products";
import { money } from "@/lib/format";
import { notifyCartUpdated } from "@/lib/client-events";

export default function CartClient() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [images, setImages] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    getCart()
      .then((nextCart) => {
        setCart(nextCart);
        void loadProductImages(nextCart);
      })
      .catch((error) => {
        setAuthRequired(error instanceof ApiError && error.code === "authentication_required");
        setMessage(error instanceof ApiError ? error.message : "Sign in to view your bag.");
      })
      .finally(() => setLoading(false));
  }, []);

  async function loadProductImages(nextCart: Cart) {
    const skus = Array.from(new Set(nextCart.items.map((item) => item.offer?.sku).filter((sku): sku is string => Boolean(sku))));
    const resolved = await Promise.allSettled(
      skus.map(async (sku) => {
        const demo = demoProducts.find((product) => product.sku === sku);
        if (demo?.primary_image?.url) return [sku, demo.primary_image.url] as const;
        const product = await getProduct(sku);
        return [sku, publicCatalogueImageUrl(product.primary_image?.url || product.images[0]?.url) || ""] as const;
      })
    );
    const next: Record<string, string> = {};
    resolved.forEach((result) => {
      if (result.status === "fulfilled" && result.value[1]) next[result.value[0]] = result.value[1];
    });
    setImages(next);
  }

  async function changeQuantity(itemId: number, quantity: number) {
    setMessage(null);
    try {
      const nextCart = await updateCartQuantity(itemId, quantity);
      setCart(nextCart);
      notifyCartUpdated();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not update quantity.");
    }
  }

  async function remove(itemId: number) {
    setMessage(null);
    try {
      const nextCart = await removeCartItem(itemId);
      setCart(nextCart);
      notifyCartUpdated();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not remove item.");
    }
  }

  if (loading) return <div className="skeleton" style={{ minHeight: 340 }} />;
  if (!cart) {
    return (
      <div className="empty-state">
        {message || "Your bag is unavailable."}
        <div className="form-actions" style={{ justifyContent: "center" }}>
          <Link className="btn primary" href={authRequired ? "/login?next=/cart" : "/shop"}>{authRequired ? "Sign in" : "Continue shopping"}</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="cart-layout">
      <div>
        {cart.items.length === 0 ? (
          <div className="empty-state">
            Your bag is empty.
            <div className="form-actions" style={{ justifyContent: "center" }}><Link className="btn primary" href="/shop">Shop eyewear</Link></div>
          </div>
        ) : (
          <div className="cart-items">
            {cart.items.map((item) => {
              const sku = item.offer?.sku || "";
              const image = images[sku];
              return (
                <div className="cart-item" key={item.id}>
                  <div className="cart-thumb">
                    {image ? <img src={image} alt={item.offer?.name || "Eyewear"} /> : <div className="cart-thumb-placeholder">CA</div>}
                  </div>
                  <div>
                    <h3>{item.offer?.name || item.item_type_label}</h3>
                    <p>{item.offer ? `${item.offer.colour}${item.offer.size ? ` · ${item.offer.size}` : ""}` : "Custom optical item"}</p>
                    {item.powered_configuration && (
                      <p>Prescription #{item.powered_configuration.prescription.id} · {item.powered_configuration.lens?.name || item.powered_configuration.state.replaceAll("_", " ")}</p>
                    )}
                    <div className="cart-item-actions">
                      {item.quantity_editable && (
                        <select className="qty" aria-label={`Quantity for ${item.offer?.name || "item"}`} value={item.quantity} onChange={(e) => void changeQuantity(item.id, Number(e.target.value))}>
                          {Array.from({ length: 10 }, (_, i) => i + 1).map((q) => <option value={q} key={q}>{q}</option>)}
                        </select>
                      )}
                      <button type="button" className="text-button" onClick={() => void remove(item.id)}>Remove</button>
                    </div>
                  </div>
                  <strong>{money(item.current_total_including_gst)}</strong>
                </div>
              );
            })}
          </div>
        )}
        {message && <div className="form-message">{message}</div>}
        {cart.items.length > 0 && <div className="cart-continue"><Link className="text-link" href="/shop">← Continue shopping</Link></div>}
      </div>
      <aside className="summary-card">
        <h3>Order summary</h3>
        <div className="summary-row"><span>Subtotal</span><strong>{money(cart.totals.subtotal_including_gst)}</strong></div>
        <div className="summary-row"><span>Delivery</span><span>Calculated at checkout</span></div>
        <div className="summary-row total"><span>Total</span><span>{money(cart.totals.subtotal_including_gst)}</span></div>
        {cart.validation.issues.length > 0 && <div className="issue-list">{cart.validation.issues.map((issue, i) => <div className="issue" key={`${issue.code}-${i}`}>{issue.message}</div>)}</div>}
        <div style={{ marginTop: 18 }}><Link className="btn primary block" aria-disabled={!cart.validation.checkout_ready || cart.items.length === 0} href={cart.validation.checkout_ready && cart.items.length ? "/checkout" : "#"}>Proceed to checkout</Link></div>
        <p className="helper">Custom prescription eyewear is non-refundable. Please review your prescription and lens configuration carefully before checkout.</p>
      </aside>
    </div>
  );
}
