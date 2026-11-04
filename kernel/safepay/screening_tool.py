"""screen_name: a T0 (read-only) tool that screens a name against the OFAC list and its aliases and returns a band that policies can use.
As with the risk tool, policies read the band (none, review, strong), never the raw score, so re-tuning thresholds never silently moves a rule.
The thresholds come from config/screening_bands.json, which is generated from the evaluation on validation names (see scripts/eval_screening.py)."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel, Field
from .tools import Tool, ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
BANDS_PATH = ROOT / "config" / "screening_bands.json"


class ScreenInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class _Cache:
    index = None
    meta: dict = {}
    key: tuple | None = None


def band_for(score: float, bands: dict) -> str:
    if score >= bands["strong"]:
        return "strong"
    if score >= bands["review"]:
        return "review"
    return "none"


def _load(bands_path: Path):
    from safepay_screening.data import alias_rows, load_aliases, load_sdn, primary_rows       # imported lazily: only a serving process that screens pays for it
    from safepay_screening.matcher import NameIndex
    bands = json.loads(bands_path.read_text())
    key = (str(bands_path), bands["list_sha256"], bands["fold_level"])
    if _Cache.key != key:
        sdn = load_sdn()
        _Cache.index = NameIndex(primary_rows(sdn) + alias_rows(load_aliases()), fold_level=bands["fold_level"])
        _Cache.meta = {"bands": bands, "entries": {e: {"sdn_type": t, "program": p} for e, t, p in zip(sdn["ent_num"], sdn["sdn_type"], sdn["program"])}}
        _Cache.key = key
    return _Cache.index, _Cache.meta


def screen_name(args: BaseModel, bands_path: Path = BANDS_PATH) -> dict:
    index, meta = _load(bands_path)
    hits = index.search(args.name, top=3)
    top = hits[0].score if hits else 0.0
    return {"screen_band": band_for(top, meta["bands"]), "top_score": top, "list_version": meta["bands"]["list_sha256"][:12],
            "hits": [{"ent_num": h.ent_num, "matched_name": h.matched_name, "is_alias": h.is_alias, "score": h.score, **meta["entries"].get(h.ent_num, {})} for h in hits]}


def screening_tool(bands_path: Path = BANDS_PATH) -> Tool:
    return Tool(name="screen_name", tier="T0", input_model=ScreenInput, handler=lambda a: screen_name(a, bands_path))


def register_if_available(registry: ToolRegistry, bands_path: Path = BANDS_PATH) -> bool:
    """Registers the tool only when the bands file and the processed OFAC data exist, so a fresh checkout still starts."""
    try:
        from safepay_screening.data import PROCESSED
    except ImportError:
        return False
    if bands_path.exists() and (PROCESSED / "ofac_alt.parquet").exists() and registry.get("screen_name") is None:
        registry.register(screening_tool(bands_path))
        return True
    return False
