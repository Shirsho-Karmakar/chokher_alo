import PrescriptionHub from "@/components/PrescriptionHub";

export const metadata = { title: "Prescription" };
export default function PrescriptionPage() {
  return <><div className="container page-hero"><div className="eyebrow">Prescription centre</div><h1 className="display-title">Upload. Verify. Match.</h1><p>A clear prescription image is required for powered-lens orders. Written values are optional and can help our optical team review it faster.</p></div><section className="section compact"><div className="container"><PrescriptionHub/></div></section></>;
}
