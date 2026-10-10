"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, createAddress, getAddresses, removeAddress, updateAddress } from "@/lib/api";
import type { Address } from "@/lib/api-types";

export default function AddressBook({ selectable = false, selectedId, onSelect }: { selectable?: boolean; selectedId?: number | null; onSelect?: (id: number) => void }) {
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Address | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh(preferredId?: number) {
    try {
      const list = await getAddresses();
      setAddresses(list);
      if (selectable && list.length) {
        const currentExists = selectedId && list.some((a) => a.id === selectedId);
        if (preferredId) onSelect?.(preferredId);
        else if (!currentExists) onSelect?.((list.find((a) => a.is_default_delivery) || list[0]).id);
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not load addresses.");
    }
  }

  useEffect(() => { void refresh(); }, []);

  function openAdd() {
    setEditing(null);
    setFormOpen(true);
    setMessage(null);
  }

  function openEdit(address: Address) {
    setEditing(address);
    setFormOpen(true);
    setMessage(null);
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    const form = new FormData(e.currentTarget);
    const values: Record<string, string | boolean> = {};
    for (const [key, value] of form.entries()) values[key] = String(value);
    values.state = "WB";
    values.is_default_delivery = form.get("is_default_delivery") === "on";
    values.is_default_billing = form.get("is_default_billing") === "on";

    try {
      const saved = editing ? await updateAddress(editing.id, values) : await createAddress(values);
      setEditing(null);
      setFormOpen(false);
      await refresh(saved.id);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not save this address.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Remove this saved address?")) return;
    try {
      await removeAddress(id);
      if (editing?.id === id) { setEditing(null); setFormOpen(false); }
      await refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not remove address.");
    }
  }

  return <div>
    <div className="address-grid">
      {addresses.map((address) => <div key={address.id} className={`address-card ${selectable && selectedId === address.id ? "selected" : ""}`} onClick={() => selectable && onSelect?.(address.id)} role={selectable ? "button" : undefined} tabIndex={selectable ? 0 : undefined} onKeyDown={(e) => { if (selectable && (e.key === "Enter" || e.key === " ")) onSelect?.(address.id); }}>
        <div className="address-head"><strong>{address.label || "Saved address"}</strong>{selectable && <span className="radio-dot" aria-hidden/>}</div>
        <div className="address-name">{address.recipient_name}</div>
        <p>{address.address_line_1}{address.address_line_2 ? `, ${address.address_line_2}` : ""}<br/>{address.landmark ? `${address.landmark}, ` : ""}{address.city}, {address.district}<br/>West Bengal {address.postal_code}<br/>{address.phone_number}</p>
        <div className="tag-row">{address.is_default_delivery && <span className="tag">Default delivery</span>}{address.is_default_billing && <span className="tag">Default billing</span>}</div>
        <div className="address-actions">
          <button className="text-button" type="button" onClick={(e) => { e.stopPropagation(); openEdit(address); }}>Edit</button>
          {!selectable && <button className="text-button danger" type="button" onClick={(e) => { e.stopPropagation(); void remove(address.id); }}>Remove</button>}
        </div>
      </div>)}
      <button type="button" className="address-card add-address" onClick={openAdd}><span>＋</span><strong>Add address</strong><small>West Bengal only</small></button>
    </div>

    {formOpen && <form key={editing?.id || "new"} className="form-card address-form" onSubmit={submit}>
      <div className="form-title-row"><div><div className="eyebrow">{editing ? "Edit address" : "New address"}</div><h3>{editing ? "Update delivery details" : "Where should we deliver?"}</h3></div><button type="button" className="text-button" onClick={() => { setFormOpen(false); setEditing(null); }}>Close</button></div>
      <div className="form-grid two">
        <div className="field"><label>Label</label><input name="label" defaultValue={editing?.label || ""} placeholder="Home / Office"/></div>
        <div className="field"><label>Recipient name</label><input name="recipient_name" defaultValue={editing?.recipient_name || ""} required/></div>
        <div className="field"><label>Phone number</label><input name="phone_number" defaultValue={editing?.phone_number || ""} required placeholder="+91 98765 43210" autoComplete="tel"/></div>
        <div className="field"><label>PIN code</label><input name="postal_code" defaultValue={editing?.postal_code || ""} required inputMode="numeric" pattern="[1-9][0-9]{5}" maxLength={6} autoComplete="postal-code"/></div>
        <div className="field span-2"><label>Address line 1</label><input name="address_line_1" defaultValue={editing?.address_line_1 || ""} required placeholder="House / flat / road" autoComplete="address-line1"/></div>
        <div className="field span-2"><label>Address line 2</label><input name="address_line_2" defaultValue={editing?.address_line_2 || ""} placeholder="Area / locality" autoComplete="address-line2"/></div>
        <div className="field"><label>Landmark</label><input name="landmark" defaultValue={editing?.landmark || ""}/></div>
        <div className="field"><label>City</label><input name="city" defaultValue={editing?.city || ""} required autoComplete="address-level2"/></div>
        <div className="field"><label>District</label><input name="district" defaultValue={editing?.district || ""} required/></div>
        <div className="field"><label>State</label><input value="West Bengal" disabled/></div>
      </div>
      <div className="check-row"><label><input type="checkbox" name="is_default_delivery" defaultChecked={editing?.is_default_delivery || false}/> Default delivery</label><label><input type="checkbox" name="is_default_billing" defaultChecked={editing?.is_default_billing || false}/> Default billing</label></div>
      <button className="btn primary" disabled={busy}>{busy ? "Saving…" : editing ? "Update address" : "Save address"}</button>
    </form>}
    {message && <div className="form-message">{message}</div>}
  </div>;
}
