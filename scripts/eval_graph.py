"""Graph experiment on the REAL Elliptic Bitcoin transaction graph. Writes docs/reports/graph.{json,md}. Usage: python scripts/eval_graph.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in ("ml", "graph"):
    sys.path.insert(0, str(ROOT / p))
from safepay_graph.experiment import run

NAME = {"features_only": "Each transaction on its own (165 features)", "with_graph": "Plus its neighbours (own features, 1-hop and 2-hop neighbour averages, degrees)",
        "with_neighbour_scores": "Plus what the neighbours' first-round scores look like (two-stage; added after seeing the first results)"}


def pct(x): return f"{100 * x:.1f}%"


def render(r: dict) -> str:
    m = r["models"]
    o = ["# Graph evaluation on the real Elliptic data (generated; do not edit by hand)", "",
         f"Data: real Bitcoin transaction graph, {r['nodes']:,} transactions, {r['edges_undirected']:,} payment links, {r['labelled']:,} labelled (illicit or licit; the rest are unknown). This is cryptocurrency, not card payments, and is used here only to test whether graph structure helps and whether alerts can be grouped into cases.", "",
         f"Protocol, fixed in advance: train on time steps 1 to 24, tune on 25 to 34 (alert threshold = 1% of licit validation transactions alert), report only on steps 35 to 49. Labelled transactions: train {r['split_sizes']['train']:,}, validation {r['split_sizes']['val']:,}, test {r['split_sizes']['test']:,} (illicit share of test: {pct(r['illicit_base_rate_test'])}). Both models use identical LightGBM settings and differ only in their inputs. Labels of other transactions are never used as inputs.", "",
         "How to read this. *Average precision* summarises how well illicit transactions are ranked above licit ones (1 is perfect; the illicit share is the score of random guessing). *Precision* is the share of alerts that are really illicit. *Recall* is the share of illicit transactions that alert.", "",
         "## Test results (steps 35 to 49)", "", "| Inputs | Average precision (95% interval) | Precision | Recall | Alerts | Illicit found | Illicit missed |", "|---|---|---|---|---|---|---|"]
    for k, v in m.items():
        t = v["test"]
        o.append(f"| {NAME[k]} | {t['average_precision']:.3f} ({v['average_precision_ci95'][0]:.3f} to {v['average_precision_ci95'][1]:.3f}) | {pct(t['precision'])} | {pct(t['recall'])} | {t['alerts']:,} | {t['tp']} | {t['fn']} |")
    g = r["paired_average_precision_gain_with_graph"]
    g2 = r["paired_average_precision_gain_with_neighbour_scores"]
    o += ["", f"Gain in average precision over the first row: neighbour averages {g['mean']:+.3f} (95% interval {g['ci95'][0]:+.3f} to {g['ci95'][1]:+.3f}); neighbour scores {g2['mean']:+.3f} (95% interval {g2['ci95'][0]:+.3f} to {g2['ci95'][1]:+.3f}). Intervals come from resampling the same test transactions for both models.", "",
          "The third row was added after the first two results were seen, so it is exploratory: nothing was chosen between the models using the test results, and all three are reported.", "",
          "## Before and after the dark market shutdown (a known break in this dataset)", "", "| Inputs | Period | Average precision | Precision | Recall |", "|---|---|---|---|---|"]
    for k, v in m.items():
        for lab, key in (("steps 35 to 42", "test_steps_35_42"), ("steps 43 to 49", "test_steps_43_49_after_market_shutdown")):
            t = v[key]
            o.append(f"| {NAME[k]} | {lab} ({t['illicit']} illicit of {t['n']:,}) | {t['average_precision']:.3f} | {pct(t['precision'])} | {pct(t['recall'])} |")
    o += ["", "## Grouping alerts into cases (test steps, same alert threshold)", "", "Alerts that are directly linked in the graph form one case. This is what the analyst workbench would show as one item.", "",
          "| Inputs | Alerts | Cases | Alerts per case | Cases with 2 or more alerts | Largest case | Share of items to review removed | Cases where every labelled alert is illicit | Cases mixing illicit and licit |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in m.items():
        c = v["cases"]
        o.append(f"| {NAME[k]} | {c['alerts']:,} | {c['cases']:,} | {c['alerts_per_case_mean']:.2f} | {c['cases_with_2_or_more_alerts']} | {c['largest_case']} | {pct(c['reduction_in_items_to_review'])} | {pct(c['pure_illicit_cases_share_of_labelled_cases'])} | {c['mixed_cases']} |")
    o += ["", "## Limits (read these)", "",
          "- One dataset, one split, one run of each model. Intervals come from resampling test transactions, not from repeating training.",
          "- This is Bitcoin, not bank payments; it says whether structure can help, not how much it would help a payments company.",
          "- Cases are judged only on labelled alerts; most graph nodes are unlabelled.",
          "- The licence terms of the dataset are not confirmed (see data registry); results are for local study.", ""]
    return "\n".join(o)


if __name__ == "__main__":
    t = time.time()
    rep = run()
    rep["seconds"] = round(time.time() - t)
    d = ROOT / "docs" / "reports"
    (d / "graph.json").write_text(json.dumps(rep, indent=2))
    (d / "graph.md").write_text(render(rep))
    print("done", rep["seconds"], "s")
