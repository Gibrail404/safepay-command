"""Load a trained model from disk and score rows. Every scorer returns a RAW score in logit space; a Calibrator turns it into a probability.
No pickles: LightGBM uses its own text format, the logistic regression is plain JSON, and the neural nets load with weights_only=True."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .calibration import logit


def _no_openmp_clash(loading: str) -> None:
    """LightGBM and PyTorch must never share a process on macOS (see safepay_ml/__init__.py). Fail loudly instead of crashing."""
    import sys
    other = "torch" if loading == "lightgbm" else "lightgbm"
    if other in sys.modules:
        raise RuntimeError(f"cannot load {loading} in a process that already imported {other}: their OpenMP runtimes clash. Serve this model from its own process.")


class LogRegScorer:
    def __init__(self, params: dict):
        self.mean, self.scale = np.array(params["mean"]), np.array(params["scale"])
        self.coef, self.intercept = np.array(params["coef"]), float(params["intercept"])

    def raw(self, X) -> np.ndarray:
        return ((np.asarray(X, dtype=float) - self.mean) / self.scale) @ self.coef + self.intercept

    @staticmethod
    def load(directory: Path) -> "LogRegScorer":
        return LogRegScorer(json.loads((directory / "logreg.json").read_text()))


class LightGBMScorer:
    def __init__(self, booster):
        self.booster = booster

    def raw(self, X) -> np.ndarray:
        return logit(self.booster.predict(np.asarray(X, dtype=np.float64)))

    @staticmethod
    def load(directory: Path) -> "LightGBMScorer":
        _no_openmp_clash("lightgbm")
        import lightgbm as lgb
        return LightGBMScorer(lgb.Booster(model_file=str(directory / "lightgbm.txt")))


class MLPScorer:
    """An ensemble: the raw score is the mean logit of several small networks trained with different seeds."""
    def __init__(self, nets, mean, std):
        self.nets, self.mean, self.std = nets, np.asarray(mean, dtype=np.float32), np.asarray(std, dtype=np.float32)

    def raw(self, X) -> np.ndarray:
        import torch
        x = torch.from_numpy(((np.asarray(X, dtype=np.float32) - self.mean) / self.std).astype(np.float32))
        with torch.no_grad():
            return np.mean([net(x).squeeze(-1).numpy() for net in self.nets], axis=0).astype(float)

    @staticmethod
    def load(directory: Path) -> "MLPScorer":
        _no_openmp_clash("torch")
        import torch
        from .nets import make_net
        meta = json.loads((directory / "mlp.json").read_text())
        nets = []
        for f in meta["files"]:
            net = make_net(meta["n_features"])
            net.load_state_dict(torch.load(directory / f, weights_only=True))
            net.eval()
            nets.append(net)
        return MLPScorer(nets, meta["mean"], meta["std"])


def _load_tfidf(directory: Path):
    from .text_model import TfidfLogRegScorer
    return TfidfLogRegScorer.load(directory)


LOADERS = {"logreg": LogRegScorer.load, "lightgbm": LightGBMScorer.load, "mlp": MLPScorer.load, "tfidf_logreg": _load_tfidf}
