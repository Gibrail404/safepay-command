"""Trains the MLP ensemble in its OWN process. PyTorch and LightGBM each bring an OpenMP runtime; running both in one process can crash or
deadlock on macOS, so the orchestrator (train_risk.py) never imports torch. Usage: python -m safepay_ml.train_mlp <output_dir>"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import torch
from . import metrics as M
from .constants import FRACTIONS, MLP_PARAMS, SEEDS
from .data import FEATURES, load_ulb, temporal_split
from .nets import make_net
from .scorers import MLPScorer
from .timing import latency_ms



def train_mlp_seed(tr, va, seed, mean, std):
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = make_net(tr.X.shape[1])
    xtr = torch.from_numpy(((tr.X - mean) / std).astype(np.float32))
    ytr = torch.from_numpy(tr.y.astype(np.float32))
    xva = torch.from_numpy(((va.X - mean) / std).astype(np.float32))
    pos, neg = float(tr.y.sum()), float((1 - tr.y).sum())
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor((neg / pos) ** 0.5))
    opt = torch.optim.AdamW(net.parameters(), lr=MLP_PARAMS["lr"], weight_decay=MLP_PARAMS["weight_decay"])
    gen = torch.Generator().manual_seed(seed)
    best, best_state, best_epoch, bad = -1.0, None, 0, 0
    for epoch in range(MLP_PARAMS["epochs"]):
        net.train()
        order = torch.randperm(len(xtr), generator=gen)
        for i in range(0, len(order), MLP_PARAMS["batch_size"]):
            idx = order[i:i + MLP_PARAMS["batch_size"]]
            opt.zero_grad()
            loss_fn(net(xtr[idx]).squeeze(-1), ytr[idx]).backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            ap = M.average_precision(va.y, net(xva).squeeze(-1).numpy())
        if ap > best:
            best, best_state, best_epoch, bad = ap, {k: v.clone() for k, v in net.state_dict().items()}, epoch, 0
        else:
            bad += 1
            if bad >= MLP_PARAMS["patience"]:
                break
    net.load_state_dict(best_state)
    net.eval()
    return net, best, best_epoch


def main(out: Path) -> None:
    parts = temporal_split(load_ulb(), FRACTIONS)
    tr, va, te = parts["train"], parts["val"], parts["test"]
    mean, std = tr.X.mean(axis=0), tr.X.std(axis=0) + 1e-6
    nets, rows, files = [], [], []
    for seed in SEEDS:
        net, ap, ep = train_mlp_seed(tr, va, seed, mean, std)
        nets.append(net)
        zt = net(torch.from_numpy(((te.X - mean) / std).astype(np.float32))).squeeze(-1).detach().numpy()
        rows.append({"seed": seed, "val_ap": ap, "best_epoch": ep, "test_ap": M.average_precision(te.y, zt)})
        f = f"mlp_seed{seed}.pt"
        torch.save(net.state_dict(), out / f)
        files.append(f)
    (out / "mlp.json").write_text(json.dumps({"files": files, "mean": mean.tolist(), "std": std.tolist(), "n_features": len(FEATURES)}))
    scorer = MLPScorer(nets, mean, std)
    np.savez(out / "mlp_scores.npz", raw_val=scorer.raw(va.X), raw_test=scorer.raw(te.X))
    extra = {"seeds": rows, "test_ap_mean_of_seeds": float(np.mean([r["test_ap"] for r in rows])), "test_ap_sd_of_seeds": float(np.std([r["test_ap"] for r in rows])),
             "latency_single_row": latency_ms(lambda x: scorer.raw(x[None, :]), te.X[0]), "params": MLP_PARAMS, "torch": torch.__version__}
    (out / "mlp_extra.json").write_text(json.dumps(extra))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
