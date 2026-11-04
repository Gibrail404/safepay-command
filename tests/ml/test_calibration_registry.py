import json
import numpy as np
import pytest
from safepay_ml.calibration import Calibrator, fit_isotonic, fit_platt, logit, sigmoid
from safepay_ml import metrics as M
from safepay_ml.registry import active_version, load_metadata, load_model, set_active, write_metadata
from safepay_ml.scorers import LogRegScorer


def overconfident_scores(n=20000, seed=0):
    """True risk p, but the model reports a stretched, overconfident logit."""
    rng = np.random.default_rng(seed)
    z_true = rng.normal(-3, 1.5, n)
    y = (rng.uniform(size=n) < sigmoid(z_true)).astype(int)
    return 2.5 * z_true + 1.0, y


def test_platt_scaling_repairs_an_overconfident_model():
    z, y = overconfident_scores()
    half = len(z) // 2
    cal = fit_platt(z[:half], y[:half])
    before, after = M.ece(y[half:], sigmoid(z[half:])), M.ece(y[half:], cal.apply(z[half:]))
    assert after < before and after < 0.01
    assert M.log_loss(y[half:], cal.apply(z[half:])) < M.log_loss(y[half:], sigmoid(z[half:]))


def test_isotonic_is_monotone_and_bounded():
    z, y = overconfident_scores()
    cal = fit_isotonic(z, y)
    grid = np.linspace(z.min() - 5, z.max() + 5, 500)
    p = cal.apply(grid)
    assert np.all(np.diff(p) >= -1e-12) and p.min() >= 0 and p.max() <= 1


def test_calibrators_survive_a_json_round_trip():
    z, y = overconfident_scores(4000)
    for cal in (fit_platt(z, y), fit_isotonic(z, y)):
        back = Calibrator.from_json(json.loads(json.dumps(cal.to_json())))
        assert np.allclose(cal.apply(z[:50]), back.apply(z[:50]))


def test_logit_and_sigmoid_are_inverse_and_safe_at_the_edges():
    p = np.array([1e-6, 0.2, 0.5, 0.9])
    assert np.allclose(sigmoid(logit(p)), p, atol=1e-9)
    assert np.isfinite(logit(np.array([0.0, 1.0]))).all()


def test_logreg_scorer_matches_a_hand_computed_value():
    s = LogRegScorer({"mean": [1.0, 2.0], "scale": [2.0, 4.0], "coef": [0.5, -1.0], "intercept": 0.25})
    # x = [3, 6] -> standardised [1, 1] -> 0.5 - 1.0 + 0.25 = -0.25
    assert s.raw(np.array([[3.0, 6.0]]))[0] == pytest.approx(-0.25)


def test_registry_round_trip_and_active_pointer(tmp_path):
    params = {"mean": [0.0], "scale": [1.0], "coef": [1.0], "intercept": 0.0}
    d = write_metadata("risk", "v1", {"name": "risk", "version": "v1", "model_type": "logreg", "calibrator": {"method": "platt", "params": {"a": 1.0, "b": 0.0}}}, base=tmp_path)
    (d / "logreg.json").write_text(json.dumps(params))
    with pytest.raises(FileNotFoundError):
        set_active("risk", "does-not-exist", base=tmp_path)
    set_active("risk", "v1", base=tmp_path)
    assert active_version("risk", base=tmp_path) == "v1" and load_metadata("risk", base=tmp_path)["model_type"] == "logreg"
    model = load_model("risk", base=tmp_path)
    assert model.probability(np.array([[0.0]]))[0] == pytest.approx(0.5)
    assert model.probability(np.array([[10.0]]))[0] > 0.99
