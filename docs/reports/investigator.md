# Investigator evaluation (generated; do not edit by hand)

**Real alerts, live AI model.** 60 cases built from real Elliptic Bitcoin alerts (the data is real; the case summaries are written by gemma4:31b). The Investigator may only use structured facts, must cite them, and a deterministic fact check rejects any sentence with an unsupported number or forbidden wording.

| Measure | Result |
|---|---|
| Cases where the system abstained by a fixed rule (single weak alert), no AI used | 18% (11 of 60; 95% interval 11% to 30%) |
| Cases sent to the AI model | 49 |
| The AI's first answer had the right format | 100% (49 of 49; 95% interval 93% to 100%) |
| The AI's first answer passed the fact check with no retry | 100% (49 of 49; 95% interval 93% to 100%) |
| Sentences in first answers that the evidence does not support | 0% (0 of 85; 95% interval 0% to 4%) |
| Final summary written by the AI (not the safe fallback text) | 100% (49 of 49; 95% interval 93% to 100%) |
| Recommendations: escalate / review / abstain | 42 / 7 / 11 |
| Time to produce a summary, median / 95th percentile | 1691 ms / 1928 ms |

## Limits (read these)

- The fact check proves sentences match the evidence; it does not prove the evidence is meaningful or that the recommendation is right. No analyst has rated these summaries.
- The recommendation barely discriminates here: 42 of 49 summaries sent to the model said escalate, because every case is an above-threshold alert with high scores. Whether the recommendation helps analysts is not measured.
- One model, one run, and sampled cases. Intervals are wide for small counts.
- Cases are Bitcoin transaction alerts, not bank payments.
