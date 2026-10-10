import Link from "next/link";
import { ArrowIcon, UploadIcon } from "./Icons";

export default function PrescriptionBanner() {
  return (
    <div className="prescription-banner">
      <div>
        <div className="eyebrow" style={{color: "#98c9d6"}}>Prescription-first shopping</div>
        <h2>Upload once. See what actually works for you.</h2>
        <p>Send a photo of your prescription. Once it is verified, Chokher Alo can show compatible lenses and let you pair them with power-ready frames without making you decode optical jargon yourself.</p>
        <Link className="btn light" href="/prescription"><UploadIcon size={16}/> Upload prescription <ArrowIcon size={15}/></Link>
      </div>
      <div className="prescription-steps">
        <div className="prescription-step"><span className="step-number">1</span><div><strong>Upload</strong><span>A clear photo is required. Written values are optional.</span></div></div>
        <div className="prescription-step"><span className="step-number">2</span><div><strong>Verification</strong><span>Our team reviews the prescription before powered-lens options are enabled.</span></div></div>
        <div className="prescription-step"><span className="step-number">3</span><div><strong>Compatible lenses</strong><span>Only lens options compatible with the approved prescription are surfaced.</span></div></div>
      </div>
    </div>
  );
}
