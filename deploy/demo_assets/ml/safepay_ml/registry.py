"""A small model registry on disk: models/<name>/<version>/ holds the files and a metadata.json; models/<name>/active.json points at one version."""
from __future__ import annotations
import json
from pathlib import Path
from .data import ROOT
from .scorers import LOADERS
from .calibration import Calibrator

MODELS_DIR = ROOT / "models"


def version_dir(name: str, version: str, base: Path = MODELS_DIR) -> Path:
    return base / name / version


def write_metadata(name: str, version: str, meta: dict, base: Path = MODELS_DIR) -> Path:
    d = version_dir(name, version, base)
    d.mkdir(parents=True, exist_ok=True)
    (d / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, default=str))
    return d


def set_active(name: str, version: str, base: Path = MODELS_DIR) -> None:
    if not (version_dir(name, version, base) / "metadata.json").exists():
        raise FileNotFoundError(f"{name}@{version} has no metadata.json")
    (base / name / "active.json").write_text(json.dumps({"version": version}))


def active_version(name: str, base: Path = MODELS_DIR) -> str:
    return json.loads((base / name / "active.json").read_text())["version"]


def load_metadata(name: str, version: str | None = None, base: Path = MODELS_DIR) -> dict:
    version = version or active_version(name, base)
    return json.loads((version_dir(name, version, base) / "metadata.json").read_text())


class LoadedModel:
    def __init__(self, meta: dict, scorer, calibrator: Calibrator):
        self.meta, self.scorer, self.calibrator = meta, scorer, calibrator

    def probability(self, X) -> "object":
        return self.calibrator.apply(self.scorer.raw(X))


def load_model(name: str, version: str | None = None, base: Path = MODELS_DIR) -> LoadedModel:
    version = version or active_version(name, base)
    d = version_dir(name, version, base)
    meta = json.loads((d / "metadata.json").read_text())
    scorer = LOADERS[meta["model_type"]](d)
    return LoadedModel(meta, scorer, Calibrator.from_json(meta["calibrator"]))
