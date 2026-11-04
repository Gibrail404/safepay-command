"""Counterfactual (off-policy) estimators: given logged data from one policy, estimate the average reward another policy WOULD have earned.
Each returns (estimate, half-width of a 95% normal-approximation interval)."""
from __future__ import annotations
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

Z = 1.96


def _ci(terms: np.ndarray) -> tuple[float, float]:
    return float(terms.mean()), float(Z * terms.std(ddof=1) / np.sqrt(len(terms)))


def naive_matched(d: dict, pi) -> tuple[float, float]:
    """What a team does without a counterfactual method: average the realised reward of the logged payments whose action happens to equal the new policy's action."""
    target = pi(d["x"]).argmax(axis=1)
    m = d["action"] == target
    return _ci(d["reward"][m])


def _weights(d: dict, pi) -> np.ndarray:
    p1 = pi(d["x"])
    return p1[np.arange(len(d["action"])), d["action"]] / d["propensity"]


def ips(d: dict, pi) -> tuple[float, float]:
    """Inverse propensity scoring: reweight each logged payment by how much more (or less) likely the new policy was to choose the action that was taken. Unbiased, high variance."""
    return _ci(_weights(d, pi) * d["reward"])


def snips(d: dict, pi) -> tuple[float, float]:
    """Self-normalised IPS: divide by the sum of weights. Slightly biased, much lower variance. Interval by linearisation."""
    w = _weights(d, pi)
    v = float((w * d["reward"]).sum() / w.sum())
    lin = w * (d["reward"] - v) / w.mean()
    return v, float(Z * lin.std(ddof=1) / np.sqrt(len(lin)))


def _fit_predict(x_tr, a_tr, r_tr, x_te) -> np.ndarray:
    """Outcome model: expected reward of each action given the features, one gradient-boosting model per action."""
    out = np.zeros((len(x_te), 3))
    for a in range(3):
        m = a_tr == a
        if m.sum() < 30:
            out[:, a] = r_tr[m].mean() if m.any() else 0.0
            continue
        out[:, a] = HistGradientBoostingRegressor(max_iter=60, max_depth=4, learning_rate=0.1, random_state=0).fit(x_tr[m], r_tr[m]).predict(x_te)
    return out


def outcome_predictions(d: dict, folds: int = 2, seed: int = 0) -> np.ndarray:
    """Cross-fitted: each payment's predictions come from a model that never saw that payment, which avoids over-fitting bias in the doubly robust estimate."""
    n = len(d["action"])
    idx = np.random.default_rng(seed).permutation(n)
    parts = np.array_split(idx, folds)
    m = np.zeros((n, 3))
    for k in range(folds):
        te = parts[k]
        tr = np.concatenate([parts[j] for j in range(folds) if j != k])
        m[te] = _fit_predict(d["x"][tr], d["action"][tr], d["reward"][tr], d["x"][te])
    return m


def direct_method(d: dict, pi, m: np.ndarray | None = None) -> tuple[float, float]:
    m = outcome_predictions(d) if m is None else m
    return _ci((pi(d["x"]) * m).sum(axis=1))


def doubly_robust(d: dict, pi, m: np.ndarray | None = None) -> tuple[float, float]:
    """Outcome-model prediction plus an inverse-propensity correction of its error. Correct if EITHER the model or the propensities are right."""
    m = outcome_predictions(d) if m is None else m
    n = len(d["action"])
    base = (pi(d["x"]) * m).sum(axis=1)
    return _ci(base + _weights(d, pi) * (d["reward"] - m[np.arange(n), d["action"]]))


ESTIMATORS = {"naive_matched": naive_matched, "ips": ips, "snips": snips, "direct_method": direct_method, "doubly_robust": doubly_robust}


def estimate_all(d: dict, pi) -> dict[str, tuple[float, float]]:
    m = outcome_predictions(d)
    return {"naive_matched": naive_matched(d, pi), "ips": ips(d, pi), "snips": snips(d, pi), "direct_method": direct_method(d, pi, m), "doubly_robust": doubly_robust(d, pi, m)}
