# Sandbox evaluation of the Interviewer (generated; do not edit by hand)

**Simulated customers.** The real Interviewer, running on gemma4:31b, asks up to three questions; sandbox actors answer. The scammer is a fixed script (generic cover stories), the victim is an LLM role-playing a customer, the attacker types injection text. Nothing here is real customer behaviour. 42 conversations, run 84 s.

A *flag* is a warning sign found in the answers (someone told me to pay, urgency, secrecy, I do not know the payee). Flags can only ADD friction to a payment; they can never lower the outcome.

## How often the answers raised a flag

| Who is answering | Conversations | Flag found, using the phrases the Interviewer extracted (how the system works today) | Flag found, searching all the answers (upper bound) |
|---|---|---|---|
| Honest customer, ordinary payment | 12 | 0% (0 of 12; 95% interval 0% to 24%) | 0% (0 of 12; 95% interval 0% to 24%) |
| Scam victim answering honestly | 12 | 92% (11 of 12; 95% interval 65% to 99%) | 100% (12 of 12; 95% interval 76% to 100%) |
| Scam victim following the scammer's cover story | 12 | 33% (4 of 12; 95% interval 14% to 61%) | 42% (5 of 12; 95% interval 19% to 68%) |
| Attacker typing injection text as answers | 6 | 0% (0 of 6; 95% interval 0% to 39%) | 17% (1 of 6; 95% interval 3% to 56%) |

Reading: an honest customer should raise no flag (a flag there means needless friction). A scam victim who answers honestly should raise one. A coached victim is the hard case: the scammer's cover story hides exactly what the flags look for.

## Which flags, searching all the answers

| Who is answering | Someone told me | Urgency | Secrecy | Do not know the payee |
|---|---|---|---|---|
| Honest customer, ordinary payment | 0 | 0 | 0 | 0 |
| Scam victim answering honestly | 11 | 4 | 4 | 6 |
| Scam victim following the scammer's cover story | 3 | 5 | 0 | 0 |
| Attacker typing injection text as answers | 0 | 1 | 0 | 0 |

## Safety checks

| Who is answering | Questions asked | Questions replaced by the fixed question bank (model reply failed a rule) | Cases where a flag lowered the outcome |
|---|---|---|---|
| Honest customer, ordinary payment | 36 | 0 | 0 |
| Scam victim answering honestly | 36 | 0 | 0 |
| Scam victim following the scammer's cover story | 36 | 0 | 0 |
| Attacker typing injection text as answers | 18 | 0 | 0 |

## Limits (read these)

- The victim is an LLM following a persona; real victims behave differently, so these rates describe this simulation only.
- The coached cover stories are three short fixed scripts. Real scammers adapt.
- The system only extracts phrases from answers 1 and 2 before it stops asking; the third answer is not extracted, so the 'extracted phrases' column can miss what the last answer said. The upper-bound column shows the difference.
- Flags are plain keyword rules, so they miss paraphrases; that is a known gap.
- Small samples, one run, one model. Intervals are wide.
