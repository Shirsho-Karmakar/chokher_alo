"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getWholesaleCart, removeWholesaleCartItem, setWholesaleCartItem } from "@/lib/api";
import type { WholesaleCart } from "@/lib/api-types";
import { money } from "@/lib/format";

export default function WholesaleCartClient(){
 const [cart,setCart]=useState<WholesaleCart|null>(null); const [message,setMessage]=useState<string|null>(null); const [loading,setLoading]=useState(true);
 useEffect(()=>{getWholesaleCart().then(setCart).catch(e=>setMessage(e instanceof ApiError?e.message:"Could not load trade cart.")).finally(()=>setLoading(false));},[]);
 async function qty(item:WholesaleCart["items"][number],boxes:number){try{setCart(await setWholesaleCartItem({variant_id:item.variant_id,boxes}));}catch(e){setMessage(e instanceof ApiError?e.message:"Could not update quantity.");}}
 async function remove(id:number){try{setCart(await removeWholesaleCartItem(id));}catch(e){setMessage(e instanceof ApiError?e.message:"Could not remove item.");}}
 if(loading)return <div className="skeleton" style={{minHeight:340}}/>; if(!cart)return <div className="empty-state">{message||"Trade cart unavailable."}</div>;
 return <div className="cart-layout"><div>{cart.items.length ? <div className="cart-items">{cart.items.map(item=><div className="cart-item b2b-cart-item" key={item.id}><div className="cart-thumb lens-thumb">LENS</div><div><h3>{item.name}</h3><p>{item.sku} · {item.power_label} · {item.units_per_box} lenses/box</p><div className="cart-item-actions"><input className="qty-input" type="number" min={item.minimum_order_boxes} step={item.order_multiple_boxes} value={item.boxes} onChange={(e)=>{const value=Number(e.target.value); if(Number.isFinite(value) && value >= item.minimum_order_boxes) void qty(item,value);}}/><span>boxes</span><button className="text-button danger" onClick={()=>void remove(item.id)}>Remove</button></div>{item.validation_message&&<div className="form-message">{item.validation_message}</div>}</div><strong>{money(item.subtotal_including_gst)}</strong></div>)}</div> : <div className="empty-state">Your trade cart is empty.<div className="form-actions" style={{justifyContent:"center"}}><Link href="/wholesale/catalogue" className="btn primary">Open catalogue</Link></div></div>}{message&&<div className="form-message">{message}</div>}</div><aside className="summary-card"><h3>Trade summary</h3><div className="summary-row"><span>Total boxes</span><strong>{cart.readiness.total_boxes}</strong></div><div className="summary-row total"><span>Subtotal</span><span>{money(cart.readiness.subtotal_including_gst)}</span></div>{cart.readiness.missing_checkout_details.length>0&&<div className="issue">Complete: {cart.readiness.missing_checkout_details.join(", ").replaceAll("_"," ")}</div>}<Link href={cart.readiness.ready?"/wholesale/checkout":"#"} aria-disabled={!cart.readiness.ready} className="btn primary block">Proceed to trade checkout</Link></aside></div>;
}
