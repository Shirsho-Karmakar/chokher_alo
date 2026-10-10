"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, getCatalogueFilters, getProducts } from "@/lib/api";
import type { CatalogueFilters, Pagination, ProductSummary } from "@/lib/api-types";
import { demoEnabled, demoProducts } from "@/lib/demo-products";
import ProductCard from "./ProductCard";

const emptyFilters: CatalogueFilters = {categories: [], brands: [], colours: [], materials: [], frame_shapes: [], frame_types: [], genders: [], offer_types: []};
const emptyPagination: Pagination = {page: 1, page_size: 24, total_pages: 1, total_items: 0, has_next: false, has_previous: false};

function demoResults(query: URLSearchParams) {
  let items = [...demoProducts];
  const q = query.get("q")?.trim().toLowerCase();
  if (q) items = items.filter((p) => `${p.name} ${p.brand || ""} ${p.colour.name} ${p.supplier_model_number || ""}`.toLowerCase().includes(q));
  const gender = query.get("gender");
  if (gender) items = items.filter((p) => p.gender === gender || (gender !== "kids" && p.gender === "unisex"));
  const offerType = query.get("offer_type");
  if (offerType) items = items.filter((p) => p.offer_type === offerType);
  const category = query.get("category");
  if (category && category !== "eyeglasses") items = [];
  const availability = query.get("availability");
  if (availability) items = items.filter((p) => p.status === availability);

  const minimum = Number(query.get("minimum_price"));
  if (query.get("minimum_price") && Number.isFinite(minimum)) items = items.filter((p) => Number(p.selling_price_including_gst || 0) >= minimum);
  const maximum = Number(query.get("maximum_price"));
  if (query.get("maximum_price") && Number.isFinite(maximum)) items = items.filter((p) => Number(p.selling_price_including_gst || 0) <= maximum);

  const ordering = query.get("ordering") || "newest";
  if (ordering === "name") items.sort((a, b) => a.name.localeCompare(b.name));
  if (ordering === "price_asc") items.sort((a, b) => Number(a.selling_price_including_gst || 0) - Number(b.selling_price_including_gst || 0));
  if (ordering === "price_desc") items.sort((a, b) => Number(b.selling_price_including_gst || 0) - Number(a.selling_price_including_gst || 0));

  const pageSize = Math.min(48, Math.max(1, Number(query.get("page_size")) || 24));
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(totalPages, Math.max(1, Number(query.get("page")) || 1));
  const start = (page - 1) * pageSize;
  return {
    products: items.slice(start, start + pageSize),
    pagination: {
      page,
      page_size: pageSize,
      total_pages: totalPages,
      total_items: items.length,
      has_next: page < totalPages,
      has_previous: page > 1
    } satisfies Pagination
  };
}

