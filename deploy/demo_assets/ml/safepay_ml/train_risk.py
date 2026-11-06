"""Train and evaluate the transaction risk models on the REAL ULB data and write a generated report.
Run:  python -m safepay_ml.train_risk
Selection rules are fixed in advance: the deployed model is the one with the best VALIDATION average precision; its probabilities are
calibrated with Platt scaling fitted on validation; the alert threshold is the score at which 1% of validation non-fraud rows alert.
Nothing is tuned on the test set."""
from __future__ import annotations
import hashlib, json, platform, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import lightgbm as lgb
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from . import __version__, metrics as M
from .calibration import fit_isotonic, fit_platt, logit, sigmoid
from .data import FEATURES, ROOT, duplicate_overlap, load_ulb, source_manifest, temporal_split
from .registry import MODELS_DIR, set_active, version_dir, write_metadata
from .scorers import LightGBMScorer, LogRegScorer
from .timing import latency_ms
from .constants import FRACTIONS, MLP_PARAMS, SEEDS

FPR_TARGET = 0.01
BOOT_N = 300
LGB_PARAMS = dict(n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=20, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.8, reg_lambda=1.0, deterministic=True, force_row_wise=True, verbose=-1, random_state=0, n_jobs=4)
REPORT_DIR = ROOT / "docs" / "reports"


def train_logreg(tr, va):
    sc = StandardScaler().fit(tr.X)
    lr = LogisticRegression(max_iter=2000, C=1.0).fit(sc.transform(tr.X), tr.y)
    params = {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}
    return LogRegScorer(params), params


def train_lightgbm(tr, va):
    model = lgb.LGBMClassifier(**LGB_PARAMS)
    model.fit(tr.X, tr.y, eval_set=[(va.X, va.y)], eval_metric="average_precision", callbacks=[lgb.early_stopping(100, verbose=False)])
    return LightGBMScorer(model.booster_), model


def evaluate(name, z_val, z_test, yv, yt, uniq_mask):
    """Ranking metrics on the raw score, the alert threshold chosen on validation, and bootstrap intervals on test."""
    thr = M.fpr_threshold(z_val[yv == 0], FPR_TARGET)
    c = M.confusion_at(yt, z_test, thr)
    recall_fn = lambda y, s: M.confusion_at(y, s, thr)["recall"]
    ap_ci = M.bootstrap_ci(M.average_precision, yt, z_test, n=BOOT_N, seed=1)
    rc_ci = M.bootstrap_ci(recall_fn, yt, z_test, n=1000, seed=2)
    u = uniq_mask
    cu = M.confusion_at(yt[u], z_test[u], thr)
    return {"val_average_precision": M.average_precision(yv, z_val), "test_average_precision": M.average_precision(yt, z_test), "test_ap_ci95": ap_ci,
            "test_roc_auc": M.roc_auc(yt, z_test), "threshold_logit_at_val_fpr": thr, "test_at_threshold": c, "test_recall_ci95": rc_ci,
            "unique_rows_only": {"n": int(u.sum()), "fraud": int(yt[u].sum()), "average_precision": M.average_precision(yt[u], z_test[u]), "recall": cu["recall"], "fpr": cu["fpr"]}}


def calibration_metrics(yt, z_test, cals):
    out = {"raw": sigmoid(z_test)}
    out.update({m: c.apply(z_test) for m, c in cals.items()})
    return {k: {"brier": M.brier(yt, p), "log_loss": M.log_loss(yt, p), "ece_quantile10": M.ece(yt, p, 10), "mean_predicted": float(p.mean())} for k, p in out.items()}, out


