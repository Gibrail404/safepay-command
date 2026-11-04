"""Flywheel experiment (REAL Elliptic data, SIMULATED analysts). Writes docs/reports/flywheel.{json,md}. Usage: python scripts/eval_flywheel.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in ("ml", "graph"):
    sys.path.insert(0, str(ROOT / p))
from safepay_graph.flywheel import run

NAME = {"no_feedback": "No feedback (model never retrained)", "review_top_scores": "Analysts review only the highest-scoring alerts", "review_near_threshold": "Analysts review alerts closest to the alert threshold",
        "review_random": "Analysts review random alerts", "half_top_half_random": "Half the highest-scoring, half random", "all_labels_oracle": "Every label from earlier steps (upper bound; no real team has this)"}


def pct(x): return "n/a" if x != x else f"{100 * x:.1f}%"


def render(r: dict) -> str:
    o = ["# Analyst feedback flywheel (generated; do not edit by hand)", "",
         "**Real transactions, simulated analysts.** The transactions and their labels are the real Elliptic Bitcoin data. The analysts are simulated: they review a fixed number of alerts per time step and answer correctly except for a random error rate. Nothing here is a real analyst.", "",
         f"Setup: the model starts trained on time steps 1 to 24. In each later time step it scores that step's labelled transactions, the simulated analyst reviews {r['budget_per_step']} of them chosen by the strategy below, their answers join the training data, and the model is retrained. Results are measured on time steps {r['evaluation_steps']}, using each step's predictions from the model as it was before seeing that step. One run, one random seed.", "",
         "How to read this. *Average precision* summarises how well illicit transactions are ranked above licit ones. The last columns show what the analysts' time produced: how many labels, and what share of the labels were illicit (a strategy that mostly reviews high scores sees mostly illicit cases and learns a skewed picture).", ""]
    for noise, res in r["results"].items():
        o += [f"## Analysts wrong {pct(float(noise))} of the time", "", "| How labels are collected | Average precision, steps 35 to 49 | Steps 35 to 42 | Steps 43 to 49 (after the market shutdown) | Illicit share of the top 100 alerts per step | Illicit share of the top 100, steps 43 to 49 | Labels collected | Illicit share of labels collected | Illicit share of training data at the end |", "|---|---|---|---|---|---|---|---|---|"]
        for s, v in res.items():
            o.append(f"| {NAME[s]} | {v['average_precision_steps_35_49']:.3f} | {v['average_precision_steps_35_42']:.3f} | {v['average_precision_steps_43_49']:.3f} | {pct(v['illicit_share_in_top_100_alerts_per_step'])} | {pct(v['illicit_share_in_top_100_steps_43_49'])} | {v['labels_collected']:,} | {pct(v['illicit_share_of_reviewed'])} | {pct(v['illicit_share_of_training_pool_end'])} |")
        o.append("")
    o += ["## Limits (read these)", "",
          "- One random seed and one run per row, so small differences between rows are not reliable. Large gaps are more trustworthy.",
          "- Simulated analysts with a simple random error. Real analysts are inconsistent in more structured ways.",
          "- Only labelled transactions can be reviewed in this simulation; real queues also contain transactions whose truth is never learned.",
          "- Bitcoin transactions, not bank payments. The model and features are the simple own-features model from the graph evaluation.",
          "- The review budget is fixed at one value; a different budget would change the picture.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    t = time.time()
    rep = run()
    rep["seconds"] = round(time.time() - t)
    d = ROOT / "docs" / "reports"
    (d / "flywheel.json").write_text(json.dumps(rep, indent=2))
    (d / "flywheel.md").write_text(render(rep))
    print("done", rep["seconds"], "s")
