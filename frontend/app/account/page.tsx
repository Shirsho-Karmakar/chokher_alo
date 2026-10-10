import AccountClient from "@/components/AccountClient";
export const metadata = { title: "Account" };
export default function AccountPage() {
  return <><div className="container page-hero"><div className="eyebrow">Account</div><h1 className="display-title">Your Chokher Alo.</h1><p>Everything you need after you find the right pair.</p></div><section className="section compact"><div className="container"><AccountClient/></div></section></>;
}
