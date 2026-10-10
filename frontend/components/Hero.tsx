import Link from "next/link";
import { ArrowIcon, UploadIcon } from "./Icons";

export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-inner">
        <div className="hero-copy">
          <div className="eyebrow">Optical shopping, simplified</div>
          <h1>See clearly.<br/>Choose simply.</h1>
          <p>Premium everyday eyewear, prescription-ready frames and compatible lenses in a low-click shopping experience designed for West Bengal.</p>
          <div className="hero-actions">
            <Link className="btn primary" href="/shop?offer_type=frame_only">Shop frames <ArrowIcon size={16}/></Link>
            <Link className="btn ghost" href="/prescription"><UploadIcon size={16}/> Upload prescription</Link>
          </div>
        </div>
        <div className="hero-visual" aria-label="Featured eyewear">
          <div className="hero-card back"><img src="/products/frame-03.png" alt="Mauve optical frame"/></div>
          <div className="hero-card main"><img src="/products/frame-13.png" alt="Classic black optical frame"/></div>
          <div className="hero-card mini"><img src="/products/frame-14.png" alt="Blue optical frame"/></div>
          <div className="hero-note">Frames + powered lenses</div>
        </div>
      </div>
    </section>
  );
}
