"use client";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, getWholesaleProfile, updateWholesaleProfile } from "@/lib/api";
import type { WholesaleProfile } from "@/lib/api-types";
import AddressBook from "./AddressBook";

export default function WholesaleProfileClient() {
  const [profile, setProfile] = useState<WholesaleProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => { getWholesaleProfile().then(setProfile).catch((e) => setMessage(e instanceof ApiError ? e.message : "Could not load wholesale profile.")); }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setMessage(null);
    const f = new FormData(e.currentTarget);
    try {
      setProfile(await updateWholesaleProfile({
        business_name: String(f.get("business_name") || ""),
        contact_person_name: String(f.get("contact_person_name") || ""),
        gstin: String(f.get("gstin") || ""),
        invoice_email: String(f.get("invoice_email") || "")
      }));
      setMessage("Business profile saved.");
    } catch (err) { setMessage(err instanceof ApiError ? err.message : "Could not save profile."); }
    finally { setBusy(false); }
  }
  if (!profile) return <div className="skeleton" style={{minHeight:320}}/>;
  return <div className="account-stack">
    <form className="form-card" onSubmit={save}>
      <div className="form-title-row"><div><div className="eyebrow">Trade account</div><h3>Business details</h3></div><span className={`status-pill ${profile.status}`}>{profile.status_label}</span></div>
      <div className="form-grid two">
        <div className="field"><label>Business name</label><input name="business_name" defaultValue={profile.business_name} required/></div>
        <div className="field"><label>Contact person</label><input name="contact_person_name" defaultValue={profile.contact_person_name} required/></div>
        <div className="field"><label>GSTIN <small>(optional)</small></label><input name="gstin" defaultValue={profile.gstin} maxLength={15}/></div>
        <div className="field"><label>Invoice email</label><input name="invoice_email" type="email" defaultValue={profile.invoice_email} required/></div>
      </div>
      <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save business profile"}</button>
      {message && <div className="form-message">{message}</div>}
    </form>
    <div className="form-card"><div className="eyebrow">Billing</div><h3>Billing address</h3><p className="helper">Mark one saved address as the default billing address to enable wholesale checkout.</p><AddressBook/></div>
  </div>;
}
