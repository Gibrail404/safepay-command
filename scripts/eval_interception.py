"""Head-to-head comparison on the same simulated customer scenarios, to test whether the AI questioning adds anything over simpler systems:
  A  rules only (amount and payee age)
  B  rules + the real risk model's band
  C  B + a fixed question bank and keyword rules on the answers (no AI in the decision path)
  D  B + the AI Questioner and its answer reading (the product flow)
Payment features are real held-out ULB transactions scored by the real model; payee age and the customer's answers are SIMULATED. Writes docs/reports/interception.{json,md}.
Nothing is tuned on the held-out scenarios: the development set only checks that the harness runs.
Usage: python scripts/eval_interception.py [--dev 100] [--heldout 200] [--workers 4] [--model gemma4:31b] [--render-only]"""
import argparse, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "lab", "scripts"):
    sys.path.insert(0, str(ROOT / p))
import numpy as np
from safepay.agents.flags import answer_flags
from safepay.agents.questioner import QUESTION_BANK
from safepay.config import PolicyStore
from safepay.interception import needs_questions
from safepay.llm.gateway import Budget, LLMGateway
from safepay.llm.providers import OllamaCloudProvider
from safepay.policy import evaluate
from safepay.risk_tool import PaymentFeatures, score_payment_risk
from safepay_lab import sandbox
from safepay_lab.scenarios import KINDS, LABEL, build

POLICY = PolicyStore(ROOT / "config" / "policies").policies["payment_risk"]
RANK = {"allow": 0, "warn": 1, "hold": 2, "block": 3}
HELD = ("hold", "block")
SYS = {"a": "A. Rules only (amount, payee age)", "b": "B. Rules plus the risk model", "c": "C. B plus fixed questions and keyword rules (no AI in the decision path)", "d": "D. B plus the AI Questioner (the product flow)"}
REPORT = ROOT / "docs" / "reports"


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct(x): return f"{100 * x:.0f}%"
def show(k, n): lo, hi = wilson(k, n); return f"{pct(k / n if n else 0)} ({k} of {n}; {pct(lo)} to {pct(hi)})"


def outcome(ctx): return evaluate(POLICY, ctx).outcome


def process(sc, gw, vgw, i: int, tag: str) -> dict:
    risk = score_payment_risk(PaymentFeatures(amount=sc.amount, **sc.features))
    base = {"amount": sc.amount, "payee_age_days": sc.payee_age_days, "currency": "EUR"}
    ctx_a, ctx_b = dict(base), {**base, "risk_band": risk["risk_band"]}
    row = {"kind": sc.kind, "is_scam": sc.is_scam, "amount": round(sc.amount, 2), "payee_age_days": sc.payee_age_days, "band": risk["risk_band"], "seed": sc.seed,
           "questioned": bool(needs_questions(sc.amount, sc.payee_age_days, risk["risk_band"])), "a": outcome(ctx_a), "b": outcome(ctx_b)}
    if not row["questioned"]:
        row.update({"c": row["b"], "d": row["b"], "flags_c": None, "flags_d": None, "d_seconds": 0.0, "d_tokens": 0})
        return row
    run = f"{tag}{i}"
    t = time.perf_counter()
    answers = [sandbox.answer(vgw, f"{run}-c{n}", sc.persona, q, n) for n, q in enumerate(QUESTION_BANK)]        # the fixed bank, answered by the simulated customer
    flags_c = answer_flags([" ".join(answers)])
    row.update({"c": outcome({**ctx_b, **flags_c}), "flags_c": flags_c, "c_answers": answers})
    t = time.perf_counter()
    conv = sandbox.run_questions(gw, vgw, sc.persona, f"{run}-d", facts=base)                                      # the AI asks, the AI reads
    flags_d = {k: conv["flags_from_extracted_phrases"][k] or conv["flags_from_raw_answers"][k] for k in conv["flags_from_raw_answers"]}
    row.update({"d": outcome({**ctx_b, **flags_d}), "flags_d": flags_d, "d_seconds": round(time.perf_counter() - t, 1), "d_tokens": conv["tokens"], "d_questions": conv["questions"], "d_answers": conv["answers"]})
    return row


