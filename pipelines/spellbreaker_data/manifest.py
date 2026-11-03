from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from . import __version__
from .registry import Dataset, PROCESSED
from .fetch import fetch_info


def write_processed(ds: Dataset, df: pd.DataFrame, stats: dict) -> dict:
    """Write parquet plus a generated manifest. The manifest is what the UI's provenance chips read; nobody types it."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pq = PROCESSED / f"{ds.name}.parquet"
    df.to_parquet(pq, index=False)
    info = fetch_info(ds)
    manifest = {
        "dataset": ds.name, "title": ds.title, "provenance": {"kind": "real", "source_url": ds.url, "licence_note": ds.licence_note, "citation": ds.citation, "caveat": ds.caveat},
        "source_sha256": info.get("sha256"), "downloaded_at": info.get("downloaded_at"),
        "rows": int(len(df)), "columns": list(map(str, df.columns)), "stats": stats,
        "parquet_sha256": hashlib.sha256(pq.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pipeline_version": __version__,
    }
    (PROCESSED / f"{ds.name}.manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def check_expected(ds: Dataset, actual: dict) -> None:
    bad = {k: (v, actual.get(k)) for k, v in ds.expected.items() if actual.get(k) != v}
    if bad:
        raise ValueError(f"{ds.name}: data does not match the registry (expected, actual): {bad}")
