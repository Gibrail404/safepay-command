#!/usr/bin/env bash
# Copies the trained risk model and the 3,000-row scenario sample into deploy/demo_assets/, which the Dockerfile picks up. Run it BEFORE `docker build` if you want the deployed demo
# to include the Interception page. The ULB licence terms are not confirmed, so build and publish an image with these assets only into a PRIVATE space until they are.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f data/processed/scenario_pool.parquet ] || .venv/bin/python scripts/build_scenario_pool.py
rm -rf deploy/demo_assets && mkdir -p deploy/demo_assets && touch deploy/demo_assets/.gitkeep      # the placeholder keeps the folder in git so a plain build (no assets) still works
cp -R models deploy/demo_assets/models
cp data/processed/scenario_pool.parquet deploy/demo_assets/scenario_pool.parquet
cp -R ml deploy/demo_assets/ml
find deploy/demo_assets -name __pycache__ -prune -exec rm -rf {} +
echo "demo assets ready in deploy/demo_assets (model, scenario sample, ml package). Now: docker build -t safepay-api ."
