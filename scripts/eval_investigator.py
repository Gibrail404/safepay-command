"""Evaluates the Investigator on REAL Elliptic alert cases with a live LLM. Measures how often the model's first answer already passes the deterministic fact check, how many
sentences in first answers are unsupported, and how often the case abstains by rule. Writes docs/reports/investigator.{json,md}.
Usage: python scripts/eval_investigator.py [--cases cases.json] [--n 60] [--model gemma4:31b]"""
import argparse, json, math, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "graph", "scripts"):
    sys.path.insert(0, str(ROOT / p))
import numpy as np
import check_llm_providers as envloader
from eval_llm import Recording, wilson
from safepay.agents.faithfulness import check_sentences
from safepay.agents.investigator import CaseSummary, build_case_evidence, evidence_is_thin, investigate
from safepay.llm.gateway import Budget, LLMGateway, extract_json
from safepay.llm.providers import OllamaCloudProvider


def pct(x): return f"{100 * x:.0f}%"
def rate(k, n): lo, hi = wilson(k, n); return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}
def show(r): return f"{pct(r['rate'])} ({r['k']} of {r['n']}; 95% interval {pct(r['ci95'][0])} to {pct(r['ci95'][1])})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases"), ap.add_argument("--n", type=int, default=60), ap.add_argument("--model", default="gemma4:31b")
    a = ap.parse_args()
    envloader.load_env()
    key = os.environ.get("OLLAMA_API_KEY") or sys.exit("OLLAMA_API_KEY missing")
    if a.cases:
        cases = json.loads(Path(a.cases).read_text())
    else:
        from seed_cases import build_cases
        cases = build_cases(150, 7)
    rng = np.random.default_rng(3)
    cases = [cases[i] for i in rng.permutation(len(cases))[: a.n]]
    rec = Recording(OllamaCloudProvider(key, a.model))
    gw = LLMGateway([rec], budget=Budget(max_requests_per_day=10_000, max_tokens_per_day=10**7, max_requests_per_run=10), timeout_s=12.0, deadline_s=24.0, cooldown_s=0.0)
    n_thin = n_model = n_first_schema = n_first_clean = n_llm_final = sent_total = sent_bad = 0
    recs = {"escalate": 0, "review": 0, "abstain": 0}
    ms = []
    for i, c in enumerate(cases):
        items = c["items"]
        before = len(rec.replies)
        t = time.perf_counter()
        summary, res, evidence, prio = investigate(gw, f"ei{i}", items)
        dt = (time.perf_counter() - t) * 1000
        recs[summary.recommendation] += 1
        if evidence_is_thin(items):
            n_thin += 1
            continue
        n_model += 1
        ms.append(dt)
        n_llm_final += res.path == "llm"
        first = rec.replies[before] if len(rec.replies) > before else None
        try:
            s1 = CaseSummary.model_validate(extract_json(first)) if first else None
        except Exception:
            s1 = None
        n_first_schema += s1 is not None
        if s1 is not None:
            issues = check_sentences(s1.sentences, evidence, "hold")
            n_first_clean += not issues
            sent_total += len(s1.sentences)
            sent_bad += len({x.sentence for x in issues})
    rep = {"model": a.model, "cases": len(cases), "abstained_by_rule": rate(n_thin, len(cases)), "sent_to_model": n_model, "first_answer_right_format": rate(n_first_schema, n_model),
           "first_answer_passed_fact_check": rate(n_first_clean, n_model), "unsupported_sentences_in_first_answers": rate(sent_bad, sent_total), "final_answer_from_model": rate(n_llm_final, n_model),
           "recommendations": recs, "latency_ms": {"p50": float(np.percentile(ms, 50)), "p95": float(np.percentile(ms, 95))} if ms else None}
    md = ["# Investigator evaluation (generated; do not edit by hand)", "",
          f"**Real alerts, live AI model.** {rep['cases']} cases built from real Elliptic Bitcoin alerts (the data is real; the case summaries are written by {a.model}). The Investigator may only use structured facts, must cite them, and a deterministic fact check rejects any sentence with an unsupported number or forbidden wording.", "",
          "| Measure | Result |", "|---|---|",
          f"| Cases where the system abstained by a fixed rule (single weak alert), no AI used | {show(rep['abstained_by_rule'])} |",
          f"| Cases sent to the AI model | {n_model} |", f"| The AI's first answer had the right format | {show(rep['first_answer_right_format'])} |",
          f"| The AI's first answer passed the fact check with no retry | {show(rep['first_answer_passed_fact_check'])} |", f"| Sentences in first answers that the evidence does not support | {show(rep['unsupported_sentences_in_first_answers'])} |",
          f"| Final summary written by the AI (not the safe fallback text) | {show(rep['final_answer_from_model'])} |",
          f"| Recommendations: escalate / review / abstain | {recs['escalate']} / {recs['review']} / {recs['abstain']} |",
          f"| Time to produce a summary, median / 95th percentile | {rep['latency_ms']['p50']:.0f} ms / {rep['latency_ms']['p95']:.0f} ms |" if rep["latency_ms"] else "| Time | n/a |", "",
          "## Limits (read these)", "",
          "- The fact check proves sentences match the evidence; it does not prove the evidence is meaningful or that the recommendation is right. No analyst has rated these summaries.",
          f"- The recommendation barely discriminates here: {recs['escalate']} of {n_model} summaries sent to the model said escalate, because every case is an above-threshold alert with high scores. Whether the recommendation helps analysts is not measured.",
          "- One model, one run, and sampled cases. Intervals are wide for small counts.",
          "- Cases are Bitcoin transaction alerts, not bank payments.", ""]
    (ROOT / "docs" / "reports" / "investigator.json").write_text(json.dumps(rep, indent=2))
    (ROOT / "docs" / "reports" / "investigator.md").write_text("\n".join(md))
    print("done")


if __name__ == "__main__":
    main()
