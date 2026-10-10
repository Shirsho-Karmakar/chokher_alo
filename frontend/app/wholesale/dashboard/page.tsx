import WholesaleNav from "@/components/WholesaleNav";
import WholesaleDashboardClient from "@/components/WholesaleDashboardClient";
export const metadata={title:"Trade dashboard"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Chokher Alo Trade</div><h1 className="display-title">Wholesale workspace.</h1><p>Prescription-matched lens ordering for approved optical partners.</p></div><section className="section compact"><div className="container"><WholesaleDashboardClient/></div></section></>}
