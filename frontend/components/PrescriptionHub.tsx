"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, getCompatibleLenses, getPrescriptions, prescriptionFileUrl, removePrescription, uploadPrescription } from "@/lib/api";
import type { Lens, Prescription } from "@/lib/api-types";
import { money, compactDate } from "@/lib/format";
import { UploadIcon } from "./Icons";

export default function PrescriptionHub() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [lenses, setLenses] = useState<Lens[]>([]);
  const [activePrescription, setActivePrescription] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);

  async function refresh() {
    setLoading(true);
    setMessage(null);
    try {
      setPrescriptions(await getPrescriptions());
      setAuthRequired(false);
    } catch (error) {
      const requiresAuth = error instanceof ApiError && error.code === "authentication_required";
      setAuthRequired(requiresAuth);
      setMessage(error instanceof ApiError ? error.message : "Could not load prescriptions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const form = new FormData(event.currentTarget);
      const created = await uploadPrescription(form);
      setPrescriptions((items) => [created, ...items]);
      event.currentTarget.reset();
      setMessage("Prescription uploaded successfully. It will appear in compatible-lens search after approval.");
    } catch (error) {
      if (error instanceof ApiError && error.code === "authentication_required") {
        setAuthRequired(true);
        setMessage("Sign in to upload and manage prescriptions.");
      } else {
        setMessage(error instanceof ApiError ? error.message : "Could not upload the prescription.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function loadLenses(prescriptionId: number) {
    setBusy(true);
    setMessage(null);
    setActivePrescription(prescriptionId);
    try {
      setLenses(await getCompatibleLenses(prescriptionId));
    } catch (error) {
      setLenses([]);
      if (error instanceof ApiError && error.code === "authentication_required") {
        setAuthRequired(true);
        setMessage("Your session has expired. Sign in to continue.");
      } else {
        setMessage(error instanceof ApiError ? error.message : "Could not load compatible lenses.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function removeSavedPrescription(prescription: Prescription) {
    const confirmed = window.confirm(
      `Remove prescription #${prescription.id} from your account? ` +
      "It will no longer appear in your saved prescriptions. Existing order records are retained securely."
    );

    if (!confirmed) return;

    setRemovingId(prescription.id);
    setMessage(null);

    try {
      await removePrescription(prescription.id);
      setPrescriptions((items) => items.filter((item) => item.id !== prescription.id));

      if (activePrescription === prescription.id) {
        setActivePrescription(null);
        setLenses([]);
      }

      setMessage(`Prescription #${prescription.id} was removed from your account.`);
    } catch (error) {
      setMessage(
        error instanceof ApiError
          ? error.message
          : "Could not remove the prescription."
      );
    } finally {
      setRemovingId(null);
    }
  }

  const uploadPanel = authRequired ? (
    <div className="form-card prescription-signin-card">
      <div className="eyebrow">Your optical profile</div>
      <h2>Sign in before uploading</h2>
      <p>Prescriptions contain personal optical information, so they are kept inside your secure customer account. Phone OTP is the quickest way to continue.</p>
      <Link className="btn primary" href="/login?next=/prescription">Sign in with phone</Link>
      <div className="prescription-flow-mini"><span>1</span> Upload prescription <span>2</span> Approval <span>3</span> Compatible lenses</div>
    </div>
  ) : (
    <div className="form-card">
      <div className="eyebrow">New prescription</div>
      <h2 style={{ fontFamily: "Georgia, serif", fontSize: 36, fontWeight: 500, letterSpacing: "-.03em", marginTop: 0 }}>Upload a clear photo</h2>
      <p style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.65 }}>The image is required. Written values are optional and can help speed up review.</p>
      <form onSubmit={submit}>
        <div className="upload-drop">
          <UploadIcon size={28} />
          <strong style={{ display: "block", marginTop: 12 }}>Prescription image or PDF</strong>
          <input required type="file" name="prescription_file" accept="image/*,.pdf" />
          <small style={{ display: "block", color: "var(--muted)" }}>Make sure both eyes and the doctor/clinic details are readable.</small>
        </div>
        <div className="field" style={{ marginTop: 16 }}><label>Notes (optional)</label><textarea name="customer_notes" placeholder="Anything our optical team should know?" /></div>
        <details style={{ marginTop: 18 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 800 }}>Add written prescription values (optional)</summary>
          <div className="form-grid" style={{ marginTop: 16 }}>
            {(["right", "left"] as const).map((eye) => (
              <div key={eye} className="form-card" style={{ padding: 16 }}>
                <strong style={{ textTransform: "capitalize" }}>{eye} eye</strong>
                <div className="field" style={{ marginTop: 12 }}><label>Sphere</label><input name={`${eye}-sphere`} inputMode="decimal" /></div>
                <div className="field" style={{ marginTop: 10 }}><label>Cylinder</label><input name={`${eye}-cylinder`} inputMode="decimal" /></div>
                <div className="field" style={{ marginTop: 10 }}><label>Axis</label><input name={`${eye}-axis`} inputMode="numeric" /></div>
                <div className="field" style={{ marginTop: 10 }}><label>Add power</label><input name={`${eye}-add_power`} inputMode="decimal" /></div>
                <div className="field" style={{ marginTop: 10 }}><label>Distance PD (mm)</label><input name={`${eye}-distance_pd_mm`} inputMode="decimal" /></div>
                <div className="field" style={{ marginTop: 10 }}><label>Near PD (mm)</label><input name={`${eye}-near_pd_mm`} inputMode="decimal" /></div>
              </div>
            ))}
          </div>
        </details>
        <div className="form-actions"><button type="submit" className="btn primary block" disabled={busy}>{busy ? "Uploading…" : "Upload prescription"}</button></div>
      </form>
    </div>
  );

  return (
    <div className="prescription-layout">
      <div>
        {uploadPanel}
        {message && <div className="form-message prescription-page-message">{message}</div>}
      </div>

      <div>
        <div className="section-heading" style={{ marginBottom: 18 }}><div><h2 style={{ fontSize: 38 }}>Your prescriptions</h2><p>Approved prescriptions unlock compatible-lens matching.</p></div></div>
        {loading ? <div className="skeleton" style={{ minHeight: 220 }} /> : authRequired ? (
          <div className="empty-state">Sign in to see saved prescriptions.<div className="form-actions" style={{ justifyContent: "center" }}><Link className="btn primary" href="/login?next=/prescription">Sign in</Link></div></div>
        ) : prescriptions.length === 0 ? <div className="empty-state">No prescriptions yet. Upload your first prescription to begin.</div> : (
          <div className="prescription-list">
            {prescriptions.map((prescription) => (
              <div className="prescription-card" key={prescription.id}>
                <div className="prescription-card-head">
                  <div><strong>Prescription #{prescription.id}</strong><div style={{ fontSize: 11, color: "var(--muted)", marginTop: 5 }}>Uploaded {compactDate(prescription.created_at)}</div></div>
                  <span className={`status-pill ${prescription.status}`}>{prescription.status_label}</span>
                </div>
                {prescription.customer_review_message && <div className="form-message">{prescription.customer_review_message}</div>}
                <div className="form-actions" style={{ flexWrap: "wrap" }}>
                  <a
                    className="btn ghost"
                    href={prescriptionFileUrl(prescription.file_download_url, true)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Preview
                  </a>

                  {prescription.is_approved ? (
                    <button
                      type="button"
                      className="btn primary"
                      onClick={() => void loadLenses(prescription.id)}
                      disabled={busy || removingId === prescription.id}
                    >
                      See compatible lenses
                    </button>
                  ) : (
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>
                      Compatibility becomes available after approval.
                    </span>
                  )}

                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => void removeSavedPrescription(prescription)}
                    disabled={removingId === prescription.id}
                    style={{ marginLeft: "auto" }}
                  >
                    {removingId === prescription.id ? "Removing…" : "Remove"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {activePrescription && lenses.length > 0 && !authRequired && (
          <div style={{ marginTop: 30 }}>
            <div className="section-heading" style={{ marginBottom: 14 }}><div><h2 style={{ fontSize: 34 }}>Compatible lenses</h2><p>{lenses.length} option{lenses.length === 1 ? "" : "s"} for prescription #{activePrescription}.</p></div></div>
            <div className="lens-grid">
              {lenses.map((lens) => <div className="lens-card" key={lens.lens_id}>
                <h4>{lens.name}</h4>
                <p>{lens.vision_type.name} · Index {lens.refractive_index.display_name || lens.refractive_index.value}<br />{lens.coatings.length ? `Coatings: ${lens.coatings.map((coating) => coating.name).join(", ")}` : "No optional coatings listed"}</p>
                <strong>{lens.price_visible ? `From ${money(lens.base_price_including_gst)}` : lens.status_label}</strong>
                <Link className="text-link lens-frame-link" href={`/shop?offer_type=frame_only&prescription_id=${activePrescription}&lens_id=${lens.lens_id}`}>Choose a frame →</Link>
              </div>)}
            </div>
          </div>
        )}
        {activePrescription && !busy && lenses.length === 0 && !authRequired && <div className="empty-state" style={{ marginTop: 24 }}>No compatible lens is currently available for prescription #{activePrescription}.</div>}
      </div>
    </div>
  );
}
