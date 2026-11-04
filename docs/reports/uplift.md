# Uplift evaluation (generated; do not edit by hand)

**Simulated data, not real customers.** Question: holding a payment costs good customers time and money, so which payments should be held? A risk score ranks payments by how likely they are to be scams. *Uplift* ranks them by how much a hold actually helps (money saved minus the cost of bothering a good customer). Uplift has to be estimated from logged data, where held payments never reveal their outcome. The simulator knows the true uplift, so the estimate can be graded.

Each row: 6 to 20 repeats on fresh data. The policy holds the top share of payments by the given ranking and allows the rest. Value per payment is minus (average loss and friction cost); closer to zero is better. 'Best possible' ranks by the true uplift, which no real team can do. Test payments are 300,000 fresh simulated payments.

| Logged payments used | How well the ranking agrees with the true uplift: risk score | Estimated uplift | Hold top share | Allow everything | Hold by risk score | Hold by estimated uplift | Best possible | Estimated uplift beats risk score in |
|---|---|---|---|---|---|---|---|---|
| 20,000 | 0.20 | 0.04 (sd 0.06) | 5% | -6.17 | -4.39 | -4.95 | -2.18 | 30% of repeats |
| 20,000 | 0.20 | 0.04 (sd 0.06) | 10% | -6.17 | -4.06 | -5.49 | -2.55 | 20% of repeats |
| 20,000 | 0.20 | 0.04 (sd 0.06) | 20% | -6.17 | -4.19 | -6.70 | -3.29 | 5% of repeats |
| 100,000 | 0.20 | 0.03 (sd 0.08) | 5% | -6.17 | -4.39 | -4.03 | -2.18 | 50% of repeats |
| 100,000 | 0.20 | 0.03 (sd 0.08) | 10% | -6.17 | -4.06 | -5.40 | -2.55 | 25% of repeats |
| 100,000 | 0.20 | 0.03 (sd 0.08) | 20% | -6.17 | -4.19 | -6.21 | -3.29 | 0% of repeats |
| 400,000 | 0.20 | 0.12 (sd 0.04) | 5% | -6.17 | -4.39 | -3.25 | -2.18 | 100% of repeats |
| 400,000 | 0.20 | 0.12 (sd 0.04) | 10% | -6.17 | -4.06 | -3.70 | -2.55 | 67% of repeats |
| 400,000 | 0.20 | 0.12 (sd 0.04) | 20% | -6.17 | -4.19 | -4.29 | -3.29 | 50% of repeats |

Agreement is a Spearman rank correlation (1 means the same order, 0 means unrelated).

## Limits (read these)

- The best-possible ranking is far ahead of both real options, so most of the available benefit is not captured by either ranking at these sizes.
- In this simulator all good payments have the same cost of a hold, so the uplift mostly depends on the chance of scam and the amount. Real friction costs vary.
- One simulator, one set of assumptions (see decision_lab.md for the list). One outcome-model family (gradient boosting, one model per action).
- Repeats are few for the largest sizes, so the percentages are rough.
