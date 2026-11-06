# Model cards

One card per learned component. Every number is copied from a generated report in `docs/reports/`; regenerate with the command shown. Nothing here is a claim about real production performance.

## 1. Transaction risk model
- **Purpose:** score a card transaction for fraud risk so a policy can warn or hold. Report: `risk_model.md` (`python -m safepay_ml.train_risk`).
- **Data:** real ULB credit-card data, 284,807 rows, 492 fraud, anonymised PCA features, two days, European, 2013. Time-ordered split: test has 75 fraud rows.
- **Method:** LightGBM, PyTorch MLP (5 seeds) and logistic regression compared; the model with the best validation average precision is deployed by a rule fixed in advance (LightGBM), Platt-calibrated on validation. Policies read a band (low, elevated, high), not a raw probability.
- **Results (test):** LightGBM average precision 0.812 (95% CI 0.727 to 0.894); at a 1% false-alert budget it catches 66 of 75 frauds (recall 0.880, CI 0.805 to 0.955) with precision 0.140.
- **Intended use:** a read-only scoring tool inside a policy flow, for study.
- **Not for:** real payments. The features have no customer, payee or device, and 75 test frauds give wide intervals.
- **Known limits:** two days of 2013 data; ULB's currency is unstated; duplicate-feature rows in test are reported separately.

## 2. Scam-like text model
- **Purpose:** flag scam-like messages. Report: `text_model.md` (`python -m safepay_ml.train_text`).
- **Data:** real SMS Spam Collection (CC BY 4.0), 5,574 messages, 415 exact duplicates removed before splitting.
- **Method:** TF-IDF plus logistic regression, Platt-calibrated, pure-numpy scorer; naive Bayes as a comparison.
- **Results (test, 1,032 messages):** average precision 0.9756 (CI 0.9568 to 0.9912); recall 0.938 at 1% false alerts (120 of 128 spam).
- **Not for:** bank-scam detection. It is general SMS spam and the split is random (no timestamps), so drift is untested.

## 3. Name matcher (sanctions screening)
- **Purpose:** find possible OFAC matches for a name, for a human to review. Report: `screening.md` (`python scripts/eval_screening.py`).
- **Data:** real OFAC SDN list (19,485 entries) and aliases (20,204); real US Census names for the false-alert test.
- **Method:** character n-gram candidate generation, then IDF-weighted token matching so a shared common token counts little. Spelling folding was tried and rejected by a rule fixed in advance. Thresholds come from validation names only.
- **Results (test):** about 0.9% of ordinary names alert at the review level and 0.1% at the strong level. Of real aliases the list had not been told about, the right entry was the top result 66.7% of the time (list with half the aliases). Real names with one change are found at the review level 83.8% (moved space) to 100% (reordered).
- **Not for:** automatic blocking. It uses names only (no date of birth, country or address); US-name false-alert rates are optimistic for a global customer base. The policy never blocks automatically.

## 4. Graph model (illicit transactions and case grouping)
- **Purpose:** test whether graph structure helps and whether linked alerts group into cases. Report: `graph.md`.
- **Data:** real Elliptic Bitcoin graph (203,769 transactions, 234,355 links, 4,545 illicit, 42,019 licit labelled).
- **Results:** own-features LightGBM average precision 0.792 (CI 0.771 to 0.813); neighbour features add +0.000 (neighbour averages) or +0.004 (first-round neighbour scores). After the known market shutdown average precision falls from 0.912 to 0.048 (recall 84.7% to 3.0%). Linked alerts rarely group: 940 alerts became 869 cases.
- **Not for:** card or bank payments. One dataset, one split.

## 5. LLM steps (Explainer, Questioner, Investigator, screening adjudicator)
- **Purpose:** write customer messages, ask up to three safety questions, summarise cases and explain name alerts. None decides anything; each reply passes a schema check and a deterministic fact check, and each has a safe fallback.
- **Models:** gemma4:31b on Ollama Cloud (first choice), then a second Ollama model, with Gemini third in the evaluated design. Reports: `llm_eval.md`, `sandbox.md`, `investigator.md`.
- **Results:** Investigator on 60 real alert cases: 49 sent to the model, all 49 first answers passed the fact check, 0 of 85 sentences unsupported; 11 abstained by a fixed rule. Questioner under simulated pressure: flags found for honest-answering scam victims in 11 of 12 conversations but for coached victims in 5 of 12.
- **Known limits:** small samples, one run, simulated customers, no analyst has rated the summaries, and the Investigator mostly says escalate on above-threshold alerts.

## 6. Name and address redaction
- **Purpose:** remove personal details before text reaches a model. Report: `redaction.md`.
- **Method:** patterns for emails, cards, phones, IBANs, IDs and street addresses; the small spaCy English model for people's names.
- **Results (`redaction.md`):** on names made only of words the evaluation list has not seen, fully removed: 92% (US-style) and 76% (real OFAC individuals, many non-US) with the language model plus the list, against 92% and 75% with the model alone, so the list adds almost nothing for unseen names. For names whose words are in the shipped list it reaches 99%, which is optimistic (circular), not an estimate. The language model alone changed 14% of real SMS messages and the list changed 5% more (upper bounds on wrong changes).
- **Not safe for:** relying on it alone. Names still leak.

## 7. Interception flow (questions, flags, policy)
- **Purpose:** decide whether to hold a payment by asking the customer up to three questions and reading the answers, with the policy engine owning the outcome. Reports: `interception.md` and `interception_hybrid.md` (`python scripts/eval_interception.py [--hybrid]`).
- **Data:** real held-out card transactions scored by the real risk model; payee age and customers are **simulated** (an AI role-player: genuine, vague, honest scam victim, victim following a cover story). Two separate sets of 200 held-out scenarios (80 scams, 120 genuine each); 100 development scenarios only to check the harness. Nothing tuned on held-out. The hybrid was designed after the first set and tested only on the second, fresh set.
- **Results:** rules only and rules plus model hold 0 of 160 scams (by construction: scams look like ordinary payments). Pooled over both sets: fixed questions plus keyword rules (no AI in the decision path) hold 80 of 160 (50%): all 80 honest victims and none of 80 coached ones. The AI Questioner flow holds 91 of 160 (57%): 72 of 80 honest victims and 19 of 80 coached ones. Paired on the same scams: 19 only the AI, 8 only fixed, exact sign-test p of 0.052. The two sets disagreed on the net (first: 39 AI against 40 fixed, p = 1.0; second: 52 against 40, p = 0.004). The hybrid (two fixed questions, then one AI-written) held 49 of 80 on the second set, between the two, so its hypothesis was not supported. False holds: 1 of 240 for fixed and for AI. The AI flow takes a median of about 10 s and about 1,470 tokens per questioned case; the hybrid about 7 s and 750 tokens.
- **Reading:** asking is where detection comes from. The fixed version never misses an honest victim but is blind to a cover story; the AI adds detection against cover stories but loses some honest victims. They are complementary, not ranked. It says nothing about real customers.
- **Known limits:** simulated customers; scam scenarios built on ordinary-looking payments; one AI model; one run per set; intervals wide; only one hybrid was tried.
