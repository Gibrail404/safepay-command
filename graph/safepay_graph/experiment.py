"""Does graph structure help find illicit transactions, and can alerts be grouped into cases? Real Elliptic data, temporal split, fixed protocol.
Protocol (fixed before looking at test): train on time steps 1-24, early-stop and choose the alert threshold on steps 25-34 (threshold = 1% false alert rate on licit validation nodes),
report only on steps 35-49. Both models use the same LightGBM settings; they differ only in their input features."""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
import lightgbm as lgb
from safepay_ml.metrics import average_precision, bootstrap_ci, fpr_threshold
from .data import Graph, load_graph
from .features import graph_features, local_features

PARAMS = dict(n_estimators=600, learning_rate=0.05, num_leaves=31, subsample=0.8, subsample_freq=1, colsample_bytree=0.5, min_child_samples=20, random_state=0, n_jobs=4, verbose=-1)


def fit_score(X: np.ndarray, g: Graph, split: dict) -> tuple[np.ndarray, int]:
    tr, va = split["train"], split["val"]
    pos = g.y[tr].sum()
    m = lgb.LGBMClassifier(**PARAMS, scale_pos_weight=float((len(tr) - pos) / pos))
    m.fit(X[tr], g.y[tr], eval_set=[(X[va], g.y[va])], eval_metric="average_precision", callbacks=[lgb.early_stopping(50, verbose=False)])
    return m.predict_proba(X)[:, 1], int(m.best_iteration_ or PARAMS["n_estimators"])


def neighbour_score_features(g: Graph, split: dict, base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two-stage idea: a first model scores every transaction from its own features; the second model also sees what the neighbours' scores look like.
    Training transactions get out-of-fold first-stage scores (4 blocks of time steps), so a transaction never sees a score from a model that was trained on it.
    No labels of other transactions are used as inputs. Returns (stage-2 features, first-stage scores used)."""
    tr = split["train"]
    steps = np.unique(g.time[tr])
    blocks = np.array_split(steps, 4)
    stage1 = np.zeros(g.n, dtype=np.float32)
    full, _ = fit_score(base, g, split)
    stage1[:] = full                                                  # unlabelled nodes and validation/test nodes: model trained on all training nodes
    for blk in blocks:
        hold = tr[np.isin(g.time[tr], blk)]
        keep = tr[~np.isin(g.time[tr], blk)]
        pos = g.y[keep].sum()
        m = lgb.LGBMClassifier(**{**PARAMS, "n_estimators": 300}, scale_pos_weight=float((len(keep) - pos) / pos)).fit(base[keep], g.y[keep])
        stage1[hold] = m.predict_proba(base[hold])[:, 1]
    from .features import row_normalise
    P = row_normalise(g.A)
    mean1 = np.asarray(P @ stage1).ravel()
    mean2 = np.asarray(P @ mean1).ravel()
    mx = np.asarray(g.A.multiply(stage1[None, :]).max(axis=1).todense()).ravel()
    return np.hstack([base, np.column_stack([stage1, mean1, mean2, mx]).astype(np.float32)]), stage1


def metrics_at(g: Graph, score: np.ndarray, idx: np.ndarray, thr: float) -> dict:
    y, s = g.y[idx], score[idx]
    pred = s > thr
    tp, fp, fn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
    return {"n": int(len(idx)), "illicit": int(y.sum()), "average_precision": average_precision(y, s), "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0, "alerts": tp + fp, "tp": tp, "fp": fp, "fn": fn}


def cases(g: Graph, score: np.ndarray, thr: float, nodes: np.ndarray) -> dict:
    """Group alerts into cases: alerts joined by an edge belong to the same case. Judged on the labelled alerts only."""
    alert = np.zeros(g.n, bool)
    alert[nodes[score[nodes] > thr]] = True
    ids = np.where(alert)[0]
    sub = g.A[ids][:, ids]
    k, comp = connected_components(sub, directed=False)
    labelled = ~np.isnan(g.y[ids])
    sizes = np.bincount(comp, minlength=k)
    rows = []
    for c in range(k):
        m = (comp == c) & labelled
        if m.sum():
            rows.append((int(sizes[c]), float(np.nanmean(g.y[ids][m])), int(m.sum())))
    arr = np.array(rows) if rows else np.zeros((0, 3))
    multi = arr[:, 0] >= 2 if len(arr) else np.array([], bool)
    illicit_alerts = int(np.nansum(g.y[ids][labelled]))
    return {"alerts": int(len(ids)), "cases": int(k), "alerts_per_case_mean": float(len(ids) / k) if k else 0.0, "cases_with_2_or_more_alerts": int(multi.sum()),
            "largest_case": int(sizes.max()) if k else 0, "pure_illicit_cases_share_of_labelled_cases": float((arr[:, 1] == 1).mean()) if len(arr) else 0.0,
            "pure_illicit_cases_with_2_or_more_alerts": int(((arr[:, 1] == 1) & multi).sum()) if len(arr) else 0, "mixed_cases": int(((arr[:, 1] > 0) & (arr[:, 1] < 1)).sum()) if len(arr) else 0,
            "illicit_alerts": illicit_alerts, "reduction_in_items_to_review": float(1 - k / len(ids)) if len(ids) else 0.0}


def run(seed: int = 0, boot: int = 500) -> dict:
    g = load_graph()
    split = g.split()
    out = {"nodes": g.n, "edges_undirected": int(g.A.nnz // 2), "labelled": int((~np.isnan(g.y)).sum()), "split_sizes": {k: int(len(v)) for k, v in split.items()}, "models": {}}
    scores = {}
    for name, feat in (("features_only", local_features), ("with_graph", graph_features), ("with_neighbour_scores", None)):
        X = feat(g) if feat else neighbour_score_features(g, split, local_features(g))[0]
        s, best = fit_score(X, g, split)
        scores[name] = s
        va_licit = split["val"][g.y[split["val"]] == 0]
        thr = fpr_threshold(s[va_licit], 0.01)
        te = split["test"]
        early, late = te[g.time[te] <= 42], te[g.time[te] > 42]
        out["models"][name] = {"n_features": int(X.shape[1]), "best_iteration": best, "threshold_from_validation": float(thr),
                               "test": metrics_at(g, s, te, thr), "test_steps_35_42": metrics_at(g, s, early, thr), "test_steps_43_49_after_market_shutdown": metrics_at(g, s, late, thr),
                               "average_precision_ci95": list(bootstrap_ci(average_precision, g.y[te], s[te], n=boot, seed=seed)), "cases": cases(g, s, thr, te)}
    te = split["test"]
    rng = np.random.default_rng(seed)
    diffs, diffs2 = [], []
    for _ in range(boot):
        b = rng.integers(0, len(te), len(te))
        yb = g.y[te][b]
        if yb.sum() == 0:
            continue
        diffs.append(average_precision(yb, scores["with_graph"][te][b]) - average_precision(yb, scores["features_only"][te][b]))
        diffs2.append(average_precision(yb, scores["with_neighbour_scores"][te][b]) - average_precision(yb, scores["features_only"][te][b]))
    out["paired_average_precision_gain_with_graph"] = {"mean": float(np.mean(diffs)), "ci95": [float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))]}
    out["paired_average_precision_gain_with_neighbour_scores"] = {"mean": float(np.mean(diffs2)), "ci95": [float(np.quantile(diffs2, 0.025)), float(np.quantile(diffs2, 0.975))]}
    out["illicit_base_rate_test"] = float(g.y[te].mean())
    return out
