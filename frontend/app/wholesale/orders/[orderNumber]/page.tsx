import WholesaleNav from "@/components/WholesaleNav";
import WholesaleOrderClient from "@/components/WholesaleOrderClient";
export const metadata={title:"Trade order"};
export default async function Page({params}:{params:Promise<{orderNumber:string}>}){const{orderNumber}=await params;return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / order</div><h1 className="display-title">Order details.</h1></div><section className="section compact"><div className="container"><WholesaleOrderClient orderNumber={orderNumber}/></div></section></>}
