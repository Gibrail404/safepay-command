"""Run the Decision Lab experiments and write docs/reports/decision_lab.{json,md} and a figure. All data here is SIMULATED. Usage: python scripts/eval_lab.py"""
import json, sys, time
from dataclasses import asdict, replace
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lab")]
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from safepay_lab.experiments import by_archetype, coverage_experiment, frontier
from safepay_lab.simulator import SimConfig

LABEL = {"naive_matched": "Naive (compare matching rows)", "ips": "Inverse propensity (IPS)", "snips": "Self-normalised IPS", "direct_method": "Outcome model only", "doubly_robust": "Doubly robust"}
ALT = {"base assumptions": SimConfig(), "rarer scams (0.5% instead of 2%)": replace(SimConfig(), scam_rate=0.005),
       "weaker risk score (gap 1.0 instead of 1.8)": replace(SimConfig(), score_separation=1.0), "less exploration (5% instead of 10%)": replace(SimConfig(), epsilon=0.05)}


def pct(x): return f"{100 * x:.0f}%"


def figure(res: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, len(res), figsize=(5 * len(res), 4.2), sharey=False)
    for ax, (tname, v) in zip(axes, res.items()):
        ks = list(v["estimators"])
        for i, k in enumerate(ks):
            e = v["estimators"][k]
            ax.errorbar(i, e["mean_estimate"], yerr=[[e["mean_estimate"] - e["p2_5"]], [e["p97_5"] - e["mean_estimate"]]], fmt="o", capsize=4, color="#2a6fdb")
        ax.axhline(v["truth"], color="#d62728", linestyle="--", label="truth (known by the simulator)")
        ax.set_xticks(range(len(ks)))
        ax.set_xticklabels(["Naive", "IPS", "SNIPS", "Outcome\nmodel", "Doubly\nrobust"], fontsize=8)
        ax.set_title(tname, fontsize=9)
        ax.set_ylabel("estimated value per payment (higher is better)")
    axes[0].legend(fontsize=8)
    fig.suptitle("Simulated data: what each method says a new policy would earn (dot = average, bar = middle 95% across repeats)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)


def render(rep: dict) -> str:
    base = rep["experiments"]["base assumptions"]
    o = ["# Decision Lab evaluation (generated; do not edit by hand)", "",
         "**All numbers on this page come from a simulator, not from real customers.** Real inputs: payment amounts follow the real ULB card data (log mean 3.005, sd 1.87). Everything else (scam rate, how well the risk score separates scams, how coached victims react, analyst catch rates, friction costs) is an assumption, listed below and varied in the last section.", "",
         "The question: a team has logged payments handled by an old policy. How well can it predict, from that log alone, what a NEW policy would have earned (money lost to scams plus the cost of bothering good customers)? The simulator knows the true answer, so each method can be graded. 'Value per payment' is minus (average loss and friction cost); closer to zero is better.", "",
         "Selective labels: a payment that was held never reveals whether it was a scam, so the log only shows outcomes for some payments. This is why simple comparisons mislead.", "",
         f"Setup: {rep['reps']} repeats, {rep['n']:,} payments each, logging policy holds from score 1.6 and warns from 0.8, plus {pct(rep['base_config']['epsilon'])} random exploration so every action has a known chance.", "",
         "## Grading each method against the truth (base assumptions)", ""]
    for tname, v in base.items():
        o += [f"### New policy: {tname}", "", f"True value per payment: **{v['truth']:.2f}**", "",
              "| Method | Average estimate | Bias | Typical error (RMSE) | Its 95% interval contains the truth | Average interval half-width |", "|---|---|---|---|---|---|"]
        for k, e in v["estimators"].items():
            o.append(f"| {LABEL[k]} | {e['mean_estimate']:.2f} | {e['bias']:+.2f} | {e['rmse']:.2f} | {pct(e['coverage_95'])} | {e['mean_halfwidth']:.2f} |")
        o.append("")
    o += ["Reading (from the tables above): the naive comparison is fine when the new policy is close to the old one and wrong when it is not: the further the new policy is from the logged one, the larger the error, and for 'allow everything' it is off by several times the true loss and never contains the truth. "
          "The outcome-model-only method has tiny intervals that contain the truth only about 8% to 41% of the time: it is overconfident. IPS and doubly robust are close to unbiased, but their intervals still miss the truth more often than the promised 5% (they contain it 68% to 88% of the time here) because a few large payments dominate the average, so normal-approximation intervals are too narrow. Doubly robust had the best coverage and, for the looser and allow-everything policies, the smallest error of the corrected methods. Note that the outcome-model-only method has the smallest typical error in several rows, but it is biased and cannot tell you how wrong it is, which is what a decision needs.", "",
          "![estimators](figures/decision_lab_estimators.png)", "", "## Trade-off between stopping scams and bothering good customers (truth from the simulator)", "",
          "| Hold from score | Warn from score | Scam money stopped | Good payments warned | Good payments held | Value per payment |", "|---|---|---|---|---|---|"]
    for r in rep["frontier"]:
        o.append(f"| {r['hold_from']} | {r['warn_from']:.1f} | {pct(r['scam_money_stopped_share'])} | {pct(r['good_payments_warned_share'])} | {pct(r['good_payments_held_share'])} | {r['value_per_payment']:.2f} |")
    o += ["", "## Which kinds of scam does the logging policy stop? (truth from the simulator; hold from 1.6, warn from 0.8)", "",
          "| Kind of scam | Chance the victim is coached | Share of all scams | Scam money stopped | Held | Warned | Allowed |", "|---|---|---|---|---|---|---|"]
    for r in rep["by_archetype"]:
        o.append(f"| {r['archetype'].replace('_', ' ')} | {pct(r['coaching'])} | {pct(r['share_of_scams'])} | {pct(r['money_stopped_share'])} | {pct(r['held_share'])} | {pct(r['warned_share'])} | {pct(r['allowed_share'])} |")
    o += ["", "## Do the conclusions survive different assumptions?", "", f"Each row repeats the experiment {rep['alt_reps']} times under different assumptions. Shown for the 'stricter' policy: how often each method's 95% interval contains the truth, and its bias.", "",
          "| Assumption set | Truth | Naive: covers / bias | IPS: covers / bias | Outcome model: covers / bias | Doubly robust: covers / bias |", "|---|---|---|---|---|---|"]
    for name, res in rep["experiments"].items():
        v = next(iter(res.values()))
        cell = lambda k: f"{pct(v['estimators'][k]['coverage_95'])} / {v['estimators'][k]['bias']:+.2f}"
        o.append(f"| {name} | {v['truth']:.2f} | {cell('naive_matched')} | {cell('ips')} | {cell('direct_method')} | {cell('doubly_robust')} |")
    o += ["", "## Assumptions used (base)", "", "```", json.dumps(rep["base_config"], indent=1), "```", "",
          "## Limits (read these)", "",
          "- A simulator can only prove a method works on worlds like the simulator. The point is to catch methods that fail even here, and to show how large their errors are.",
          "- Coverage is measured over a finite number of repeats, so each percentage has roughly +/- 7 points of noise at 200 repeats and +/- 13 at 60.",
          "- Payment amounts are capped (an assumption). Without a cap, a few huge payments dominate the average and every method fails at this sample size, which is itself a real-world warning.",
          "- Interval type: normal approximation, not bootstrap.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    t = time.time()
    reps, alt_reps, n = 200, 60, 20000
    exps = {}
    for name, cfg in ALT.items():
        exps[name] = coverage_experiment(cfg, reps if name == "base assumptions" else alt_reps, n, seed=11)
        print(name, round(time.time() - t), "s", flush=True)
    rep = {"reps": reps, "alt_reps": alt_reps, "n": n, "base_config": asdict(SimConfig()), "experiments": exps, "frontier": frontier(SimConfig()), "by_archetype": by_archetype(SimConfig()), "seconds": round(time.time() - t)}
    d = ROOT / "docs" / "reports"
    (d / "figures").mkdir(exist_ok=True)
    figure(exps["base assumptions"], d / "figures" / "decision_lab_estimators.png")
    (d / "decision_lab.json").write_text(json.dumps(rep, indent=2))
    (d / "decision_lab.md").write_text(render(rep))
    print("done")
