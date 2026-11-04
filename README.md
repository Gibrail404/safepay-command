# SafePay Command

An AI decision platform for payment risk, sanctions screening and fraud investigation, built in public as a portfolio project. It is independent and is not affiliated with, endorsed by, or built from any company's data or code.

**Status: M2 partly done.** Built and tested: the real-data pipeline (M0), the kernel (M1), and trained models (M2): a transaction risk model (LightGBM, PyTorch MLP, logistic regression, calibrated, with a generated report) and a scam-like text model, both served as read-only tools. The kernel (M1): a hash-chained ledger, idempotent and replayable decisions, a deterministic policy engine, a tool gateway with risk tiers, signed capabilities and approvals, and the HTTP API. Also built: the model gateway (redaction, injection screening, validation, retries, budgets, provider fallback chain), the Interviewer and Explainer agents with a deterministic faithfulness checker, and a generated provider evaluation (`docs/reports/llm_eval.md`). Not built yet: screening, the simulator, the console (M3 and later).

- Master spec: [docs/SPEC.md](docs/SPEC.md)
- Data register, licences and verification log: [docs/DATA.md](docs/DATA.md)

## Principles

1. Real data wherever a public dataset exists. Where none exists (scam conversations), a simulator is used and everything it produces is labelled "simulated".
2. No hand-written product data. Raw files are downloaded by script and verified against a checksum; processed data and its manifest are generated.
3. Every metric is reported with its data source and, once evaluation exists, with confidence intervals.

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pandas numpy scipy pyarrow pyyaml pytest
cd pipelines && python -m safepay_data all    # downloads and validates the real datasets (about 150 MB)
cd .. && python -m pytest -q                         # unit tests plus tests on the real data
```

## Run the kernel

```bash
docker compose up -d db                                   # PostgreSQL 16 on localhost:5433 (development password, localhost only)
export DATABASE_URL=postgresql+psycopg://safepay:safepay_dev_only@127.0.0.1:5433/safepay_test
export SAFEPAY_TENANTS="demo:replace-with-your-own-key"   # tenant:key pairs
PYTHONPATH=kernel:ml:screening uvicorn --factory safepay.api:create_app --port 8000
# tests: SQLite by default, PostgreSQL (including the concurrency tests) with:
SAFEPAY_TEST_DATABASE_URL=$DATABASE_URL python -m pytest tests/kernel -q
```
The API contract is generated from the code into `docs/openapi.json` (`python scripts/export_openapi.py`). Policies are version-controlled rules in `config/policies/`.

## Train the models (real data)

```bash
cd pipelines && python -m safepay_data all && cd ../ml
python -m safepay_ml.train_risk     # writes models/risk/ and docs/reports/risk_model.md (about 20 s)
python -m safepay_ml.train_text     # writes models/text_scam/ and docs/reports/text_model.md (about 1 s)
```
macOS note: LightGBM needs `brew install libomp`, and LightGBM and PyTorch must never share one process (see `ml/safepay_ml/__init__.py`).

## Data in v0.1 (all downloaded and validated, see docs/DATA.md for licence caveats)

| Dataset | Rows | Role |
|---|---|---|
| ULB credit card fraud (real, anonymised) | 284,807 (492 fraud) | transaction-risk model |
| UCI SMS Spam Collection (CC BY 4.0) | 5,574 | scam-like text classifier |
| OFAC SDN list (official) | 19,485 | payee and name screening |

Citations: Dal Pozzolo, Caelen, Johnson, Bontempi (IEEE CIDM 2015) for the ULB data; Almeida and Hidalgo (2011), UCI, doi:10.24432/C5CC84 for SMS Spam.

## Roadmap

v1 risk model, text classifier, screening, interception flow, analyst workbench, faithfulness evals. v2 simulator and counterfactual estimators. v3 graph-based ring detection and conformal abstention. See the spec for exit criteria.
