# The Harness: a runtime for AI decisions in regulated money flows (draft v0.1)

Working idea: an operating system for financial-crime and payment-risk decisions. The "OS" is an architecture, not a market claim. Applications ("workloads") run on a small trusted kernel that makes every AI-assisted decision policy-gated, auditable, replayable and measurable.

Spellbreaker (scam interception) is the first workload. A harness with one workload is not an abstraction, so v1 also ships a second workload (payee and name screening on the OFAC list that the data pipeline already downloads).

## Why a harness and not another app

Fintechs rarely lack models. They lack a safe way to let AI take part in decisions that move money: who may do what, what happened and why, whether a change made things better, and how to prove it to an auditor. The harness provides exactly that and nothing else.

## OS analogy (this is the design, not decoration)

| OS concept | Harness equivalent |
|---|---|
| Process | Workflow run (an agent or deterministic state machine) |
| System call | Tool call through the Tool Gateway, always capability-checked |
| Permissions | Capability tokens scoped to a run, a tool and a risk tier |
| Kernel | Policy engine plus decision ledger. Deterministic. The LLM is never inside it |
| Filesystem | Evidence ledger: append-only, hash-chained |
| Drivers | Connectors (payments, cards, KYC, sanctions lists, case tools) |
| Scheduler | Run queue with budgets (latency, cost, retries) |
| Interrupts | Human approvals and escalations |
| Debugger | Replay, shadow mode, counterfactual evaluation |

## Layers

- **L0 Connectors.** Adapters that turn outside systems into validated events with provenance. Each connector declares its schema and what data class it touches.
- **L1 State and ledger.** Append-only decision ledger (each record hashes the previous one), case store, feature store, evidence store, and a PII vault that tokenises personal data.
- **L2 Policy and capability kernel.** Versioned policies evaluated deterministically. Decides outcomes. Issues capability tokens. Enforces risk tiers and limits. Can simulate "what would this policy have done on last month's events".
- **L3 Model gateway.** One entry point for ML models and LLMs: routing, caching, redaction, prompt-injection screening, structured output validation, cost and latency budgets, fallbacks, model registry with versions.
- **L4 Agent runtime.** Workflows as explicit state machines with LLM steps inside them. Tool Gateway, idempotent actions, approval interrupts, resumable runs, sandboxed execution.
- **L5 Assurance.** Offline evals, replay, shadow mode, counterfactual estimators (the Decision Lab), faithfulness checker, red-team suites, drift monitoring, auto-generated model cards.
- **L6 Control plane.** HTTP APIs, SSE events, and a console for analysts, owners and admins.
- **L7 Workloads.** Spellbreaker, screening, and later others, packaged as plugins that declare their tools, policies, evals and UI panels.

## Risk tiers (what an AI step may do)

- T0 read-only, T1 reversible and customer-visible (warn, ask a question), T2 financial effect but reversible (hold a payment), T3 irreversible (release funds, block account, file a report).
- T2 and T3 always need a recorded human approval or a deterministic policy rule. The LLM can propose; it cannot execute.

## Core APIs (draft, versioned under /v1, OpenAPI is the source of truth)

| Endpoint | Purpose |
|---|---|
| `POST /v1/events` | Ingest an event (idempotency key required) |
| `POST /v1/decisions` | Real-time decision with a latency budget. Returns outcome, reasons with evidence ids, policy and model versions, trace id, mode (enforce or shadow) |
| `GET /v1/decisions/{id}` and `/replay` | Fetch a decision, or re-run it with the same inputs and versions |
| `/v1/cases`, `/v1/cases/{id}/evidence` | Cases, evidence and analyst dispositions |
| `POST /v1/runs`, `GET /v1/runs/{id}`, `POST /v1/runs/{id}/resume` | Start, inspect and resume workflow runs |
| `/v1/approvals` | Approval queue for T2 and T3 actions |
| `/v1/tools` | Register a tool: schema, risk tier, rate limits, idempotency |
| `/v1/policies`, `POST /v1/policies/{id}/simulate` | Versioned policies and "what would have happened" simulation |
| `/v1/models` | Model registry, versions, canary share, model cards |
| `/v1/evals`, `/v1/evals/{id}/runs` | Suites and results, gating for releases |
| `/v1/audit`, `GET /v1/audit/verify` | Query the ledger and verify the hash chain |
| `/v1/connectors` | Register and monitor connectors |

