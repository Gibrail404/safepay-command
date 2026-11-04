"""Analyst-feedback flywheel on the REAL Elliptic data with SIMULATED analysts. Each time step: the current model scores that step's labelled transactions, a simulated analyst
reviews a fixed budget of them (chosen by a strategy), their answers (correct with probability 1 - noise) join the training pool, and the model is retrained.
The question is how the way labels are collected changes what the model learns. Truth comes from the dataset's own labels; the analyst is simulated and labelled so."""
from __future__ import annotations
import numpy as np
import lightgbm as lgb
from safepay_ml.metrics import average_precision, fpr_threshold
from .data import Graph, load_graph, TRAIN_END, VAL_END
from .features import local_features

STRATEGIES = ("no_feedback", "review_top_scores", "review_near_threshold", "review_random", "half_top_half_random", "all_labels_oracle")
PARAMS = dict(n_estimators=250, learning_rate=0.06, num_leaves=31, subsample=0.8, subsample_freq=1, colsample_bytree=0.5, random_state=0, n_jobs=4, verbose=-1)


def train(X, idx, y) -> lgb.LGBMClassifier:
    pos = max(1.0, float(y.sum()))
    return lgb.LGBMClassifier(**PARAMS, scale_pos_weight=float((len(y) - pos) / pos)).fit(X[idx], y)


def choose(strategy: str, scores: np.ndarray, thr: float, budget: int, rng: np.random.Generator) -> np.ndarray:
    n = len(scores)
    b = min(budget, n)
    if strategy == "review_top_scores":
        return np.argsort(-scores)[:b]
    if strategy == "review_near_threshold":
        return np.argsort(np.abs(scores - thr))[:b]
    if strategy == "review_random":
        return rng.choice(n, b, replace=False)
    if strategy == "half_top_half_random":
        top = np.argsort(-scores)[: b // 2]
        rest = np.setdiff1d(np.arange(n), top)
        return np.concatenate([top, rng.choice(rest, b - len(top), replace=False)])
    raise ValueError(strategy)


def run_strategy(g: Graph, X: np.ndarray, strategy: str, budget: int, noise: float, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    lab = ~np.isnan(g.y)
    pool_idx = list(np.where(lab & (g.time <= TRAIN_END))[0])
    pool_y = list(g.y[pool_idx])
    val = np.where(lab & (g.time > TRAIN_END) & (g.time <= VAL_END))[0]
    model = train(X, np.array(pool_idx), np.array(pool_y))
    thr = fpr_threshold(model.predict_proba(X[val[g.y[val] == 0]])[:, 1], 0.01)
    preds, reviewed_illicit, reviewed_total, per_step = [], 0, 0, []
    for t in range(TRAIN_END + 1, int(g.time.max()) + 1):
        step = np.where(lab & (g.time == t))[0]
        if len(step) == 0:
            continue
        sc = model.predict_proba(X[step])[:, 1]
        if t > VAL_END:
            preds.append((t, step, sc))
        if strategy == "all_labels_oracle":
            new = np.arange(len(step))
            flip = np.zeros(len(step), bool)
        elif strategy == "no_feedback":
            continue
        else:
            new = choose(strategy, sc, thr, budget, rng)
            flip = rng.random(len(new)) < noise
        ys = g.y[step[new]].copy()
        ys[flip] = 1 - ys[flip]
        reviewed_total += len(new)
        reviewed_illicit += int(g.y[step[new]].sum())
        pool_idx += list(step[new])
        pool_y += list(ys)
        model = train(X, np.array(pool_idx), np.array(pool_y))
    idx = np.concatenate([p[1] for p in preds])
    s = np.concatenate([p[2] for p in preds])
    t_arr = np.concatenate([[p[0]] * len(p[1]) for p in preds])
    y = g.y[idx]
    ap = lambda m: float(average_precision(y[m], s[m])) if y[m].sum() > 0 else float("nan")
    p_at_100 = []
    for t, st, sc in preds:
        top = np.argsort(-sc)[:100]
        p_at_100.append(float(g.y[st[top]].mean()))
    return {"average_precision_steps_35_49": ap(np.ones(len(y), bool)), "average_precision_steps_35_42": ap(t_arr <= 42), "average_precision_steps_43_49": ap(t_arr >= 43),
            "illicit_share_in_top_100_alerts_per_step": float(np.mean(p_at_100)), "illicit_share_in_top_100_steps_43_49": float(np.mean([p for (t, _, _), p in zip(preds, p_at_100) if t >= 43])),
            "labels_collected": reviewed_total, "illicit_share_of_reviewed": reviewed_illicit / reviewed_total if reviewed_total else 0.0,
            "illicit_share_of_training_pool_end": float(np.mean(pool_y)), "training_pool_size_end": len(pool_y)}


def run(budget: int = 50, noises=(0.05, 0.20), seed: int = 0) -> dict:
    g = load_graph()
    X = local_features(g)
    out = {"budget_per_step": budget, "noises": list(noises), "results": {}, "feedback_steps": f"{TRAIN_END + 1} to {int(g.time.max())}", "evaluation_steps": f"{VAL_END + 1} to {int(g.time.max())}"}
    for noise in noises:
        out["results"][str(noise)] = {s: run_strategy(g, X, s, budget, noise, seed) for s in STRATEGIES}
        print("noise", noise, "done", flush=True)
    return out
