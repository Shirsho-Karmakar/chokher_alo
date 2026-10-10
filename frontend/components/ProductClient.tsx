"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError, addPoweredItem, addStandardItem, configurePoweredItem, createStockAlert, getCompatibleLenses, getPrescriptions, getProduct, publicCatalogueImageUrl } from "@/lib/api";
import type { Lens, Prescription, ProductDetail } from "@/lib/api-types";
import { demoEnabled, demoProductDetail } from "@/lib/demo-products";
import { money } from "@/lib/format";
import { ArrowIcon, CheckIcon, CloseIcon } from "./Icons";
import WishlistButton from "./WishlistButton";
import PincodeChecker from "./PincodeChecker";
import { notifyCartUpdated } from "@/lib/client-events";

export default function ProductClient({ sku, initialPrescriptionId, initialLensId }: { sku: string; initialPrescriptionId?: number; initialLensId?: number }) {
  const [product, setProduct] = useState<ProductDetail | null>(() => demoEnabled ? demoProductDetail(sku) : null);
  const [loading, setLoading] = useState(!product);
  const [message, setMessage] = useState<string | null>(null);
  const [powerFlow, setPowerFlow] = useState(false);

  useEffect(() => {
    if (sku.startsWith("DEMO-")) { setLoading(false); return; }
    getProduct(sku).then(setProduct).catch((error) => {
      setMessage(error instanceof ApiError ? error.message : "Product could not be loaded.");
    }).finally(() => setLoading(false));
  }, [sku]);

  async function addFrame() {
    if (!product) return;
    setMessage(null);
    if (product.sku.startsWith("DEMO-")) {
      setMessage("This preview item is for design review only. Add the real product in Django Admin to enable checkout.");
      return;
    }
    if (product.status !== "available") {
      setMessage(`${product.name} is ${product.status_label.toLowerCase()} and cannot be added to the bag yet.`);
      return;
    }
    try {
      await addStandardItem(product.sku, 1);
      notifyCartUpdated();
      window.location.href = "/cart";
    } catch (error) {
      if (error instanceof ApiError && error.code === "authentication_required") {
        window.location.href = `/login?next=${encodeURIComponent(`/product/${product.sku}`)}`;
        return;
      }
      setMessage(error instanceof ApiError ? error.message : "Could not add this frame.");
    }
  }

  if (loading) return <div className="container product-page"><div className="skeleton" style={{minHeight: 620}}/></div>;
  if (!product) return <div className="container product-page"><div className="empty-state">{message || "Product not found."}</div></div>;

  const images = product.images.length ? product.images : product.primary_image ? [product.primary_image] : [];

  return (
    <>
      <div className="container product-page">
        <div className="product-layout">
          <div className="product-gallery">
            {images.map((image) => <div className="gallery-item" key={image.id}><img src={publicCatalogueImageUrl(image.url)} alt={image.alt_text || product.name}/></div>)}
          </div>
          <aside className="product-panel">
            <div className="product-title-row"><div><div className="brand-line">{product.brand || "Chokher Alo"}</div><h1>{product.name}</h1></div><WishlistButton sku={product.sku} className="product-wishlist"/></div>
            <div className="price-row"><span className="price-current">{product.price_visible ? money(product.selling_price_including_gst) : product.status_label}</span>{product.mrp_including_gst && product.mrp_including_gst !== product.selling_price_including_gst && <span className="price-mrp">{money(product.mrp_including_gst)}</span>}</div>
            <div className="product-subtext">MRP inclusive of GST · {product.colour.name}{product.size ? ` · ${product.size}` : ""}</div>
            {product.description && <p style={{color: "var(--ink-soft)", fontSize: 13, lineHeight: 1.65}}>{product.description}</p>}

            <div className="product-choice-stack">
              {product.status === "available" && product.purchase_options.direct_purchase_allowed && <button className="choice-button" onClick={() => void addFrame()}><div><strong>Add to bag</strong><span>Frame only · no prescription needed.</span></div><ArrowIcon size={18}/></button>}
              {product.status === "available" && product.purchase_options.supports_powered_lenses && <button className="choice-button" onClick={() => setPowerFlow(true)}><div><strong>{initialPrescriptionId ? "Add selected prescription lenses" : "Add prescription lenses"}</strong><span>{initialPrescriptionId ? `Prescription #${initialPrescriptionId} is ready for this frame.` : "Use an approved prescription and choose a compatible lens."}</span></div><ArrowIcon size={18}/></button>}
              {product.status !== "available" && <StockAlertButton sku={product.sku} productName={product.name} statusLabel={product.status_label}/>} 
            </div>

            <PincodeChecker/>
            {message && <div className="form-message">{message}</div>}

            <div className="spec-list">
              <div className="spec-row"><span>Frame type</span><strong>{product.attributes.frame_type?.name || "—"}</strong></div>
              <div className="spec-row"><span>Shape</span><strong>{product.attributes.frame_shape?.name || "—"}</strong></div>
              <div className="spec-row"><span>Material</span><strong>{product.attributes.material?.name || "—"}</strong></div>
              <div className="spec-row"><span>Gender</span><strong>{product.gender_label}</strong></div>
              <div className="spec-row"><span>SKU</span><strong>{product.sku}</strong></div>
            </div>
          </aside>
        </div>
      </div>
      {powerFlow && <PoweredLensFlow product={product} initialPrescriptionId={initialPrescriptionId} initialLensId={initialLensId} onClose={() => setPowerFlow(false)}/>} 
    </>
  );
}

