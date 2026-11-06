# SafePay Command

An AI decision platform for payment risk, sanctions screening and fraud investigation, built in public as a portfolio project. It is independent and is not affiliated with, endorsed by, or built from any company's data or code.

**Status: milestones M0 to M6 built and tested. Not deployed to a cloud yet** (the container image is built and run locally; see [docs/DEPLOY.md](docs/DEPLOY.md)). Every number below comes from a generated report in `docs/reports/`, each of which states whether its data is real or simulated.

- Master spec: [docs/SPEC.md](docs/SPEC.md) · Harness design: [docs/HARNESS.md](docs/HARNESS.md) · Data register and licence caveats: [docs/DATA.md](docs/DATA.md)
- [Threat model](docs/THREAT_MODEL.md) (each threat with its test and its residual risk) · [Model cards](docs/MODEL_CARDS.md) · [Product requirements](docs/PRD.md) · [Deploying](docs/DEPLOY.md) · [Demo script](docs/DEMO_SCRIPT.md) · [Blog draft](docs/BLOG.md)

![A 45-second tour on real data with a live AI model: a payment is questioned, the case run is replayed, an AI recommendation is overridden with a reason, the audit chain is tampered with, and the policy sliders move](docs/figures/demo.gif)

| | |
|---|---|
| ![Overview counted from real recorded data](docs/figures/console-overview.png) | ![One payment end to end: risk score, questions, decision, ledger, hidden truth](docs/figures/console-interception.png) |
| ![A case, its AI summary, the run replay and the analyst override with a reason](docs/figures/console-override.png) | ![Tampering with a copy of the audit chain, detected in the browser](docs/figures/console-tamper.png) |

## What is in it

| Part | What it does | Evidence |
|---|---|---|
| Kernel | Hash-chained tamper-evident ledger, idempotent and replayable decisions, deterministic policy engine, tool gateway with risk tiers, signed capabilities and one-use approvals | tests, including race tests on PostgreSQL |
| Risk and scam-text models | Calibrated transaction-risk model (LightGBM, PyTorch MLP, logistic regression) and a scam-like text model | `docs/reports/risk_model.md`, `text_model.md` (real data) |
| LLM steps | Model gateway (redaction, injection screening, validation, budgets, provider fallback), Questioner, Explainer and Investigator agents, deterministic faithfulness checker | `docs/reports/llm_eval.md`, `sandbox.md` |
| Screening | OFAC name matching with a policy and an adjudicator that can explain but never clear a hit | `docs/reports/screening.md` (real data) |
| Decision Lab | Simulator with known truth, counterfactual estimators checked against it, uplift, simulation API | `docs/reports/decision_lab.md`, `uplift.md` (simulated) |
| Graph and cases | Real Elliptic transaction graph: does structure help, how alerts group into cases | `docs/reports/graph.md` (real data) |
| Flywheel | How the way analysts' labels are collected changes what the model learns | `docs/reports/flywheel.md` (real transactions, simulated analysts) |
| Interception flow | One payment end to end through the API and the console: real risk model, up to three customer questions, warning signs, policy decision, customer message, audit record, hidden-truth reveal. The AI can only add friction. | `tests/kernel/test_interception.py`, `reports/interception.md` |
| Console | Next.js analyst console that renders only what the API returns: an **overview** counted from real recorded data (AI guardrail gauge, ledger activity, decisions and reasons, AI usage); case queue with a real-link **alert network**; investigation summary with citations and an **analyst override that requires a written reason**; a **run replay** that animates the real recorded steps (facts, redaction, abstain rule, AI call, fact check, fallback, priority, ledger) with real timings; an audit trail where **your browser re-computes every hash** and lets you try to tamper with a copy; a **Decision Lab** with live simulated policy sliders; reports; read-only roles | 21 Playwright browser tests (`cd console && npm run e2e`) |
| Security and operations | Email and password accounts (salted scrypt, expiring sessions, open sign-up only as analyst and capped), roles per account or API key, per-key rate limit, request-size limits, AI spending caps kept in the database, name and address redaction | `docs/THREAT_MODEL.md`, `reports/redaction.md`, `reports/load.md` |

Honest headline findings: **asking the customer questions is where all the scam detection comes from, and a fixed list of questions with keyword rules is a strong baseline**: it held all 80 honest simulated scam victims and none of 80 coached ones, while the AI questioner held 19 of 80 coached ones but missed 8 honest ones (160 simulated scams over two held-out sets: 57% against 50%, paired p of about 0.05; the two sets disagreed on the net, so the two are complementary rather than ranked, and a hybrid of both was no better than the AI alone; rules and the model alone caught none because the scams look like ordinary payments); simple neighbour features add almost nothing on the real graph while the model collapses after a known market shutdown (drift); corrected counterfactual estimators are close to unbiased but their intervals still under-cover; name folding did not help screening; coached victims evade question-based checks. See each report's limits section.