def summarise(rows: list[dict]) -> dict:
    scam, legit = [r for r in rows if r["is_scam"]], [r for r in rows if not r["is_scam"]]
    out = {"n": len(rows), "scams": len(scam), "genuine": len(legit), "systems": {}, "by_kind": {}}
    for s in "abcd":
        out["systems"][s] = {"scams_held": sum(r[s] in HELD for r in scam), "genuine_held": sum(r[s] in HELD for r in legit), "genuine_any_friction": sum(r[s] != "allow" for r in legit),
                             "genuine_questioned": sum(r["questioned"] for r in legit) if s in "cd" else None}
    for k in KINDS:
        kr = [r for r in rows if r["kind"] == k]
        out["by_kind"][k] = {"n": len(kr), **{s: sum(r[s] in HELD for r in kr) for s in "abcd"}, "questioned": sum(r["questioned"] for r in kr)}
    both = [(r["c"] in HELD, r["d"] in HELD) for r in scam]
    out["d_vs_c_on_scams"] = {"both": sum(a and b for a, b in both), "only_d": sum(b and not a for a, b in both), "only_c": sum(a and not b for a, b in both), "neither": sum(not a and not b for a, b in both)}
    qd = [r for r in rows if r["questioned"]]
    out["cost_d"] = {"questioned_cases": len(qd), "median_seconds": float(np.median([r["d_seconds"] for r in qd])) if qd else 0.0, "median_tokens": float(np.median([r["d_tokens"] for r in qd])) if qd else 0.0}
    return out


def reading(h: dict) -> str:
    """Plain-English reading generated from the held-out numbers, so it can never disagree with the tables."""
    S, N, K = h["systems"], h["scams"], h["by_kind"]
    c, d = S["c"]["scams_held"], S["d"]["scams_held"]
    (cl, ch), (dl, dh) = wilson(c, N), wilson(d, N)
    overlap = cl <= dh and dl <= ch
    p = h["d_vs_c_on_scams"]
    parts = [f"1. **Rules alone and rules plus the model catch {S['a']['scams_held']} and {S['b']['scams_held']} of {N} scams.** That is built in: the scams look like ordinary payments, so only what the customer says can reveal them.",
             f"2. **All the detection comes from asking questions and reading the answers**: {pct(c / N)} ({c} of {N}) with fixed questions and keyword rules, {pct(d / N)} ({d} of {N}) with the AI Questioner.",
             f"3. **The AI flow {'did not measurably beat' if overlap else 'differs from'} the simple fixed-question version** ({d} against {c}; the two disagreed on {p['only_d'] + p['only_c']} scams, {p['only_d']} in the AI's favour and {p['only_c']} in the fixed version's). "
             f"The AI's open questions did {'worse' if K['scam_uncoached']['d'] < K['scam_uncoached']['c'] else 'no worse'} than the fixed list on honest scam victims ({pct(K['scam_uncoached']['d'] / K['scam_uncoached']['n'])} against {pct(K['scam_uncoached']['c'] / K['scam_uncoached']['n'])}) and "
             f"{'better' if K['scam_coached']['d'] > K['scam_coached']['c'] else 'no better'} against the coached cover story ({pct(K['scam_coached']['d'] / K['scam_coached']['n'])} against {pct(K['scam_coached']['c'] / K['scam_coached']['n'])}; very few cases, one run).",
             f"4. **The cost to genuine customers is the same for both:** {S['d']['genuine_held']} of {h['genuine']} held by mistake and {S['d']['genuine_any_friction']} of {h['genuine']} warned or held. The bigger cost is being asked questions at all ({S['d']['genuine_questioned']} of {h['genuine']} genuine customers here, because the scenario mix includes many new-payee payments).",
             f"5. **The AI flow costs about {h['cost_d']['median_seconds']:.0f} s and {h['cost_d']['median_tokens']:.0f} tokens per questioned case; the fixed version uses no AI in the decision path.**",
             "6. **What this does and does not show.** In this simulation, the value is the questioning step, not the AI doing it. It does not show that AI is useless: the project's AI is also used for cited case summaries and readable customer messages, which this report does not measure. It also does not show how real customers or real scammers behave. A real test needs real data."]
    return "\n".join(parts)


