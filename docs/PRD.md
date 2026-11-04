# Product requirements: SafePay Command

Status: a study project with working software and measured results, **not** a product with users. Nothing here has been tested with real analysts, and demand is an untested hypothesis.

## Problem
Payment scams coach victims to lie, so a plain warning fails. Analysts work across scattered tools and write inconsistent notes. A blocked payment never shows whether it was fraud, so teams cannot tell whether a model or a friction step helps. Auditors ask who decided what and why, and letting an AI near that decision makes it harder.

## Users
1. **Fraud analyst:** reviews a queue of cases and decides. Needs evidence, a short cited summary, and a record.
2. **Risk lead:** sets policy and wants to know, before changing it, what a change would have done.
3. **Auditor:** needs a tamper-evident record of every decision and a way to replay it.
4. **ML engineer:** needs honest evaluation, drift visibility and a safe way to retrain from analyst decisions.

## Goals and what exists
| Goal | Status |
|---|---|
| The AI assists, a deterministic policy decides; AI can only add friction | Built and tested (kernel, policies, flags) |
| Every decision is recorded and replayable; tampering is detectable | Built (hash-chained ledger, replay, verify) |
| Score payments and screen names | Built (risk and text models, OFAC matcher) as tools and policies |
| Group alerts into cases; cited AI summary; analyst decision; audit trail | Built; console and API; Playwright and API tests |
| Measure what a policy change would do without running it | Built on **simulated** data (Decision Lab, uplift) |
| Improve from analyst labels, with control over how labels are collected | Built as an experiment on real transactions with simulated analysts |
| Roles, rate limits, spending caps, size limits | Built and tested |

## Non-goals
Real money movement; any regulatory or compliance claim; customer data; branding or affiliation with any company; production-grade authentication; a mobile app.

## Requirements and measured results
- **Faithful summaries:** every sentence cites a fact and passes a deterministic check. Measured: 0 of 85 unsupported sentences in first answers (60 real alert cases, one model, one run).
- **No silent personal-data leakage:** measured partial defence only (names removed 73% to 88% in tests).
- **Honest evaluation:** every report states its data (real or simulated), intervals where possible and its limits. Negative results are kept (neighbour features add almost nothing; folding did not help; the model collapses after a market shutdown).
- **Performance (local, one laptop):** at 8 concurrent clients, decisions about 440 to 480 requests per second with 95th percentile about 25 ms; name screening about 260 (one process) to about 560 (four) requests per second. See `reports/load.md` for what these numbers do not mean.

## Risks
Licences for the OFAC, ULB and Elliptic data are unconfirmed. Names still leak to the AI provider. Simulated results are not evidence about real victims or analysts. Scope is large for one person; milestones kept each piece shippable.

## Open questions
Do analysts find the cited summaries useful (unmeasured)? Which drift response works (monitoring and retraining are only sketched by the flywheel experiment)? Is a public demo acceptable under the data licences? Which cloud target and budget for AI evaluation?
