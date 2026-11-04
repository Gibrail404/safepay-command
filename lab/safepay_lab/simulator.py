"""A payment-scam simulator with KNOWN ground truth. Everything here is SIMULATED and must be labelled so wherever a number from it is shown.
Real inputs: the log-amount distribution is fitted to the real ULB card data (mean 3.005, sd 1.87 on log amounts). Assumptions (not measured anywhere): the scam
rate, how much larger scam amounts are, how well the risk score separates scams, how coached victims react to warnings and how well analysts catch scams. They are
parameters in `SimConfig`, printed in every report, and the experiments are re-run across alternative values (see experiments.py).

Because the simulator knows each payment's latent status, it also knows the expected reward of EVERY action for EVERY payment. That is what lets us check
counterfactual estimators against the truth, which real data can never do."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

ACTIONS = ("allow", "warn", "hold")
ALLOW, WARN, HOLD = 0, 1, 2
ARCHETYPES = ("impersonation", "romance", "investment", "account_takeover")


@dataclass(frozen=True)
class SimConfig:
    scam_rate: float = 0.02
    log_amount_mean: float = 3.005            # real: fitted to ULB
    log_amount_sd: float = 1.87               # real: fitted to ULB
    scam_log_amount_shift: float = 1.2        # assumption: scam payments are larger
    score_separation: float = 1.8             # assumption: logit-score gap between scams and legit (about 0.90 ROC AUC)
    archetype_share: tuple = (0.35, 0.25, 0.25, 0.15)
    coaching_by_archetype: tuple = (0.9, 0.5, 0.6, 0.0)     # assumption: chance the victim is coached to ignore or defeat a check
    warn_ignore_uncoached: float = 0.25       # assumption: chance an uncoached victim sends the payment anyway after a warning
    hold_catch_uncoached: float = 0.9         # assumption: analyst catches an uncoached scam when the payment is held
    hold_catch_coached: float = 0.55          # assumption: lower when the victim lies to the analyst
    legit_abandon_warn: float = 0.02          # assumption
    legit_abandon_hold: float = 0.12          # assumption
    abandon_cost: float = 20.0                # assumption: value lost when a good customer gives up
    review_cost: float = 5.0                  # assumption: analyst time per held payment
    amount_cap: float = 5000.0                # assumption: a per-payment limit (real ULB amounts reach 25,691, but one payment limit keeps averages estimable)
    epsilon: float = 0.10                     # logging policy explores uniformly with this probability (needed for counterfactuals)


@dataclass
class Population:
    x: np.ndarray                  # observed features: columns log_amount, score_logit, new_payee
    amount: np.ndarray
    scam: np.ndarray               # latent, hidden from estimators
    archetype: np.ndarray          # latent
    coached: np.ndarray            # latent, probability the victim follows the scammer's coaching
    expected_reward: np.ndarray    # (n, 3): E[reward | payment, action], the truth
    cfg: SimConfig = field(repr=False, default=SimConfig())

    @property
    def n(self) -> int:
        return len(self.amount)


def expected_rewards(cfg: SimConfig, amount, scam, coach) -> np.ndarray:
    """Reward = minus (money lost to a successful scam + friction costs). Closed form per payment and action."""
    legit = 1 - scam
    r = np.zeros((len(amount), 3))
    r[:, ALLOW] = -scam * amount
    p_send_warn = cfg.warn_ignore_uncoached + (1 - cfg.warn_ignore_uncoached) * coach          # coaching makes the victim ignore the warning
    r[:, WARN] = -scam * p_send_warn * amount - legit * cfg.legit_abandon_warn * cfg.abandon_cost
    p_miss = 1 - (cfg.hold_catch_uncoached * (1 - coach) + cfg.hold_catch_coached * coach)
    r[:, HOLD] = -scam * p_miss * amount - legit * cfg.legit_abandon_hold * cfg.abandon_cost - cfg.review_cost
    return r


def sample_population(n: int, seed: int, cfg: SimConfig = SimConfig()) -> Population:
    rng = np.random.default_rng(seed)
    scam = (rng.random(n) < cfg.scam_rate).astype(float)
    arch = rng.choice(len(ARCHETYPES), n, p=cfg.archetype_share)
    coach = np.where(scam == 1, np.array(cfg.coaching_by_archetype)[arch], 0.0)
    log_amount = rng.normal(cfg.log_amount_mean, cfg.log_amount_sd, n) + scam * cfg.scam_log_amount_shift
    amount = np.minimum(np.exp(log_amount), cfg.amount_cap)
    log_amount = np.log(amount)
    new_payee = (rng.random(n) < np.where(scam == 1, 0.8, 0.12)).astype(float)
    score = rng.normal(scam * cfg.score_separation, 1.0, n)
    x = np.column_stack([log_amount, score, new_payee])
    return Population(x, amount, scam, arch, coach, expected_rewards(cfg, amount, scam, coach), cfg)


# ---------- policies: functions from observed features to a probability over actions ----------
def threshold_policy(warn_at: float, hold_at: float):
    """Deterministic: hold when the score logit is at least hold_at, warn when at least warn_at, otherwise allow."""
    def pi(x: np.ndarray) -> np.ndarray:
        a = np.where(x[:, 1] >= hold_at, HOLD, np.where(x[:, 1] >= warn_at, WARN, ALLOW))
        p = np.zeros((len(x), 3))
        p[np.arange(len(x)), a] = 1.0
        return p
    return pi


def with_exploration(pi, epsilon: float):
    """The logging policy: follow `pi` but with probability epsilon pick an action uniformly. Propensities are then known and never zero."""
    return lambda x: (1 - epsilon) * pi(x) + epsilon / 3


def true_value(pop: Population, pi) -> float:
    """Exact expected reward per payment of policy `pi`, from the known expected rewards. Estimators never see this."""
    return float((pi(pop.x) * pop.expected_reward).sum(axis=1).mean())


def log_data(pop: Population, logging_pi, seed: int) -> dict:
    """What a real company would have: features, the action taken, its propensity and the realised reward. Latent fields are not included.
    Selective labels: whether a payment was a scam is only learned when the payment was allowed (or the customer sent it despite a warning)."""
    rng = np.random.default_rng(seed)
    p = logging_pi(pop.x)
    a = (rng.random(pop.n)[:, None] > np.cumsum(p, axis=1)).sum(axis=1).clip(0, 2)
    cfg, scam, amount, coach = pop.cfg, pop.scam, pop.amount, pop.coached
    u = rng.random(pop.n)
    sends_after_warn = u < (cfg.warn_ignore_uncoached + (1 - cfg.warn_ignore_uncoached) * coach)
    caught = u < (cfg.hold_catch_uncoached * (1 - coach) + cfg.hold_catch_coached * coach)
    abandon = np.where(a == WARN, u < cfg.legit_abandon_warn, np.where(a == HOLD, u < cfg.legit_abandon_hold, False))
    loss = np.select([a == ALLOW, a == WARN, a == HOLD], [scam * amount, scam * sends_after_warn * amount, scam * (~caught) * amount])
    friction = (1 - scam) * abandon * cfg.abandon_cost + (a == HOLD) * cfg.review_cost
    reward = -(loss + friction)
    label_seen = (a == ALLOW) | ((a == WARN) & sends_after_warn)
    return {"x": pop.x, "amount": amount, "action": a, "propensity": p[np.arange(pop.n), a], "reward": reward, "scam_label": np.where(label_seen, scam, np.nan), "logging_probs": p}