export default function ShopClient() {
  const router = useRouter();
  const params = useSearchParams();
  const [filters, setFilters] = useState<CatalogueFilters>(emptyFilters);
  const [products, setProducts] = useState<ProductSummary[]>(demoEnabled ? demoProducts : []);
  const [pagination, setPagination] = useState<Pagination>(demoEnabled ? {...emptyPagination, total_items: demoProducts.length} : emptyPagination);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [moreFilters, setMoreFilters] = useState(false);
  const [minPrice, setMinPrice] = useState(params.get("minimum_price") || "");
  const [maxPrice, setMaxPrice] = useState(params.get("maximum_price") || "");

  const queryString = params.toString();

  useEffect(() => {
    getCatalogueFilters().then(setFilters).catch(() => undefined);
  }, []);

  useEffect(() => {
    setMinPrice(params.get("minimum_price") || "");
    setMaxPrice(params.get("maximum_price") || "");
  }, [queryString, params]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMessage(null);
    const query = new URLSearchParams(queryString);
    if (!query.get("page_size")) query.set("page_size", "24");

    getProducts(query).then((data) => {
      if (cancelled) return;
      if (data.products.length || !demoEnabled) {
        setProducts(data.products);
        setPagination(data.pagination);
        return;
      }
      const demo = demoResults(query);
      setProducts(demo.products);
      setPagination(demo.pagination);
    }).catch((error) => {
      if (cancelled) return;
      if (demoEnabled) {
        const demo = demoResults(query);
        setProducts(demo.products);
        setPagination(demo.pagination);
        setMessage("Preview catalogue shown while the live catalogue is unavailable.");
      } else {
        setProducts([]);
        setPagination(emptyPagination);
        setMessage(error instanceof ApiError ? error.message : "Could not load catalogue.");
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [queryString]);

  function navigate(next: URLSearchParams, replace = false) {
    const href = `/shop${next.toString() ? `?${next.toString()}` : ""}`;
    if (replace) router.replace(href, {scroll: false}); else router.push(href);
  }

  function setParam(name: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(name, value); else next.delete(name);
    next.delete("page");
    navigate(next);
  }

  function setPage(page: number) {
    const next = new URLSearchParams(params.toString());
    if (page <= 1) next.delete("page"); else next.set("page", String(page));
    navigate(next);
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function applyPrice() {
    const next = new URLSearchParams(params.toString());
    if (minPrice.trim()) next.set("minimum_price", minPrice.trim()); else next.delete("minimum_price");
    if (maxPrice.trim()) next.set("maximum_price", maxPrice.trim()); else next.delete("maximum_price");
    next.delete("page");
    navigate(next);
  }

  function clearFilters() {
    const next = new URLSearchParams();
    const prescriptionId = params.get("prescription_id");
    const lensId = params.get("lens_id");
    if (prescriptionId) next.set("prescription_id", prescriptionId);
    if (lensId) next.set("lens_id", lensId);
    navigate(next);
  }

  const title = useMemo(() => {
    if (params.get("gender") === "kids") return "Kids eyewear";
    if (params.get("offer_type") === "sunglasses") return "Sunglasses";
    if (params.get("offer_type") === "frame_only") return "Eyeglasses";
    if (params.get("q")) return `Search: “${params.get("q")}”`;
    return "Shop eyewear";
  }, [params]);

  const activeFilterCount = useMemo(() => {
    const ignored = new Set(["page", "page_size", "ordering", "prescription_id", "lens_id"]);
    return Array.from(params.keys()).filter((key) => !ignored.has(key)).length;
  }, [params]);

  const pageNumbers = useMemo(() => {
    const current = pagination.page;
    const last = pagination.total_pages;
    const values = new Set<number>([1, last, current - 1, current, current + 1]);
    return Array.from(values).filter((page) => page >= 1 && page <= last).sort((a, b) => a - b);
  }, [pagination]);

  return (
    <>
      <div className="container page-hero"><div className="eyebrow">Catalogue</div><h1 className="display-title">{title}</h1><p>Browse the complete public catalogue. Prescription upload is only required when you choose powered lenses.</p></div>
      <div className="container">
        <div className="shop-toolbar">
          <div className="filter-row">
            <select className="filter-select" aria-label="Gender" value={params.get("gender") || ""} onChange={(e) => setParam("gender", e.target.value)}><option value="">All genders</option>{filters.genders.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select>
            <select className="filter-select" aria-label="Frame shape" value={params.get("frame_shape") || ""} onChange={(e) => setParam("frame_shape", e.target.value)}><option value="">All shapes</option>{filters.frame_shapes.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
            <select className="filter-select" aria-label="Material" value={params.get("material") || ""} onChange={(e) => setParam("material", e.target.value)}><option value="">All materials</option>{filters.materials.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
            <select className="filter-select" aria-label="Brand" value={params.get("brand") || ""} onChange={(e) => setParam("brand", e.target.value)}><option value="">All brands</option>{filters.brands.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
            <button type="button" className="filter-toggle" onClick={() => setMoreFilters((value) => !value)} aria-expanded={moreFilters}>More filters{activeFilterCount ? ` (${activeFilterCount})` : ""}</button>
            {activeFilterCount > 0 && <button type="button" className="clear-filter" onClick={clearFilters}>Clear</button>}
          </div>
          <div className="shop-meta"><span>{pagination.total_items} item{pagination.total_items === 1 ? "" : "s"}</span><select className="filter-select" aria-label="Sort catalogue" value={params.get("ordering") || "newest"} onChange={(e) => setParam("ordering", e.target.value)}><option value="newest">Newest</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="name">Name</option></select></div>
        </div>

        {moreFilters && <div className="advanced-filters">
          <select className="filter-select" aria-label="Category" value={params.get("category") || ""} onChange={(e) => setParam("category", e.target.value)}><option value="">All categories</option>{filters.categories.map((f) => <option key={f.id} value={f.slug}>{f.name}</option>)}</select>
          <select className="filter-select" aria-label="Frame type" value={params.get("frame_type") || ""} onChange={(e) => setParam("frame_type", e.target.value)}><option value="">All frame types</option>{filters.frame_types.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
          <select className="filter-select" aria-label="Colour" value={params.get("colour") || ""} onChange={(e) => setParam("colour", e.target.value)}><option value="">All colours</option>{filters.colours.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
          <select className="filter-select" aria-label="Availability" value={params.get("availability") || ""} onChange={(e) => setParam("availability", e.target.value)}><option value="">Any availability</option><option value="available">Available</option><option value="sold_out">Sold out</option><option value="coming_soon">Coming soon</option></select>
          <div className="price-filter"><input value={minPrice} onChange={(e) => setMinPrice(e.target.value.replace(/[^0-9.]/g, ""))} inputMode="decimal" placeholder="Min ₹" aria-label="Minimum price"/><span>–</span><input value={maxPrice} onChange={(e) => setMaxPrice(e.target.value.replace(/[^0-9.]/g, ""))} inputMode="decimal" placeholder="Max ₹" aria-label="Maximum price"/><button type="button" onClick={applyPrice}>Apply</button></div>
        </div>}

        {params.get("prescription_id") && <div className="journey-banner"><strong>Prescription #{params.get("prescription_id")} selected.</strong><span>Choose a power-ready frame; your prescription choice will carry into lens configuration.</span></div>}
        {message && <div className="form-message">{message}</div>}
        {loading && products.length === 0 ? <div className="loading-grid">{Array.from({length: 8}).map((_, i) => <div className="skeleton" key={i}/>)}</div> : products.length ? <div className="product-grid">{products.map((p) => { const journey = new URLSearchParams(); const rx = params.get("prescription_id"); const lens = params.get("lens_id"); if (rx) journey.set("prescription_id", rx); if (lens) journey.set("lens_id", lens); return <ProductCard key={p.sku} product={p} journey={journey.toString()}/>; })}</div> : <div className="empty-state">No products match these filters.<div className="form-actions" style={{justifyContent: "center"}}><button className="btn ghost" type="button" onClick={clearFilters}>Clear filters</button></div></div>}

        {pagination.total_pages > 1 && <nav className="pagination" aria-label="Catalogue pages">
          <button type="button" disabled={!pagination.has_previous || loading} onClick={() => setPage(pagination.page - 1)}>← Previous</button>
          <div className="pagination-pages">{pageNumbers.map((page, index) => <span key={page} className="pagination-slot">{index > 0 && pageNumbers[index - 1] < page - 1 && <span className="pagination-ellipsis">…</span>}<button type="button" className={page === pagination.page ? "active" : ""} aria-current={page === pagination.page ? "page" : undefined} disabled={loading} onClick={() => setPage(page)}>{page}</button></span>)}</div>
          <button type="button" disabled={!pagination.has_next || loading} onClick={() => setPage(pagination.page + 1)}>Next →</button>
        </nav>}
      </div>
      <div style={{height: 90}}/>
    </>
  );
}
