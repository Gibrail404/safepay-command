"""Evaluation metrics for rare-event scoring. Small, dependency-light and unit-tested against hand-computed values."""
from __future__ import annotations
import math
from typing import Callable
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def average_precision(y, s) -> float:
    """PR-AUC as average precision: the area under the precision-recall curve, step-wise. Baseline equals the fraud rate."""
    return float(average_precision_score(y, s))


def roc_auc(y, s) -> float:
    return float(roc_auc_score(y, s))


def fpr_threshold(neg_scores, fpr: float) -> float:
    """Smallest score threshold with at most `fpr` of the negatives scoring above it. Chosen on validation data, then applied unchanged to test."""
    neg = np.sort(np.asarray(neg_scores, dtype=float))
    k = max(1, math.ceil((1.0 - fpr) * len(neg)))
    return float(neg[k - 1])


def confusion_at(y, s, threshold: float) -> dict:
    y, s = np.asarray(y), np.asarray(s)
    pred = s > threshold
    tp, fp = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum())
    fn, tn = int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "fpr": fp / (fp + tn) if fp + tn else float("nan"),
            "precision": tp / (tp + fp) if tp + fp else float("nan")}


def brier(y, p) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss(y, p, eps: float = 1e-12) -> float:
    y, p = np.asarray(y, dtype=float), np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(y, p, bins: int = 10, strategy: str = "quantile") -> float:
    """Expected calibration error: weighted gap between predicted probability and observed fraud rate per bin.
    'quantile' bins hold equal numbers of rows, which suits rare events (equal-width bins put nearly everything in the first bin)."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if strategy == "quantile":
        edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    else:
        edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, max(len(edges) - 2, 0))
    total, err = len(y), 0.0
    for b in np.unique(idx):
        m = idx == b
        err += m.sum() / total * abs(p[m].mean() - y[m].mean())
    return float(err)


def reliability_table(y, p, bins: int = 10) -> list[dict]:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, max(len(edges) - 2, 0))
    return [{"bin": int(b), "n": int((idx == b).sum()), "mean_predicted": float(p[idx == b].mean()), "observed_rate": float(y[idx == b].mean())} for b in np.unique(idx)]


def bootstrap_ci(fn: Callable, y, s, n: int = 1000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap: resample rows with replacement, recompute the metric, take the central (1 - alpha) range."""
    y, s = np.asarray(y), np.asarray(s)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue                                       # a resample with one class cannot score
        vals.append(fn(y[i], s[i]))
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
