import Link from "next/link";
import type { ProductSummary } from "@/lib/api-types";
import { publicCatalogueImageUrl } from "@/lib/api";
import { money } from "@/lib/format";
import WishlistButton from "./WishlistButton";

export default function ProductCard({ product, journey = "" }: { product: ProductSummary; journey?: string }) {
  const image = publicCatalogueImageUrl(product.primary_image?.url) || "/products/frame-01.jpg";
  const href = `/product/${encodeURIComponent(product.sku)}${journey ? `?${journey}` : ""}`;

  return <article className="product-card">
    <div className="product-image-wrap">
      <Link href={href} className="product-image-link" aria-label={`View ${product.name}`}>
        <img src={image} alt={product.primary_image?.alt_text || product.name} loading="lazy" />
        {product.supports_powered_lenses && <span className="product-badge">Power ready</span>}
      </Link>
      <WishlistButton sku={product.sku}/>
    </div>
    <Link href={href} className="product-card-info">
      <div className="product-meta">{product.brand || "Chokher Alo"} · {product.colour.name}</div>
      <div className="product-name">{product.name}</div>
      <div className="price-row"><span className="price-current">{product.price_visible ? money(product.selling_price_including_gst) : product.status_label}</span>{product.price_visible && product.mrp_including_gst && product.mrp_including_gst !== product.selling_price_including_gst && <span className="price-mrp">{money(product.mrp_including_gst)}</span>}</div>
    </Link>
  </article>;
}
