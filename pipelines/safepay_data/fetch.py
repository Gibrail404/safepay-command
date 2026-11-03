from __future__ import annotations
import hashlib, json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .registry import Dataset, RAW

UA = {"User-Agent": "safepay-data/0.1 (portfolio project; reproducible download)"}


def _hash(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_dir(ds: Dataset) -> Path:
    return RAW / ds.name


def fetch(ds: Dataset, filename: str | None = None, force: bool = False) -> Path:
    """Download once, verify the md5 from the registry when there is one, and record sha256 and download time next to the file."""
    d = raw_dir(ds)
    d.mkdir(parents=True, exist_ok=True)
    name = filename or os.path.basename(ds.url.split("?")[0]) or f"{ds.name}.{ds.format}"
    dest = d / name
    if dest.exists() and not force:
        if ds.md5 and _hash(dest, "md5") != ds.md5:
            raise RuntimeError(f"{ds.name}: existing file fails the md5 check, delete {dest} and fetch again")
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(ds.url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if ds.md5 and _hash(tmp, "md5") != ds.md5:
        got = _hash(tmp, "md5")
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{ds.name}: md5 mismatch (expected {ds.md5}, got {got}); refusing to use this file")
    tmp.rename(dest)
    (d / "FETCH.json").write_text(json.dumps({
        "dataset": ds.name, "url": ds.url, "file": dest.name, "bytes": dest.stat().st_size,
        "sha256": _hash(dest, "sha256"), "md5_verified_against_registry": bool(ds.md5),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))
    return dest


def fetch_info(ds: Dataset) -> dict:
    p = raw_dir(ds) / "FETCH.json"
    return json.loads(p.read_text()) if p.exists() else {}
