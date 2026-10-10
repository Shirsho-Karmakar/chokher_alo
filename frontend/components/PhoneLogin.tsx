"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, requestRetailOtp, requestWholesaleOtp, verifyRetailOtp, verifyWholesaleOtp } from "@/lib/api";

function safeNext(value: string | null, fallback: string) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/backend")) return fallback;
  return value;
}

export default function PhoneLogin({ wholesale = false }: { wholesale?: boolean }) {
  const [phone, setPhone] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setInterval(() => setResendIn((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [resendIn > 0]);

  async function sendOtp() {
    const result = wholesale
      ? await requestWholesaleOtp(phone)
      : await requestRetailOtp(phone);

    setChallenge(result.challenge_id);
    setCode("");
    setResendIn(result.resend_after_seconds);

    const expiryMinutes = Math.max(
      1,
      Math.round(result.expires_in_seconds / 60)
    );

    if (result.development_otp) {
      setMessage(
        `Local development OTP: ${result.development_otp} · expires in ${expiryMinutes} minutes.`
      );
    } else {
      setMessage(
        `OTP sent. It expires in ${expiryMinutes} minutes.`
      );
    }
  }

  async function requestOtp(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await sendOtp();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not send OTP.");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (busy || resendIn > 0) return;
    setBusy(true);
    setMessage(null);
    try {
      await sendOtp();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Could not resend OTP.");
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    if (!challenge) return;
    setBusy(true);
    setMessage(null);
    try {
      if (wholesale) await verifyWholesaleOtp(challenge, code);
      else await verifyRetailOtp(challenge, code);
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = safeNext(next, wholesale ? "/wholesale/dashboard" : "/account");
    } catch (error) {
      if (error instanceof ApiError && ["otp_expired", "otp_already_used", "otp_attempt_limit_exceeded"].includes(error.code)) {
        setChallenge(null);
        setCode("");
        setResendIn(0);
      }
      setMessage(error instanceof ApiError ? error.message : "Could not verify OTP.");
    } finally {
      setBusy(false);
    }
  }

  if (!challenge) {
    return (
      <form onSubmit={requestOtp}>
        <div className="field"><label>Mobile number</label><input required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" autoComplete="tel" inputMode="tel"/></div>
        <div className="form-actions"><button className="btn primary block" disabled={busy || phone.trim().length < 10}>{busy ? "Sending…" : "Send OTP"}</button></div>
        {message && <div className="form-message">{message}</div>}
      </form>
    );
  }

  return (
    <form onSubmit={verify}>
      <div className="otp-destination">Code sent to <strong>{phone}</strong></div>
      <div className="field"><label>6-digit OTP</label><input required inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="••••••" autoComplete="one-time-code"/></div>
      <div className="form-actions"><button className="btn primary block" disabled={busy || code.length !== 6}>{busy ? "Checking…" : "Continue"}</button></div>
      <div className="otp-actions"><button type="button" className="text-button" disabled={busy || resendIn > 0} onClick={() => void resend()}>{resendIn > 0 ? `Resend in ${resendIn}s` : "Resend OTP"}</button><button type="button" className="text-button" onClick={() => {setChallenge(null); setCode(""); setMessage(null); setResendIn(0);}}>Use a different number</button></div>
      {message && <div className="form-message">{message}</div>}
    </form>
  );
}
