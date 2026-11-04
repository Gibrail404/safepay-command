# Project: SafePay Command, AI Decision Platform for Payment Risk, Screening and Investigation

Category: Applied AI Engineering · FinTech · Fraud and Scam Defence · LLM Applications
Resume line (draft): "SafePay Command: an AI decision platform for payment risk, sanctions screening and fraud investigation, with policy-gated LLM steps, a tamper-evident audit ledger and simulator-validated impact measurement."
Platform it runs on: the SafePay Harness (a runtime for policy-gated, auditable AI decisions)
Repo: `safepay-command`. Independent portfolio project, not affiliated with any company.

## 1. Project overview

SafePay Command is a financial-crime platform. It watches payment events, stops risky payments with explainable questions, screens payees against sanctions lists, groups related alerts into investigation cases, and gives fraud analysts evidence-cited AI summaries they can accept or override. Every decision is policy-checked, recorded in a tamper-evident ledger and replayable. A built-in assurance layer measures, with estimators checked against a simulator, whether each intervention really reduces loss.

It is one product made of five modules on one platform:

| Module | What it does |
|---|---|
| Workbench (the product face) | Case queue, evidence view, cited AI summary, analyst disposition, audit trail |
| Interception (codename Spellbreaker) | Payment-time scam interception: score, at most three adaptive questions, then allow, warn, hold or block |
| Screening | Payee and name screening on the OFAC list with an adjudicator step and human review |
| Decision Lab | Replay, shadow mode and counterfactual estimators: naive vs corrected vs ground truth |
| Graph and flywheel | Ring detection on a real labelled graph groups alerts into cases; analyst decisions become labels and improve the system, measured |

Scope decision (confirmed by the owner): financial crime and payment risk only. "Defense" means fraud defence and the platform's own defensive security, not the defence sector.

## 2. Problem statement

Fintechs process huge payment volumes. Scammers coach victims to lie, so a simple warning fails. Analysts work across fragmented tools and write inconsistent notes. Labels are censored: a blocked payment never shows whether it was fraud, so most teams cannot tell if a model or a friction step helps. Auditors ask who decided what and why, and AI makes that harder. Few teams can safely let an LLM near a payment decision.

## 3. Proposed solution (pipeline)

1. Ingest payment events with idempotency keys.
2. Risk scoring: calibrated ML model plus deterministic rules.
3. Interception: Interviewer step asks at most three adaptive questions; a deterministic policy engine decides allow, warn, hold or block; Explainer step writes the plain-language reason, every fact tied to an evidence id.
4. Screening: algorithmic candidate matching against OFAC, an adjudicator step explains hits, humans clear high-risk ones.
5. Case generation: related alerts grouped by graph clusters and shared entities.
6. AI-assisted investigation: Investigator step summarises the case with citations and may abstain.
7. Analyst review: inspect evidence, accept or override, record a disposition.
8. Audit and replay: hash-chained ledger; any decision can be replayed with the same inputs and versions.
9. Assurance and learning: dispositions feed labels; Decision Lab measures real effect versus naive estimates.

Design principle: the LLM assists, it never decides. A deterministic policy engine owns outcomes. Money-moving actions are tiered (T0 read, T1 customer-visible, T2 reversible hold, T3 irreversible); T2 and T3 need an allowing rule or a recorded approval. In this project T3 acts on a sandbox ledger only, never real money.

## 4. Platform: the Harness (OS analogy as design)

Process = workflow run; system call = tool call through the Tool Gateway with a capability token; kernel = policy engine plus ledger; filesystem = hash-chained evidence ledger; drivers = connectors; interrupts = approvals; debugger = replay, shadow mode, counterfactuals.

Layers: L0 connectors, L1 ledger and state (PII vault), L2 policy and capability kernel, L3 model gateway (ML and LLM routing, redaction, injection screening, structured outputs, budgets, registry), L4 agent runtime (state machines, idempotency, approvals), L5 assurance, L6 control plane (APIs, SSE, console), L7 workloads packaged as skills.

Agents (LLM steps with schemas): Interviewer, Explainer, Investigator, Screening adjudicator. Test-only sandbox agents: scammer, victim, red-team. Not agents: risk model, candidate matcher, policy engine, faithfulness checker.
Skills: `payment-risk-interception`, `payee-screening`, `case-investigation`.

APIs (OpenAPI is the source of truth; full detail in `docs/HARNESS.md`): `/v1/events`, `/v1/decisions` (+`/replay`), `/v1/cases`, `/v1/runs`, `/v1/approvals`, `/v1/tools`, `/v1/policies` (+`/simulate`), `/v1/models`, `/v1/evals`, `/v1/audit` (+`/verify`), `/v1/connectors`, plus `/v1/screenings`, `/v1/graph/clusters`, `/v1/labels`, `/v1/experiments`, `/v1/simulations`, and an SSE stream.

