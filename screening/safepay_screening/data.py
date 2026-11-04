"""Load the real OFAC tables and the real Census name lists produced by the data pipeline (data/processed)."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
ALIAS_TYPES = {"aka", "fka", "nka"}


def load_sdn() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "ofac_sdn.parquet")
    df["sdn_type"] = df["sdn_type"].replace("", "entity")
    return df


def load_aliases() -> pd.DataFrame:
    a = pd.read_parquet(PROCESSED / "ofac_alt.parquet")
    return a[a["alt_type"].isin(ALIAS_TYPES) & (a["alt_name"] != "")].reset_index(drop=True)


def primary_rows(sdn: pd.DataFrame) -> list[tuple[str, str, bool]]:
    return [(e, n, False) for e, n in zip(sdn["ent_num"], sdn["name"]) if n]


def alias_rows(aliases: pd.DataFrame) -> list[tuple[str, str, bool]]:
    return [(e, n, True) for e, n in zip(aliases["ent_num"], aliases["alt_name"])]


def compose_negative_names(n: int, seed: int) -> list[str]:
    """Real first names and real surnames drawn by frequency and paired at random. The parts are real; the pairing is synthetic."""
    rng = np.random.default_rng(seed)
    first = pd.concat([pd.read_parquet(PROCESSED / f"census_first_{g}.parquet") for g in ("male", "female")]).groupby("name", as_index=False)["percent"].sum()
    sur = pd.read_parquet(PROCESSED / "census_surnames.parquet")
    sur = sur[sur["count"] > 0]
    f = rng.choice(first["name"].to_numpy(), n, p=(first["percent"] / first["percent"].sum()).to_numpy())
    s = rng.choice(sur["name"].to_numpy(), n, p=(sur["count"] / sur["count"].sum()).to_numpy())
    return [f"{a.title()} {b.title()}" for a, b in zip(f, s)]
