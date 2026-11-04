"""Uplift: which payments gain most from a hold? A risk score ranks by how likely a payment is a scam; uplift ranks by how much a hold changes the outcome
(money saved minus the cost of bothering a good customer). The T-learner fits one outcome model per action on the logged data and subtracts them."""
from __future__ import annotations
import numpy as np
from scipy.stats import spearmanr
from .estimators import _fit_predict
from .simulator import ALLOW, HOLD, SimConfig, log_data, sample_population, true_value, with_exploration
from .experiments import LOGGING


def fit_uplift(d: dict):
    """Returns a function x -> predicted (reward of hold minus reward of allow)."""
    def predict(x: np.ndarray) -> np.ndarray:
        m = _fit_predict(d["x"], d["action"], d["reward"], x)
        return m[:, HOLD] - m[:, ALLOW]
    return predict


def hold_top_fraction(rank_fn, reference_x: np.ndarray, q: float):
    """Hold the payments whose rank value is in the top q of a reference sample, allow the rest. A deterministic function of the features."""
    cut = float(np.quantile(rank_fn(reference_x), 1 - q))
    def pi(x: np.ndarray) -> np.ndarray:
        p = np.zeros((len(x), 3))
        hold = rank_fn(x) >= cut
        p[hold, HOLD], p[~hold, ALLOW] = 1.0, 1.0
        return p
    return pi


def uplift_experiment(cfg: SimConfig, reps: int, n: int, seed: int, fractions=(0.05, 0.10, 0.20), test_n: int = 300_000) -> dict:
    test = sample_population(test_n, seed + 7_000, cfg)
    true_uplift = test.expected_reward[:, HOLD] - test.expected_reward[:, ALLOW]
    log_pi = with_exploration(LOGGING, cfg.epsilon)
    score_fn = lambda x: x[:, 1]
    out = {"rank_correlation_with_true_uplift": {"risk_score": float(spearmanr(score_fn(test.x), true_uplift)[0])}, "values": {}, "reps": reps, "n": n}
    corr, per = [], {q: {"uplift": [], "score": [], "oracle": None, "allow_all": true_value(test, hold_top_fraction(score_fn, test.x, 1e-9))} for q in fractions}
    for r in range(reps):
        pop = sample_population(n, seed + r, cfg)
        d = log_data(pop, log_pi, seed + 900_000 + r)
        up = fit_uplift(d)
        pred_test = up(test.x)
        corr.append(float(spearmanr(pred_test, true_uplift)[0]))
        cache = {id(test.x): pred_test}
        up_fn = lambda x: cache[id(x)] if id(x) in cache else up(x)
        for q in fractions:
            per[q]["uplift"].append(true_value(test, hold_top_fraction(up_fn, test.x, q)))
            per[q]["score"].append(true_value(test, hold_top_fraction(score_fn, test.x, q)))
    out["rank_correlation_with_true_uplift"]["estimated_uplift_mean"] = float(np.mean(corr))
    out["rank_correlation_with_true_uplift"]["estimated_uplift_sd"] = float(np.std(corr))
    for q in fractions:
        oracle = true_value(test, hold_top_fraction(lambda x: true_uplift + 1e-6 * x[:, 1], test.x, q))      # ties (all good payments have the same uplift) are broken by score
        u, s = np.array(per[q]["uplift"]), np.array(per[q]["score"])
        out["values"][str(q)] = {"allow_everything": per[q]["allow_all"], "hold_top_by_score": float(s.mean()), "hold_top_by_estimated_uplift": float(u.mean()), "hold_top_by_true_uplift_oracle": oracle,
                                 "uplift_minus_score_mean": float((u - s).mean()), "uplift_better_share": float((u > s).mean())}
    return out
