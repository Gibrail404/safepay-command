"""Load the real Elliptic graph (data/processed) and build the sparse structure. Nothing here is simulated."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.sparse as sp

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
TRAIN_END, VAL_END = 24, 34            # time steps 1-24 train, 25-34 validation, 35-49 test (the test period contains the known market shutdown at step 43)


@dataclass
class Graph:
    X: np.ndarray                  # (n, 165) local transaction features
    time: np.ndarray               # time step of each node
    y: np.ndarray                  # 1 illicit, 0 licit, nan unknown
    A: sp.csr_matrix               # undirected adjacency (symmetric, no weights)
    out_deg: np.ndarray
    in_deg: np.ndarray
    txid: np.ndarray

    @property
    def n(self) -> int:
        return len(self.time)

    def split(self) -> dict[str, np.ndarray]:
        lab = ~np.isnan(self.y)
        return {"train": np.where(lab & (self.time <= TRAIN_END))[0], "val": np.where(lab & (self.time > TRAIN_END) & (self.time <= VAL_END))[0], "test": np.where(lab & (self.time > VAL_END))[0]}


def load_graph() -> Graph:
    f = pd.read_parquet(PROCESSED / "elliptic.parquet")
    c = pd.read_parquet(PROCESSED / "elliptic_classes.parquet")
    e = pd.read_parquet(PROCESSED / "elliptic_edges.parquet")
    idx = pd.Series(np.arange(len(f)), index=f["txid"].to_numpy())
    y = c.set_index("txid")["label"].reindex(f["txid"]).to_numpy(dtype=np.float32)
    src, dst = idx.reindex(e["src"]).to_numpy(), idx.reindex(e["dst"]).to_numpy()
    n = len(f)
    directed = sp.csr_matrix((np.ones(len(src), dtype=np.float32), (src, dst)), shape=(n, n))
    A = ((directed + directed.T) > 0).astype(np.float32).tocsr()
    feat_cols = [col for col in f.columns if col.startswith("f")]
    return Graph(f[feat_cols].to_numpy(dtype=np.float32), f["time_step"].to_numpy(), y, A, np.asarray(directed.sum(axis=1)).ravel(), np.asarray(directed.sum(axis=0)).ravel(), f["txid"].to_numpy())
