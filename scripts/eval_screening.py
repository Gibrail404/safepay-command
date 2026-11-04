"""Run the screening evaluation on the real OFAC and Census data and write docs/reports/screening.{json,md}. Usage: python scripts/eval_screening.py"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "screening")]
from safepay_screening.evaluate import run


def pct(x): return f"{100 * x:.1f}%"
def ci(d): return f"{pct(d['rate'])} ({pct(d['ci95'][0])} to {pct(d['ci95'][1])})"


def render(r: dict) -> str:
    th = r["thresholds_from_validation_negatives"]
    t1, t01 = th["fpr_1pct"], th["fpr_0.1pct"]
    out = ["# Name screening evaluation (generated; do not edit by hand)", "",
           f"Data: {r['list_entries']:,} real OFAC list entries, {r['alias_rows']:,} real aliases, real US Census first names and surnames. Seed {r['seed']}.", "",
           "How to read this. A *score* is a number from 0 to 100 for how alike two names are. An *alert* means the score reached the threshold, so a person must look. "
           "*Recall* is the share of sanctioned names that raise an alert. *False alert rate* is the share of ordinary, non-sanctioned names that raise one.", "",
           "## Thresholds (chosen on validation names only, never on the test names)", "",
           f"- Alert level A: score >= {t1:.0f} (about 1 in 100 ordinary names alerts)",
           f"- Alert level B: score >= {t01:.0f} (about 1 in 1000 ordinary names alerts)", "",
           "## Ordinary names that wrongly alert (test half, composed from real first names and real surnames)", "",
           "| Threshold | Alerts | False alert rate (95% interval) |", "|---|---|---|"]
    for t, v in r["false_alert_rate_on_test_negatives"].items():
        out.append(f"| score >= {float(t):.0f} | {v['alerts']} of {r['negatives']['test']:,} | {ci(v)} |")
    out += ["", f"## Real aliases the list does not know yet ({r['held_out_alias_queries']} held-out aliases)", "",
            "We hide a random half of the aliases, search with the hidden ones, and check whether the right list entry comes back in the top results. These are real spelling variants written by OFAC.", "",
            "| Scenario | Matcher | Right entry is the top result | In top 5 | In top 10 | Top result AND alert level A | Top result AND alert level B |", "|---|---|---|---|---|---|---|"]
    labels = {"primary_plus_known_aliases": "List has primary names and half the aliases", "primary_names_only": "List has primary names only"}
    mnames = {"strong_folding": "Strong spelling folding", "mild_folding": "Mild spelling folding", "no_folding": "No spelling folding"}
    for sc, vs in r["held_out_aliases"].items():
        if sc.startswith("exact"):
            continue
        for v, row in vs.items():
            out.append(f"| {labels[sc]} | {mnames[v]} | {pct(row['recall_at_1'])} | {pct(row['recall_at_5'])} | {pct(row['recall_at_10'])} | {ci(row['found_as_top_hit_at_fpr_1pct'])} | {ci(row['found_as_top_hit_at_fpr_0.1pct'])} |")
    fc = r["fold_choice"]
    out += ["", f"Each matcher uses thresholds from its own validation names, so rows are compared at the same false alert rate. Which folding is shipped was decided by a rule fixed in advance ({fc['rule']}), on separate validation aliases: "
            + ", ".join(f"{mnames[k]} {pct(v)}" for k, v in fc["validation_scores"].items()) + f". Shipped: {mnames[fc['chosen']]}.", "",
            f"Baseline, exact match after cleaning case and punctuation: right entry is the top result for {pct(r['held_out_aliases']['exact_match_baseline_primary_plus_known_aliases']['recall_at_1'])} (list has primary names and half the aliases).", "",
            "## Sanctioned names written slightly wrong (real list names, one change each)", "",
            "| Change made | Queries | Right entry is the top result | In top 5 | Found with alert level A | Found with alert level B |", "|---|---|---|---|---|---|"]
    for k, row in r["perturbed_primary_names"].items():
        out.append(f"| {k.replace('_', ' ')} | {row['queries']} | {pct(row['recall_at_1'])} | {pct(row['recall_at_5'])} | {ci(row['found_at_fpr_1pct'])} | {ci(row['found_at_fpr_0.1pct'])} |")
    out += ["", "## Limits (read these)", "",
            "- Ordinary names are US census names composed at random. The sanctions list is mostly non-US names, so the true false alert rate on a global customer base is probably higher.",
            "- The list changes; this run is tied to the data file hashes in the manifests.",
            "- Each query is only a name. Real screening also uses date of birth, country and address; this matcher does not.", ""]
    return "\n".join(out)


def write_bands(rep: dict) -> None:
    """The thresholds the serving tool uses. Generated from the evaluation's validation names; nobody types them."""
    import hashlib
    sha = lambda n: json.loads((ROOT / "data" / "processed" / f"{n}.manifest.json").read_text())["source_sha256"]
    th = rep["thresholds_from_validation_negatives"]
    (ROOT / "config" / "screening_bands.json").write_text(json.dumps({
        "review": th["fpr_1pct"], "strong": th["fpr_0.1pct"], "fold_level": {"strong_folding": 2, "mild_folding": 1, "no_folding": 0}[rep["fold_choice"]["chosen"]],
        "list_sha256": sha("ofac_sdn"), "alias_sha256": sha("ofac_alt"), "source": "docs/reports/screening.json", "seed": rep["seed"]}, indent=2))


if __name__ == "__main__":
    if "--write-bands" in sys.argv:
        write_bands(json.loads((ROOT / "docs" / "reports" / "screening.json").read_text()))
        print("wrote config/screening_bands.json")
        sys.exit(0)
    t = time.time()
    rep = run()
    rep["seconds"] = round(time.time() - t, 1)
    d = ROOT / "docs" / "reports"
    (d / "screening.json").write_text(json.dumps(rep, indent=2))
    (d / "screening.md").write_text(render(rep))
    write_bands(rep)
    print(f"done in {rep['seconds']}s")
