import CartClient from "@/components/CartClient";
export const metadata = { title: "Bag" };
export default function CartPage() { return <><div className="container page-hero"><div className="eyebrow">Your bag</div><h1 className="display-title">Review your eyewear.</h1></div><section className="section compact"><div className="container"><CartClient/></div></section></>; }