## 5. Core technologies

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Database and ledger | PostgreSQL (hash-chained decision ledger) |
| Machine learning | LightGBM, PyTorch (tabular model and graph model), scikit-learn, networkx or PyG, calibration |
| Applied AI | LLM APIs with structured outputs, retrieval of evidence, deterministic faithfulness checker; local models in development, one cheap API model for final evals |
| Frontend | Next.js console reading only from the API; SSE for live updates |
| Infrastructure | Docker Compose, a cloud demo, GitHub Actions CI, OpenTelemetry traces |
| Testing | pytest, property-based invariant tests, Playwright e2e |

No Kafka until a measured throughput need appears. Early risk: local Python is 3.14, so check PyTorch and LightGBM wheel support in M1; otherwise pin Python 3.12 with uv.

### Stack decisions in detail

- **Is a backend needed? Yes.** The product is a runtime that enforces policy, keeps a ledger, runs models and serves APIs. A frontend-only app cannot hold secrets, state or guarantees.
- **Languages:** Python for kernel, API, ML and evaluation; TypeScript (Next.js) for the console; SQL for Postgres.
- **LLM access:** one OpenAI-compatible client interface. Local models through Ollama during development; one cheap API model for the final measured evals. Provider and budget are open decisions.
- **Policy language:** typed Python rules first (testable, simple), with an interface that can move to Cedar or OPA later.
- **Queues and streaming:** none at first (in-process async plus a Postgres jobs table). Kafka only if a measured throughput need appears.
- **Machine facts checked on 2026-11-04:** Docker 29.2.1, Ollama 0.33.2, uv, Node and npm are installed; Python is 3.14.7. `pip index` lists torch 2.15.0 and lightgbm 4.7.0 for this interpreter; a real install and import test is the first task of M1, with a fallback to Python 3.12 through uv.

### LLM in a deployed demo (decision 2026-11-04)

Local Ollama exists only on the developer's machine, so a deployed demo cannot depend on it. The model gateway therefore has three interchangeable providers behind one interface:

1. **Hosted, OpenAI-compatible API** (base URL, key and model from environment variables, never in the repo). This is what the deployed demo uses, with a hard per-run and per-day spend cap.
2. **Ollama** for local development and offline tests.
3. **Deterministic fallback**: template-based Interviewer and Explainer output. It is used when no key is set, when the budget is exhausted, or when the provider fails, so the deployed app never breaks. It is also the baseline that the LLM versions are measured against in the evaluations.

Trained models (LightGBM and the text model, about 1.5 MB in total) ship inside the container image and need no GPU. The database is managed PostgreSQL. The cloud target stays an open decision for M6.

### API keys and secrets

| Need | Key required | When |
|---|---|---|
| ULB, UCI SMS Spam, OFAC downloads | None | Works today |
| Elliptic via the PyG mirror | None (licence unconfirmed) | M5 |
| Development LLM | None (local Ollama) | M2 |
| Final-eval LLM | One provider API key (open decision), with a spend limit | M2 onwards |
| Postgres | Connection string; local Docker Compose, no cloud key | M1 |
| Cloud demo | Cloud credentials, chosen at M6 | M6 |

Secrets live in `.env` (git-ignored) and in the host's secret store. They are never committed, never written in docs, and are entered by the owner, not by the assistant.

### Phase detail: stack and learning goal per milestone

The owner keeps a living teaching guide (Word document, outside this repository) with a table of milestone, what we build, stack touched, what the owner learns and how to verify. It is updated at the end of every milestone.

## 6. Data (real first; simulated only where none exists, always labelled)

| Need | Source | Status |
|---|---|---|
| Transaction risk | ULB credit card fraud: 284,807 rows, 492 fraud, anonymised, no customer ids | Downloaded and validated |
| Scam-like text | UCI SMS Spam: 5,574 messages, CC BY 4.0, general spam | Downloaded and validated |
| Screening | OFAC SDN list: 19,485 entries | Downloaded and validated |
| Graph rings | Elliptic Bitcoin graph: 203,769 nodes, 234,355 edges, crypto, licence unconfirmed | Links verified; fetch in M5 |
| Negative names for screening evals | Public name lists (candidates: US Census surnames, SSA first names) | Verify in M3 |
| Scam conversations, interventions, counterfactuals | Simulator calibrated to real marginals | Built in M4, labelled "simulated" |

Honest limit: ULB lacks payee, device and call-in-progress signals, so scam context in the interception flow comes from the simulator and is labelled; the risk score itself comes from the real model.

## 7. Evaluation (no preset targets; measure and report with confidence intervals)

