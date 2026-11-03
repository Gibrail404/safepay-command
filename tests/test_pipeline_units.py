"""Unit tests for the parsing code. The tiny inputs here only test the parsers; no product data is ever hand-written."""
import io, zipfile
import pandas as pd
import pytest
from spellbreaker_data.builders import parse_sms, parse_sdn
from spellbreaker_data.manifest import check_expected
from spellbreaker_data.registry import Dataset, load_registry


def test_registry_is_complete_and_wellformed():
    reg = load_registry()
    assert {"ulb_creditcard", "sms_spam", "ofac_sdn", "elliptic"} <= set(reg)
    for d in reg.values():
        assert d.url.startswith("https://") and d.licence_note
    assert len(reg["ulb_creditcard"].md5) == 32


def test_parse_sms_splits_label_and_text(tmp_path):
    z = tmp_path / "s.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("SMSSpamCollection", "ham\tSee you at 5\nspam\tWIN a prize now, call 0800\n")
    df = parse_sms(z)
    assert list(df["is_spam"]) == [0, 1] and df.loc[1, "text"].startswith("WIN")


def test_parse_sdn_blanks_the_placeholder(tmp_path):
    p = tmp_path / "sdn.csv"
    p.write_text('36,"ACME TRADING LLC","-0-","SDGT","-0-","-0-","-0-","-0-","-0-","-0-","-0-","-0- "\n')
    df = parse_sdn(p)
    assert df.loc[0, "name"] == "ACME TRADING LLC" and df.loc[0, "sdn_type"] == ""


def test_expected_counts_are_enforced():
    ds = Dataset(name="x", title="x", role="x", url="https://x", format="csv", expected={"rows": 10})
    check_expected(ds, {"rows": 10})
    with pytest.raises(ValueError):
        check_expected(ds, {"rows": 9})
