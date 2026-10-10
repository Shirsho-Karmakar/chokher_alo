"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, getWholesaleDashboard, getWholesaleProfile, getWholesaleStatus } from "@/lib/api";
import type { WholesaleProfile } from "@/lib/api-types";

export default function WholesaleDashboardClient() {
  const [state, setState] = useState<{reference?: string; status?: string; contacts?: Array<{label:string; phone_number:string}>; approved?: boolean}>({});
  const [profile,setProfile]=useState<WholesaleProfile|null>(null);
  const [loading,setLoading]=useState(true); const [message,setMessage]=useState<string|null>(null);
  useEffect(()=>{Promise.allSettled([getWholesaleStatus(),getWholesaleDashboard(),getWholesaleProfile()]).then(([s,d,p])=>{if(s.status==="fulfilled")setState(x=>({...x,reference:s.value.reference_id,status:s.value.status_label,contacts:s.value.verification.contacts}));if(d.status==="fulfilled")setState(x=>({...x,reference:d.value.reference_id,approved:true}));if(p.status==="fulfilled")setProfile(p.value);if(s.status==="rejected"&&d.status==="rejected")setMessage(s.reason instanceof ApiError?s.reason.message:"Could not load wholesale account.");}).finally(()=>setLoading(false));},[]);
  if(loading)return <div className="skeleton" style={{minHeight:300}}/>;
  if(message)return <div className="empty-state">{message}<div className="form-actions" style={{justifyContent:"center"}}><Link href="/wholesale/login" className="btn primary">Wholesale sign in</Link></div></div>;
  if(!state.approved)return <div className="verification-panel"><div className="eyebrow">Verification pending</div><h2>{state.status||"Wholesale account"}</h2><p>Your trade reference is <strong>{state.reference}</strong>. Wholesale pricing and ordering unlock after approval.</p>{state.contacts?.length?<div className="verification-contacts">{state.contacts.map((c,i)=><div key={i}><span>{c.label||"Wholesale support"}</span><strong>{c.phone_number}</strong></div>)}</div>:null}<Link href="/wholesale/profile" className="btn ghost">Complete business profile</Link></div>;
  return <><div className="dashboard-grid"><Link href="/wholesale/catalogue" className="dashboard-card"><div className="category-kicker">Catalogue</div><div className="metric">Order</div><p>Find prescription-compatible wholesale lenses and bulk tiers.</p></Link><Link href="/wholesale/cart" className="dashboard-card"><div className="category-kicker">Trade cart</div><div className="metric">Review</div><p>Manage eye-wise box quantities and validate MOQ.</p></Link><Link href="/wholesale/orders" className="dashboard-card"><div className="category-kicker">Orders</div><div className="metric">Track</div><p>Payments, fulfilment, tracking and invoices.</p></Link></div><div className="form-card" style={{marginTop:20}}><div className="form-title-row"><div><div className="eyebrow">Account</div><h3>{profile?.business_name||state.reference}</h3></div><span className="status-pill approved">Approved</span></div><p className="helper">Reference {state.reference} · {profile?.invoice_email||"Complete invoice email"}</p><Link href="/wholesale/profile" className="btn ghost">Business & billing</Link></div></>;
}
