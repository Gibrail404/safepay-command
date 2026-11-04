"""Uplift experiment on SIMULATED data: does ranking payments by estimated benefit of a hold beat ranking by risk score, and how much logged data does it need?
Writes docs/reports/uplift.{json,md}. Usage: python scripts/eval_uplift.py"""
import json, sys, time
from dataclasses import asdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lab")]
from safepay_lab.simulator import SimConfig
from safepay_lab.uplift import uplift_experiment


def render(rep: dict) -> str:
    o = ["# Uplift evaluation (generated; do not edit by hand)", "",
         "**Simulated data, not real customers.** Question: holding a payment costs good customers time and money, so which payments should be held? A risk score ranks payments by how likely they are to be scams. "
         "*Uplift* ranks them by how much a hold actually helps (money saved minus the cost of bothering a good customer). Uplift has to be estimated from logged data, where held payments never reveal their outcome. "
         "The simulator knows the true uplift, so the estimate can be graded.", "",
         f"Each row: {rep['reps']} repeats on fresh data. The policy holds the top share of payments by the given ranking and allows the rest. Value per payment is minus (average loss and friction cost); closer to zero is better. "
         "'Best possible' ranks by the true uplift, which no real team can do. Test payments are 300,000 fresh simulated payments.", "",
         "| Logged payments used | How well the ranking agrees with the true uplift: risk score | Estimated uplift | Hold top share | Allow everything | Hold by risk score | Hold by estimated uplift | Best possible | Estimated uplift beats risk score in |", "|---|---|---|---|---|---|---|---|---|"]
    for n, r in rep["by_size"].items():
        c = r["rank_correlation_with_true_uplift"]
        for q, v in r["values"].items():
            o.append(f"| {int(n):,} | {c['risk_score']:.2f} | {c['estimated_uplift_mean']:.2f} (sd {c['estimated_uplift_sd']:.2f}) | {float(q):.0%} | {v['allow_everything']:.2f} | {v['hold_top_by_score']:.2f} | {v['hold_top_by_estimated_uplift']:.2f} | {v['hold_top_by_true_uplift_oracle']:.2f} | {v['uplift_better_share']:.0%} of repeats |")
    o += ["", "Agreement is a Spearman rank correlation (1 means the same order, 0 means unrelated).", "", "## Limits (read these)", "",
          "- The best-possible ranking is far ahead of both real options, so most of the available benefit is not captured by either ranking at these sizes.",
          "- In this simulator all good payments have the same cost of a hold, so the uplift mostly depends on the chance of scam and the amount. Real friction costs vary.",
          "- One simulator, one set of assumptions (see decision_lab.md for the list). One outcome-model family (gradient boosting, one model per action).",
          "- Repeats are few for the largest sizes, so the percentages are rough.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    t = time.time()
    sizes = {20_000: 20, 100_000: 12, 400_000: 6}
    rep = {"reps": "6 to 20", "base_config": asdict(SimConfig()), "by_size": {str(n): uplift_experiment(SimConfig(), reps=k, n=n, seed=21) for n, k in sizes.items()}}
    rep["seconds"] = round(time.time() - t)
    (ROOT / "docs" / "reports" / "uplift.json").write_text(json.dumps(rep, indent=2))
    (ROOT / "docs" / "reports" / "uplift.md").write_text(render(rep))
    print("done", rep["seconds"], "s")
