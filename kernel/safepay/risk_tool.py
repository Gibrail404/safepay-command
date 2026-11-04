"""score_payment_risk: a T0 (read-only) tool that scores a card transaction with the ACTIVE trained model and returns a calibrated probability
plus a band that policies can use. Policies read the band, not the raw probability, so retraining or recalibrating never silently moves a rule."""
from __future__ import annotations
import math
from pathlib import Path
from pydantic import BaseModel, Field, create_model
import numpy as np
from .tools import Tool, ToolRegistry

V_FIELDS = {f"V{i}": (float, Field(...)) for i in range(1, 29)}
PaymentFeatures = create_model("PaymentFeatures", amount=(float, Field(..., ge=0)), **V_FIELDS)   # the 28 anonymised components plus the amount


class _Cache:
    model = None
    key: tuple | None = None


def _load(models_dir: Path | None):
    from safepay_ml.registry import MODELS_DIR, active_version, load_model     # imported lazily: only a serving process that needs a model pays for it
    base = models_dir or MODELS_DIR
    key = (str(base), active_version("risk", base))
    if _Cache.key != key:
        _Cache.model, _Cache.key = load_model("risk", key[1], base), key
    return _Cache.model


def band_for(probability: float, bands: dict) -> str:
    """Strictly above the threshold, the same rule the evaluation report uses for its alerts (score > threshold)."""
    if probability > bands["high"]:
        return "high"
    if probability > bands["elevated"]:
        return "elevated"
    return "low"


def score_payment_risk(args: BaseModel, models_dir: Path | None = None) -> dict:
    model = _load(models_dir)
    d = args.model_dump()
    row = np.array([[d[f] for f in model.meta["features"] if f != "log_amount"] + [math.log1p(d["amount"])]], dtype=np.float32)
    p = float(model.probability(row)[0])
    return {"risk_score": p, "risk_band": band_for(p, model.meta["bands"]), "model_version": model.meta["version"], "model_type": model.meta["model_type"]}


def risk_tool(models_dir: Path | None = None) -> Tool:
    return Tool(name="score_payment_risk", tier="T0", input_model=PaymentFeatures, handler=lambda a: score_payment_risk(a, models_dir))


def register_if_available(registry: ToolRegistry, models_dir: Path | None = None) -> bool:
    """Registers the tool only when a trained model exists, so a fresh checkout still starts."""
    from safepay_ml.registry import MODELS_DIR
    if (Path(models_dir or MODELS_DIR) / "risk" / "active.json").exists() and registry.get("score_payment_risk") is None:
        registry.register(risk_tool(models_dir))
        return True
    return False
