import RetailOrderClient from "@/components/RetailOrderClient";
export const metadata = { title: "Order" };
export default async function OrderPage({ params }: { params: Promise<{ orderNumber: string }> }) {
  const { orderNumber } = await params;
  return <><div className="container page-hero compact-page-hero"><div className="eyebrow">Account / order</div><h1 className="display-title">Order details.</h1></div><section className="section compact"><div className="container"><RetailOrderClient orderNumber={orderNumber}/></div></section></>;
}
