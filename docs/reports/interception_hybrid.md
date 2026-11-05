# Interception: a hybrid of fixed and AI questions (generated; do not edit by hand)

The first comparison (`interception.md`) found no measurable difference between the AI questioner and a fixed list of questions on its set, and that the two were better in different places. This tests the obvious combination: **the first two questions come from the fixed list, the third is written by the AI from the customer's answers so far**, then the answers are read as before. Same kind of simulated customers, same real payments scored by the real model.

**How to trust it.** The hybrid was designed after reading the first report, so it is tested on **fresh scenarios that report never saw** (seeds from 20,000), with the fixed and AI versions rerun on the same scenarios. 200 scenarios (80 scams, 120 genuine). Nothing was tuned on them. Model: gemma4:31b. Run time: 679 s.

## Results

| System | Scams held or blocked | Genuine payments held or blocked (false holds) | Genuine payments warned, held or blocked | Genuine customers asked questions |
|---|---|---|---|---|
| B. Rules plus the risk model (no questions) | 0% (0 of 80; 0% to 5%) | 0% (0 of 120; 0% to 3%) | 6% (7 of 120; 3% to 12%) | not applicable |
| C. B plus fixed questions and keyword rules (no AI in the decision path) | 50% (40 of 80; 39% to 61%) | 0% (0 of 120; 0% to 3%) | 6% (7 of 120; 3% to 12%) | 67% (80 of 120; 58% to 74%) |
| D. B plus the AI Questioner (the product flow) | 65% (52 of 80; 54% to 75%) | 0% (0 of 120; 0% to 3%) | 6% (7 of 120; 3% to 12%) | 67% (80 of 120; 58% to 74%) |
| E. Hybrid: two fixed questions, then one AI-written question | 61% (49 of 80; 50% to 71%) | 0% (0 of 120; 0% to 3%) | 6% (7 of 120; 3% to 12%) | 67% (80 of 120; 58% to 74%) |

## By kind of scenario (share held or blocked)

| Scenario | Count | Asked questions | B | C | D | E |
|---|---|---|---|---|---|---|
| Ordinary payment to a known payee | 40 | 0% | 0% | 0% | 0% | 0% |
| Large payment to a new payee (genuine) | 40 | 100% | 0% | 0% | 0% | 0% |
| Genuine customer who gives short answers | 40 | 100% | 0% | 0% | 0% | 0% |
| Scam victim who answers honestly | 40 | 100% | 0% | 100% | 95% | 100% |
| Scam victim following the scammer's cover story | 40 | 100% | 0% | 0% | 35% | 22% |

## Hybrid against fixed questions (scam scenarios, same scenarios)

| | Count |
|---|---|
| Both held the payment | 40 |
| Only the hybrid held it | 9 |
| Only fixed questions held it | 0 |
| Neither held it | 31 |

## Hybrid against the AI questioner (scam scenarios, same scenarios)

| | Count |
|---|---|
| Both held the payment | 47 |
| Only the hybrid held it | 2 |
| Only the AI questioner held it | 5 |
| Neither held it | 26 |

## Both held-out sets together: fixed questions against the AI questioner

The first report (100 development scenarios aside) used 200 held-out scenarios; this report used 200 fresh ones. The two sets disagreed about the net result, so here they are pooled. 'Paired' counts scams where exactly one of the two held the payment; the p-value is an exact sign test on those.

| Scenario | Scams | Fixed questions held | AI questioner held |
|---|---|---|---|
| Scam victim who answers honestly | 80 | 100% (80 of 80; 95% to 100%) | 90% (72 of 80; 81% to 95%) |
| Scam victim following the cover story | 80 | 0% (0 of 80; 0% to 5%) | 24% (19 of 80; 16% to 34%) |
| All scams | 160 | 50% (80 of 160; 42% to 58%) | 57% (91 of 160; 49% to 64%) |

| Held-out set | Fixed held | AI held | Only the AI held | Only fixed held | Exact sign-test p |
|---|---|---|---|---|---|
| First report's set | 40 of 80 | 39 of 80 | 5 | 6 | 1.000 |
| This report's fresh set | 40 of 80 | 52 of 80 | 14 | 2 | 0.004 |
| Pooled | 80 of 160 | 91 of 160 | 19 | 8 | 0.052 |

**What is stable:** fixed questions with keyword rules held 80 of 80 honest scam victims and 0 of 80 coached ones; the AI questioner held 19 of 80 coached ones (Fisher exact p = 1e-06) but missed 8 of 80 honest victims that the keyword rules would have caught. So the two are complementary, not ranked. **What is not stable:** the net difference. The first set showed none (39 against 40), this one a clear AI advantage (52 against 40); pooled, 57% against 50% with a sign-test p of 0.05. The first report's headline that the AI 'did not measurably beat' fixed questions was true of its own set and should not be read as general.


## Reading this report

- **Hypothesis, written before this run:** the hybrid (first two questions fixed, third written by the AI) holds at least as many scams as the better of the two single approaches, without more false holds.
- **Result:** hybrid 49 of 80 (61%), fixed questions 40 (50%), AI questioner 52 (65%). **Supported only weakly or not at all:** the hybrid held no more scams than the better single approach (the AI questioner, 52), and the intervals overlap.
- **Paired on the same scams:** against fixed questions the hybrid alone held 9 and fixed alone held 0; against the AI questioner the hybrid alone held 2 and the AI alone held 5.
- **By kind of scam:** honest victims: fixed 100%, AI 95%, hybrid 100%. Coached cover story: fixed 0%, AI 35%, hybrid 22%.
- **Genuine customers:** held by mistake 0, 0 and 0 of 120 (fixed, AI, hybrid).
- **Cost:** the hybrid makes one AI question and one answer reading per questioned case: median 7.0 s and 746 tokens, against 9.4 s and 1473 tokens for the full AI questioner (times include the simulated customer's own answers).

## Limits (read these)

- Simulated customers (an AI role-player), real payments scored by the real model. Real customers and scammers behave differently.
- One model, one run, 80 scams: intervals are wide, and differences of a few scams are within noise.
- The hybrid is one of several possible combinations (which questions are fixed, how many); only this one was tried, so a negative result does not rule out others and a positive one could be luck of the draw.
- Scam scenarios use ordinary-looking payments by construction. Policy thresholds were not tuned here.
