# Chokher Alo frontend ↔ Django integration

This frontend is wired to the uploaded Django codebase. During this pass, the small API gaps that blocked a complete retail/wholesale experience were filled in rather than mocked in the UI.

## Authentication and session

- `GET /auth/csrf/` — CSRF-cookie bootstrap
- `GET /auth/session/` — current retail/wholesale session summary
- `POST /auth/logout/`
- `POST /auth/phone/request/`
- `POST /auth/phone/verify/`
- `POST /wholesale/auth/phone/request/`
- `POST /wholesale/auth/phone/verify/`

Retail and wholesale use Django session authentication. The Next.js `/backend/*` rewrite keeps browser calls same-origin in development.

## Catalogue and prescriptions

- `GET /catalogue/filters/`
- `GET /catalogue/products/`
- `GET /catalogue/products/<sku>/`
- prescription list/upload endpoints under `/prescriptions/`
- `GET /lenses/compatible/?prescription_id=...`

The legacy customer-owned-frame add/configure routes have also been removed from the public retail-cart URL configuration for launch. The underlying historical models/services are left in place to avoid destructive schema rewrites.

## West Bengal delivery and addresses

Added under `apps.locations`:

- `GET /locations/serviceability/?postal_code=...`
- `GET /locations/addresses/`
- `POST /locations/addresses/`
- `POST /locations/addresses/<id>/`
- `POST /locations/addresses/<id>/deactivate/`

New/updated addresses are restricted to West Bengal for this launch. Retail checkout also enforces the West Bengal launch region server-side and requires an active `ServiceablePincode` row.

## Retail cart and checkout

Existing retail-cart endpoints are used for standard and powered eyewear.

Retail checkout uses:

- `POST /retail/checkout/preview/`
- `POST /retail/checkout/create/`
- `POST /retail/payments/razorpay/confirm/`
- `GET /retail/orders/`
- `GET /retail/orders/<order_number>/`
- `POST /retail/orders/<order_number>/cancel/`

### Cash on Delivery

A real `cod` retail payment method was added instead of relabelling `pay_at_store`.

Migration: `apps/retail_orders/migrations/0005_cod_support.py`

Changes include:

- `RetailCheckoutPolicy.cod_enabled`
- `RetailOrder.PaymentMethod.COD`
- COD stock-reservation reason
- COD restricted to delivery orders
- COD order creation as confirmed/unpaid
- staff delivery transition marks COD payment captured/paid

`pay_at_store` remains a separate store-pickup-only method in the backend and is not exposed by the launch storefront.

## Wholesale

Profile API added:

- `GET /wholesale/profile/`
- `POST /wholesale/profile/`

Wholesale cart HTTP API added on top of the existing service layer:

- `GET /wholesale/cart/`
- `POST /wholesale/cart/items/set/`
- `POST /wholesale/cart/items/<id>/remove/`

Wholesale ordering uses the existing `/api/wholesale/` endpoints for checkout, Razorpay confirmation, order history, order detail, cancellation and invoices.

## Intentionally not added

Google retail OAuth is still not implemented in the Django repository, so the production UI exposes the working phone-OTP method only. A Google button should be added only after a real OAuth backend flow exists.

## Catalogue image proxying

Django catalogue image URLs are normalized through the frontend `/backend` proxy. This prevents production product images from pointing at a private Django upstream such as `127.0.0.1:8000`.

## Validation performed in the packaging environment

- Python `compileall` passes for `apps/`, `config/` and `manage.py`.
- All 57 frontend `.ts/.tsx` application files pass TypeScript syntax/transpile validation in the packaging environment.
- Full Django checks and `next build` could not be executed in the packaging environment because external dependency installation is blocked by DNS/network restrictions. Full semantic TypeScript/Django checks and `next build` could not be executed here because npm/Python dependencies cannot be downloaded in this sandbox. Run the commands below on a normal development machine before deployment:

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate

cd frontend
npm install
npm run typecheck
npm run build
```
