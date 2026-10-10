# Chokher Alo launch checklist

The application code is prepared for the agreed first launch: English-only, serviceable West Bengal PIN codes, retail + wholesale, phone OTP, Razorpay and retail COD. This file lists the things that require your machine, credentials, catalogue data, or business decisions.

## 1. Install the project locally

Backend:

```bash
cd chokher_alo
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a PostgreSQL database/user matching `.env`, then:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

Frontend in another terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000` and Django Admin at `http://127.0.0.1:8000/admin/`.

## 2. Run the verification command

After dependencies are installed:

```bash
./scripts/verify-local.sh
```

It runs Django checks, verifies that no migrations are missing, TypeScript typechecking, and a real Next.js production build.

## 3. Configure the West Bengal delivery area

In Django Admin, add `Serviceable PIN codes` under Locations. Only rows with:

- State: West Bengal
- Status: Delivery available

will pass checkout. Add the PIN codes you can actually serve; do not bulk-enable all West Bengal PIN codes unless your courier can cover them.

## 4. Configure retail checkout

In Django Admin create/activate a `Retail checkout policy` and decide:

- delivery fee
- free-delivery threshold
- Cash on Delivery enabled/disabled
- payment reservation time
- cancellation window

The storefront reads the policy during checkout and automatically disables COD when the active policy disables it.

## 5. Add the real catalogue

The 15 supplied frame photos are currently a design-preview catalogue only. They cannot be purchased.

Populate the real data in Django Admin in roughly this order:

1. Brands, Categories, Colours, Materials, Frame Shapes and Frame Types
2. Product Designs
3. Product Variants
4. Product Offers (SKU, retail price, GST, availability, frame/sunglass offer type)
5. Product Images
6. Lens Vision Types, Refractive Indices and Coatings
7. Lens Specifications and compatibility/pricing rules

Once real products and images are visible from the API, change:

```env
NEXT_PUBLIC_DEMO_CATALOG=false
```

in `frontend/.env.local` and in the production frontend environment.

## 6. Prescription operations

Test the staff flow in Django Admin:

1. customer uploads a prescription
2. staff reviews/approves it
3. customer sees compatible lenses
4. customer chooses a store frame
5. customer configures the lens and coatings
6. configured eyewear reaches the cart

The customer-owned-frame HTTP endpoints have been removed from the public cart URLs. The launch flow only allows lenses with Chokher Alo frames.

## 7. Razorpay

Start in Razorpay test mode. Add to `.env`:

```env
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

Configure webhook delivery to the public Django routes once the domain exists:

- `/retail/payments/razorpay/webhook/`
- `/api/wholesale/payments/razorpay/webhook/`

If Django is exposed behind a `/backend` reverse-proxy prefix, the public webhook URLs will include that prefix. Test successful payment, failed/closed checkout, duplicate webhook delivery, and payment confirmation before switching Razorpay to live mode.

## 8. Choose a production SMS/OTP provider

This is a real launch blocker. The repository currently contains `ConsoleOTPProvider`, which intentionally refuses to run when `DEBUG=False`.

Choose your production Indian SMS provider (for example the provider your business already uses), obtain its credentials/template setup, and implement/configure a `BaseOTPProvider` subclass. The same applies to production order/stock-alert SMS delivery; the current SMS notification backend is development-only.

Do not launch phone login until a real provider is connected and OTP delivery has been tested on multiple Indian numbers.

## 9. Email and business details

Replace the console email backend with your real mail provider and set a real `DEFAULT_FROM_EMAIL`.

Fill the wholesale invoice seller values in `.env`:

- seller legal/business name
- GSTIN, if applicable
- seller address/state
- invoice email

Also create wholesale verification contacts in Django Admin and test new wholesale registration → approval → catalogue → cart → checkout → invoice.

## 10. Buy the domain and configure production

After you buy the domain, use the production Django settings:

```env
DJANGO_ALLOWED_HOSTS=yourdomain.in,www.yourdomain.in
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.in,https://www.yourdomain.in
DJANGO_DEBUG=False
```

Run Django with:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production ...
```

Serve the site only over HTTPS. The production settings already enable secure session/CSRF cookies and HTTPS-oriented security settings. Put Django behind a reverse proxy/application server rather than exposing `runserver` publicly.

For the Next.js server keep:

```env
DJANGO_BACKEND_URL=http://127.0.0.1:8000
NEXT_PUBLIC_API_PREFIX=/backend
NEXT_PUBLIC_DEMO_CATALOG=false
```

The Next server proxies browser `/backend/*` requests to Django, keeping sessions and CSRF same-origin.

## 11. Final business/legal content

Before accepting real orders, finalize and publish your business-specific:

- privacy policy
- terms of sale/use
- shipping/delivery policy
- cancellation policy
- returns/refunds policy
- contact/support information

The application already warns that custom prescription eyewear is non-refundable, but the rest of the legal wording should match your actual business policy and applicable law rather than being invented in code.

## 12. Final end-to-end test

Use Razorpay test mode and at least two accounts (retail and wholesale). Verify on both desktop and a real phone:

- phone OTP and logout
- public browsing/search/filter/pagination
- frame-only purchase
- prescription upload/approval/compatible-lens route
- powered eyewear cart
- wishlist and stock alerts
- West Bengal serviceability rejection/acceptance
- saved address creation/edit/default behavior
- Razorpay retail checkout
- COD retail checkout
- order tracking/cancellation
- wholesale account approval
- wholesale MOQ/bulk pricing/cart
- wholesale Razorpay and bank-transfer orders
- invoice access

Only switch Razorpay/live SMS and DNS traffic after this passes.
