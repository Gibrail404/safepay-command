"""Loads the real ULB data produced by the M0 pipeline and cuts it by time. Never shuffles: the test set is the future."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ULB_PARQUET = ROOT / "data" / "processed" / "ulb_creditcard.parquet"
ULB_MANIFEST = ROOT / "data" / "processed" / "ulb_creditcard.manifest.json"
V_COLS = [f"V{i}" for i in range(1, 29)]
FEATURES = V_COLS + ["log_amount"]            # Time is an offset in seconds, not a clock, so it is not a feature


@dataclass(frozen=True)
class Split:
    name: str
    X: np.ndarray
    y: np.ndarray
    time: np.ndarray
    frame: pd.DataFrame


def load_ulb(path: Path = ULB_PARQUET) -> pd.DataFrame:
    df = pd.read_parquet(path).sort_values("Time", kind="stable").reset_index(drop=True)
    df["log_amount"] = np.log1p(df["Amount"])
    return df


def temporal_split(df: pd.DataFrame, fractions=(0.6, 0.2, 0.2)) -> dict[str, Split]:
    """Rows are already in time order. Train is the oldest block, validation the next, test the newest."""
    assert abs(sum(fractions) - 1.0) < 1e-9
    n = len(df)
    cut1, cut2 = int(n * fractions[0]), int(n * (fractions[0] + fractions[1]))
    out = {}
    for name, part in (("train", df.iloc[:cut1]), ("val", df.iloc[cut1:cut2]), ("test", df.iloc[cut2:])):
        out[name] = Split(name, part[FEATURES].to_numpy(dtype=np.float32), part["Class"].to_numpy(dtype=np.int8), part["Time"].to_numpy(), part)
    return out


def duplicate_overlap(train: Split, test: Split) -> np.ndarray:
    """Boolean mask over test rows whose features are identical to some training row (a possible memorisation leak)."""
    seen = {r.tobytes() for r in train.X}
    return np.array([r.tobytes() in seen for r in test.X])


def source_manifest() -> dict:
    return json.loads(ULB_MANIFEST.read_text())
