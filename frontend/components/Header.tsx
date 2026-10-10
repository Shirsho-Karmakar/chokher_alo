"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  BagIcon,
  MenuIcon,
  SearchIcon,
  UserIcon,
  CloseIcon
} from "./Icons";

import {
  getCart,
  getSession,
  getWholesaleCart,
  logoutSession
} from "@/lib/api";

import { CART_UPDATED_EVENT } from "@/lib/client-events";

const anonymousRetailNav = [
  ["Eyeglasses", "/shop?offer_type=frame_only"],
  ["Sunglasses", "/shop?offer_type=sunglasses"],
  ["Prescription", "/prescription"],
  ["Kids", "/shop?gender=kids"],
  ["Wholesale", "/wholesale/login"]
] as const;

const retailNav = [
  ["Eyeglasses", "/shop?offer_type=frame_only"],
  ["Sunglasses", "/shop?offer_type=sunglasses"],
  ["Prescription", "/prescription"],
  ["Kids", "/shop?gender=kids"]
] as const;

const wholesaleNav = [
  ["Lens catalogue", "/wholesale/catalogue"],
  ["Trade cart", "/wholesale/cart"],
  ["Orders", "/wholesale/orders"],
  ["Profile", "/wholesale/profile"]
] as const;

export default function Header() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [cartCount, setCartCount] = useState(0);
  const [authenticated, setAuthenticated] = useState(false);
  const [mode, setMode] = useState<"retail" | "wholesale" | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const wholesaleMode = authenticated && mode === "wholesale";

  useEffect(() => {
    let active = true;

    async function refresh() {
      try {
        const session = await getSession();
        if (!active) return;

        setAuthenticated(session.authenticated);
        setMode(session.account_mode);

        if (!session.authenticated) {
          setCartCount(0);
          return;
        }

        try {
          if (
            session.account_mode === "wholesale" &&
            session.wholesale?.is_approved
          ) {
            const cart = await getWholesaleCart();
            if (active) {
              setCartCount(
                cart.items.reduce(
                  (total, item) => total + item.boxes,
                  0
                )
              );
            }
          } else if (session.account_mode === "wholesale") {
            if (active) setCartCount(0);
          } else {
            const cart = await getCart();
            if (active) {
              setCartCount(
                cart.items.reduce(
                  (total, item) => total + item.quantity,
                  0
                )
              );
            }
          }
        } catch {
          if (active) setCartCount(0);
        }
      } catch {
        if (active) {
          setAuthenticated(false);
          setMode(null);
          setCartCount(0);
        }
      }
    }

    void refresh();
    window.addEventListener(CART_UPDATED_EVENT, refresh);
    window.addEventListener("focus", refresh);

    return () => {
      active = false;
      window.removeEventListener(CART_UPDATED_EVENT, refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await logoutSession();
    } finally {
      window.location.href = wholesaleMode ? "/wholesale/login" : "/";
    }
  }

  const navItems = wholesaleMode
    ? wholesaleNav
    : authenticated
      ? retailNav
      : anonymousRetailNav;

  const accountHref = authenticated
    ? wholesaleMode
      ? "/wholesale/dashboard"
      : "/account"
    : "/login";

  const cartHref = wholesaleMode ? "/wholesale/cart" : "/cart";
  const searchHref = wholesaleMode ? "/wholesale/catalogue" : "/shop";
  const logoHref = wholesaleMode ? "/wholesale/catalogue" : "/";

  return (
    <>
      <div className="announcement">
        {wholesaleMode
          ? "Wholesale stock lenses · 50 same-power lenses per sealed box · Trade pricing"
          : "Now serving selected PIN codes across West Bengal · Upload a prescription only when you need powered lenses"}
      </div>

      <header className="header">
        <div className="header-main">
          <Link href={logoHref} className="brand" aria-label="Chokher Alo home">
            <span className="brand-mark"><span /></span>
            <span className="brand-name">CHOKHER ALO</span>
          </Link>

          <nav className="nav" aria-label="Primary navigation">
            {navItems.map(([label, href]) => (
              <Link key={label} href={href}>{label}</Link>
            ))}
          </nav>

          <div className="header-actions">
            <form className="search-compact" action={searchHref}>
              <SearchIcon size={17} />
              <input
                name="q"
                aria-label="Search catalogue"
                placeholder={wholesaleMode ? "Search trade lenses" : "Search frames"}
              />
            </form>

            <Link className="icon-button search-mobile" href={searchHref} aria-label="Search">
              <SearchIcon />
            </Link>

            {!wholesaleMode && (
              <Link className="icon-button heart-link" href="/wishlist" aria-label="Wishlist">
                ♡
              </Link>
            )}

            <Link
              className={`icon-button ${authenticated ? "signed-in" : ""}`}
              href={accountHref}
              aria-label={wholesaleMode ? "Wholesale account" : "Account"}
            >
              <UserIcon />
            </Link>

            <Link
              className="icon-button cart-icon"
              href={cartHref}
              aria-label={wholesaleMode ? "Trade cart" : "Bag"}
            >
              <BagIcon />
              {cartCount > 0 && <span className="count-badge">{cartCount}</span>}
            </Link>

            {authenticated && (
              <button
                className="btn ghost"
                type="button"
                disabled={signingOut}
                onClick={() => void signOut()}
              >
                {signingOut ? "Signing out..." : "Sign out"}
              </button>
            )}

            <button
              className="icon-button mobile-menu"
              type="button"
              aria-label="Open menu"
              aria-expanded={open}
              onClick={() => setOpen(true)}
            >
              <MenuIcon />
            </button>
          </div>
        </div>
      </header>

      {open && (
        <div className="modal-backdrop mobile-menu-backdrop" onClick={() => setOpen(false)}>
          <div
            className="mobile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <strong>CHOKHER ALO</strong>
              <button
                className="icon-button"
                type="button"
                aria-label="Close menu"
                onClick={() => setOpen(false)}
              >
                <CloseIcon />
              </button>
            </div>

            <form className="mobile-search" action={searchHref}>
              <SearchIcon size={17} />
              <input
                name="q"
                aria-label="Search catalogue"
                placeholder={wholesaleMode ? "Search trade lenses" : "Search eyewear"}
              />
            </form>

            <div className="mobile-nav-links">
              {navItems.map(([label, href]) => (
                <Link key={label} href={href} onClick={() => setOpen(false)}>
                  {label}<span>→</span>
                </Link>
              ))}

              {!wholesaleMode && (
                <Link href="/wishlist" onClick={() => setOpen(false)}>
                  Wishlist<span>→</span>
                </Link>
              )}

              <Link href={accountHref} onClick={() => setOpen(false)}>
                {authenticated
                  ? wholesaleMode
                    ? "Trade account"
                    : "My account"
                  : "Sign in"}
                <span>→</span>
              </Link>

              {authenticated && (
                <button
                  className="btn ghost"
                  type="button"
                  disabled={signingOut}
                  onClick={() => void signOut()}
                >
                  {signingOut ? "Signing out..." : "Sign out"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
