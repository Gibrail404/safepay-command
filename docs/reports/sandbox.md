# Sandbox evaluation of the Questioner (generated; do not edit by hand)

**Simulated customers.** The real Questioner, running on gemma4:31b, asks up to three questions; sandbox actors answer. The scammer is a fixed script (generic cover stories), the victim is an LLM role-playing a customer, the attacker types injection text. Nothing here is real customer behaviour. 42 conversations, run 100 s.

A *flag* is a warning sign found in the answers (someone told me to pay, urgency, secrecy, I do not know the payee). Flags can only ADD friction to a payment; they can never lower the outcome.

## How often the answers raised a flag

| Who is answering | Conversations | Flag found, using the phrases the Questioner extracted (how the system works today) | Flag found, searching all the answers (upper bound) |
|---|---|---|---|
| Honest customer, ordinary payment | 12 | 17% (2 of 12; 95% interval 5% to 45%) | 17% (2 of 12; 95% interval 5% to 45%) |
| Scam victim answering honestly | 12 | 92% (11 of 12; 95% interval 65% to 99%) | 100% (12 of 12; 95% interval 76% to 100%) |
| Scam victim following the scammer's cover story | 12 | 42% (5 of 12; 95% interval 19% to 68%) | 42% (5 of 12; 95% interval 19% to 68%) |
| Attacker typing injection text as answers | 6 | 0% (0 of 6; 95% interval 0% to 39%) | 17% (1 of 6; 95% interval 3% to 56%) |

Reading: an honest customer should raise no flag (a flag there means needless friction). A scam victim who answers honestly should raise one. A coached victim is the hard case: the scammer's cover story hides exactly what the flags look for.

## Which flags, searching all the answers

| Who is answering | Someone told me | Urgency | Secrecy | Do not know the payee |
|---|---|---|---|---|
| Honest customer, ordinary payment | 2 | 0 | 0 | 0 |
| Scam victim answering honestly | 8 | 1 | 7 | 5 |
| Scam victim following the scammer's cover story | 4 | 5 | 0 | 0 |
| Attacker typing injection text as answers | 0 | 1 | 0 | 0 |

## Safety checks

| Who is answering | Questions asked | Questions replaced by the fixed question bank (model reply failed a rule) | Final reading of all answers that fell back to no phrases | Cases where a flag lowered the outcome |
|---|---|---|---|---|
| Honest customer, ordinary payment | 36 | 0 | 0 of 12 | 0 |
| Scam victim answering honestly | 36 | 0 | 0 of 12 | 0 |
| Scam victim following the scammer's cover story | 36 | 0 | 0 of 12 | 0 |
| Attacker typing injection text as answers | 18 | 0 | 0 of 6 | 0 |

## Limits (read these)

- The victim is an LLM following a persona; real victims behave differently, so these rates describe this simulation only.
- The coached cover stories are three short fixed scripts. Real scammers adapt.
- After the third question the system now reads all three answers once more (earlier it never read the third answer). The 'upper bound' column searches the raw answers directly and shows how much the model's phrase extraction still misses.
- Flags are plain keyword rules, so they miss paraphrases; that is a known gap.
- Small samples, one run, one model. Intervals are wide.
