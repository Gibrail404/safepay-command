import torch.nn as nn


def make_net(n_features: int) -> nn.Module:
    """A deliberately small network: 29 -> 64 -> 32 -> 1. Dropout fights overfitting on only a few hundred fraud rows."""
    return nn.Sequential(nn.Linear(n_features, 64), nn.ReLU(), nn.Dropout(0.1), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))
