"""Only meaningful on PostgreSQL (real row locks and unique constraints). Skipped on in-memory SQLite.
Run with: SAFEPAY_TEST_DATABASE_URL=postgresql+psycopg://safepay:safepay_dev_only@127.0.0.1:5433/safepay_test"""
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import func, select
from conftest import TEST_DB_URL
from safepay import ledger
from safepay.db import DecisionRow, LedgerEntry, init_db
from safepay.decisions import DecisionRequest, DecisionService
from test_decisions import req
from test_policy import make_policy

pytestmark = pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"), reason="needs PostgreSQL")


def test_parallel_appends_keep_one_unbroken_chain(sf):
    def work(i):
        for j in range(10):
            with sf.begin() as s:
                ledger.append(s, "t1", "decision", {"worker": i, "n": j})
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(work, range(8)))
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(LedgerEntry)) == 80
        r = ledger.verify(s, "t1")
    assert r.ok and r.checked == 80


def test_parallel_requests_with_one_idempotency_key_have_one_effect(sf):
    svc = DecisionService(sf, lambda t, w: make_policy())
    def go(_):
        try:
            return svc.decide("t1", "same-key", req())[0].decision_id
        except Exception as e:                      # a loser of the race may see an integrity error; it must not create a second decision
            return f"error:{type(e).__name__}"
    with ThreadPoolExecutor(8) as ex:
        out = list(ex.map(go, range(8)))
    ids = {o for o in out if not o.startswith("error:")}
    with sf() as s:
        assert s.scalar(select(func.count()).select_from(DecisionRow)) == 1
        assert s.scalar(select(func.count()).select_from(LedgerEntry)) == 1
        assert ledger.verify(s, "t1").ok
    assert len(ids) == 1
