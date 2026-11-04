"""Measured evaluation of the matcher. Nothing here is tuned on the test queries: thresholds are chosen on validation negatives only."""
from __future__ import annotations
import math, random
import numpy as np
from .data import alias_rows, compose_negative_names, load_aliases, load_sdn, primary_rows
from .matcher import NameIndex
from .normalise import clean

VOWELS = "aeiou"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def perturb(name: str, kind: str, rng: random.Random) -> str | None:
    t = name.split()
    if kind == "typo":                                              # one letter swapped, dropped or replaced
        i = rng.randrange(len(name))
        op = rng.choice(["swap", "drop", "sub"])
        if op == "swap" and i + 1 < len(name):
            return name[:i] + name[i + 1] + name[i] + name[i + 2:]
        if op == "drop":
            return name[:i] + name[i + 1:]
        return name[:i] + rng.choice("abcdefghijklmnopqrstuvwxyz") + name[i + 1:]
    if kind == "reorder":
        return " ".join(reversed(t)) if len(t) > 1 else None
    if kind == "drop_token":
        return " ".join(t[:-1]) if len(t) >= 3 else None
    if kind == "vowel_variant":                                     # a vowel replaced, like Mohammed to Muhammed
        pos = [i for i, c in enumerate(name.lower()) if c in VOWELS]
        if not pos:
            return None
        i = rng.choice(pos)
        return name[:i] + rng.choice([v for v in VOWELS if v != name[i].lower()]) + name[i + 1:]
    if kind == "spacing":                                           # "AL ZOMOR" written as "ALZOMOR"
        return "".join(t[:2]) + (" " + " ".join(t[2:]) if len(t) > 2 else "") if len(t) > 1 else None
    raise ValueError(kind)


PERTURBATIONS = ["typo", "reorder", "drop_token", "vowel_variant", "spacing"]


def best_scores(index: NameIndex, queries: list[str]) -> list[tuple[str | None, float]]:
    out = []
    for q in queries:
        h = index.search(q, top=1)
        out.append((h[0].ent_num, h[0].score) if h else (None, 0.0))
    return out


def rank_of(index: NameIndex, query: str, ent: str, top: int = 10) -> tuple[int | None, float]:
    hits = index.search(query, top=top)
    for r, h in enumerate(hits, 1):
        if h.ent_num == ent:
            return r, h.score
    return None, 0.0


