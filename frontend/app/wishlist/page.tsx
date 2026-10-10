import WishlistClient from "@/components/WishlistClient";
export const metadata = { title: "Wishlist" };
export default function WishlistPage() { return <><div className="container page-hero"><div className="eyebrow">Saved</div><h1 className="display-title">Your shortlist.</h1><p>Frames you want to come back to.</p></div><section className="section compact"><div className="container"><WishlistClient/></div></section></>; }
