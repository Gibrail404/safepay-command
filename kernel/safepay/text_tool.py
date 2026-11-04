"""classify_text: a T0 (read-only) tool that scores a message with the ACTIVE scam-like text model. Pure numpy: it loads neither LightGBM nor PyTorch.
The message is UNTRUSTED input. It is never sent to an LLM here, and the explanation terms returned are restricted to the model's own vocabulary, so a
sentence an attacker planted in the text cannot be echoed back through this tool."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from .tools import Tool, ToolRegistry


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class _Cache:
    model = None
    key: tuple | None = None


def _load(models_dir: Path | None):
    from safepay_ml.registry import MODELS_DIR, active_version, load_model
    base = models_dir or MODELS_DIR
    key = (str(base), active_version("text_scam", base))
    if _Cache.key != key:
        _Cache.model, _Cache.key = load_model("text_scam", key[1], base), key
    return _Cache.model


def classify_text(args: TextIn, models_dir: Path | None = None) -> dict:
    model = _load(models_dir)
    p = float(model.probability([args.text])[0])
    return {"scam_text_score": p, "text_band": "suspicious" if p > model.meta["bands"]["elevated"] else "normal",
            "top_terms": model.scorer.top_terms(args.text), "model_version": model.meta["version"]}


def text_tool(models_dir: Path | None = None) -> Tool:
    return Tool(name="classify_text", tier="T0", input_model=TextIn, handler=lambda a: classify_text(a, models_dir))


def register_if_available(registry: ToolRegistry, models_dir: Path | None = None) -> bool:
    from safepay_ml.registry import MODELS_DIR
    if (Path(models_dir or MODELS_DIR) / "text_scam" / "active.json").exists() and registry.get("classify_text") is None:
        registry.register(text_tool(models_dir))
        return True
    return False
