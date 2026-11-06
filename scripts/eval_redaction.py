"""Measures how well the redactor removes people's names and street addresses before text reaches a model. Writes docs/reports/redaction.{json,md}.
Names: real Census first names and surnames paired at random (US style), and real OFAC individuals (many non-US). Addresses: street addresses built from real Census surnames (synthetic).
Over-redaction: the real SMS Spam Collection, to see how often the layer changes ordinary messages. Usage: python scripts/eval_redaction.py"""
import json, math, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "screening", "scripts"):
    sys.path.insert(0, str(ROOT / p))
from safepay.llm import ner
from build_name_gazetteer import parity
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


def run_set(entities, templates, use_ner):
    res = {"removed": 0, "partly": 0, "kept": 0}
    for i, e in enumerate(entities):
        text = templates[i % len(templates)].format(x=e)
        res[outcome(e, redact(text, use_ner=use_ner).text)] += 1
    n = len(entities)
    return {"fully_removed": rate(res["removed"], n), "partly_removed": rate(res["partly"], n), "left_in_place": rate(res["kept"], n)}


def unseen(names, held_out_parity=1, want=300):
    """Names whose every word is in the half of the word list that the evaluation list does NOT contain, so the list cannot have 'seen' them."""
    out = [n for n in names if all(parity(t) == held_out_parity for t in tokens(n) if len(t) >= 3)]
    return out[:want]


