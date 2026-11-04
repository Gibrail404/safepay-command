# Name screening evaluation (generated; do not edit by hand)

Data: 19,485 real OFAC list entries, 20,204 real aliases, real US Census first names and surnames. Seed 7.

How to read this. A *score* is a number from 0 to 100 for how alike two names are. An *alert* means the score reached the threshold, so a person must look. *Recall* is the share of sanctioned names that raise an alert. *False alert rate* is the share of ordinary, non-sanctioned names that raise one.

## Thresholds (chosen on validation names only, never on the test names)

- Alert level A: score >= 81 (about 1 in 100 ordinary names alerts)
- Alert level B: score >= 89 (about 1 in 1000 ordinary names alerts)

## Ordinary names that wrongly alert (test half, composed from real first names and real surnames)

| Threshold | Alerts | False alert rate (95% interval) |
|---|---|---|
| score >= 80 | 138 of 10,000 | 1.4% (1.2% to 1.6%) |
| score >= 85 | 20 of 10,000 | 0.2% (0.1% to 0.3%) |
| score >= 90 | 4 of 10,000 | 0.0% (0.0% to 0.1%) |
| score >= 95 | 1 of 10,000 | 0.0% (0.0% to 0.1%) |
| score >= 81 | 94 of 10,000 | 0.9% (0.8% to 1.1%) |
| score >= 89 | 5 of 10,000 | 0.1% (0.0% to 0.1%) |

## Real aliases the list does not know yet (1500 held-out aliases)

We hide a random half of the aliases, search with the hidden ones, and check whether the right list entry comes back in the top results. These are real spelling variants written by OFAC.

| Scenario | Matcher | Right entry is the top result | In top 5 | In top 10 | Top result AND alert level A | Top result AND alert level B |
|---|---|---|---|---|---|---|
| List has primary names and half the aliases | Strong spelling folding | 64.9% | 75.8% | 79.8% | 39.5% (37.1% to 42.0%) | 24.2% (22.1% to 26.4%) |
| List has primary names and half the aliases | Mild spelling folding | 65.3% | 76.8% | 81.0% | 40.5% (38.1% to 43.0%) | 20.9% (18.9% to 23.0%) |
| List has primary names and half the aliases | No spelling folding | 66.7% | 78.6% | 82.1% | 53.7% (51.2% to 56.2%) | 39.4% (37.0% to 41.9%) |
| List has primary names only | Strong spelling folding | 56.6% | 67.7% | 70.8% | 29.1% (26.8% to 31.4%) | 15.9% (14.1% to 17.8%) |
| List has primary names only | Mild spelling folding | 57.3% | 67.9% | 72.1% | 32.2% (29.9% to 34.6%) | 16.3% (14.5% to 18.2%) |
| List has primary names only | No spelling folding | 58.6% | 70.0% | 73.4% | 43.7% (41.2% to 46.3%) | 27.6% (25.4% to 29.9%) |

Each matcher uses thresholds from its own validation names, so rows are compared at the same false alert rate. Which folding is shipped was decided by a rule fixed in advance (highest validation top-hit rate at alert level A), on separate validation aliases: Strong spelling folding 31.7%, Mild spelling folding 33.8%, No spelling folding 45.1%. Shipped: No spelling folding.

Baseline, exact match after cleaning case and punctuation: right entry is the top result for 1.1% (list has primary names and half the aliases).

## Sanctioned names written slightly wrong (real list names, one change each)

| Change made | Queries | Right entry is the top result | In top 5 | Found with alert level A | Found with alert level B |
|---|---|---|---|---|---|
| typo | 400 | 98.5% | 99.8% | 97.0% (94.8% to 98.3%) | 87.5% (83.9% to 90.4%) |
| reorder | 400 | 99.8% | 100.0% | 100.0% (99.0% to 100.0%) | 100.0% (99.0% to 100.0%) |
| drop token | 400 | 91.8% | 96.2% | 94.8% (92.1% to 96.5%) | 75.8% (71.3% to 79.7%) |
| vowel variant | 400 | 99.5% | 100.0% | 97.5% (95.5% to 98.6%) | 90.8% (87.5% to 93.2%) |
| spacing | 400 | 94.0% | 99.8% | 83.8% (79.8% to 87.0%) | 49.8% (44.9% to 54.6%) |

## Limits (read these)

- Ordinary names are US census names composed at random. The sanctions list is mostly non-US names, so the true false alert rate on a global customer base is probably higher.
- The list changes; this run is tied to the data file hashes in the manifests.
- Each query is only a name. Real screening also uses date of birth, country and address; this matcher does not.
