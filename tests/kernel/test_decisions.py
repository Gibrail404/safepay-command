"""Invariants 2 (replay reproduces the outcome) and 6 (one idempotency key, one effect)."""
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import func, select, text
from safepay import ledger
from safepay.db import DecisionRow, LedgerEntry, init_db, make_engine
from safepay.decisions import DecisionRequest, DecisionService, IdempotencyConflict, NotFound, PolicyIntegrityError
from safepay.policy import Cond, Policy, Rule
from test_policy import C, make_policy


def service(sf):
    return DecisionService(sf, lambda tenant, workload: make_policy())


def req(amount=4800, age=0, mode="enforce"):
    return DecisionRequest(workload="payment_risk", subject={"type": "payment", "id": "p1"}, context={"amount": amount, "payee_age_days": age}, mode=mode)


def count(sf, model):
    with sf() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_a_decision_is_stored_and_ledgered(sf):
    d, replayed = service(sf).decide("t1", "k1", req())
    assert not replayed and d.outcome == "hold" and d.decision_id.startswith("d_")
    assert count(sf, DecisionRow) == 1 and count(sf, LedgerEntry) == 1
    with sf() as s:
        assert ledger.verify(s, "t1").ok


def test_same_key_same_request_returns_the_same_decision_with_no_second_effect(sf):
    svc = service(sf)
    a, r1 = svc.decide("t1", "k1", req())
    b, r2 = svc.decide("t1", "k1", req())
    assert (r1, r2) == (False, True) and a == b
    assert count(sf, DecisionRow) == 1 and count(sf, LedgerEntry) == 1


def test_same_key_different_request_is_a_conflict(sf):
    svc = service(sf)
    svc.decide("t1", "k1", req(4800))
    with pytest.raises(IdempotencyConflict):
        svc.decide("t1", "k1", req(10))
    assert count(sf, DecisionRow) == 1


def test_keys_are_scoped_per_tenant(sf):
    svc = service(sf)
    a, _ = svc.decide("t1", "k1", req())
    b, replayed = svc.decide("t2", "k1", req())
    assert not replayed and a.decision_id != b.decision_id


def test_a_tenant_cannot_read_another_tenants_decision(sf):
    svc = service(sf)
    a, _ = svc.decide("t1", "k1", req())
    with pytest.raises(NotFound):
        svc.get("t2", a.decision_id)
    with pytest.raises(NotFound):
        svc.replay("t2", a.decision_id)


def test_shadow_decisions_are_recorded_with_their_mode(sf):
    d, _ = service(sf).decide("t1", "k1", req(mode="shadow"))
    assert d.mode == "shadow"


def test_replay_reproduces_the_decision(sf):
    svc = service(sf)
    d, _ = svc.decide("t1", "k1", req())
    r = svc.replay("t1", d.decision_id)
    assert r.same and r.original_outcome == r.recomputed_outcome == "hold"


def test_replay_still_works_after_the_live_policy_changes(sf):
    live = {"p": make_policy()}
    svc = DecisionService(sf, lambda t, w: live["p"])
    d, _ = svc.decide("t1", "k1", req())
    live["p"] = Policy(name="test", rules=[Rule(id="r1", code="NOTHING", when=C(field="amount", op=">", value=10**9), outcome="warn")])
    assert svc.decide("t1", "k2", req())[0].outcome == "allow"
    assert svc.replay("t1", d.decision_id).same          # the old decision replays against its own snapshot


def test_a_tampered_policy_snapshot_is_refused(sf):
    svc = service(sf)
    d, _ = svc.decide("t1", "k1", req())
    with sf.begin() as s:
        s.execute(text("UPDATE policies SET content = replace(content, '4000', '9000')"))
    with pytest.raises(PolicyIntegrityError):
        svc.replay("t1", d.decision_id)


@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
@given(st.integers(0, 10000), st.integers(0, 400))
def test_replay_is_deterministic_for_any_request(sf, amount, age):
    svc = service(sf)
    key = f"k-{amount}-{age}"
    d, _ = svc.decide("t1", key, req(amount, age))
    assert svc.replay("t1", d.decision_id).same
