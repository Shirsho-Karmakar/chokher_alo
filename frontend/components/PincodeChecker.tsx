"use client";

import { FormEvent, useState } from "react";
import { ApiError, checkServiceability } from "@/lib/api";

export default function PincodeChecker({ compact = false }: { compact?: boolean }) {
  const [pin, setPin] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [ok, setOk] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  async function check(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMessage(null); setOk(null);
    try {
      const result = await checkServiceability(pin);
      setOk(result.serviceable);
      setMessage(result.message);
    } catch (error) {
      setOk(false);
      setMessage(error instanceof ApiError ? error.message : "Could not check this PIN code.");
    } finally { setBusy(false); }
  }

  return <div className={compact ? "pincode compact-pin" : "pincode"}>
    <div className="pincode-title">Check delivery</div>
    <form onSubmit={check} className="pincode-form">
      <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="6-digit PIN" aria-label="PIN code" required pattern="[1-9][0-9]{5}" />
      <button disabled={busy || pin.length !== 6}>{busy ? "Checking…" : "Check"}</button>
    </form>
    {message && <div className={`pin-result ${ok ? "success" : "error"}`}>{message}</div>}
  </div>;
}
