import OrdersClient from "@/components/OrdersClient";
export const metadata = { title: "Orders" };
export default function OrdersPage() { return <><div className="container page-hero"><div className="eyebrow">Account / orders</div><h1 className="display-title">Your orders.</h1></div><section className="section compact"><div className="container"><OrdersClient/></div></section></>; }
