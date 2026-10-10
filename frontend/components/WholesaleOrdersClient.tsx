"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getWholesaleOrders } from "@/lib/api";
import type { WholesaleOrderSummary } from "@/lib/api-types";
import { compactDate, money } from "@/lib/format";
import { ArrowIcon } from "./Icons";
export default function WholesaleOrdersClient(){const[orders,setOrders]=useState<WholesaleOrderSummary[]>([]);const[loading,setLoading]=useState(true);const[message,setMessage]=useState<string|null>(null);useEffect(()=>{getWholesaleOrders().then(setOrders).catch(e=>setMessage(e instanceof ApiError?e.message:"Could not load trade orders.")).finally(()=>setLoading(false));},[]);if(loading)return <div className="skeleton" style={{minHeight:280}}/>;if(message)return <div className="empty-state">{message}</div>;if(!orders.length)return <div className="empty-state">No trade orders yet.</div>;return <div className="order-list">{orders.map((o)=><Link href={`/wholesale/orders/${o.order_number}`} className="order-card order-link" key={o.order_number}><div><div className="order-number">{o.order_number}</div><div className="order-meta"><span>{compactDate(o.created_at)}</span><span className={`status-pill ${o.status}`}>{o.status_label}</span><span>{o.payment_status_label}</span><span>{o.total_boxes} boxes</span></div></div><div className="order-total"><strong>{money(o.grand_total_including_gst)}</strong><ArrowIcon size={16}/></div></Link>)}</div>}