def main() -> dict:
    t0 = time.time()
    df = load_ulb()
    parts = temporal_split(df, FRACTIONS)
    tr, va, te = parts["train"], parts["val"], parts["test"]
    uniq = ~duplicate_overlap(tr, te)
    src = source_manifest()
    spec = {"data": src["parquet_sha256"], "fractions": FRACTIONS, "seeds": SEEDS, "lgb": LGB_PARAMS, "mlp": MLP_PARAMS, "code": __version__}
    version = hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:12]
    d = version_dir("risk", version)
    d.mkdir(parents=True, exist_ok=True)

    raw_val, raw_test, extra, scorers = {}, {}, {}, {}
    lr_scorer, lr_params = train_logreg(tr, va)
    scorers["logreg"] = lr_scorer
    raw_val["logreg"], raw_test["logreg"] = lr_scorer.raw(va.X), lr_scorer.raw(te.X)

    lgb_scorer, lgb_model = train_lightgbm(tr, va)
    scorers["lightgbm"] = lgb_scorer
    nit = lgb_model.best_iteration_
    lgb_scorer.raw = lambda X, b=lgb_model.booster_, n=nit: logit(b.predict(np.asarray(X, dtype=np.float64), num_iteration=n))
    raw_val["lightgbm"], raw_test["lightgbm"] = lgb_scorer.raw(va.X), lgb_scorer.raw(te.X)
    extra["lightgbm"] = {"best_iteration": int(nit)}

    # The MLP ensemble trains in a separate process: PyTorch and LightGBM each carry an OpenMP runtime and must not share a process on macOS.
    subprocess.run([sys.executable, "-m", "safepay_ml.train_mlp", str(d)], check=True, cwd=str(Path(__file__).resolve().parents[1]))
    scores = np.load(d / "mlp_scores.npz")
    raw_val["mlp"], raw_test["mlp"] = scores["raw_val"], scores["raw_test"]
    extra["mlp"] = json.loads((d / "mlp_extra.json").read_text())

    amount_ap = M.average_precision(te.y, te.frame["log_amount"].to_numpy())
    results, cal_results, cals_by_model = {}, {}, {}
    for name in ("logreg", "lightgbm", "mlp"):
        results[name] = evaluate(name, raw_val[name], raw_test[name], va.y, te.y, uniq)
        cals = {"platt": fit_platt(raw_val[name], va.y), "isotonic": fit_isotonic(raw_val[name], va.y)}
        cals_by_model[name] = cals
        cal_results[name], _ = calibration_metrics(te.y, raw_test[name], cals)
        results[name]["latency_single_row"] = extra["mlp"]["latency_single_row"] if name == "mlp" else latency_ms((lambda x, s=scorers[name]: s.raw(x[None, :])), te.X[0])

    deployed = max(results, key=lambda k: results[k]["val_average_precision"])         # rule fixed in advance: best validation AP
    platt = cals_by_model[deployed]["platt"]
    thr_logit = results[deployed]["threshold_logit_at_val_fpr"]
    thr_prob = float(platt.apply(np.array([thr_logit]))[0])

    (d / "logreg.json").write_text(json.dumps(lr_params))
    lgb_model.booster_.save_model(str(d / "lightgbm.txt"), num_iteration=nit)
    # alert bands in PROBABILITY space, from validation: "elevated" = 1% of validation non-fraud alert, "high" = 0.1%
    z_neg_val = raw_val[deployed][va.y == 0]
    bands = {"elevated": float(platt.apply(np.array([M.fpr_threshold(z_neg_val, 0.01)]))[0]), "high": float(platt.apply(np.array([M.fpr_threshold(z_neg_val, 0.001)]))[0])}
    meta = {"name": "risk", "version": version, "model_type": deployed, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "features": FEATURES, "calibrator": platt.to_json(), "alert_threshold_probability": thr_prob, "alert_threshold_logit": thr_logit, "bands": bands,
            "selection_rule": "best validation average precision; Platt calibration on validation; threshold = 1% validation FPR",
            "data": {"source": "ULB credit card fraud (real, anonymised)", "parquet_sha256": src["parquet_sha256"], "split_fractions": FRACTIONS,
                     "rows": {k: int(len(p.y)) for k, p in parts.items()}, "fraud": {k: int(p.y.sum()) for k, p in parts.items()}},
            "hyperparameters": {"lightgbm": LGB_PARAMS, "mlp": MLP_PARAMS, "seeds": SEEDS},
            "libraries": {"python": platform.python_version(), "numpy": np.__version__, "scikit-learn": sklearn.__version__, "lightgbm": lgb.__version__, "torch": extra["mlp"]["torch"]},
            "test_summary": {k: {"average_precision": v["test_average_precision"], "recall_at_1pct_fpr": v["test_at_threshold"]["recall"]} for k, v in results.items()},
            "limitations": ["Features V1-V28 are anonymised PCA components; no customer ids, payee, device or time-of-day clock.",
                            "Only 75 fraud rows in the test period: intervals are wide.", "Trained on European card transactions from two days in 2013; not representative of any other portfolio.",
                            "A score is a probability of fraud among card transactions, not of a scam."]}
    write_metadata("risk", version, meta)
    set_active("risk", version)

    report = {"generated_at": meta["trained_at"], "version": version, "seconds": round(time.time() - t0, 1), "data": meta["data"], "fpr_target": FPR_TARGET, "bootstrap_resamples": BOOT_N,
              "prevalence_test": float(te.y.mean()), "amount_only_test_average_precision": amount_ap, "models": results, "extras": extra, "calibration_test": cal_results,
              "deployed": {"model_type": deployed, "threshold_probability": thr_prob}, "duplicate_overlap": {"test_rows": int(len(te.y)), "also_in_train": int((~uniq).sum()), "fraud_also_in_train": int(te.y[~uniq].sum())},
              "libraries": meta["libraries"]}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "risk_model.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    (REPORT_DIR / "risk_model.md").write_text(render_markdown(report))
    print(f"version {version} deployed {deployed} in {report['seconds']}s")
    return report


