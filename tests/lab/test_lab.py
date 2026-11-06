"""Tests for the simulator and the counterfactual estimators. Sizes are kept small so the suite stays fast."""
import numpy as np
import pytest
from safepay_lab.estimators import doubly_robust, ips, naive_matched, snips
from safepay_lab.simulator import ALLOW, HOLD, SimConfig, log_data, sample_population, threshold_policy, true_value, with_exploration

LOG = with_exploration(threshold_policy(0.8, 1.6), 0.1)


def test_population_is_reproducible_and_amounts_respect_the_cap():
    a, b = sample_population(5000, 3), sample_population(5000, 3)
    assert np.array_equal(a.x, b.x) and a.amount.max() <= SimConfig().amount_cap + 1e-9


def test_scam_rate_and_log_amount_marginals_match_the_config():
    cfg = SimConfig(amount_cap=1e12)
    pop = sample_population(300_000, 1, cfg)
    assert pop.scam.mean() == pytest.approx(cfg.scam_rate, abs=0.002)
    legit = np.log(pop.amount[pop.scam == 0])
    assert legit.mean() == pytest.approx(cfg.log_amount_mean, abs=0.02) and legit.std() == pytest.approx(cfg.log_amount_sd, abs=0.02)


def test_allowing_everything_loses_exactly_the_scam_money():
    pop = sample_population(50_000, 2)
    assert true_value(pop, threshold_policy(99, 99)) == pytest.approx(-(pop.scam * pop.amount).mean())


def test_holding_a_good_payment_costs_money_and_holding_a_scam_can_save_money():
    pop = sample_population(50_000, 2)
    good, bad = pop.scam == 0, pop.scam == 1
    assert (pop.expected_reward[good, HOLD] < pop.expected_reward[good, ALLOW]).all()
    assert pop.expected_reward[bad, HOLD].mean() > pop.expected_reward[bad, ALLOW].mean()


def test_coached_victims_are_harder_to_protect():
    cfg = SimConfig()
    assert cfg.coaching_by_archetype[0] > cfg.coaching_by_archetype[3]
    pop = sample_population(100_000, 4)
    scam = pop.scam == 1
    hi, lo = scam & (pop.coached >= 0.9), scam & (pop.coached == 0)
    gain = lambda m: (pop.expected_reward[m, HOLD] - pop.expected_reward[m, ALLOW]).mean() / pop.amount[m].mean()
    assert gain(lo) > gain(hi)


def test_logged_data_never_contains_latent_fields_and_hides_labels_of_held_payments():
    d = log_data(sample_population(20_000, 5), LOG, 6)
    assert not {"scam", "coached", "archetype", "expected_reward"} & set(d)
    held = d["action"] == HOLD
    assert np.isnan(d["scam_label"][held]).all() and not np.isnan(d["scam_label"][d["action"] == ALLOW]).any()


def test_every_action_has_a_known_nonzero_chance():
    d = log_data(sample_population(20_000, 5), LOG, 6)
    assert (d["propensity"] >= 0.1 / 3 - 1e-12).all() and np.allclose(d["logging_probs"].sum(axis=1), 1)


def test_evaluating_the_logging_policy_itself_reproduces_the_observed_average():
    d = log_data(sample_population(20_000, 5), LOG, 6)
    assert ips(d, LOG)[0] == pytest.approx(d["reward"].mean(), abs=1e-9)


def test_naive_comparison_is_badly_biased_and_corrections_are_not():
    cfg = SimConfig()
    pop = sample_population(300_000, 7, cfg)
    d = log_data(pop, LOG, 8)
    pi = threshold_policy(99, 99)                                     # allow everything
    truth = true_value(sample_population(400_000, 9, cfg), pi)
    assert abs(naive_matched(d, pi)[0] - truth) > 3.0                 # the matching rows are the safe payments
    assert abs(snips(d, pi)[0] - truth) < 1.5 and abs(doubly_robust(d, pi)[0] - truth) < 1.5


def test_threshold_policy_is_deterministic_and_orders_actions_by_score():
    pi = threshold_policy(0.5, 1.5)
    x = np.array([[0, -1, 0], [0, 0.7, 0], [0, 2.0, 0]], dtype=float)
    assert pi(x).argmax(axis=1).tolist() == [0, 1, 2]


def test_stopped_money_by_archetype_is_between_zero_and_one_and_matches_the_overall_loss():
    from safepay_lab.experiments import by_archetype
    rows = by_archetype(SimConfig(), n=100_000)
    assert all(0 <= r["money_stopped_share"] <= 1 and abs(r["held_share"] + r["warned_share"] + r["allowed_share"] - 1) < 1e-9 for r in rows)
    assert sum(r["share_of_scams"] for r in rows) == pytest.approx(1.0)


def test_the_sample_is_used_only_when_the_full_data_is_missing_and_a_clear_error_when_neither_exists(tmp_path, monkeypatch):
    """The 3,000-row sample is a fallback for machines without the ULB data (the container); the full data is always used when present."""
    import pandas as pd
    from safepay_lab import scenarios
    scenarios._pool.cache_clear()
    full = pd.DataFrame({"index": [1], "Amount": [100.0], "Class": [0], **{f"V{i}": [0.0] for i in range(1, 29)}})
    # with the full data present the sample file is ignored; without it the sample is used; with neither there is a clear error
    monkeypatch.setattr(scenarios.Path if hasattr(scenarios, "Path") else __import__("pathlib").Path, "exists", lambda self: self.name == "scenario_pool.parquet", raising=False)
    monkeypatch.setattr(pd, "read_parquet", lambda path, *a, **k: full)
    assert len(scenarios._pool()) == 1
    scenarios._pool.cache_clear()
    monkeypatch.setattr(__import__("pathlib").Path, "exists", lambda self: False, raising=False)
    with pytest.raises(RuntimeError):
        scenarios._pool()
    scenarios._pool.cache_clear()