def run(seed: int = 7, n_alias: int = 1500, n_alias_val: int = 800, n_perturb: int = 400, n_neg: int = 20000) -> dict:
    rng = random.Random(seed)
    sdn, aliases = load_sdn(), load_aliases()
    prim, alis = primary_rows(sdn), alias_rows(aliases)
    order = list(range(len(alis)))
    rng.shuffle(order)
    half = len(order) // 2
    known = [alis[i] for i in order[:half]]
    hidden = [alis[i] for i in order[half:] if clean(alis[i][1])]
    rng.shuffle(hidden)
    alias_val, alias_test = hidden[:n_alias_val], hidden[n_alias_val: n_alias_val + n_alias]

    report: dict = {"seed": seed, "list_entries": len(sdn), "alias_rows": len(alis), "held_out_alias_queries": len(alias_test), "validation_alias_queries": len(alias_val)}
    negs = compose_negative_names(n_neg, seed)
    val_neg, test_neg = negs[: n_neg // 2], negs[n_neg // 2:]
    report["negatives"] = {"validation": len(val_neg), "test": len(test_neg)}

    def thresholds_for(index: NameIndex) -> dict[str, float]:
        """Each matcher gets its own thresholds from its own validation negatives, so that variants are compared at the same false alert rate."""
        sc = np.array([x for _, x in best_scores(index, val_neg)])
        return {"fpr_1pct": math.floor(float(np.quantile(sc, 0.99))) + 1.0, "fpr_0.1pct": math.floor(float(np.quantile(sc, 0.999))) + 1.0}

    def found_rates(index, queries, th):
        ranks = [rank_of(index, q, e) for e, q, _ in queries]
        row = {"recall_at_1": sum(1 for r, _ in ranks if r == 1) / len(ranks), "recall_at_5": sum(1 for r, _ in ranks if r and r <= 5) / len(ranks),
               "recall_at_10": sum(1 for r, _ in ranks if r and r <= 10) / len(ranks), "thresholds_used": th}
        for tname, t in th.items():
            k = sum(1 for r, x in ranks if r == 1 and x >= t)
            row[f"found_as_top_hit_at_{tname}"] = {"rate": k / len(ranks), "ci95": list(wilson(k, len(ranks)))}
        return row

    # A. real held-out aliases for three variants. Selection rule fixed in advance: the variant with the highest top-hit rate at alert level A on the
    # validation aliases (both list scenarios averaged) is shipped. The test aliases are never used to choose.
    variants = {"strong_folding": 2, "mild_folding": 1, "no_folding": 0}
    report["held_out_aliases"], val_score = {}, {v: 0.0 for v in variants}
    for scenario, rows in (("primary_plus_known_aliases", prim + known), ("primary_names_only", prim)):
        report["held_out_aliases"][scenario] = {}
        for vname, level in variants.items():
            idx = NameIndex(rows, fold_level=level)
            th = thresholds_for(idx)
            val_score[vname] += found_rates(idx, alias_val, th)["found_as_top_hit_at_fpr_1pct"]["rate"] / 2
            report["held_out_aliases"][scenario][vname] = found_rates(idx, alias_test, th)
    chosen = max(val_score, key=val_score.get)
    level = variants[chosen]
    report["fold_choice"] = {"rule": "highest validation top-hit rate at alert level A", "validation_scores": {k: round(v, 4) for k, v in val_score.items()}, "chosen": chosen}
    exact = {clean(n): e for e, n, _ in prim + known}
    report["held_out_aliases"]["exact_match_baseline_primary_plus_known_aliases"] = {"recall_at_1": sum(1 for e, q, _ in alias_test if exact.get(clean(q)) == e) / len(alias_test)}

    # B. headline matcher: full list, chosen variant
    full = NameIndex(prim + alis, fold_level=level)
    thresholds = thresholds_for(full)
    test_scores = np.array([x for _, x in best_scores(full, test_neg)])
    report["thresholds_from_validation_negatives"] = thresholds
    report["negatives"]["test_score_quantiles"] = {str(q): float(np.quantile(test_scores, q)) for q in (0.5, 0.9, 0.99, 0.999)}
    report["false_alert_rate_on_test_negatives"] = {}
    for t in [80.0, 85.0, 90.0, 95.0] + sorted(set(thresholds.values())):
        k = int((test_scores >= t).sum())
        report["false_alert_rate_on_test_negatives"][str(t)] = {"alerts": k, "rate": k / len(test_scores), "ci95": list(wilson(k, len(test_scores)))}

    # C. perturbed real primary names against the full list
    pool = [r for r in prim if len(clean(r[1])) >= 4]
    report["perturbed_primary_names"] = {}
    for kind in PERTURBATIONS:
        qs = []
        for e, n, _ in rng.sample(pool, len(pool)):
            q = perturb(n, kind, rng)
            if q and clean(q) != clean(n):
                qs.append((e, q))
            if len(qs) >= n_perturb:
                break
        ranks = [rank_of(full, q, e) for e, q in qs]
        row = {"queries": len(qs), "recall_at_1": sum(1 for r, _ in ranks if r == 1) / len(qs), "recall_at_5": sum(1 for r, _ in ranks if r and r <= 5) / len(qs)}
        for tname, t in thresholds.items():
            k = sum(1 for r, x in ranks if r and x >= t)
            row[f"found_at_{tname}"] = {"rate": k / len(qs), "ci95": list(wilson(k, len(qs)))}
        report["perturbed_primary_names"][kind] = row
    return report
