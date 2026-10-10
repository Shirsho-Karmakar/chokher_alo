import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 20, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  );
}

export const SearchIcon = (props: IconProps) => <Svg {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></Svg>;
export const UserIcon = (props: IconProps) => <Svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/></Svg>;
export const BagIcon = (props: IconProps) => <Svg {...props}><path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/></Svg>;
export const ArrowIcon = (props: IconProps) => <Svg {...props}><path d="M5 12h14"/><path d="m14 7 5 5-5 5"/></Svg>;
export const MenuIcon = (props: IconProps) => <Svg {...props}><path d="M4 7h16M4 12h16M4 17h16"/></Svg>;
export const CloseIcon = (props: IconProps) => <Svg {...props}><path d="m6 6 12 12M18 6 6 18"/></Svg>;
export const UploadIcon = (props: IconProps) => <Svg {...props}><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></Svg>;
export const ShieldIcon = (props: IconProps) => <Svg {...props}><path d="M12 3 5 6v5c0 4.5 2.5 8 7 10 4.5-2 7-5.5 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></Svg>;
export const TruckIcon = (props: IconProps) => <Svg {...props}><path d="M3 6h11v10H3z"/><path d="M14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></Svg>;
export const SparkIcon = (props: IconProps) => <Svg {...props}><path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z"/><path d="m18 14 .8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14Z"/></Svg>;
export const ChevronDownIcon = (props: IconProps) => <Svg {...props}><path d="m7 10 5 5 5-5"/></Svg>;
export const CheckIcon = (props: IconProps) => <Svg {...props}><path d="m5 12 4 4L19 6"/></Svg>;
