"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Footer() {
  const pathname = usePathname();

  const wholesale =
    pathname === "/wholesale" ||
    pathname.startsWith("/wholesale/");

  if (wholesale) {
    return (
      <footer className="footer">
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand">
              <div className="brand" style={{ color: "white" }}>
                <span
                  className="brand-mark"
                  style={{ filter: "invert(1)" }}
                >
                  <span />
                </span>
                <span className="brand-name">CHOKHER ALO TRADE</span>
              </div>

              <p>
                Bulk stock lenses for verified optical businesses.
                Each sealed box contains 50 lenses of one selected power.
              </p>
            </div>

            <div>
              <h4>Trade</h4>
              <div className="footer-links">
                <Link href="/wholesale/catalogue">Lens catalogue</Link>
                <Link href="/wholesale/cart">Trade cart</Link>
                <Link href="/wholesale/orders">Orders</Link>
                <Link href="/wholesale/profile">Business profile</Link>
              </div>
            </div>

            <div>
              <h4>Orders</h4>
              <div className="footer-links">
                <Link href="/wholesale/orders">Track trade orders</Link>
                <span>GST invoice support</span>
                <span>50 same-power lenses / box</span>
                <span>West Bengal delivery</span>
              </div>
            </div>

            <div>
              <h4>Account</h4>
              <div className="footer-links">
                <Link href="/wholesale/dashboard">Dashboard</Link>
                <Link href="/wholesale/profile">
                  Billing and business details
                </Link>
                <span>Wholesale access only</span>
              </div>
            </div>
          </div>

          <div className="footer-bottom">
            <span>© 2026 Chokher Alo. All rights reserved.</span>
            <span>
              Trade pricing and fulfilment are subject to wholesale account terms.
            </span>
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="brand" style={{ color: "white" }}>
              <span
                className="brand-mark"
                style={{ filter: "invert(1)" }}
              >
                <span />
              </span>
              <span className="brand-name">CHOKHER ALO</span>
            </div>

            <p>
              Eyewear and prescription lenses with a simpler way to shop.
              Built for clear choices, verified prescriptions and dependable
              fulfilment across West Bengal.
            </p>
          </div>

          <div>
            <h4>Shop</h4>
            <div className="footer-links">
              <Link href="/shop?offer_type=frame_only">Eyeglasses</Link>
              <Link href="/shop?offer_type=sunglasses">Sunglasses</Link>
              <Link href="/prescription">Prescription lenses</Link>
              <Link href="/shop?gender=kids">Kids</Link>
            </div>
          </div>

          <div>
            <h4>Help</h4>
            <div className="footer-links">
              <Link href="/prescription">Upload prescription</Link>
              <Link href="/account/orders">Track order</Link>
              <Link href="/cart">Bag</Link>
              <span>Delivery: West Bengal</span>
            </div>
          </div>

          <div>
            <h4>Account</h4>
            <div className="footer-links">
              <Link href="/account">My account</Link>
              <Link href="/wishlist">Wishlist</Link>
              <span>Retail access only</span>
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <span>© 2026 Chokher Alo. All rights reserved.</span>
          <span>
            Prescription/custom products are subject to applicable
            non-refundable terms.
          </span>
        </div>
      </div>
    </footer>
  );
}
