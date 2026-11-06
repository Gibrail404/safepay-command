"""Probability calibration stored as plain JSON numbers (no pickles). Fit on validation data, applied unchanged to test."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def logit(p, eps: float = 1e-9):
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


@dataclass
class Calibrator:
    method: str                                   # "platt" or "isotonic"
    params: dict = field(default_factory=dict)

    def apply(self, z) -> np.ndarray:
        """z is the raw score in logit space (a log-odds number), for every model type."""
        z = np.asarray(z, dtype=float)
        if self.method == "platt":
            return sigmoid(self.params["a"] * z + self.params["b"])
        if self.method == "isotonic":
            return np.interp(z, self.params["x"], self.params["y"])
        raise ValueError(self.method)

    def to_json(self) -> dict:
        return {"method": self.method, "params": {k: (v if np.isscalar(v) else list(map(float, v))) for k, v in self.params.items()}}

    @staticmethod
    def from_json(d: dict) -> "Calibrator":
        return Calibrator(d["method"], d["params"])


def fit_platt(z_val, y_val) -> Calibrator:
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(np.asarray(z_val, dtype=float).reshape(-1, 1), y_val)
    return Calibrator("platt", {"a": float(lr.coef_[0, 0]), "b": float(lr.intercept_[0])})


def fit_isotonic(z_val, y_val) -> Calibrator:
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(np.asarray(z_val, dtype=float), y_val)
    return Calibrator("isotonic", {"x": iso.X_thresholds_.astype(float), "y": iso.y_thresholds_.astype(float)})