- Risk model: time-ordered split, PR-AUC, recall at 1% FPR, calibration error, p95 latency; LightGBM vs a small PyTorch model.
- Text model: TF-IDF plus logistic regression vs a small fine-tuned model; cost and latency.
- Screening: recall@k on perturbed real SDN names, false-positive rate on real non-sanctioned names, human-review rate.
- Interception (simulated): interception rate by archetype and coaching level, false-friction rate, friction vs loss-prevented curve.
- LLM steps: unsupported-claim rate (deterministic check of each cited fact), abstain rate, injection block rate, cost per 100 cases.
- Decision Lab: bias and CI coverage of IPS, doubly robust and uplift estimators against the simulator's known counterfactuals, vs a naive comparison.
- Graph: ring-detection precision and recall on a temporal split vs a features-only baseline.
- Flywheel: precision at fixed recall as analyst feedback accumulates (simulated analysts, labelled).

## 8. Security of the platform (each threat has a test)

Prompt injection via memos, payee names and case notes (untrusted channel, screening, schema-only outputs). Forbidden tool use (capability tokens, tiers, policy has final say). Ledger tampering (hash chain and verify). Replay and duplicates (idempotency keys). PII leakage (vault tokens, canary tests). Cross-tenant access (tenant scoping). Feedback poisoning (label provenance, holdout). Cost abuse (budgets, rate limits).

Eight invariants become executable tests: no T2 or T3 without approval or rule; same inputs and versions reproduce the same outcome; ledger tampering is detected; LLM output changes an outcome only through validated policy fields; PII never reaches the model gateway unredacted; repeated idempotency key means one effect; shadow mode causes no side effect; no cross-tenant reads or actions.

## 9. What this project demonstrates

- Designing production-oriented AI applications and integrating LLMs into a real workflow.
- Combining classical ML, deep learning and LLM reasoning, with a deterministic safety kernel.
- Evidence retrieval, citation-checked generation and honest abstention.
- Rigorous evaluation: statistics, calibration, causal and counterfactual estimation, confidence intervals.
- Event-style backend design, idempotency, audit, access control, defensive security.
- Human-in-the-loop AI for financial services, and measuring product impact (friction vs loss).
- Reproducible data work on real public datasets with provenance.

Rendering and "no fake data" rules: UI reads only from the API; no mock JSON; raw data checksummed and fetched by script; manifests generated; every number shows a provenance chip (real source or "simulated"); loading, empty and error states on every page; schema contracts; Playwright smoke tests against the deployed app; demo snapshots generated by the pipeline.

## 10. Roadmap (each milestone shippable)

- M0 Foundations: done (spec, data register, real-data pipeline, 8 tests).
- M1 Kernel (DONE 2026-11-04): hash-chained ledger and verify, `/v1/events`, `/v1/decisions`, policy engine, tool gateway, idempotency, OpenAPI, CI. Exit: invariants 1, 2, 3, 6, 7 pass; replay reproduces outcomes.
- M2 Risk and interception (risk model, text model and tools DONE 2026-11-04; model gateway, agents and faithfulness checker still to do): ULB model with calibration and the PyTorch comparison, SMS model, model registry, Interviewer and Explainer, faithfulness checker, injection tests. Exit: generated metrics table; first shareable demo for the referrer.
- M3 Screening: matcher, adjudicator, second skill loaded on the same kernel. Exit: recall and FPR tables with CIs; invariants hold for both workloads.
- M4 Simulator and Decision Lab: scenario engine, sandbox agents, shadow mode, estimators validated against ground truth. Exit: "naive vs corrected vs truth" figure and measured CI coverage.
- M5 Workbench, graph and flywheel: cases, Elliptic ring detection, Investigator, console with provenance chips, labels and flywheel experiment. Exit: graph metrics, unsupported-claim rate, UI renders only live data.
- M6 Hardening and release: threat-model tests, tenant isolation, Playwright e2e on the deployed demo, p95 load numbers, model cards, PRD, README metric table, blog post and demo video. Exit: from-scratch reproduction; every README number regenerates from a command.

Apply to the role now; share milestones with the referrer as they ship.

## 11. Not claimed, risks and open decisions

No regulatory compliance claim, no real money or customer data, no affiliation or branding of any company. Simulated results are not evidence about real victims. Licences for ULB, OFAC and Elliptic have no formal text found; do not redistribute raw data and settle terms before any public demo. Demand is an untested hypothesis (five practitioner conversations recommended). Scope is large, hence the milestones. Open: cheap API model and budget for final evals; policy language (typed Python DSL first, Cedar or OPA later); public or private demo; cloud target; negative-names dataset.

## 12. Verification

Per milestone: `python -m pytest -q` (unit, invariants, real-data integration); `python -m safepay_data all` reproduces data from scratch; tampering a ledger row makes `GET /v1/audit/verify` fail; a repeated idempotency key returns the same decision; Playwright e2e against the running console; a `make report` command regenerates every metrics table from raw data.
