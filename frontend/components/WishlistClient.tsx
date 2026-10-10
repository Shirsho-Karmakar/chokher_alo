"use client";

import { useEffect, useState } from "react";
import { getProduct } from "@/lib/api";
import type { ProductSummary } from "@/lib/api-types";
import { demoProducts } from "@/lib/demo-products";
import ProductCard from "./ProductCard";
import { getWishlistSkus } from "./WishlistButton";
import Link from "next/link";

export default function WishlistClient() {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [loading, setLoading] = useState(true);
  async function load() {
    const skus = getWishlistSkus();
    const demo = demoProducts.filter((p) => skus.includes(p.sku));
    const missing = skus.filter((sku) => !demo.some((p) => p.sku === sku));
    const live = (await Promise.all(missing.map((sku) => getProduct(sku).catch(() => null)))).filter(Boolean) as ProductSummary[];
    setProducts([...demo, ...live]); setLoading(false);
  }
  useEffect(() => { void load(); const listener = () => void load(); window.addEventListener("chokher-alo-wishlist", listener); return () => window.removeEventListener("chokher-alo-wishlist", listener); }, []);
  if (loading) return <div className="loading-grid">{Array.from({length:4}).map((_,i)=><div className="skeleton" key={i}/>)}</div>;
  if (!products.length) return <div className="empty-state">Nothing saved yet.<div className="form-actions" style={{justifyContent:"center"}}><Link className="btn primary" href="/shop">Explore eyewear</Link></div></div>;
  return <div className="product-grid">{products.map((p) => <ProductCard key={p.sku} product={p}/>)}</div>;
}
