"use client";

import { useEffect, useState } from "react";
import { getProducts } from "@/lib/api";
import type { ProductSummary } from "@/lib/api-types";
import ProductCard from "./ProductCard";

export default function FeaturedProducts() {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getProducts({ page_size: 8, ordering: "newest", offer_type: "frame_only" })
      .then((data) => {
        setProducts(data.products || []);
        setError("");
      })
      .catch((err) => {
        console.error("Featured products failed:", err);
        setError("Products could not be loaded.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="product-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ minHeight: 360 }} />
        ))}
      </div>
    );
  }

  if (error) {
    return <div className="form-message">{error}</div>;
  }

  if (!products.length) {
    return <div className="form-message">No catalogue products are currently available.</div>;
  }

  return (
    <div className="product-grid">
      {products.map((product) => (
        <ProductCard key={product.sku} product={product} />
      ))}
    </div>
  );
}
