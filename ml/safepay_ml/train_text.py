"""Train and evaluate the scam-like text model on the REAL UCI SMS Spam Collection and write a generated report.
Run:  python -m safepay_ml.train_text
Rules fixed in advance: exact-duplicate messages are removed before splitting; the regularisation strength is chosen by VALIDATION average
precision; Platt calibration is fitted on validation; the alert threshold lets 1% of validation non-spam messages alert. Test is touched once."""
from __future__ import annotations
import hashlib, json, platform, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from . import __version__, metrics as M
from .calibration import fit_platt, sigmoid
from .data import ROOT
from .registry import set_active, version_dir, write_metadata
from .text_model import TfidfLogRegScorer
from .timing import latency_ms

SMS_PARQUET = ROOT / "data" / "processed" / "sms_spam.parquet"
SMS_MANIFEST = ROOT / "data" / "processed" / "sms_spam.manifest.json"
REPORT_DIR = ROOT / "docs" / "reports"
C_GRID = [0.3, 1.0, 3.0, 10.0, 30.0]
FPR_TARGET, BOOT_N, SEED = 0.01, 1000, 0


def load_split():
    df = pd.read_parquet(SMS_PARQUET)
    df["key"] = df["text"].str.lower().str.strip()
    conflicts = int(df.groupby("key")["is_spam"].nunique().gt(1).sum())
    raw_rows = len(df)
    df = df.drop_duplicates("key", keep="first").reset_index(drop=True)
    train, rest = train_test_split(df, test_size=0.4, random_state=SEED, stratify=df["is_spam"])
    val, test = train_test_split(rest, test_size=0.5, random_state=SEED, stratify=rest["is_spam"])
    return df, train, val, test, {"raw_rows": raw_rows, "after_dedup": len(df), "removed_duplicates": raw_rows - len(df), "label_conflicts_among_duplicates": conflicts}


def main() -> dict:
    t0 = time.time()
    df, tr, va, te, dedup = load_split()
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, lowercase=True)
    Xtr, Xva, Xte = vec.fit_transform(tr["text"]), vec.transform(va["text"]), vec.transform(te["text"])
    ytr, yva, yte = tr["is_spam"].to_numpy(), va["is_spam"].to_numpy(), te["is_spam"].to_numpy()

    grid = []
    for C in C_GRID:
        lr = LogisticRegression(C=C, max_iter=2000).fit(Xtr, ytr)
        grid.append({"C": C, "val_ap": M.average_precision(yva, lr.decision_function(Xva)), "model": lr})
    best = max(grid, key=lambda g: g["val_ap"])
    lr = best["model"]
    params = TfidfLogRegScorer.from_sklearn(vec, lr)
    scorer = TfidfLogRegScorer(params)

    z_val, z_test = scorer.raw(va["text"]), scorer.raw(te["text"])
    check = float(np.max(np.abs(z_test - lr.decision_function(Xte))))             # the numpy scorer must equal scikit-learn
    assert check < 1e-9, f"numpy scorer differs from scikit-learn by {check}"

    cv = CountVectorizer(ngram_range=(1, 2), min_df=2).fit(tr["text"])
    nb = MultinomialNB().fit(cv.transform(tr["text"]), ytr)
    log_odds = lambda texts: (lambda lp: lp[:, 1] - lp[:, 0])(nb.predict_log_proba(cv.transform(texts)))
    nb_val, nb_test = log_odds(va["text"]), log_odds(te["text"])

    def block(zv, zt):
        thr = M.fpr_threshold(zv[yva == 0], FPR_TARGET)
        c = M.confusion_at(yte, zt, thr)
        lo, hi = M.bootstrap_ci(M.average_precision, yte, zt, n=BOOT_N, seed=1)
        rl, rh = M.bootstrap_ci(lambda y, s: M.confusion_at(y, s, thr)["recall"], yte, zt, n=BOOT_N, seed=2)
        return {"val_ap": M.average_precision(yva, zv), "test_ap": M.average_precision(yte, zt), "test_ap_ci95": [lo, hi], "test_roc_auc": M.roc_auc(yte, zt),
                "threshold_logit": thr, "test_at_threshold": c, "test_recall_ci95": [rl, rh]}

    res = {"tfidf_logreg": block(z_val, z_test), "naive_bayes_baseline": block(nb_val, nb_test)}
    platt = fit_platt(z_val, yva)
    p_test = platt.apply(z_test)
    cal = {"raw": sigmoid(z_test), "platt": p_test}
    cal_metrics = {k: {"brier": M.brier(yte, p), "log_loss": M.log_loss(yte, p), "ece_quantile10": M.ece(yte, p, 10), "mean_predicted": float(p.mean())} for k, p in cal.items()}
    thr_logit = res["tfidf_logreg"]["threshold_logit"]
    thr_prob = float(platt.apply(np.array([thr_logit]))[0])
    lat = latency_ms(lambda t: scorer.raw_one(t), te["text"].iloc[0])

    src = json.loads(SMS_MANIFEST.read_text())
    spec = {"data": src["parquet_sha256"], "c_grid": C_GRID, "seed": SEED, "code": __version__}
    version = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    d = version_dir("text_scam", version)
    d.mkdir(parents=True, exist_ok=True)
    (d / "tfidf_logreg.json").write_text(json.dumps(params))
    meta = {"name": "text_scam", "version": version, "model_type": "tfidf_logreg", "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "calibrator": platt.to_json(), "bands": {"elevated": thr_prob}, "alert_threshold_probability": thr_prob,
            "selection_rule": "C chosen by validation average precision; Platt on validation; threshold = 1% validation FPR", "chosen_C": best["C"],
            "data": {"source": "UCI SMS Spam Collection (CC BY 4.0)", "parquet_sha256": src["parquet_sha256"], **dedup,
                     "rows": {"train": len(tr), "val": len(va), "test": len(te)}, "spam": {"train": int(ytr.sum()), "val": int(yva.sum()), "test": int(yte.sum())}},
            "libraries": {"python": platform.python_version(), "numpy": np.__version__, "scikit-learn": sklearn.__version__},
            "limitations": ["General SMS spam (promotions, prizes, premium-rate lines), not payment scams specifically.", "Short, mostly English SMS; not tested on other channels or languages.",
                            "Stratified random split (no timestamps in the data), so a drift test is not possible."]}
    write_metadata("text_scam", version, meta)
    set_active("text_scam", version)

    report = {"generated_at": meta["trained_at"], "version": version, "seconds": round(time.time() - t0, 1), "data": meta["data"], "dedup": dedup, "chosen_C": best["C"],
              "c_grid": [{"C": g["C"], "val_ap": g["val_ap"]} for g in grid], "models": res, "calibration_test": cal_metrics, "threshold_probability": thr_prob,
              "numpy_vs_sklearn_max_abs_diff": check, "latency_single_message": lat, "vocabulary_size": len(params["vocab"]), "libraries": meta["libraries"], "prevalence_test": float(yte.mean())}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "text_model.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    (REPORT_DIR / "text_model.md").write_text(render(report))
    print(f"version {version} C={best['C']} test AP {res['tfidf_logreg']['test_ap']:.3f} in {report['seconds']}s")
    return report


