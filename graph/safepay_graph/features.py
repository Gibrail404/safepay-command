"""Graph features: what a transaction's neighbours look like. Only features and structure are used, never the labels of other nodes, so nothing about the test period's labels can leak."""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from .data import Graph


def row_normalise(A: sp.csr_matrix) -> sp.csr_matrix:
    deg = np.asarray(A.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros_like(deg, dtype=np.float32), where=deg > 0)
    return sp.diags(inv.astype(np.float32)) @ A


def local_features(g: Graph) -> np.ndarray:
    return g.X


def graph_features(g: Graph) -> np.ndarray:
    """Own features, the average of the 1-hop neighbours' features, the average over 2 hops, and simple structure counts (in, out and 2-hop reach)."""
    P = row_normalise(g.A)
    h1 = P @ g.X
    h2 = P @ h1
    deg = np.asarray(g.A.sum(axis=1)).ravel()
    reach2 = np.asarray(g.A @ deg).ravel()                      # total degree of the neighbours: how big the surrounding cluster is
    struct = np.column_stack([g.in_deg, g.out_deg, deg, reach2]).astype(np.float32)
    return np.hstack([g.X, h1.astype(np.float32), np.asarray(h2, dtype=np.float32), struct])
