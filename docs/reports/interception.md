# Interception: does the AI questioning add anything? (generated; do not edit by hand)

**Real payments, simulated customers.** Each scenario is a real held-out card transaction scored by the real risk model, with a simulated payee age and a simulated customer whose answers come from an AI role-player (honest, vague, honest scam victim, or scam victim following the scammer's cover story). Whether a scenario is a scam is known by construction.

Scam scenarios are built on ordinary-looking payments **on purpose**: in an authorised-push scam the customer sends the money, so the payment itself looks normal and only the customer's story reveals the problem. That means the risk model alone cannot be expected to catch them. What this report measures is how much the questions recover, what they cost in friction for genuine customers, and how coaching erodes it.

Four systems see the same scenarios. **A** rules only. **B** rules plus the model's risk band. **C** B plus a fixed list of three questions and keyword rules on the answers, with no AI in the decision path. **D** B plus the AI Questioner and its answer reading. C is the honest test of whether the AI adds value over something simple. Questions are only asked when there is a reason (a sizeable payment to a new payee, an elevated model band, or a large amount).

Scenarios: 200 held-out (80 scams, 120 genuine) used for every number below; 100 development scenarios were used only to check the harness. Nothing was tuned on the held-out set. Model: gemma4:31b. Run time: 1633 s.

## Held-out results

| System | Scams held or blocked | Genuine payments held or blocked (false holds) | Genuine payments warned, held or blocked | Genuine customers asked questions |
|---|---|---|---|---|
| A. Rules only (amount, payee age) | 0% (0 of 80; 0% to 5%) | 0% (0 of 120; 0% to 3%) | 0% (0 of 120; 0% to 3%) | not applicable |
| B. Rules plus the risk model | 0% (0 of 80; 0% to 5%) | 1% (1 of 120; 0% to 5%) | 4% (5 of 120; 2% to 9%) | not applicable |
| C. B plus fixed questions and keyword rules (no AI in the decision path) | 50% (40 of 80; 39% to 61%) | 1% (1 of 120; 0% to 5%) | 4% (5 of 120; 2% to 9%) | 67% (80 of 120; 58% to 74%) |
| D. B plus the AI Questioner (the product flow) | 49% (39 of 80; 38% to 60%) | 1% (1 of 120; 0% to 5%) | 4% (5 of 120; 2% to 9%) | 67% (80 of 120; 58% to 74%) |

## By kind of scenario (share held or blocked)

| Scenario | Count | Asked questions | A | B | C | D |
|---|---|---|---|---|---|---|
| Ordinary payment to a known payee | 40 | 0% | 0% | 0% | 0% | 0% |
| Large payment to a new payee (genuine) | 40 | 100% | 0% | 2% | 2% | 2% |
| Genuine customer who gives short answers | 40 | 100% | 0% | 0% | 0% | 0% |
| Scam victim who answers honestly | 40 | 100% | 0% | 0% | 100% | 85% |
| Scam victim following the scammer's cover story | 40 | 100% | 0% | 0% | 0% | 12% |

## Does the AI add anything over fixed questions and keywords? (scam scenarios, same scenarios)

| | Count |
|---|---|
| Both C and D held the payment | 34 |
| Only D (the AI flow) held it | 5 |
| Only C (fixed questions) held it | 6 |
| Neither held it | 35 |

## What the AI flow costs

Over 160 questioned held-out cases: median 10.2 s of AI time per case (including the simulated customer's own answers) and median 1468 tokens for the questions and answer reading. These are the Questioner's costs, not the customer role-player's.

## Reading this report

1. **Rules alone and rules plus the model catch 0 and 0 of 80 scams.** That is built in: the scams look like ordinary payments, so only what the customer says can reveal them.
2. **All the detection comes from asking questions and reading the answers**: 50% (40 of 80) with fixed questions and keyword rules, 49% (39 of 80) with the AI Questioner.
3. **The AI flow did not measurably beat the simple fixed-question version** (39 against 40; the two disagreed on 11 scams, 5 in the AI's favour and 6 in the fixed version's). The AI's open questions did worse than the fixed list on honest scam victims (85% against 100%) and better against the coached cover story (12% against 0%; very few cases, one run).
4. **The cost to genuine customers is the same for both:** 1 of 120 held by mistake and 5 of 120 warned or held. The bigger cost is being asked questions at all (80 of 120 genuine customers here, because the scenario mix includes many new-payee payments).
5. **The AI flow costs about 10 s and 1468 tokens per questioned case; the fixed version uses no AI in the decision path.**
6. **What this does and does not show.** In this simulation, the value is the questioning step, not the AI doing it. It does not show that AI is useless: the project's AI is also used for cited case summaries and readable customer messages, which this report does not measure. It also does not show how real customers or real scammers behave. A real test needs real data.

## Limits (read these)

- The customer is an AI role-player following a persona, not a real customer. Real people, and real scammers, behave differently, so these rates describe this simulation only.
- Scam scenarios use ordinary-looking payments by construction, so the model's inability to catch them is built in. Card-fraud cases (where the model does work) are not part of this comparison.
- Payment features are real, but the payee's age and the link between a payment and a story are simulated. Amounts come from a real card dataset in an unstated currency (shown as EUR).
- One AI model, one run, a few hundred scenarios: intervals are wide. The policy thresholds are the project's existing ones and were not tuned here.
- 'Held' includes blocked; 'friction' for genuine customers counts warnings and holds but not the questions themselves (shown in the last column).
