#!/usr/bin/env bash
# Local development API server. Reads .env (git-ignored) for keys; never prints them.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://safepay:safepay_dev_only@127.0.0.1:5433/safepay}"
export SAFEPAY_TENANTS="${SAFEPAY_TENANTS:-demo:demo-key}"
export SAFEPAY_CORS_ORIGINS="${SAFEPAY_CORS_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000}"
export PYTHONPATH=kernel:ml:screening:lab
exec .venv/bin/uvicorn --factory safepay.api:create_app --port 8000 --workers "${UVICORN_WORKERS:-1}"