def f(x, nd=3):
    return f"{x:.{nd}f}"


def render(r: dict) -> str:
    d, m = r["data"], r["models"]
    L = ["# Scam-like text model: generated report", "", f"Generated by `python -m safepay_ml.train_text` on {r['generated_at']} (version `{r['version']}`, {r['seconds']} s). Every number is produced by that command from the real UCI SMS Spam Collection. Do not edit by hand.", "",
         "## Data", "", f"{r['dedup']['raw_rows']:,} messages; {r['dedup']['removed_duplicates']} exact duplicates removed before splitting (so a message cannot sit in both train and test); {r['dedup']['label_conflicts_among_duplicates']} duplicated messages carried conflicting labels. After removal: {r['dedup']['after_dedup']:,}.", "",
         "| Split | Messages | Spam | Spam rate |", "|---|---|---|---|"]
    for k in ("train", "val", "test"):
        L.append(f"| {k} | {d['rows'][k]:,} | {d['spam'][k]} | {d['spam'][k] / d['rows'][k]:.2%} |")
    L += ["", "Split: stratified random (this dataset has no timestamps). Regularisation chosen on validation:", "", "| C | Validation AP |", "|---|---|"] + [f"| {g['C']} | {f(g['val_ap'], 4)} |" for g in r["c_grid"]]
    L += ["", f"Chosen C = {r['chosen_C']}. Vocabulary: {r['vocabulary_size']:,} terms (single words and word pairs).", "", "## Test results", "", f"Random scoring would give average precision equal to the spam rate ({r['prevalence_test']:.2%}).", "",
          "| Model | Test AP (95% CI) | Test ROC-AUC | Recall at 1% FPR (95% CI) | Test FPR | Test precision | Spam caught / total |", "|---|---|---|---|---|---|---|"]
    for k, v in m.items():
        c = v["test_at_threshold"]
        L.append(f"| {k} | {f(v['test_ap'], 4)} ({f(v['test_ap_ci95'][0], 4)} to {f(v['test_ap_ci95'][1], 4)}) | {f(v['test_roc_auc'], 4)} | {f(c['recall'])} ({f(v['test_recall_ci95'][0])} to {f(v['test_recall_ci95'][1])}) | {f(c['fpr'], 4)} | {f(c['precision'])} | {c['tp']} / {c['tp'] + c['fn']} |")
    L += ["", "The naive Bayes row is a comparison only; the deployed model is the TF-IDF logistic regression because it has a pure-numpy scorer.", "", "## Calibration on test", "", "| Calibration | Brier | Log loss | ECE (quantile, 10 bins) | Mean predicted |", "|---|---|---|---|---|"]
    for k, v in r["calibration_test"].items():
        L.append(f"| {k} | {v['brier']:.5f} | {v['log_loss']:.4f} | {v['ece_quantile10']:.5f} | {v['mean_predicted']:.4f} |")
    L += ["", f"Observed test spam rate: {r['prevalence_test']:.4f}. Alert threshold: calibrated probability {r['threshold_probability']:.4f}.", "", "## Engineering checks", "",
          f"- The pure-numpy scorer differs from scikit-learn's pipeline by at most {r['numpy_vs_sklearn_max_abs_diff']:.2e} on the test messages.",
          f"- Single-message latency: p50 {r['latency_single_message']['p50_ms']:.3f} ms, p95 {r['latency_single_message']['p95_ms']:.3f} ms.", "",
          "## Limits (read before quoting any number)", "", "- General SMS spam (promotions, prizes, premium-rate lines), not payment scams. It is a weak proxy signal for scam-like wording.",
          "- Short, mostly English messages; not tested on other channels or languages.", "- The test set is small, so intervals matter.", "- A random split cannot test drift.", "",
          "Libraries: " + ", ".join(f"{k} {v}" for k, v in r["libraries"].items()) + "."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
