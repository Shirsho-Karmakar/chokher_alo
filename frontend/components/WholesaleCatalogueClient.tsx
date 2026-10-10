"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError, getWholesaleCatalogue, setWholesaleCartItem } from "@/lib/api";
import type { WholesaleVariant } from "@/lib/api-types";
import { notifyCartUpdated } from "@/lib/client-events";
import { money } from "@/lib/format";

export default function WholesaleCatalogueClient() {
  const [variants, setVariants] = useState<WholesaleVariant[]>([]);
  const [family, setFamily] = useState("all");
  const [power, setPower] = useState("all");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    getWholesaleCatalogue()
      .then((result) => {
        setVariants(result.variants);
        setMessage(null);
      })
      .catch((error) =>
        setMessage(error instanceof ApiError ? error.message : "Could not load trade catalogue.")
      )
      .finally(() => setLoading(false));
  }, []);

  const families = useMemo(
    () => Array.from(new Set(variants.map((variant) => variant.catalogue_code))),
    [variants]
  );
  const powers = useMemo(
    () => Array.from(new Set(variants.map((variant) => variant.power.label))).sort(),
    [variants]
  );
  const shown = variants.filter(
    (variant) =>
      (family === "all" || variant.catalogue_code === family) &&
      (power === "all" || variant.power.label === power)
  );

  return (
    <div>
      <div className="b2b-toolbar">
        <div>
          <strong>Stock lens catalogue</strong>
          <p style={{ margin: "4px 0 0" }}>
            Choose an exact power. Every sealed box contains 50 lenses of that same power.
          </p>
        </div>
        <Link href="/wholesale/cart" className="btn ghost">View trade cart</Link>
      </div>

      <div className="shop-toolbar" style={{ marginBottom: 24 }}>
        <select className="filter-select" value={family} onChange={(event) => setFamily(event.target.value)}>
          <option value="all">All lens families</option>
          {families.map((value) => <option value={value} key={value}>{value}</option>)}
        </select>
        <select className="filter-select" value={power} onChange={(event) => setPower(event.target.value)}>
          <option value="all">All powers</option>
          {powers.map((value) => <option value={value} key={value}>{value}</option>)}
        </select>
      </div>

      {message && <div className="form-message" style={{ marginBottom: 18 }}>{message}</div>}

      {loading ? (
        <div className="loading-grid">
          {Array.from({ length: 6 }).map((_, index) => <div className="skeleton" key={index} />)}
        </div>
      ) : (
        <div className="wholesale-product-grid">
          {shown.map((variant) => <WholesaleVariantCard key={variant.variant_id} variant={variant} />)}
        </div>
      )}
      {!loading && !shown.length && <div className="empty-state">No wholesale lens boxes match those filters.</div>}
    </div>
  );
}

function WholesaleVariantCard({ variant }: { variant: WholesaleVariant }) {
  const [boxes, setBoxes] = useState(variant.minimum_order_boxes || 1);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  async function add() {
    if (!Number.isInteger(boxes) || boxes < variant.minimum_order_boxes) {
      setAdded(false);
      setFeedback(`Enter at least ${variant.minimum_order_boxes} box${variant.minimum_order_boxes === 1 ? "" : "es"}.`);
      return;
    }
    if (boxes % variant.order_multiple_boxes !== 0) {
      setAdded(false);
      setFeedback(`Boxes must be ordered in multiples of ${variant.order_multiple_boxes}.`);
      return;
    }

    setBusy(true);
    setAdded(false);
    setFeedback("Adding to trade cart…");
    try {
      await setWholesaleCartItem({ variant_id: variant.variant_id, boxes });
      notifyCartUpdated();
      setAdded(true);
      setFeedback(`${boxes} box${boxes === 1 ? "" : "es"} of ${variant.name} ${variant.power.label} added.`);
    } catch (error) {
      setAdded(false);
      setFeedback(error instanceof ApiError ? error.message : "Could not add this lens box to the trade cart.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="wholesale-product-card">
      <div className="category-kicker">{variant.catalogue_code}</div>
      <h3>{variant.name}</h3>
      <p>
        {variant.vision_type.name} · Index {variant.refractive_index.display_name || variant.refractive_index.value}
        {variant.coating ? ` · ${variant.coating.name}` : ""}
      </p>
      <div className="wholesale-price">{variant.power.label}</div>
      <div className="wholesale-price">
        {variant.price_visible ? `${money(variant.base_box_price_including_gst)} / box` : variant.status_label}
      </div>
      <div className="tag-row">
        <span className="tag">{variant.box.units_per_box} lenses / box</span>
        <span className="tag">MOQ {variant.minimum_order_boxes} box</span>
        <span className="tag">{variant.boxes_in_stock} boxes in stock</span>
      </div>
      {variant.bulk_price_tiers.length > 0 && (
        <div className="bulk-tiers">
          {variant.bulk_price_tiers.map((tier) => (
            <div key={tier.id}>
              <span>{tier.minimum_boxes}{tier.maximum_boxes ? `–${tier.maximum_boxes}` : "+"} boxes</span>
              <strong>{money(tier.box_price_including_gst)}</strong>
            </div>
          ))}
        </div>
      )}
      <div className="b2b-buy-row">
        <input
          aria-label="Boxes"
          type="number"
          min={variant.minimum_order_boxes}
          max={variant.boxes_in_stock}
          step={variant.order_multiple_boxes}
          value={boxes}
          onChange={(event) => setBoxes(Number(event.target.value))}
        />
        <button className="btn primary" type="button" disabled={busy || variant.status !== "available"} onClick={() => void add()}>
          {busy ? "Adding…" : "Add boxes"}
        </button>
      </div>
      {feedback && (
        <div className="form-message" style={{ marginTop: 12 }}>
          {feedback}
          {added && <div style={{ marginTop: 10 }}><Link href="/wholesale/cart" className="text-button">View trade cart →</Link></div>}
        </div>
      )}
    </article>
  );
}
