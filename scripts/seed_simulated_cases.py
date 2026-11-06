"""Seeds a demo server with SIMULATED alert cases, so a public demo has something to open without putting any real dataset on it.
Every case is labelled `simulated`; the scores, links and labels are drawn from a seeded generator and describe nothing real. Idempotent: a case is identified by its external id.
Usage: python scripts/seed_simulated_cases.py --url https://<api> --key <admin key> [--seed 7]"""
import argparse, json, sys
import httpx
import numpy as np

KINDS = [   # (name, how many, alerts per case, score range, share of alerts that are really illicit, priority)
    ("ring of linked alerts", 5, (3, 6), (0.88, 0.99), 0.85, "high"),
    ("linked pair", 4, (2, 2), (0.70, 0.93), 0.55, "normal"),
    ("busy but legitimate cluster (looks like a ring, is not)", 3, (3, 5), (0.80, 0.94), 0.0, "normal"),
    ("single weak alert", 4, (1, 1), (0.52, 0.72), 0.1, "normal"),
]


def build(seed: int) -> list[dict]:
    rng, out = np.random.default_rng(seed), []
    for name, n, (lo, hi), (s_lo, s_hi), illicit_share, priority in KINDS:
        for k in range(n):
            size = int(rng.integers(lo, hi + 1))
            cid = f"sim-{name.split()[0]}-{seed}-{k}"
            refs = [f"{cid}-a{j}" for j in range(size)]
            step = int(rng.integers(30, 49))
            items = [{"ref": r, "score": round(float(rng.uniform(s_lo, s_hi)), 4), "time_step": step,
                      "facts": {"neighbours": int(rng.integers(1, 9)), "linked_alerts": size - 1}} for r in refs]
            truth = {r: int(rng.random() < illicit_share) for r in refs}
            if illicit_share > 0.5 and not any(truth.values()):
                truth[refs[0]] = 1                                      # a "ring" with no illicit alert at all would be a different kind of case
            links = [[refs[i], refs[i + 1]] for i in range(size - 1)] + ([[refs[0], refs[-1]]] if size > 3 else [])
            out.append({"external_id": cid, "source": "simulated-demo", "provenance": "simulated", "priority": priority,
                        "title": f"Simulated: {name}" + (f" ({size} alerts)" if size > 1 else ""),
                        "items": items, "facts": {"dataset": "Simulated demo data (not real)", "scenario": name, "links": links}, "truth": truth})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--key", required=True), ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    cases = build(a.seed)
    r = httpx.post(a.url.rstrip("/") + "/v1/cases/import", headers={"X-API-Key": a.key}, json={"cases": cases}, timeout=60)
    print(f"HTTP {r.status_code}: {len(cases)} simulated cases sent")
    if r.status_code != 200:
        print(r.text[:300]); return 1
    print(json.dumps(r.json())[:300]); return 0


if __name__ == "__main__":
    sys.exit(main())