function StockAlertButton({ sku, productName, statusLabel }: { sku: string; productName: string; statusLabel: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function subscribe() {
    if (sku.startsWith("DEMO-")) {
      setMessage("Preview items do not send stock alerts.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await createStockAlert(sku, "sms");
      setMessage(result.created ? `We’ll text you when ${productName} is available.` : "Your SMS stock alert is already active.");
    } catch (error) {
      if (error instanceof ApiError && error.code === "authentication_required") {
        window.location.href = `/login?next=${encodeURIComponent(`/product/${sku}`)}`;
        return;
      }
      setMessage(error instanceof ApiError ? error.message : "Could not create a stock alert.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="availability-card"><div><strong>{statusLabel}</strong><span>Get an SMS when this item can be ordered.</span></div><button className="btn primary" type="button" disabled={busy} onClick={() => void subscribe()}>{busy ? "Saving…" : "Notify me"}</button>{message && <div className="form-message availability-message">{message}</div>}</div>;
}

function PoweredLensFlow({ product, initialPrescriptionId, initialLensId, onClose }: { product: ProductDetail; initialPrescriptionId?: number; initialLensId?: number; onClose: () => void }) {
  const [step, setStep] = useState(1);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [selectedPrescription, setSelectedPrescription] = useState<number | null>(null);
  const [lenses, setLenses] = useState<Lens[]>([]);
  const [selectedLens, setSelectedLens] = useState<Lens | null>(null);
  const [coatings, setCoatings] = useState<number[]>([]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);

  const loginHref = `/login?next=${encodeURIComponent(`/product/${product.sku}`)}`;

  function handleError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.code === "authentication_required") {
      setAuthRequired(true);
      setMessage("Sign in to use a saved prescription and configure powered lenses.");
      return;
    }
    setMessage(error instanceof ApiError ? error.message : fallback);
  }

  useEffect(() => {
    if (product.sku.startsWith("DEMO-")) {
      setBusy(false);
      setMessage("This preview frame is not available for powered-lens checkout yet.");
      return;
    }
    if (initialPrescriptionId) {
      setSelectedPrescription(initialPrescriptionId);
      getCompatibleLenses(initialPrescriptionId)
        .then((items) => {
          setLenses(items);
          if (initialLensId) setSelectedLens(items.find((lens) => lens.lens_id === initialLensId) || null);
          setStep(2);
        })
        .catch((error) => handleError(error, "Could not load compatible lenses."))
        .finally(() => setBusy(false));
      return;
    }
    getPrescriptions()
      .then((items) => setPrescriptions(items.filter((prescription) => prescription.is_approved)))
      .catch((error) => handleError(error, "Could not load prescriptions."))
      .finally(() => setBusy(false));
  }, [product.sku, initialPrescriptionId, initialLensId]);

  async function choosePrescription(id: number) {
    setBusy(true);
    setMessage(null);
    setAuthRequired(false);
    try {
      setSelectedPrescription(id);
      setLenses(await getCompatibleLenses(id));
      setStep(2);
    } catch (error) {
      handleError(error, "Could not start powered-lens configuration.");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!selectedPrescription || !selectedLens) return;
    setBusy(true);
    setMessage(null);
    setAuthRequired(false);
    try {
      const cartResponse = await addPoweredItem(product.sku, selectedPrescription);
      await configurePoweredItem(cartResponse.mutation.item_id, selectedLens.lens_id, coatings);
      notifyCartUpdated();
      setStep(3);
    } catch (error) {
      handleError(error, "Could not save lens configuration.");
    } finally {
      setBusy(false);
    }
  }

  const coatingOptions = useMemo(() => selectedLens?.coatings || [], [selectedLens]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-label="Add prescription lenses" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head"><h2>Add prescription lenses</h2><button type="button" aria-label="Close" className="icon-button" onClick={onClose}><CloseIcon /></button></div>
        <div className="modal-body">
          <div className="stepper" aria-hidden="true"><span className="active" /><span className={step >= 2 ? "active" : ""} /><span className={step >= 3 ? "active" : ""} /></div>
          {step === 1 && (
            <div>
              <h3>Choose an approved prescription</h3>
              <p style={{ color: "var(--muted)", fontSize: 12 }}>Only approved prescriptions are shown here.</p>
              {busy ? <div className="skeleton" style={{ minHeight: 140 }} /> : authRequired ? (
                <div className="empty-state" style={{ padding: 30 }}>
                  Sign in to continue with your prescription.
                  <div className="form-actions" style={{ justifyContent: "center" }}><a className="btn primary" href={loginHref}>Sign in</a></div>
                </div>
              ) : prescriptions.length ? (
                <div className="prescription-list">{prescriptions.map((prescription) => <button type="button" key={prescription.id} className="choice-button" onClick={() => void choosePrescription(prescription.id)}><div><strong>Prescription #{prescription.id}</strong><span>{prescription.status_label}</span></div><ArrowIcon size={17} /></button>)}</div>
              ) : (
                <div className="empty-state" style={{ padding: 30 }}>No approved prescription yet. <a href="/prescription" style={{ textDecoration: "underline" }}>Upload one first.</a></div>
              )}
            </div>
          )}
          {step === 2 && (
            <div>
              <h3>Choose your lens</h3>
              <p style={{ color: "var(--muted)", fontSize: 12 }}>Compatible with prescription #{selectedPrescription}.</p>
              {authRequired ? (
                <div className="empty-state" style={{ padding: 30 }}>Your session has expired.<div className="form-actions" style={{ justifyContent: "center" }}><a className="btn primary" href={loginHref}>Sign in again</a></div></div>
              ) : lenses.length ? (
                <div className="lens-grid">{lenses.map((lens) => <button type="button" key={lens.lens_id} className="lens-card" style={{ textAlign: "left", cursor: "pointer", borderColor: selectedLens?.lens_id === lens.lens_id ? "var(--ink)" : undefined }} onClick={() => { setSelectedLens(lens); setCoatings([]); }}><h4>{lens.name}</h4><p>{lens.vision_type.name} · Index {lens.refractive_index.display_name || lens.refractive_index.value}</p><strong>{lens.price_visible ? money(lens.base_price_including_gst) : lens.status_label}</strong></button>)}</div>
              ) : !busy && <div className="empty-state" style={{ padding: 26 }}>No compatible lens is currently available for this prescription. Our catalogue can be updated without changing your saved prescription.</div>}
              {selectedLens && coatingOptions.length > 0 && (
                <div style={{ marginTop: 20 }}><strong style={{ fontSize: 13 }}>Optional coatings</strong><div style={{ display: "grid", gap: 8, marginTop: 10 }}>{coatingOptions.map((coating) => <label key={coating.id} style={{ display: "flex", gap: 9, alignItems: "center", fontSize: 12 }}><input type="checkbox" checked={coatings.includes(coating.id)} onChange={(event) => setCoatings((ids) => event.target.checked ? [...ids, coating.id] : ids.filter((id) => id !== coating.id))} />{coating.name}</label>)}</div></div>
              )}
              {!authRequired && <div className="form-actions"><button type="button" className="btn primary block" disabled={!selectedLens || busy} onClick={() => void finish()}>{busy ? "Saving…" : "Add configured eyewear to bag"}</button></div>}
            </div>
          )}
          {step === 3 && <div style={{ textAlign: "center", padding: "24px 0" }}><div className="feature-icon" style={{ margin: "0 auto 16px" }}><CheckIcon /></div><h3>Configured and added</h3><p style={{ color: "var(--muted)", fontSize: 12 }}>Your frame and compatible prescription lens are now in the bag.</p><a className="btn primary" href="/cart">Go to bag</a></div>}
          {message && !authRequired && <div className="form-message">{message}</div>}
        </div>
      </div>
    </div>
  );
}