## Principles

1. Real data wherever a public dataset exists. Where none exists (scam conversations, analyst behaviour) a simulator or simulated actor is used and everything it produces is labelled "simulated".
2. No hand-written product data. Raw files are downloaded by script and verified against a checksum; processed data and manifests are generated. The console renders only API responses.
3. Every metric is reported with its data source, and where possible with confidence intervals. Negative results are kept.
4. The LLM assists, it never decides. A deterministic policy engine owns outcomes, and LLM output can only add friction.

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pandas numpy scipy pyarrow pyyaml pytest fastapi uvicorn httpx pydantic sqlalchemy "psycopg[binary]" hypothesis scikit-learn lightgbm torch rapidfuzz matplotlib spacy
python -m spacy download en_core_web_sm         # optional: the name-redaction layer; without it only patterns run
cd pipelines && python -m safepay_data all    # downloads and validates the real datasets (about 300 MB)
cd .. && python -m pytest -q                  # SQLite by default; set SAFEPAY_TEST_DATABASE_URL for PostgreSQL
```
macOS: LightGBM needs `brew install libomp`, and LightGBM and PyTorch must never share one process (see `ml/safepay_ml/__init__.py`).

## Run the API and the console

```bash
docker compose up -d db                                   # PostgreSQL 16 on localhost:5433 (development password, localhost only)
docker compose exec db psql -U safepay -d postgres -c "CREATE DATABASE safepay"      # once
make demo              # or run the steps below one by one
cp .env.example .env   # optional: OLLAMA_API_KEY enables the AI summaries; without it a safe plain summary is used
bash scripts/dev_server.sh                                # API on :8000, API key "demo-key" for scripts, sign-up open on the demo tenant
python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key    # real Elliptic alerts become cases
cd console && npm install && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev      # console on :3000, then create an account on the first screen
```
Deploying (steps in [docs/DEPLOY.md](docs/DEPLOY.md)): `docker build -t safepay-api .`, then `python scripts/check_deploy.py --url <api address> --key <key> --origin <console address> --try-interception` prints PASS or FAIL for each thing that matters. A free-tier deployment exists (Vercel, Railway, Neon); see the first section of that file.

Tests: `SAFEPAY_TEST_DATABASE_URL=postgresql+psycopg://safepay:safepay_dev_only@127.0.0.1:5433/safepay_test python -m pytest tests -q` also runs the PostgreSQL-only concurrency tests. The API contract is generated into `docs/openapi.json` (`python scripts/export_openapi.py`).

## Regenerate the reports

`make help` lists one command per job (`make test-pg`, `make reports`, `make console-check`, `make load`). Each report script was run individually when its report was produced; the full `make reports` chain has not been run end to end.

```bash
cd ml && python -m safepay_ml.train_risk && python -m safepay_ml.train_text && cd ..
python scripts/eval_screening.py && python scripts/eval_redaction.py && python scripts/eval_graph.py && python scripts/eval_flywheel.py
python scripts/eval_lab.py && python scripts/eval_uplift.py           # simulated
python scripts/eval_llm.py && python scripts/eval_sandbox.py          # need OLLAMA_API_KEY (and optionally GEMINI_API_KEY)
```

## Data (all downloaded by script, see docs/DATA.md for licence caveats)

| Dataset | Rows | Role |
|---|---|---|
| ULB credit card fraud (real, anonymised) | 284,807 (492 fraud) | transaction-risk model; amount distribution for the simulator |
| UCI SMS Spam Collection (CC BY 4.0) | 5,574 | scam-like text classifier |
| OFAC SDN list and alias list (official) | 19,485 entries, 20,204 aliases | name screening |
| US Census names (official) | 162,254 surnames, 5,494 first names | non-sanctioned names for screening false-alert rates |
| Elliptic Bitcoin graph (real) | 203,769 nodes, 234,355 edges | graph, cases and the flywheel |

Licences were read from the publishers' pages on 2026-11-07 ([docs/DATA_LICENCES.md](docs/DATA_LICENCES.md)): ULB is under the Open Database / Database Contents licences, Elliptic is **CC BY-NC-ND 4.0** (so it stays local and out of any public instance), and OFAC and Census state no terms on the pages I could read. The repository contains no raw data, only scripts that download it. Citations: Dal Pozzolo, Caelen, Johnson, Bontempi (IEEE CIDM 2015) for ULB; Almeida and Hidalgo (2011), doi:10.24432/C5CC84 for SMS Spam; Weber et al. (2019) for Elliptic.

## Known gaps

Names still leak to the AI provider (on names whose words the name list has not seen, 92% of US-style and 76% of non-US names were fully removed; the list makes names it already contains reliable but does not generalise); injection screening is heuristic; API keys are static strings with three roles and no rotation; the rate limiter is per process; tool handlers run inside the database transaction (an outbox pattern was considered and not built); nothing is deployed; data licences are unconfirmed. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
