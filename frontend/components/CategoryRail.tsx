import Link from "next/link";
import { ArrowIcon } from "./Icons";

const items = [
  ["01", "Eyeglasses", "/shop?offer_type=frame_only"],
  ["02", "Sunglasses", "/shop?offer_type=sunglasses"],
  ["03", "Powered lenses", "/prescription"],
  ["04", "Kids", "/shop?gender=kids"],
  ["05", "Wholesale", "/wholesale/login"]
];

export default function CategoryRail() {
  return <div className="category-rail">{items.map(([num, label, href]) => (
    <Link className="category-tile" href={href} key={label}>
      <span className="category-kicker">{num}</span>
      <span className="category-name">{label}<ArrowIcon size={18}/></span>
    </Link>
  ))}</div>;
}
