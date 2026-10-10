import WholesaleNav from "@/components/WholesaleNav";
import WholesaleCatalogueClient from "@/components/WholesaleCatalogueClient";
export const metadata={title:"Trade catalogue"};
export default function Page(){return <><WholesaleNav/><div className="container page-hero compact-page-hero"><div className="eyebrow">Trade / catalogue</div><h1 className="display-title">Trade lens boxes.</h1><p>Choose an exact lens power and order sealed boxes. Each box contains 50 lenses of the same power.</p></div><section className="section compact"><div className="container"><WholesaleCatalogueClient/></div></section></>}