def f(x, nd=3):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def render_markdown(r: dict) -> str:
    d, m = r["data"], r["models"]
    L = ["# Transaction risk model: generated report", "",
         f"Generated by `python -m safepay_ml.train_risk` on {r['generated_at']} (model version `{r['version']}`, {r['seconds']} s). Every number below is produced by that command from the real ULB data. Do not edit by hand.", "",
         "## Data and split (time-ordered, never shuffled)", "", "| Split | Rows | Fraud | Fraud rate |", "|---|---|---|---|"]
    for k in ("train", "val", "test"):
        L.append(f"| {k} | {d['rows'][k]:,} | {d['fraud'][k]} | {d['fraud'][k] / d['rows'][k]:.4%} |")
    o = r["duplicate_overlap"]
    L += ["", f"Test rows whose features exactly match a training row: {o['also_in_train']:,} of {o['test_rows']:,} (fraud among them: {o['fraud_also_in_train']}). Section 'Sensitivity' repeats the key metrics without them.", "",
          "## Ranking quality on the test period", "", f"Reference points: random scoring gives average precision equal to the fraud rate ({r['prevalence_test']:.4%}); scoring by amount alone gives {r['amount_only_test_average_precision']:.4f}.", "",
          "| Model | Val AP | Test AP (95% CI) | Test ROC-AUC |", "|---|---|---|---|"]
    for k, v in m.items():
        lo, hi = v["test_ap_ci95"]
        L.append(f"| {k} | {f(v['val_average_precision'])} | {f(v['test_average_precision'])} ({f(lo)} to {f(hi)}) | {f(v['test_roc_auc'])} |")
    mlp = r["extras"]["mlp"]
    L += ["", f"The MLP row is an ensemble of {len(mlp['seeds'])} seeds. Individual seeds: mean test AP {f(mlp['test_ap_mean_of_seeds'])}, standard deviation {f(mlp['test_ap_sd_of_seeds'])}.", "",
          f"## Alerting at a fixed false-positive budget ({r['fpr_target']:.0%})", "", "The threshold is chosen on validation so that 1% of validation non-fraud rows alert, then applied unchanged to test.", "",
          "| Model | Test recall (95% CI) | Test false-positive rate | Test precision | Frauds caught / total | Single-row latency p50 / p95 (ms) |", "|---|---|---|---|---|---|"]
    for k, v in m.items():
        c, lo_hi, lat = v["test_at_threshold"], v["test_recall_ci95"], v["latency_single_row"]
        L.append(f"| {k} | {f(c['recall'])} ({f(lo_hi[0])} to {f(lo_hi[1])}) | {f(c['fpr'], 4)} | {f(c['precision'])} | {c['tp']} / {c['tp'] + c['fn']} | {f(lat['p50_ms'], 3)} / {f(lat['p95_ms'], 3)} |")
    L += ["", "## Calibration on the test period (lower is better)", "", "| Model | Calibration | Brier | Log loss | ECE (quantile, 10 bins) | Mean predicted |", "|---|---|---|---|---|---|"]
    for k, cs in r["calibration_test"].items():
        for cname, v in cs.items():
            L.append(f"| {k} | {cname} | {v['brier']:.6f} | {v['log_loss']:.5f} | {v['ece_quantile10']:.5f} | {v['mean_predicted']:.5f} |")
    L += ["", f"Observed test fraud rate: {r['prevalence_test']:.5f}.", "", "## Sensitivity: test rows that do not appear in training", "", "| Model | Rows | Fraud | Average precision | Recall at threshold | FPR |", "|---|---|---|---|---|---|"]
    for k, v in m.items():
        u = v["unique_rows_only"]
        L.append(f"| {k} | {u['n']:,} | {u['fraud']} | {f(u['average_precision'])} | {f(u['recall'])} | {f(u['fpr'], 4)} |")
    dep = r["deployed"]
    L += ["", "## Selection and deployment", "", f"Rule fixed in advance: the model with the best validation average precision is deployed. Selected: **{dep['model_type']}**, Platt-calibrated on validation. Alert threshold: probability {dep['threshold_probability']:.5f}.", "",
          "## Limits (read before quoting any number)", "",
          "- Features V1 to V28 are anonymised PCA components; there are no customer ids, payee or device signals.",
          f"- The test period has only {d['fraud']['test']} fraud rows, so every interval is wide and differences between models can be noise.",
          "- Two days of European card transactions from 2013; results do not transfer to other portfolios.",
          "- A score estimates card fraud, not scams. Scam context comes from the simulator later and is labelled as simulated.", "",
          f"Libraries: " + ", ".join(f"{k} {v}" for k, v in r["libraries"].items()) + "."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
