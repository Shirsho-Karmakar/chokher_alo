import CheckoutClient from "@/components/CheckoutClient";
export const metadata = { title: "Checkout" };
export default function CheckoutPage() {
  return <><div className="container page-hero checkout-hero"><div className="eyebrow">Secure checkout</div><h1 className="display-title">Delivery. Payment. Done.</h1><p>A focused single-screen checkout for West Bengal.</p></div><section className="section compact"><div className="container"><CheckoutClient/></div></section></>;
}
