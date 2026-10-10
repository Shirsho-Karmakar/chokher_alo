# Chokher Alo Frontend

Production-oriented Next.js storefront for the Chokher Alo Django backend.

## Product direction

- English-only launch
- delivery limited to serviceable PIN codes in West Bengal
- frames and sunglasses presented as first-class categories
- prescription-first path: upload → approval → compatible lenses → choose frame
- frame-first path: choose frame → approved prescription → compatible lens → cart
- Razorpay and Cash on Delivery for retail delivery
- separate wholesale workspace and wholesale cart/checkout
- no customer-owned-frame journey; the public cart endpoints for that legacy service are disabled for launch

The 15 supplied frame photographs are included under `public/products/` and are used only by the optional preview catalogue. Real catalogue records and `ProductImage` rows remain the source of truth when demo mode is disabled.

## Local development

Start Django first at `http://127.0.0.1:8000`, then from `frontend/`:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

`next.config.mjs` proxies `/backend/*` to Django so the browser can use Django session and CSRF cookies through one origin during local development.

## Preview catalogue

The included `.env.example` uses:

```env
NEXT_PUBLIC_DEMO_CATALOG=true
```

This lets the design be reviewed before real product photography is added to Django. Demo items deliberately cannot be purchased.

After real products and images are populated in Django Admin, use:

```env
NEXT_PUBLIC_DEMO_CATALOG=false
```

## Customer routes

- `/` — home
- `/shop` — searchable/filterable catalogue
- `/product/[sku]` — product details and frame/powered-lens choice
- `/prescription` — upload, review status and compatible lenses
- `/wishlist` — locally saved shortlist
- `/login` — retail phone OTP
- `/cart` — retail cart
- `/checkout` — West Bengal delivery + Razorpay/COD
- `/account` — account and saved addresses
- `/account/orders` — order history
- `/account/orders/[orderNumber]` — order details/tracking/cancellation

## Wholesale routes

- `/wholesale/login`
- `/wholesale/dashboard`
- `/wholesale/catalogue`
- `/wholesale/cart`
- `/wholesale/profile`
- `/wholesale/checkout`
- `/wholesale/orders`
- `/wholesale/orders/[orderNumber]`

## Before launch

1. Run Django migrations, including `retail_orders.0005_cod_support`.
2. Create/activate a `RetailCheckoutPolicy` and configure COD as desired.
3. Add active West Bengal rows to `ServiceablePincode`.
4. Populate real catalogue products, inventory and `ProductImage` rows.
5. Configure Razorpay test keys and test the full payment/webhook lifecycle.
6. Configure real OTP/SMS and notification providers.
7. Set production Django hosts/security settings and configure the final domain/reverse proxy.
8. Turn `NEXT_PUBLIC_DEMO_CATALOG` off.

See `BACKEND_INTEGRATION.md` for the exact API map added/used by this frontend and `../LAUNCH_CHECKLIST.md` for the step-by-step launch work that still requires your data/credentials.