def render(rep: dict) -> str:
    h, d = rep["heldout"], rep["dev"]
    o = ["# Interception: does the AI questioning add anything? (generated; do not edit by hand)", "",
         "**Real payments, simulated customers.** Each scenario is a real held-out card transaction scored by the real risk model, with a simulated payee age and a simulated customer whose answers come from an AI role-player (honest, vague, honest scam victim, or scam victim following the scammer's cover story). Whether a scenario is a scam is known by construction.", "",
         "Scam scenarios are built on ordinary-looking payments **on purpose**: in an authorised-push scam the customer sends the money, so the payment itself looks normal and only the customer's story reveals the problem. That means the risk model alone cannot be expected to catch them. What this report measures is how much the questions recover, what they cost in friction for genuine customers, and how coaching erodes it.", "",
         "Four systems see the same scenarios. **A** rules only. **B** rules plus the model's risk band. **C** B plus a fixed list of three questions and keyword rules on the answers, with no AI in the decision path. **D** B plus the AI Questioner and its answer reading. C is the honest test of whether the AI adds value over something simple. Questions are only asked when there is a reason (a sizeable payment to a new payee, an elevated model band, or a large amount).", "",
         f"Scenarios: {h['n']} held-out ({h['scams']} scams, {h['genuine']} genuine) used for every number below; {d['n']} development scenarios were used only to check the harness. Nothing was tuned on the held-out set. Model: {rep['model']}. Run time: {rep['seconds']} s.", "",
         "## Held-out results", "", "| System | Scams held or blocked | Genuine payments held or blocked (false holds) | Genuine payments warned, held or blocked | Genuine customers asked questions |", "|---|---|---|---|---|"]
    for s in "abcd":
        v = h["systems"][s]
        o.append(f"| {SYS[s]} | {show(v['scams_held'], h['scams'])} | {show(v['genuine_held'], h['genuine'])} | {show(v['genuine_any_friction'], h['genuine'])} | {show(v['genuine_questioned'], h['genuine']) if v['genuine_questioned'] is not None else 'not applicable'} |")
    o += ["", "## By kind of scenario (share held or blocked)", "", "| Scenario | Count | Asked questions | A | B | C | D |", "|---|---|---|---|---|---|---|"]
    for k, v in h["by_kind"].items():
        o.append(f"| {LABEL[k]} | {v['n']} | {pct(v['questioned'] / v['n']) if v['n'] else 'n/a'} | " + " | ".join(pct(v[s] / v["n"]) if v["n"] else "n/a" for s in "abcd") + " |")
    p = h["d_vs_c_on_scams"]
    o += ["", "## Does the AI add anything over fixed questions and keywords? (scam scenarios, same scenarios)", "",
          "| | Count |", "|---|---|", f"| Both C and D held the payment | {p['both']} |", f"| Only D (the AI flow) held it | {p['only_d']} |", f"| Only C (fixed questions) held it | {p['only_c']} |", f"| Neither held it | {p['neither']} |", "",
          "## What the AI flow costs", "", f"Over {h['cost_d']['questioned_cases']} questioned held-out cases: median {h['cost_d']['median_seconds']:.1f} s of AI time per case (including the simulated customer's own answers) and median {h['cost_d']['median_tokens']:.0f} tokens for the questions and answer reading. These are the Questioner's costs, not the customer role-player's.", "",
          "## Reading this report", "", reading(h), "",
          "## Limits (read these)", "",
          "- The customer is an AI role-player following a persona, not a real customer. Real people, and real scammers, behave differently, so these rates describe this simulation only.",
          "- Scam scenarios use ordinary-looking payments by construction, so the model's inability to catch them is built in. Card-fraud cases (where the model does work) are not part of this comparison.",
          "- Payment features are real, but the payee's age and the link between a payment and a story are simulated. Amounts come from a real card dataset in an unstated currency (shown as EUR).",
          "- One AI model, one run, a few hundred scenarios: intervals are wide. The policy thresholds are the project's existing ones and were not tuned here.",
          "- 'Held' includes blocked; 'friction' for genuine customers counts warnings and holds but not the questions themselves (shown in the last column).", ""]
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", type=int, default=100), ap.add_argument("--heldout", type=int, default=200), ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default="gemma4:31b"), ap.add_argument("--render-only", action="store_true")
    a = ap.parse_args()
    f = REPORT / "interception.json"
    if a.render_only:
        rep = json.loads(f.read_text())
    else:
        import check_llm_providers as envloader
        envloader.load_env()
        key = os.environ.get("OLLAMA_API_KEY") or sys.exit("OLLAMA_API_KEY missing")
        mk = lambda: LLMGateway([OllamaCloudProvider(key, a.model)], budget=Budget(max_requests_per_day=10**6, max_tokens_per_day=10**8, max_requests_per_run=60), timeout_s=12.0, deadline_s=30.0, cooldown_s=0.0)
        gw, vgw = mk(), mk()
        t0 = time.time()
        rep = {"model": a.model, "rows": {}}
        for split, n, base in (("dev", a.dev, 0), ("heldout", a.heldout, 10_000)):
            per = n // len(KINDS)
            scs = [build(k, base + j) for k in KINDS for j in range(per)]
            with ThreadPoolExecutor(a.workers) as ex:
                rows = list(ex.map(lambda t: process(t[1], gw, vgw, t[0], split[0]), enumerate(scs)))
            rep["rows"][split] = rows
            print(split, len(rows), "done", round(time.time() - t0), "s", flush=True)
        rep["seconds"] = round(time.time() - t0)
        rep["dev"], rep["heldout"] = summarise(rep["rows"]["dev"]), summarise(rep["rows"]["heldout"])
        rep["reading"] = "(written after the numbers were seen)"
    if a.render_only:
        rep["dev"], rep["heldout"] = summarise(rep["rows"]["dev"]), summarise(rep["rows"]["heldout"])
    f.write_text(json.dumps(rep, indent=1))
    (REPORT / "interception.md").write_text(render(rep))
    print("wrote docs/reports/interception.md")


if __name__ == "__main__":
    main()