Decision request (sketch):

```json
{ "tenant": "t1", "idempotency_key": "…", "workload": "payment_risk",
  "subject": { "type": "payment", "id": "…" }, "context": { },
  "budget_ms": 300, "mode": "enforce" }
```

Decision response (sketch):

```json
{ "decision_id": "…", "outcome": "allow|warn|hold|block|abstain",
  "reasons": [{ "code": "NEW_PAYEE_LARGE_AMOUNT", "evidence_ids": ["…"] }],
  "risk_tier": "T2", "requires_human": true,
  "policy_version": "…", "model_versions": ["…"], "trace_id": "…", "mode": "enforce" }
```

## Invariants (each is a test, not a promise)

1. No T2 or T3 tool runs without a recorded approval or an allowing policy rule.
2. The same inputs and the same versions reproduce the same deterministic outcome.
3. Any change to a past ledger record is detected by `/v1/audit/verify`.
4. LLM output can change an outcome only through fields the policy engine accepts and validates.
5. Personal data never reaches the model gateway unredacted (tested with canary values).
6. A repeated idempotency key returns the same decision and causes no second side effect.
7. Shadow mode never causes a side effect.
8. One tenant can never read or act on another tenant's data.

## Where this repo's current work fits

- `pipelines/` is L0 plus L1 for datasets (checksums, manifests, provenance).
- The risk model, text classifier and OFAC screening are L3 models and L2 inputs.
- The Decision Lab is L5.
- The analyst workbench and customer interception flow are L6 and L7.

## Proposed stack

Python, FastAPI, Pydantic, Postgres (including the hash-chained ledger), a small typed policy language evaluated in Python (interface kept compatible with Cedar or OPA later), Next.js console, OpenTelemetry traces. No Kafka until a measured throughput need appears.

## Stages

- **H0 kernel skeleton:** ledger with hash chain and verify endpoint, `/v1/decisions` and `/v1/events`, policy engine v1, Tool Gateway with risk tiers, invariant tests 1 to 8.
- **H1 first workload:** Spellbreaker on the kernel with the real ULB risk model and the interception flow.
- **H2 second workload and assurance:** OFAC payee screening as a plugin (proves the abstraction), replay and shadow mode, faithfulness checker, eval gating.
- **H3 Decision Lab and hardening:** counterfactual estimators, conformal abstention, tenant isolation tests, load numbers.

## Not claimed

- No claim of regulatory compliance. Mapping to specific rules (for example EU AI Act or local central-bank guidance) is a later task and must be checked against the actual texts.
- "Defence" and "security" beyond financial crime are out of scope. A different trust domain needs different evidence than a portfolio project can give.
- Demand is a hypothesis until tested with practitioners.

## Decisions (2026-11-04, confirmed by the owner)

1. Scope: financial crime and payment risk only. Defence and wider security are out of scope.
2. Second workload: OFAC payee and name screening, built on the real OFAC data already in the pipeline.
3. Deployment: self-hostable, single tenant (Docker Compose plus a cloud demo). Tenant isolation is still tested (invariant 8) but this is not a multi-tenant SaaS.
4. LLMs: local models during development, one cheap API model only for the final measured eval runs. Evals are cached and seeded so repeats are cheap.

## Who might want this (hypotheses, not validated)

I have not done market research or spoken to anyone. These are guesses to test before the pitch leans on them.

- Payment apps and neobanks that carry scam losses and need friction that does not annoy legitimate users.
- Payment processors, BNPL and wallet providers with small fraud teams that cannot build this in-house.
- Crypto exchanges and money-service businesses that must screen payees and explain decisions to auditors.
- Banks and exchange houses in the Gulf, where screening and audit trails are heavily scrutinised.

Test: five short conversations with fraud or compliance practitioners. Ask what they cannot currently prove to an auditor, how they measure whether an intervention reduced loss, and what stops them letting an LLM near a payment decision.

## Open questions

- Which cheap API model to use for final evals, and the budget cap per full eval run.
- Policy language: start with a typed Python DSL, or adopt Cedar or OPA from day one.
- Whether the demo is public. Public means the data licence notes in `docs/DATA.md` must be settled first.
