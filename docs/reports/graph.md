# Graph evaluation on the real Elliptic data (generated; do not edit by hand)

Data: real Bitcoin transaction graph, 203,769 transactions, 234,355 payment links, 46,564 labelled (illicit or licit; the rest are unknown). This is cryptocurrency, not card payments, and is used here only to test whether graph structure helps and whether alerts can be grouped into cases.

Protocol, fixed in advance: train on time steps 1 to 24, tune on 25 to 34 (alert threshold = 1% of licit validation transactions alert), report only on steps 35 to 49. Labelled transactions: train 23,606, validation 6,288, test 16,670 (illicit share of test: 6.5%). Both models use identical LightGBM settings and differ only in their inputs. Labels of other transactions are never used as inputs.

How to read this. *Average precision* summarises how well illicit transactions are ranked above licit ones (1 is perfect; the illicit share is the score of random guessing). *Precision* is the share of alerts that are really illicit. *Recall* is the share of illicit transactions that alert.

## Test results (steps 35 to 49)

| Inputs | Average precision (95% interval) | Precision | Recall | Alerts | Illicit found | Illicit missed |
|---|---|---|---|---|---|---|
| Each transaction on its own (165 features) | 0.792 (0.771 to 0.813) | 82.9% | 71.9% | 940 | 779 | 304 |
| Plus its neighbours (own features, 1-hop and 2-hop neighbour averages, degrees) | 0.792 (0.771 to 0.813) | 77.9% | 72.4% | 1,006 | 784 | 299 |
| Plus what the neighbours' first-round scores look like (two-stage; added after seeing the first results) | 0.796 (0.776 to 0.818) | 73.5% | 72.6% | 1,070 | 786 | 297 |

Gain in average precision over the first row: neighbour averages +0.000 (95% interval -0.005 to +0.005); neighbour scores +0.004 (95% interval +0.001 to +0.008). Intervals come from resampling the same test transactions for both models.

The third row was added after the first two results were seen, so it is exploratory: nothing was chosen between the models using the test results, and all three are reported.

## Before and after the dark market shutdown (a known break in this dataset)

| Inputs | Period | Average precision | Precision | Recall |
|---|---|---|---|---|
| Each transaction on its own (165 features) | steps 35 to 42 (914 illicit of 9,983) | 0.912 | 91.1% | 84.7% |
| Each transaction on its own (165 features) | steps 43 to 49 (169 illicit of 6,687) | 0.048 | 5.6% | 3.0% |
| Plus its neighbours (own features, 1-hop and 2-hop neighbour averages, degrees) | steps 35 to 42 (914 illicit of 9,983) | 0.917 | 88.3% | 85.3% |
| Plus its neighbours (own features, 1-hop and 2-hop neighbour averages, degrees) | steps 43 to 49 (169 illicit of 6,687) | 0.046 | 3.3% | 2.4% |
| Plus what the neighbours' first-round scores look like (two-stage; added after seeing the first results) | steps 35 to 42 (914 illicit of 9,983) | 0.912 | 86.2% | 85.2% |
| Plus what the neighbours' first-round scores look like (two-stage; added after seeing the first results) | steps 43 to 49 (169 illicit of 6,687) | 0.066 | 4.2% | 4.1% |

## Grouping alerts into cases (test steps, same alert threshold)

Alerts that are directly linked in the graph form one case. This is what the analyst workbench would show as one item.

| Inputs | Alerts | Cases | Alerts per case | Cases with 2 or more alerts | Largest case | Share of items to review removed | Cases where every labelled alert is illicit | Cases mixing illicit and licit |
|---|---|---|---|---|---|---|---|---|
| Each transaction on its own (165 features) | 940 | 869 | 1.08 | 63 | 4 | 7.6% | 82.6% | 3 |
| Plus its neighbours (own features, 1-hop and 2-hop neighbour averages, degrees) | 1,006 | 919 | 1.09 | 72 | 4 | 8.6% | 78.2% | 3 |
| Plus what the neighbours' first-round scores look like (two-stage; added after seeing the first results) | 1,070 | 966 | 1.11 | 83 | 6 | 9.7% | 74.4% | 3 |

## Limits (read these)

- One dataset, one split, one run of each model. Intervals come from resampling test transactions, not from repeating training.
- This is Bitcoin, not bank payments; it says whether structure can help, not how much it would help a payments company.
- Cases are judged only on labelled alerts; most graph nodes are unlabelled.
- The licence terms of the dataset are not confirmed (see data registry); results are for local study.
