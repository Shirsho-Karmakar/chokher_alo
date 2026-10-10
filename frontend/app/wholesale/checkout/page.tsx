import WholesaleNav from "@/components/WholesaleNav";
import WholesaleCheckoutClient from "@/components/WholesaleCheckoutClient";
export const metadata={title:"Trade checkout"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / checkout</div><h1 className="display-title">Confirm trade order.</h1></div><section className="section compact"><div className="container"><WholesaleCheckoutClient/></div></section></>}
