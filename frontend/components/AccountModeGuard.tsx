"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { getSession } from "@/lib/api";

function isWholesalePath(pathname: string) {
  return (
    pathname === "/wholesale" ||
    pathname.startsWith("/wholesale/")
  );
}

function isRetailPath(pathname: string) {
  return (
    pathname === "/" ||
    pathname === "/login" ||
    pathname === "/shop" ||
    pathname.startsWith("/shop/") ||
    pathname === "/product" ||
    pathname.startsWith("/product/") ||
    pathname === "/prescription" ||
    pathname.startsWith("/prescription/") ||
    pathname === "/cart" ||
    pathname.startsWith("/cart/") ||
    pathname === "/checkout" ||
    pathname.startsWith("/checkout/") ||
    pathname === "/account" ||
    pathname.startsWith("/account/") ||
    pathname === "/wishlist" ||
    pathname.startsWith("/wishlist/")
  );
}

export default function AccountModeGuard({
  children
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    setReady(false);

    getSession()
      .then((session) => {
        if (!active) return;

        if (!session.authenticated) {
          if (
            isWholesalePath(pathname) &&
            pathname !== "/wholesale/login"
          ) {
            window.location.replace("/wholesale/login");
            return;
          }

          setReady(true);
          return;
        }

        if (session.account_mode === "wholesale") {
          if (isRetailPath(pathname)) {
            window.location.replace("/wholesale/catalogue");
            return;
          }
        }

        if (session.account_mode === "retail") {
          if (isWholesalePath(pathname)) {
            window.location.replace("/");
            return;
          }
        }

        setReady(true);
      })
      .catch(() => {
        if (active) setReady(true);
      });

    return () => {
      active = false;
    };
  }, [pathname]);

  if (!ready) {
    return (
      <div
        className="container"
        style={{
          minHeight: "55vh",
          display: "grid",
          placeItems: "center"
        }}
      >
        <div className="eyebrow">
          Checking account access...
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
