"""Integration tests: they read the REAL processed data and its generated manifests. Run `python -m safepay_data all` first."""
import json
import pandas as pd
import pytest
from safepay_data.registry import PROCESSED, load_registry

pytestmark = pytest.mark.integration
REG = load_registry()


def manifest(name):
    p = PROCESSED / f"{name}.manifest.json"
    if not p.exists():
        pytest.skip(f"{name} not built; run python -m safepay_data {name}")
    return json.loads(p.read_text())


def test_ulb_matches_the_published_counts():
    m = manifest("ulb_creditcard")
    df = pd.read_parquet(PROCESSED / "ulb_creditcard.parquet")
    assert len(df) == REG["ulb_creditcard"].expected["rows"] == m["rows"]
    assert int(df["Class"].sum()) == REG["ulb_creditcard"].expected["positives"]
    assert {"Time", "Amount", "Class"} <= set(df.columns) and sum(c.startswith("V") for c in df.columns) == 28
    assert m["provenance"]["kind"] == "real" and m["source_sha256"] and m["downloaded_at"]


def test_sms_is_real_text_with_both_classes():
    m = manifest("sms_spam")
    df = pd.read_parquet(PROCESSED / "sms_spam.parquet")
    assert len(df) == 5574 and df["is_spam"].nunique() == 2 and df["text"].str.len().min() > 0
    assert "CC BY 4.0" in m["provenance"]["licence_note"]


def test_ofac_list_looks_like_the_sdn_list():
    m = manifest("ofac_sdn")
    df = pd.read_parquet(PROCESSED / "ofac_sdn.parquet")
    assert len(df) > 10000 and (df["name"] != "").mean() > 0.99
    assert set(m["stats"]["types"]) >= {"individual", "entity", "vessel"}
    assert "NOT confirmed" in m["provenance"]["licence_note"]


def test_every_manifest_has_a_hash_and_provenance():
    for name in ("ulb_creditcard", "sms_spam", "ofac_sdn"):
        m = manifest(name)
        assert m["parquet_sha256"] and m["provenance"]["source_url"].startswith("https://") and m["generated_at"]
