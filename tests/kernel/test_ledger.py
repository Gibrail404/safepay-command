"""Invariant 3: any change to a past ledger record is detected."""
import json
from hypothesis import given, strategies as st
from sqlalchemy import delete, text
from safepay import ledger
from safepay.db import LedgerEntry, LedgerHead

json_values = st.recursive(st.none() | st.booleans() | st.integers(-10**9, 10**9) | st.text(max_size=20),
                           lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(min_size=1, max_size=6), c, max_size=3), max_leaves=8)


def fill(sf, tenant="t1", n=5):
    with sf.begin() as s:
        for i in range(n):
            ledger.append(s, tenant, "decision", {"i": i, "amount": 100 + i}, ts=f"2026-11-04T10:00:0{i}.000000+00:00")


def test_clean_chain_verifies(sf):
    fill(sf)
    with sf() as s:
        r = ledger.verify(s, "t1")
    assert r.ok and r.checked == 5


def test_empty_ledger_verifies(sf):
    with sf() as s:
        assert ledger.verify(s, "nobody").ok


def test_editing_a_payload_is_detected_at_that_record(sf):
    fill(sf)
    with sf.begin() as s:
        s.execute(text("UPDATE ledger_entries SET payload = :p WHERE seq = 3"), {"p": json.dumps({"i": 2, "amount": 1})})
    with sf() as s:
        r = ledger.verify(s, "t1")
    assert not r.ok and r.bad_seq == 3 and "hash" in r.reason


def test_deleting_a_middle_record_is_detected(sf):
    fill(sf)
    with sf.begin() as s:
        s.execute(delete(LedgerEntry).where(LedgerEntry.seq == 3))
    with sf() as s:
        r = ledger.verify(s, "t1")
    assert not r.ok and r.bad_seq == 4


def test_deleting_the_last_record_is_detected_by_the_head(sf):
    fill(sf)
    with sf.begin() as s:
        s.execute(delete(LedgerEntry).where(LedgerEntry.seq == 5))
    with sf() as s:
        r = ledger.verify(s, "t1")
    assert not r.ok and "head" in r.reason


def test_a_forged_but_correctly_hashed_tail_record_is_detected(sf):
    fill(sf)
    with sf.begin() as s:
        last = s.get(LedgerHead, "t1")
        payload = ledger.canonical_json({"forged": True})
        ts = "2026-11-04T11:00:00.000000+00:00"
        h = ledger.entry_hash(last.head_hash, "t1", "decision", ts, payload)
        s.add(LedgerEntry(tenant="t1", kind="decision", payload=payload, ts=ts, prev_hash=last.head_hash, hash=h))   # head not updated
    with sf() as s:
        r = ledger.verify(s, "t1")
    assert not r.ok and "head" in r.reason


def test_tenants_have_separate_chains(sf):
    fill(sf, "a", 3); fill(sf, "b", 3)
    with sf.begin() as s:
        s.execute(text("UPDATE ledger_entries SET payload = '{}' WHERE tenant = 'a' AND seq = 2"))
    with sf() as s:
        assert not ledger.verify(s, "a").ok
        assert ledger.verify(s, "b").ok


@given(json_values)
def test_canonical_json_is_stable_under_key_order(v):
    a = ledger.canonical_json(v)
    assert json.loads(a) == v
    assert ledger.canonical_json(json.loads(a)) == a


def test_canonical_json_rejects_nan():
    import pytest
    with pytest.raises(ValueError):
        ledger.canonical_json({"x": float("nan")})
