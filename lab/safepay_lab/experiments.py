"""Decision Lab experiments: how wrong, and how over-confident, is each way of evaluating a new policy, measured against the simulator's truth."""
from __future__ import annotations
from dataclasses import replace
import numpy as np
from .estimators import estimate_all
from .simulator import SimConfig, sample_population, threshold_policy, true_value, with_exploration, ALLOW, WARN, HOLD

LOGGING = threshold_policy(0.8, 1.6)
TARGETS = {"stricter (warn from 0.5, hold from 1.2)": threshold_policy(0.5, 1.2), "looser (warn from 1.0, hold from 2.0)": threshold_policy(1.0, 2.0),
           "allow everything": threshold_policy(99, 99)}


def coverage_experiment(cfg: SimConfig, reps: int, n: int, seed: int, truth_n: int = 400_000) -> dict:
    """Repeat the whole pipeline `reps` times on fresh simulated data. For each estimator: bias, RMSE and how often its 95% interval contains the truth."""
    big = sample_population(truth_n, seed + 10_000, cfg)
    log_pi = with_exploration(LOGGING, cfg.epsilon)
    out = {}
    for tname, pi in TARGETS.items():
        truth = true_value(big, pi)
        est: dict[str, list] = {}
        for r in range(reps):
            pop = sample_population(n, seed + r, cfg)
            d = _log(pop, log_pi, seed + 500_000 + r)
            for k, (v, hw) in estimate_all(d, pi).items():
                est.setdefault(k, []).append((v, hw))
        out[tname] = {"truth": truth, "estimators": {}}
        for k, arr in est.items():
            a = np.array(arr)
            err = a[:, 0] - truth
            out[tname]["estimators"][k] = {"mean_estimate": float(a[:, 0].mean()), "bias": float(err.mean()), "rmse": float(np.sqrt((err ** 2).mean())),
                                           "coverage_95": float((np.abs(err) <= a[:, 1]).mean()), "mean_halfwidth": float(a[:, 1].mean()), "p2_5": float(np.quantile(a[:, 0], 0.025)), "p97_5": float(np.quantile(a[:, 0], 0.975))}
    return out


def _log(pop, log_pi, seed):
    from .simulator import log_data
    return log_data(pop, log_pi, seed)


def frontier(cfg: SimConfig, n: int = 400_000, seed: int = 3) -> list[dict]:
    """Truth about a family of policies: how much scam money each stops against how many good customers it bothers."""
    pop = sample_population(n, seed, cfg)
    scam_money = float((pop.scam * pop.amount).sum())
    rows = []
    for hold_at in (0.4, 0.8, 1.2, 1.6, 2.0, 2.4, 3.0, 99.0):
        pi = threshold_policy(hold_at - 0.4, hold_at)
        p = pi(pop.x)
        loss = float((-(p * pop.expected_reward).sum(axis=1) - (p[:, HOLD] * cfg.review_cost) - (1 - pop.scam) * (p[:, WARN] * cfg.legit_abandon_warn + p[:, HOLD] * cfg.legit_abandon_hold) * cfg.abandon_cost).sum())
        stopped = scam_money - loss
        legit = pop.scam == 0
        rows.append({"hold_from": hold_at, "warn_from": hold_at - 0.4, "scam_money_stopped_share": stopped / scam_money, "good_payments_warned_share": float(p[legit, WARN].mean()),
                     "good_payments_held_share": float(p[legit, HOLD].mean()), "value_per_payment": true_value(pop, pi)})
    return rows


def by_archetype(cfg: SimConfig, warn_at: float = 0.8, hold_at: float = 1.6, n: int = 400_000, seed: int = 4) -> list[dict]:
    """Truth about one policy, split by kind of scam: how much of each kind's money it stops, and how often it holds or warns that kind."""
    from .simulator import ARCHETYPES
    pop = sample_population(n, seed, cfg)
    p = threshold_policy(warn_at, hold_at)(pop.x)
    out = []
    for i, name in enumerate(ARCHETYPES):
        m = (pop.scam == 1) & (pop.archetype == i)
        amount, coach = pop.amount[m], pop.coached[m]
        sent_after_warn = cfg.warn_ignore_uncoached + (1 - cfg.warn_ignore_uncoached) * coach
        missed_by_analyst = 1 - (cfg.hold_catch_uncoached * (1 - coach) + cfg.hold_catch_coached * coach)
        loss = float((amount * (p[m, ALLOW] + p[m, WARN] * sent_after_warn + p[m, HOLD] * missed_by_analyst)).sum())
        out.append({"archetype": name, "coaching": cfg.coaching_by_archetype[i], "share_of_scams": float(m.sum() / (pop.scam == 1).sum()), "money_stopped_share": 1 - loss / float(amount.sum()),
                    "held_share": float(p[m, HOLD].mean()), "warned_share": float(p[m, WARN].mean()), "allowed_share": float(p[m, ALLOW].mean())})
    return out
