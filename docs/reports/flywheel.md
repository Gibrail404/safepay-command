# Analyst feedback flywheel (generated; do not edit by hand)

**Real transactions, simulated analysts.** The transactions and their labels are the real Elliptic Bitcoin data. The analysts are simulated: they review a fixed number of alerts per time step and answer correctly except for a random error rate. Nothing here is a real analyst.

Setup: the model starts trained on time steps 1 to 24. In each later time step it scores that step's labelled transactions, the simulated analyst reviews 50 of them chosen by the strategy below, their answers join the training data, and the model is retrained. Results are measured on time steps 35 to 49, using each step's predictions from the model as it was before seeing that step. One run, one random seed.

How to read this. *Average precision* summarises how well illicit transactions are ranked above licit ones. The last columns show what the analysts' time produced: how many labels, and what share of the labels were illicit (a strategy that mostly reviews high scores sees mostly illicit cases and learns a skewed picture).

## Analysts wrong 5.0% of the time

| How labels are collected | Average precision, steps 35 to 49 | Steps 35 to 42 | Steps 43 to 49 (after the market shutdown) | Illicit share of the top 100 alerts per step | Illicit share of the top 100, steps 43 to 49 | Labels collected | Illicit share of labels collected | Illicit share of training data at the end |
|---|---|---|---|---|---|---|---|---|
| No feedback (model never retrained) | 0.791 | 0.912 | 0.048 | 44.9% | 8.1% | 0 | 0.0% | 9.4% |
| Analysts review only the highest-scoring alerts | 0.844 | 0.911 | 0.336 | 48.8% | 15.6% | 1,250 | 69.8% | 12.4% |
| Analysts review alerts closest to the alert threshold | 0.883 | 0.933 | 0.468 | 50.2% | 17.7% | 1,250 | 19.5% | 10.1% |
| Analysts review random alerts | 0.813 | 0.911 | 0.083 | 46.5% | 11.6% | 1,250 | 11.0% | 9.7% |
| Half the highest-scoring, half random | 0.844 | 0.912 | 0.317 | 48.0% | 15.3% | 1,250 | 44.4% | 11.2% |
| Every label from earlier steps (upper bound; no real team has this) | 0.914 | 0.940 | 0.673 | 52.3% | 22.0% | 22,958 | 10.1% | 9.8% |

## Analysts wrong 20.0% of the time

| How labels are collected | Average precision, steps 35 to 49 | Steps 35 to 42 | Steps 43 to 49 (after the market shutdown) | Illicit share of the top 100 alerts per step | Illicit share of the top 100, steps 43 to 49 | Labels collected | Illicit share of labels collected | Illicit share of training data at the end |
|---|---|---|---|---|---|---|---|---|
| No feedback (model never retrained) | 0.791 | 0.912 | 0.048 | 44.9% | 8.1% | 0 | 0.0% | 9.4% |
| Analysts review only the highest-scoring alerts | 0.834 | 0.914 | 0.189 | 48.6% | 15.7% | 1,250 | 68.9% | 12.0% |
| Analysts review alerts closest to the alert threshold | 0.830 | 0.912 | 0.160 | 47.4% | 13.7% | 1,250 | 11.0% | 10.2% |
| Analysts review random alerts | 0.757 | 0.864 | 0.069 | 43.9% | 9.6% | 1,250 | 11.0% | 10.2% |
| Half the highest-scoring, half random | 0.738 | 0.834 | 0.095 | 42.9% | 9.4% | 1,250 | 41.6% | 11.2% |
| Every label from earlier steps (upper bound; no real team has this) | 0.914 | 0.940 | 0.673 | 52.3% | 22.0% | 22,958 | 10.1% | 9.8% |

## Limits (read these)

- One random seed and one run per row, so small differences between rows are not reliable. Large gaps are more trustworthy.
- Simulated analysts with a simple random error. Real analysts are inconsistent in more structured ways.
- Only labelled transactions can be reviewed in this simulation; real queues also contain transactions whose truth is never learned.
- Bitcoin transactions, not bank payments. The model and features are the simple own-features model from the graph evaluation.
- The review budget is fixed at one value; a different budget would change the picture.
