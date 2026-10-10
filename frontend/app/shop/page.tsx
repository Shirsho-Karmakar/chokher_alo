import { Suspense } from "react";
import ShopClient from "@/components/ShopClient";

export const metadata = { title: "Shop" };
export default function ShopPage() { return <Suspense fallback={<div className="container section"><div className="skeleton" style={{minHeight: 560}}/></div>}><ShopClient/></Suspense>; }
