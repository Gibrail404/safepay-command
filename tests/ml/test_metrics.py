"""Metrics tested against values worked out by hand."""
import math
import numpy as np
import pytest
from safepay_ml import metrics as m


def test_average_precision_matches_the_textbook_example():
    # y = 0,0,1,1 with scores .1,.4,.35,.8: ranked 1(.8) 0(.4) 1(.35) 0(.1) -> precision 1.0 at first hit, 2/3 at second
    assert m.average_precision([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) == pytest.approx((1.0 + 2 / 3) / 2)


def test_perfect_and_random_rankings():
    y = np.array([0] * 90 + [1] * 10)
    assert m.average_precision(y, y.astype(float)) == 1.0
    assert m.roc_auc(y, y.astype(float)) == 1.0
    assert m.roc_auc(y, np.full(100, 0.5)) == 0.5


def test_fpr_threshold_allows_exactly_the_requested_false_positive_rate():
    neg = np.arange(100) / 100
    thr = m.fpr_threshold(neg, 0.01)
    assert thr == pytest.approx(0.98) and (neg > thr).sum() == 1          # 1 of 100 negatives is above: FPR = 1%
    assert (neg > m.fpr_threshold(neg, 0.10)).sum() == 10


def test_confusion_counts_and_rates():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    s = np.array([0.9, 0.8, 0.2, 0.7, 0.1, 0.1, 0.1, 0.1])
    c = m.confusion_at(y, s, 0.5)
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (2, 1, 1, 4)
    assert c["recall"] == pytest.approx(2 / 3) and c["fpr"] == pytest.approx(1 / 5) and c["precision"] == pytest.approx(2 / 3)


def test_brier_and_log_loss_values():
    assert m.brier([1, 0], [0.8, 0.2]) == pytest.approx(0.04)
    assert m.log_loss([1, 0], [0.8, 0.2]) == pytest.approx(-math.log(0.8))
    assert m.log_loss([1], [0.0]) < 40                                      # clipped, never infinite


def test_ece_is_zero_when_calibrated_and_large_when_overconfident():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 50000)
    y = (rng.uniform(0, 1, 50000) < p).astype(int)
    assert m.ece(y, p) < 0.01
    assert m.ece(np.zeros(1000), np.full(1000, 0.3)) == pytest.approx(0.3)


def test_bootstrap_ci_brackets_the_estimate_and_is_reproducible():
    rng = np.random.default_rng(1)
    y = (rng.uniform(size=3000) < 0.1).astype(int)
    s = y * 0.5 + rng.uniform(size=3000)
    point = m.average_precision(y, s)
    lo, hi = m.bootstrap_ci(m.average_precision, y, s, n=200, seed=3)
    assert lo < point < hi and (lo, hi) == m.bootstrap_ci(m.average_precision, y, s, n=200, seed=3)
    lo2, hi2 = m.bootstrap_ci(m.average_precision, y[:600], s[:600], n=200, seed=3)
    assert (hi2 - lo2) > (hi - lo)                                           # less data, wider interval


def test_reliability_table_covers_all_rows():
    rng = np.random.default_rng(2)
    p = rng.uniform(size=1000)
    t = m.reliability_table((rng.uniform(size=1000) < p).astype(int), p, bins=5)
    assert sum(r["n"] for r in t) == 1000
