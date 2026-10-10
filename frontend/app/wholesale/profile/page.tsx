import WholesaleNav from "@/components/WholesaleNav";
import WholesaleProfileClient from "@/components/WholesaleProfileClient";
export const metadata={title:"Trade profile"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / profile</div><h1 className="display-title">Business & billing.</h1></div><section className="section compact"><div className="container"><WholesaleProfileClient/></div></section></>}
