import WholesaleNav from "@/components/WholesaleNav";
import WholesaleOrdersClient from "@/components/WholesaleOrdersClient";
export const metadata={title:"Trade orders"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / orders</div><h1 className="display-title">Wholesale orders.</h1></div><section className="section compact"><div className="container"><WholesaleOrdersClient/></div></section></>}
