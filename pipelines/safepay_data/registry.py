from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REGISTRY_PATH = ROOT / "data" / "registry.yaml"


@dataclass(frozen=True)
class Dataset:
    name: str
    title: str
    role: str
    url: str
    format: str
    md5: str | None = None
    expected: dict = field(default_factory=dict)
    licence_note: str = ""
    citation: str = ""
    caveat: str = ""


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Dataset]:
    raw = yaml.safe_load(path.read_text())
    out: dict[str, Dataset] = {}
    for name, d in raw["datasets"].items():
        out[name] = Dataset(name=name, title=d["title"], role=d["role"], url=d["url"], format=d["format"], md5=d.get("md5"),
                            expected=d.get("expected", {}), licence_note=d.get("licence_note", ""), citation=d.get("citation", ""), caveat=d.get("caveat", ""))
    return out
