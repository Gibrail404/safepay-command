"""Turn the REAL Elliptic alerts (test period, own-features model) into investigation cases and post them to a running API.
Alerts that are directly linked form one case. The dataset's own labels are sent as hidden `truth`, revealed to the analyst only after a disposition.
Usage: python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key [--max 150] [--out cases.json]"""
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
for p in ("kernel", "ml", "graph"):
    sys.path.insert(0, str(ROOT / p))
from scipy.sparse.csgraph import connected_components
from safepay_graph.data import load_graph
from safepay_graph.experiment import fit_score
from safepay_graph.features import local_features
from safepay_ml.metrics import fpr_threshold


def build_cases(max_cases: int, seed: int) -> list[dict]:
    g = load_graph()
    split = g.split()
    score, _ = fit_score(local_features(g), g, split)
    thr = fpr_threshold(score[split["val"][g.y[split["val"]] == 0]], 0.01)
    test_nodes = np.where(g.time > 34)[0]
    alert = np.zeros(g.n, bool)
    alert[test_nodes[score[test_nodes] > thr]] = True
    ids = np.where(alert)[0]
    k, comp = connected_components(g.A[ids][:, ids], directed=False)
    sub_adj = g.A[ids][:, ids].tocoo()
    adj_alerts = np.asarray(g.A[ids][:, ids].sum(axis=1)).ravel()
    pairs_by_comp: dict[int, list[tuple[int, int]]] = {}
    for r_, c_ in zip(sub_adj.row, sub_adj.col):
        if r_ < c_:
            pairs_by_comp.setdefault(int(comp[r_]), []).append((int(r_), int(c_)))             # a real payment link between two alerts of the same case
    deg = np.asarray(g.A.sum(axis=1)).ravel()
    groups = [np.where(comp == c)[0] for c in range(k)]
    rng = np.random.default_rng(seed)
    multi = [m for m in groups if len(m) >= 2]
    single = [m for m in groups if len(m) == 1]
    multi = sorted(multi, key=lambda m: -len(m))[: int(0.65 * max_cases)]            # the largest linked groups first
    pick = multi + [single[i] for i in rng.permutation(len(single))[: max(0, max_cases - len(multi))]]
    out = []
    for m in pick[:max_cases]:
        nodes = ids[m]
        items = [{"ref": str(int(g.txid[n])), "score": round(float(score[n]), 4), "time_step": int(g.time[n]), "facts": {"neighbours": int(deg[n]), "linked_alerts": int(adj_alerts[m[j]])}} for j, n in enumerate(nodes)]
        truth = {it["ref"]: int(g.y[n]) for it, n in zip(items, nodes) if not np.isnan(g.y[n])}
        top = max(i["score"] for i in items)
        out.append({"external_id": f"elliptic-{int(g.txid[nodes[0]])}", "source": "elliptic-bitcoin", "provenance": "real", "priority": "high" if top >= 0.95 else "normal",
                    "title": (f"{len(items)} linked alerts at time step {items[0]['time_step']}" if len(items) > 1 else f"1 alert at time step {items[0]['time_step']}"), "items": items,
                    "facts": {"dataset": "Elliptic Bitcoin transaction graph (real, crypto)", "alert_threshold": round(float(thr), 4),
                              "links": [[str(int(g.txid[ids[a_]])), str(int(g.txid[ids[b_]]))] for a_, b_ in pairs_by_comp.get(int(comp[m[0]]), [])][:300]}, "truth": truth})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"), ap.add_argument("--key"), ap.add_argument("--max", type=int, default=150), ap.add_argument("--seed", type=int, default=7), ap.add_argument("--out")
    a = ap.parse_args()
    cases = build_cases(a.max, a.seed)
    print(len(cases), "cases;", sum(len(c["items"]) for c in cases), "alerts;", sum(len(c["items"]) > 1 for c in cases), "multi-alert cases")
    if a.out:
        Path(a.out).write_text(json.dumps(cases))
    if a.url:
        import httpx
        for i in range(0, len(cases), 50):
            r = httpx.post(a.url.rstrip("/") + "/v1/cases/import", json={"cases": cases[i:i + 50]}, headers={"X-API-Key": a.key}, timeout=60)
            r.raise_for_status()
            print(r.json())