def main():
    rng = np.random.default_rng(5)
    full = set(Path(ner.GAZETTEER_PATH).read_text().split())
    half = {t for t in full if parity(t) == 0}                       # the evaluation list: only half of the words
    us = unseen(compose_negative_names(8000, 11))
    non_us = unseen(sdn_names(100000, rng))
    surnames = [n.split()[-1] for n in compose_negative_names(200, 13)]
    addrs = [f"{int(rng.integers(1, 400))} {s} {SUFFIX[i % len(SUFFIX)]}" for i, s in enumerate(surnames)]
    variants = {"patterns_only": (False, set()), "model_only": (True, set()), "model_plus_list_unseen": (True, half), "model_plus_full_list": (True, full)}
    rep = {"ner_available": ner.available(), "list_tokens": len(full), "evaluation_list_tokens": len(half), "sets": {}}
    for label, ents, tpl in ((f"US-style names, words the list has not seen ({len(us)})", us, NAME_TEMPLATES), (f"Real OFAC individuals, words the list has not seen ({len(non_us)})", non_us, NAME_TEMPLATES), ("Street addresses (synthetic)", addrs, ADDR_TEMPLATES)):
        rep["sets"][label] = {}
        for vname, (use, tokens_) in variants.items():
            ner.set_gazetteer(tokens_)
            rep["sets"][label][vname] = run_set(ents, tpl, use)
    sms = pd.read_parquet(ROOT / "data" / "processed" / "sms_spam.parquet")
    changed_model = changed_extra = 0
    extra_samples, ms = [], []
    for t in sms["text"]:
        ner.set_gazetteer(set())
        m = redact(t, use_ner=True)
        ner.set_gazetteer(full)
        t0 = time.perf_counter()
        f = redact(t, use_ner=True)
        ms.append((time.perf_counter() - t0) * 1000)
        base = redact(t, use_ner=False)
        names = lambda r: {v for k, v in r.mapping.items() if k.startswith("[NAME") and v not in base.mapping.values()}
        nm, nf = names(m), names(f)
        changed_model += bool(nm)
        extra = nf - nm
        if extra:
            changed_extra += 1
            if len(extra_samples) < 60:
                extra_samples.append(sorted(extra)[0])
    ner.set_gazetteer(None)
    rep["real_messages"] = {"messages": int(len(sms)), "changed_by_model": rate(changed_model, len(sms)), "additionally_changed_by_list": rate(changed_extra, len(sms)),
                            "sample_added_by_list": [extra_samples[i] for i in rng.permutation(len(extra_samples))[:20]], "latency_ms": {"p50": float(np.percentile(ms, 50)), "p95": float(np.percentile(ms, 95))}}
    d = ROOT / "docs" / "reports"
    (d / "redaction.json").write_text(json.dumps(rep, indent=2))
    o = ["# Name and address redaction (generated; do not edit by hand)", "",
         "Before customer text reaches an AI model, the redactor replaces personal details with tokens. Patterns handle emails, card numbers, phone numbers, IBANs, ID numbers and street addresses. For **people's names** there are two layers: a small spaCy language model, and a **name list** (about "
         f"{rep['list_tokens']:,} name words from the real US Census and OFAC lists, with ordinary English words removed). The list redacts a run of two or more known name words, or one name word right after a cue such as 'landlord', 'pay' or 'named', or a name word touching a name the model already found. Cities and countries are deliberately left readable.", "",
         f"**Honest evaluation.** The list is built from real name lists, so testing it on those same names would be circular. The test names below are made only of words that the *evaluation list* (a random half of the real list, {rep['evaluation_list_tokens']:,} words) does not contain, so they stand in for names the list has never seen. The last column uses the full shipped list on the same names and is an optimistic number, not an estimate.", "",
         f"Name model available when this ran: {'yes' if rep['ner_available'] else 'NO (the with-model columns equal the patterns-only columns)'}.", "",
         "## Did the personal detail disappear from the text? (fully removed)", "", "| What was inserted into a sentence | Patterns only | Language model only | Model plus the list (unseen words) | Model plus the full list (optimistic) |", "|---|---|---|---|---|"]
    for k, v in rep["sets"].items():
        o.append(f"| {k} | {show(v['patterns_only']['fully_removed'])} | {show(v['model_only']['fully_removed'])} | {show(v['model_plus_list_unseen']['fully_removed'])} | {show(v['model_plus_full_list']['fully_removed'])} |")
    o += ["", "Left in place or only partly removed, for the same rows:", "", "| What was inserted into a sentence | Model only: partly / left in place | Model plus the list (unseen words): partly / left in place |", "|---|---|---|"]
    for k, v in rep["sets"].items():
        o.append(f"| {k} | {pct(v['model_only']['partly_removed']['rate'])} / {pct(v['model_only']['left_in_place']['rate'])} | {pct(v['model_plus_list_unseen']['partly_removed']['rate'])} / {pct(v['model_plus_list_unseen']['left_in_place']['rate'])} |")
    m = rep["real_messages"]
    o += ["", "'Partly removed' means some words of a multi-word name were redacted and others stayed visible.", "", "## Does it change ordinary text it should not?", "",
          f"On the real SMS Spam Collection ({m['messages']:,} messages) the language model alone changed {show(m['changed_by_model'])} of messages, and the list changed **{show(m['additionally_changed_by_list'])} more** (with the full list). Many contain a real first name, which is correct to redact, so these numbers are upper bounds on wrong changes, not error rates. What the list added, a random sample: " + "; ".join(f"`{x}`" for x in m["sample_added_by_list"]) + ".", "",
          f"Time per message with both layers: median {m['latency_ms']['p50']:.1f} ms, 95th percentile {m['latency_ms']['p95']:.1f} ms.", "",
          "## Limits (read these)", "",
          "- Names built from random pairs of real words are a proxy for real customers' names. Real names have more variety, and nicknames, misspellings and lower-case typing are not tested (the list only matches capitalised words).",
          "- Common words that are also names (for example Mark, Rose, Baker) are only redacted when they follow a cue word, touch a name the model found, or sit in a run of two name words.",
          "- Addresses are synthetic and follow one common format; other formats and languages are not tested. Names in non-Latin scripts are not tested at all.",
          "- Redacted tokens appear in the model's input, so a claim copied from the redacted text will not match the customer's original words and is rejected by the existing word-for-word check; the system then falls back to a safe default.", ""]
    (d / "redaction.md").write_text("\n".join(o))
    print("done", rep["ner_available"])


if __name__ == "__main__":
    main()
