"""Runs the real Questioner against sandbox actors (SIMULATED customers) with a live LLM and writes docs/reports/sandbox.{json,md}.
Usage: python scripts/eval_sandbox.py [--limit N] [--model gemma4:31b]"""
import argparse, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "lab", "scripts"):
    sys.path.insert(0, str(ROOT / p))
import check_llm_providers as envloader
from safepay.config import PolicyStore
from safepay.llm.gateway import Budget, LLMGateway
from safepay.llm.providers import OllamaCloudProvider
from safepay.policy import SEVERITY, evaluate
from safepay_lab.sandbox import personas, run_questions

POLICY = PolicyStore(ROOT / "config" / "policies").policies["payment_risk"]
BASE = {"amount": 4800, "payee_age_days": 0, "risk_band": "elevated"}
GROUPS = ["benign", "uncoached_victim", "coached_victim", "red_team"]
NAMES = {"benign": "Honest customer, ordinary payment", "uncoached_victim": "Scam victim answering honestly", "coached_victim": "Scam victim following the scammer's cover story", "red_team": "Attacker typing injection text as answers"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(x): return f"{100 * x:.0f}%"
def rate(k, n): lo, hi = wilson(k, n); return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci95": [lo, hi]}
def show(r): return f"{pct(r['rate'])} ({r['k']} of {r['n']}; 95% interval {pct(r['ci95'][0])} to {pct(r['ci95'][1])})"


def friction_only_violation(flags: dict) -> bool:
    """True if turning on the flags LOWERED the policy outcome. It must never happen."""
    return SEVERITY[evaluate(POLICY, {**BASE, **flags}).outcome] < SEVERITY[evaluate(POLICY, BASE).outcome]


def summarise(rows: list[dict]) -> dict:
    out = {}
    for g in GROUPS:
        r = [x for x in rows if x["kind"] == g]
        if not r:
            continue
        anyf = lambda key: sum(any(x[key].values()) for x in r)
        out[g] = {"conversations": len(r), "any_flag_from_extracted_phrases": rate(anyf("flags_from_extracted_phrases"), len(r)), "any_flag_from_raw_answers": rate(anyf("flags_from_raw_answers"), len(r)),
                  "by_flag_raw": {f: sum(x["flags_from_raw_answers"][f] for x in r) for f in r[0]["flags_from_raw_answers"]},
                  "questions_that_fell_back_to_the_fixed_bank": sum(x["fallback_questions"] for x in r), "total_questions": 3 * len(r),
                  "friction_only_violations": sum(friction_only_violation(x["flags_from_raw_answers"]) or friction_only_violation(x["flags_from_extracted_phrases"]) for x in r)}
    return out


def render(rep: dict) -> str:
    s = rep["summary"]
    o = ["# Sandbox evaluation of the Questioner (generated; do not edit by hand)", "",
         f"**Simulated customers.** The real Questioner, running on {rep['model']}, asks up to three questions; sandbox actors answer. The scammer is a fixed script (generic cover stories), the victim is an LLM role-playing a customer, the attacker types injection text. Nothing here is real customer behaviour. {rep['conversations']} conversations, run {rep['seconds']} s.", "",
         "A *flag* is a warning sign found in the answers (someone told me to pay, urgency, secrecy, I do not know the payee). Flags can only ADD friction to a payment; they can never lower the outcome.", "",
         "## How often the answers raised a flag", "", "| Who is answering | Conversations | Flag found, using the phrases the Questioner extracted (how the system works today) | Flag found, searching all the answers (upper bound) |", "|---|---|---|---|"]
    for g, v in s.items():
        o.append(f"| {NAMES[g]} | {v['conversations']} | {show(v['any_flag_from_extracted_phrases'])} | {show(v['any_flag_from_raw_answers'])} |")
    o += ["", "Reading: an honest customer should raise no flag (a flag there means needless friction). A scam victim who answers honestly should raise one. A coached victim is the hard case: the scammer's cover story hides exactly what the flags look for.", "",
          "## Which flags, searching all the answers", "", "| Who is answering | Someone told me | Urgency | Secrecy | Do not know the payee |", "|---|---|---|---|---|"]
    for g, v in s.items():
        b = v["by_flag_raw"]
        o.append(f"| {NAMES[g]} | {b['third_party_instructed']} | {b['urgency']} | {b['secrecy']} | {b['unknown_payee']} |")
    o += ["", "## Safety checks", "", "| Who is answering | Questions asked | Questions replaced by the fixed question bank (model reply failed a rule) | Cases where a flag lowered the outcome |", "|---|---|---|---|"]
    for g, v in s.items():
        o.append(f"| {NAMES[g]} | {v['total_questions']} | {v['questions_that_fell_back_to_the_fixed_bank']} | {v['friction_only_violations']} |")
    o += ["", "## Limits (read these)", "",
          "- The victim is an LLM following a persona; real victims behave differently, so these rates describe this simulation only.",
          "- The coached cover stories are three short fixed scripts. Real scammers adapt.",
          "- The system only extracts phrases from answers 1 and 2 before it stops asking; the third answer is not extracted, so the 'extracted phrases' column can miss what the last answer said. The upper-bound column shows the difference.",
          "- Flags are plain keyword rules, so they miss paraphrases; that is a known gap.",
          "- Small samples, one run, one model. Intervals are wide.", ""]
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="gemma4:31b")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    envloader.load_env()
    key = os.environ.get("OLLAMA_API_KEY")
    if not key:
        sys.exit("OLLAMA_API_KEY missing")
    people = personas()
    if a.limit:
        people = [p for g in GROUPS for p in [x for x in people if x.kind == g][: a.limit]]
    mk = lambda: LLMGateway([OllamaCloudProvider(key, a.model)], budget=Budget(max_requests_per_day=10_000, max_tokens_per_day=10**7, max_requests_per_run=50), timeout_s=12.0, deadline_s=24.0, cooldown_s=0.0)
    gw, vgw = mk(), mk()
    t = time.time()

    def one(i):
        try:
            return run_questions(gw, vgw, people[i], f"sb{i}")
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"[:200], "kind": people[i].kind}
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, range(len(people))))
    errs = [r for r in rows if "error" in r]
    rows = [r for r in rows if "error" not in r]
    rep = {"model": a.model, "conversations": len(rows), "errors": errs, "seconds": round(time.time() - t), "summary": summarise(rows), "transcripts": rows}
    if a.limit:
        print(render(rep)); print("errors:", errs[:2])
    else:
        (ROOT / "docs" / "reports" / "sandbox.json").write_text(json.dumps(rep, indent=2))
        (ROOT / "docs" / "reports" / "sandbox.md").write_text(render(rep))
        print("done", rep["seconds"], "s; errors", len(errs))


if __name__ == "__main__":
    main()
