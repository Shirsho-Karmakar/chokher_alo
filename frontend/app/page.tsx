import Link from "next/link";
import Hero from "@/components/Hero";
import CategoryRail from "@/components/CategoryRail";
import FeaturedProducts from "@/components/FeaturedProducts";
import PrescriptionBanner from "@/components/PrescriptionBanner";
import SectionHeading from "@/components/SectionHeading";
import { ShieldIcon, SparkIcon, TruckIcon } from "@/components/Icons";

export default function Home() {
  return <>
    <Hero/>
    <CategoryRail/>
    <section className="section"><div className="container"><SectionHeading title="Frames worth a closer look" description="A clean, image-first product experience with no prescription wall for ordinary eyewear." href="/shop"/><FeaturedProducts/></div></section>
    <section className="section compact"><div className="container"><PrescriptionBanner/></div></section>
    <section className="section"><div className="container"><SectionHeading title="Built around the optical journey" description="Less friction at the moments that usually make eyewear shopping feel complicated."/><div className="feature-row">
      <div className="feature"><div className="feature-icon"><SparkIcon/></div><h3>Compatible, not overwhelming</h3><p>Approved prescriptions narrow the choice to compatible lens options, so you can shop without decoding a wall of technical specifications.</p></div>
      <div className="feature"><div className="feature-icon"><ShieldIcon/></div><h3>Verified prescription flow</h3><p>Prescription photos are reviewed before powered-lens configuration is completed, keeping the selection process clear and controlled.</p></div>
      <div className="feature"><div className="feature-icon"><TruckIcon/></div><h3>West Bengal first</h3><p>Delivery is currently focused on serviceable PIN codes across West Bengal, with availability checked before you place an order.</p></div>
    </div></div></section>
    <section className="section soft"><div className="container" style={{display: "grid", gridTemplateColumns: "1fr auto", gap: 30, alignItems: "center"}}><div><div className="eyebrow">For optical businesses</div><h2 style={{fontFamily: "Georgia, serif", fontWeight: 500, fontSize: "clamp(38px,5vw,68px)", letterSpacing: "-.04em", margin: 0}}>Wholesale gets its own workspace.</h2></div><Link className="btn primary" href="/wholesale/login">Wholesale login</Link></div></section>
  </>;
}
