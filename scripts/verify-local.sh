#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/5] Django system checks"
python manage.py check

echo "[2/5] Migration consistency"
python manage.py makemigrations --check --dry-run

echo "[3/5] Python bytecode compilation"
python -m compileall -q apps config manage.py

echo "[4/5] Frontend typecheck"
cd frontend
npm run typecheck

echo "[5/5] Frontend production build"
npm run build

echo "All local verification checks passed."
