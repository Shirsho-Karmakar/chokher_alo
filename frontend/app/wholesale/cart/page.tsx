import WholesaleNav from "@/components/WholesaleNav";
import WholesaleCartClient from "@/components/WholesaleCartClient";
export const metadata={title:"Trade cart"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / cart</div><h1 className="display-title">Bulk order cart.</h1></div><section className="section compact"><div className="container"><WholesaleCartClient/></div></section></>}
