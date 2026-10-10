"use client";

import { useEffect, useState, type MouseEvent } from "react";

const KEY = "chokher-alo-wishlist";

function getSaved(): string[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

export default function WishlistButton({ sku, className = "wishlist-button" }: { sku: string; className?: string }) {
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(getSaved().includes(sku)), [sku]);
  function toggle(e: MouseEvent) {
    e.preventDefault(); e.stopPropagation();
    const list = getSaved();
    const next = list.includes(sku) ? list.filter((item) => item !== sku) : [...list, sku];
    localStorage.setItem(KEY, JSON.stringify(next));
    setSaved(next.includes(sku));
    window.dispatchEvent(new Event("chokher-alo-wishlist"));
  }
  return <button type="button" className={`${className} ${saved ? "active" : ""}`} onClick={toggle} aria-label={saved ? "Remove from wishlist" : "Save to wishlist"}>{saved ? "♥" : "♡"}</button>;
}

export { KEY as WISHLIST_KEY, getSaved as getWishlistSkus };
