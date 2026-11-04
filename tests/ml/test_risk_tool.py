"""The risk tool, first with a tiny hand-made model (exact arithmetic), then with the REAL trained model and the REAL ULB test period."""
import json
import math
import numpy as np
import pytest
from fastapi.testclient import TestClient
from safepay.api import create_app
from safepay.config import Settings
from safepay.risk_tool import PaymentFeatures, band_for, risk_tool, score_payment_risk
from safepay_ml.data import FEATURES
from safepay_ml.registry import MODELS_DIR, write_metadata, set_active


def make_tiny_model(base):
    names = [f for f in FEATURES]
    d = write_metadata("risk", "tiny", {"name": "risk", "version": "tiny", "model_type": "logreg", "features": names, "bands": {"elevated": 0.1, "high": 0.5},
                                        "calibrator": {"method": "platt", "params": {"a": 1.0, "b": 0.0}}}, base=base)
    coef = [0.0] * 28 + [1.0]                                         # only log_amount matters
    (d / "logreg.json").write_text(json.dumps({"mean": [0.0] * 29, "scale": [1.0] * 29, "coef": coef, "intercept": -5.0}))
    set_active("risk", "tiny", base=base)


def features(amount, **v):
    return PaymentFeatures(amount=amount, **{f"V{i}": v.get(f"V{i}", 0.0) for i in range(1, 29)})


def test_tiny_model_gives_the_hand_computed_probability_and_band(tmp_path):
    make_tiny_model(tmp_path)
    out = score_payment_risk(features(math.e ** 3 - 1), models_dir=tmp_path)       # log1p(amount) = 3 -> logit = 3 - 5 = -2
    assert out["risk_score"] == pytest.approx(1 / (1 + math.exp(2))) and out["risk_band"] == "elevated" and out["model_version"] == "tiny"
    assert score_payment_risk(features(0.0), models_dir=tmp_path)["risk_band"] == "low"
    assert score_payment_risk(features(math.e ** 6 - 1), models_dir=tmp_path)["risk_band"] == "high"


def test_band_boundaries_are_strict():
    b = {"elevated": 0.1, "high": 0.5}
    assert [band_for(p, b) for p in (0.0, 0.1, 0.1000001, 0.5, 0.5000001)] == ["low", "low", "elevated", "elevated", "high"]


def test_the_tool_rejects_bad_input(tmp_path):
    with pytest.raises(Exception):
        PaymentFeatures(amount=-1, **{f"V{i}": 0.0 for i in range(1, 29)})
    with pytest.raises(Exception):
        PaymentFeatures(amount=1.0)                                      # features missing


# ---------------- real model, real data ----------------
real = pytest.mark.integration
needs_model = pytest.mark.skipif(not (MODELS_DIR / "risk" / "active.json").exists(), reason="run: cd ml && python -m safepay_ml.train_risk")


@pytest.fixture(scope="module")
def real_parts():
    from safepay_ml.data import load_ulb, temporal_split
    return temporal_split(load_ulb())


@pytest.fixture(scope="module")
def report():
    from safepay_ml.data import ROOT
    return json.loads((ROOT / "docs" / "reports" / "risk_model.json").read_text())


@real
@needs_model
def test_the_saved_model_reproduces_the_reported_test_metric(real_parts, report):
    from safepay_ml.registry import load_model
    from safepay_ml import metrics as M
    model = load_model("risk")
    p = model.probability(real_parts["test"].X)
    reported = report["models"][model.meta["model_type"]]["test_average_precision"]
    assert M.average_precision(real_parts["test"].y, p) == pytest.approx(reported, abs=1e-9)


@real
@needs_model
def test_alerts_from_the_tool_match_the_reported_recall_on_real_test_frauds(real_parts, report):
    te = real_parts["test"].frame
    frauds = te[te["Class"] == 1]
    tool = risk_tool()
    bands = []
    for _, r in frauds.iterrows():
        args = PaymentFeatures(amount=float(r["Amount"]), **{f"V{i}": float(r[f"V{i}"]) for i in range(1, 29)})
        bands.append(tool.handler(args)["risk_band"])
    alerted = sum(b != "low" for b in bands)
    assert alerted == report["models"][report["deployed"]["model_type"]]["test_at_threshold"]["tp"]


@real
@needs_model
def test_a_real_fraud_row_flows_through_the_api_to_a_policy_decision(real_parts):
    te = real_parts["test"].frame
    app = create_app(Settings(tenants={"k": "t1"}))
    c = TestClient(app)
    H = {"X-API-Key": "k"}
    assert "score_payment_risk" in [t["name"] for t in c.get("/v1/tools", headers=H).json()]
    run = c.post("/v1/runs", json={"tools": ["score_payment_risk"]}, headers=H).json()
    found = None
    for i, (_, r) in enumerate(te[te["Class"] == 1].iterrows()):
        body = {"tool": "score_payment_risk", "args": {"amount": float(r["Amount"]), **{f"V{j}": float(r[f"V{j}"]) for j in range(1, 29)}}}
        res = c.post("/v1/tools/call", json=body, headers={**H, "X-Capability": run["capability"], "Idempotency-Key": f"score-{i}"}).json()
        assert res["status"] == "executed"
        if res["result"]["risk_band"] == "high":
            found = (res["result"], float(r["Amount"]))
            break
    assert found, "expected at least one real fraud row in the high band"
    result, amount = found
    d = c.post("/v1/decisions", json={"workload": "payment_risk", "subject": {"type": "payment", "id": "real-1"},
                                       "context": {"amount": amount, "risk_band": result["risk_band"]}}, headers={**H, "Idempotency-Key": "d1"}).json()
    assert d["outcome"] == "hold" and any(x["code"] == "MODEL_RISK_HIGH" for x in d["reasons"])
