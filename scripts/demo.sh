#!/usr/bin/env bash
# One command for a local demo: database, API, real alerts as cases, console. Needs Docker, the Python venv (.venv) with dependencies, the downloaded data and trained models (see README), and node.
# Stop everything with Ctrl-C. The demo key is a local development key: never reuse it anywhere else.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d db
until docker compose exec -T db pg_isready -U safepay -d postgres >/dev/null 2>&1; do sleep 1; done
docker compose exec -T db psql -U safepay -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='safepay'" | grep -q 1 || docker compose exec -T db psql -U safepay -d postgres -c "CREATE DATABASE safepay" >/dev/null
bash scripts/dev_server.sh > /tmp/safepay-api.log 2>&1 & API=$!
trap 'kill $API ${WEB:-} 2>/dev/null || true' EXIT INT TERM
until curl -sf http://127.0.0.1:8000/healthz >/dev/null; do sleep 1; done
if [ "$(curl -s -H 'X-API-Key: demo-key' http://127.0.0.1:8000/v1/cases/stats | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["open"]+d["dispositioned"])')" = "0" ]; then
  .venv/bin/python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key
fi
[ -d console/node_modules ] || (cd console && npm install)
(cd console && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev) & WEB=$!
echo; echo "SafePay demo: http://localhost:3000  (create an account on the first screen; it joins the demo tenant)"; wait
