# DRAFT: What I learned building a payments-risk platform where the AI never decides

*(Draft for you to edit and put your own voice into. Every number comes from a generated report in `docs/reports/`.)*

I wanted a project that showed how to put an LLM near a payment decision without trusting it. The rule I set was simple: **the AI assists, a deterministic policy decides, and anything the AI says can only add friction, never remove it.** Everything else followed from that.

## The platform in one paragraph
A kernel with a hash-chained ledger, idempotent and replayable decisions, a versioned policy engine and a tool gateway with risk tiers. On top of it, three workloads: scam interception (a risk model and a short question round), name screening against the OFAC list, and case investigation. An analyst console shows cases, a cited summary and an audit trail. A simulator measures, against known truth, what a policy change would do.

## Seven things I measured, including the ones that did not work
1. **Graph structure barely helped.** On the real Elliptic Bitcoin graph, adding neighbour features changed average precision by +0.000; a two-stage variant added +0.004. I had assumed the graph would help; the data said otherwise.
2. **Drift mattered far more.** After a known market shutdown the same model's average precision fell from 0.912 to 0.048 and recall from 85% to 3%. Collecting analyst labels near the alert threshold recovered it to 0.468 using 1,250 labels instead of 22,958.
3. **Feedback is not free.** At 20% analyst error some labelling strategies did worse than never retraining.
4. **Spelling folding did not help name screening.** I expected "Mohammed" and "Muhammad" folding to help. A rule I fixed before looking at test data chose no folding, and I kept the negative result.
5. **Naive comparison lies about new policies.** In a simulator that knows the truth, comparing "rows that happened to match" said an allow-everything policy lost 1.48 per payment when the truth was 6.16. Corrected estimators were close to unbiased but their confidence intervals still missed the truth far more often than the promised 5%.
6. **Coached victims beat questions.** In a sandbox with scripted scammer cover stories, a safety question round flagged 11 of 12 honest scam victims but only 5 of 12 coached ones.
7. **Redaction leaks names.** A small language model removed 88% of US-style and 73% of non-US names. Not good enough on its own, which is why the AI also has no tools and cannot act.

## Bugs that taught me something
A flaky test turned out to be a real race: one approval could be decided three times, and used twice, because I read a row and then wrote it. One conditional `UPDATE` with a row count fixed both. Running the container for real found a second bug: one missing package silently hid the screening tool. Both now have regression tests that fail on the old code.

## What I did not do
No real customers, no real money, no compliance claim. The data licences are unconfirmed. The analysts in the flywheel experiment are simulated, no human has rated the AI summaries, and nothing is deployed yet.

## If you want to look
Code and reports: https://github.com/Gibrail404/safepay-command. Start with `README.md`, then `docs/THREAT_MODEL.md` and `docs/MODEL_CARDS.md`.
