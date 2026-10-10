# Chokher Alo

Full-stack eyewear commerce platform: Django backend + Next.js storefront.

## Launch scope

- English only
- retail delivery to configured serviceable PIN codes in West Bengal
- eyeglasses, sunglasses and prescription lenses
- phone OTP authentication
- Razorpay and Cash on Delivery
- prescription upload/review/compatibility journey
- separate wholesale workspace

## Structure

```text
apps/        Django applications
config/      Django project settings/URLs
frontend/    Next.js + TypeScript storefront
manage.py
```

## Backend setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

PostgreSQL settings, OTP provider and Razorpay values are configured through `.env`.

## Frontend setup

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

Read `LAUNCH_CHECKLIST.md` first, then `frontend/README.md` and `frontend/BACKEND_INTEGRATION.md` for the frontend/API details.

After installing both backend and frontend dependencies, run `./scripts/verify-local.sh` before deployment.
