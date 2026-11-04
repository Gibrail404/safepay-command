"""Measures how well the redactor removes people's names and street addresses before text reaches a model. Writes docs/reports/redaction.{json,md}.
Names: real Census first names and surnames paired at random (US style), and real OFAC individuals (many non-US). Addresses: street addresses built from real Census surnames (synthetic).
Over-redaction: the real SMS Spam Collection, to see how often the layer changes ordinary messages. Usage: python scripts/eval_redaction.py"""
import json, math, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "screening"):
    sys.path.insert(0, str(ROOT / p))
from safepay.llm import ner
from safepay.llm.safety import redact
from safepay_screening.data import compose_negative_names, load_sdn

NAME_TEMPLATES = ["My landlord {x} asked me to send the rent today.", "Please pay {x} for the invoice I mentioned.", "I am transferring money to {x}, we agreed the price yesterday.",
                  "A man called {x} phoned me and said it was urgent.", "This is for my cousin {x}.", "{x} is my supplier and I have paid him before.", "I met {x} online and he asked me to pay him.", "Payee: {x}, for the repair work."]
ADDR_TEMPLATES = ["Deliver to {x} please.", "The payee lives at {x}.", "Send the cheque to {x} by Friday.", "My new address is {x}, update it please."]
SUFFIX = ["Street", "Road", "Avenue", "Lane", "Drive", "Court"]


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


def tokens(entity: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", entity)]


def outcome(entity: str, out: str) -> str:
    toks = tokens(entity)
    left = [t for t in toks if t in out.lower()]
    return "removed" if not left else "partly" if len(left) < len(toks) else "kept"


def sdn_names(n: int, rng) -> list[str]:
    df = load_sdn()
    names = []
    for raw in df[df["sdn_type"] == "individual"]["name"]:
        if "," in raw:
            last, first = [x.strip() for x in raw.split(",", 1)]
            full = f"{first} {last}".title()
        else:
            full = raw.title()
        if re.fullmatch(r"[A-Za-z .'\-]+", full) and 2 <= len(full.split()) <= 4:
            names.append(full)
    return [names[i] for i in rng.permutation(len(names))[:n]]


def run_set(entities, templates, rng, use_ner):
    res = {"removed": 0, "partly": 0, "kept": 0}
    for i, e in enumerate(entities):
        text = templates[i % len(templates)].format(x=e)
        res[outcome(e, redact(text, use_ner=use_ner).text)] += 1
    n = len(entities)
    return {"fully_removed": rate(res["removed"], n), "partly_removed": rate(res["partly"], n), "left_in_place": rate(res["kept"], n)}


def main():
    rng = np.random.default_rng(5)
    us = compose_negative_names(300, 11)
    non_us = sdn_names(300, rng)
    surnames = [n.split()[-1] for n in compose_negative_names(200, 13)]
    addrs = [f"{int(rng.integers(1, 400))} {s} {SUFFIX[i % len(SUFFIX)]}" for i, s in enumerate(surnames)]
    rep = {"ner_available": ner.available(), "sets": {}}
    for label, ents, tpl in (("US-style names (real Census parts)", us, NAME_TEMPLATES), ("Real OFAC individuals (many non-US names)", non_us, NAME_TEMPLATES), ("Street addresses (synthetic)", addrs, ADDR_TEMPLATES)):
        rep["sets"][label] = {"patterns_only": run_set(ents, tpl, rng, False), "with_name_model": run_set(ents, tpl, rng, True)}
    sms = pd.read_parquet(ROOT / "data" / "processed" / "sms_spam.parquet")
    changed, samples, ms = 0, [], []
    for t in sms["text"]:
        t0 = time.perf_counter()
        r = redact(t, use_ner=True)
        ms.append((time.perf_counter() - t0) * 1000)
        base = redact(t, use_ner=False)
        extra = [v for k, v in r.mapping.items() if k.startswith(("[NAME", "[ADDRESS")) and v not in base.mapping.values()]
        if extra:
            changed += 1
            if len(samples) < 40:
                samples.append(extra[0])
    rep["real_messages"] = {"messages": int(len(sms)), "changed_by_name_layer": rate(changed, len(sms)), "sample_of_redacted_strings": [samples[i] for i in rng.permutation(len(samples))[:15]],
                            "latency_ms": {"p50": float(np.percentile(ms, 50)), "p95": float(np.percentile(ms, 95))}}
    d = ROOT / "docs" / "reports"
    (d / "redaction.json").write_text(json.dumps(rep, indent=2))
    o = ["# Name and address redaction (generated; do not edit by hand)", "",
         "Before customer text reaches an AI model, the redactor replaces personal details with tokens. Patterns already handle emails, card numbers, phone numbers, IBANs and ID numbers. This report measures the added layer for **people's names** (a small spaCy language model) and **street addresses** (patterns). Cities and countries are deliberately left readable.", "",
         f"Name model available when this ran: {'yes' if rep['ner_available'] else 'NO (the with-model columns equal the patterns-only columns)'}.", "",
         "## Did the personal detail disappear from the text?", "", "| What was inserted into a sentence | Patterns only: fully removed | With the name model: fully removed | With the name model: partly removed | With the name model: left in place |", "|---|---|---|---|---|"]
    for k, v in rep["sets"].items():
        o.append(f"| {k} | {show(v['patterns_only']['fully_removed'])} | {show(v['with_name_model']['fully_removed'])} | {show(v['with_name_model']['partly_removed'])} | {show(v['with_name_model']['left_in_place'])} |")
    m = rep["real_messages"]
    o += ["", "'Partly removed' means some words of a multi-word name were redacted and others stayed visible.", "", "## Does it change ordinary text it should not?", "",
          f"On the real SMS Spam Collection ({m['messages']:,} messages), the name layer changed {show(m['changed_by_name_layer'])} of messages. Many of those contain a real first name, which is correct to redact; this number is an upper bound on wrong changes, not an error rate. A random sample of what it redacted: " + "; ".join(f"`{s}`" for s in m["sample_of_redacted_strings"]) + ".", "",
          f"Time per message: median {m['latency_ms']['p50']:.1f} ms, 95th percentile {m['latency_ms']['p95']:.1f} ms.", "",
          "## Limits (read these)", "",
          "- A statistical name model misses unusual names and can redact words that are not names; the numbers above are for these test sets only.",
          "- US-style test names are real parts paired at random; addresses are synthetic and follow one common format. Addresses in other formats, other languages and other scripts are not tested.",
          "- Names in non-Latin scripts are not tested at all.",
          "- Redacted tokens appear in the model's input, so a claim copied from the redacted text will not match the customer's original words and is rejected by the existing word-for-word check; the system then falls back to a safe default.", ""]
    (d / "redaction.md").write_text("\n".join(o))
    print("done", rep["ner_available"])


if __name__ == "__main__":
    main()
