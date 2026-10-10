import Link from "next/link";
import { ArrowIcon } from "./Icons";

export default function SectionHeading({ title, description, href, linkLabel = "View all" }: { title: string; description?: string; href?: string; linkLabel?: string }) {
  return (
    <div className="section-heading">
      <div><h2>{title}</h2>{description && <p style={{marginTop: 12}}>{description}</p>}</div>
      {href && <Link className="text-link" href={href}>{linkLabel}<ArrowIcon size={15}/></Link>}
    </div>
  );
}
