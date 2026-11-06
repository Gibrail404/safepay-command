"""Invariants 1 (no T2/T3 without approval or rule) and 7 (shadow mode has no side effects), plus capability checks and idempotency."""
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from hypothesis import given, settings, strategies as st
from pydantic import BaseModel
from safepay import ledger
from conftest import TEST_DB_URL
from safepay.db import ApprovalRow, ToolCallRow, init_db, make_engine
from safepay.tools import CapabilityError, Tool, ToolGateway, ToolRegistry, mint_capability, verify_capability

SECRET = b"test-secret-not-for-production"


class Args(BaseModel):
    payment_id: str


def build(sf):
    calls = {"n": 0}

    def handler(a: Args) -> dict:
        calls["n"] += 1
        return {"ok": True, "payment_id": a.payment_id}

    reg = ToolRegistry()
    for tier in ("T0", "T1", "T2", "T3"):
        reg.register(Tool(name=f"tool_{tier}", tier=tier, input_model=Args, handler=handler))
    return ToolGateway(sf, reg, SECRET), calls


def token(tenant="t1", tools=("tool_T0", "tool_T1", "tool_T2", "tool_T3"), ttl=300, now=None):
    return mint_capability(SECRET, tenant, "run1", list(tools), ttl, now)


def test_t0_and_t1_run_with_a_capability(sf):
    gw, calls = build(sf)
    assert gw.call("t1", token(), "tool_T0", {"payment_id": "p"}, "k0").status == "executed"
    assert gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k1").status == "executed"
    assert calls["n"] == 2


def test_t2_and_t3_need_approval_and_do_not_run_without_it(sf):
    gw, calls = build(sf)
    for t in ("tool_T2", "tool_T3"):
        r = gw.call("t1", token(), t, {"payment_id": "p"}, f"k-{t}")
        assert r.status == "approval_required" and r.approval_id
    assert calls["n"] == 0


def test_policy_can_pre_approve_t2_but_never_t3(sf):
    gw, calls = build(sf)
    assert gw.call("t1", token(), "tool_T2", {"payment_id": "p"}, "a", policy_pre_approved=True).status == "executed"
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "b", policy_pre_approved=True).status == "approval_required"
    assert calls["n"] == 1


def test_an_approval_covers_exactly_one_execution_of_exactly_those_arguments(sf):
    gw, calls = build(sf)
    r = gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k1")
    gw.decide_approval("t1", r.approval_id, "analyst_1", True)
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "OTHER"}, "k2").status == "approval_required"     # different arguments
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k3").status == "executed"
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k4").status == "approval_required"           # approval already used
    assert calls["n"] == 1


def test_a_rejected_approval_does_not_unlock_the_tool(sf):
    gw, calls = build(sf)
    r = gw.call("t1", token(), "tool_T2", {"payment_id": "p"}, "k1")
    gw.decide_approval("t1", r.approval_id, "analyst_1", False)
    assert gw.call("t1", token(), "tool_T2", {"payment_id": "p"}, "k2").status == "approval_required"
    assert calls["n"] == 0


def test_another_tenant_cannot_approve(sf):
    gw, _ = build(sf)
    r = gw.call("t1", token(), "tool_T2", {"payment_id": "p"}, "k1")
    with pytest.raises(KeyError):
        gw.decide_approval("t2", r.approval_id, "analyst_x", True)


def test_idempotent_retry_does_not_call_the_handler_twice(sf):
    gw, calls = build(sf)
    a = gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "same")
    b = gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "same")
    assert (a.status, b.status) == ("executed", "replayed") and a.result == b.result and calls["n"] == 1
    assert gw.call("t1", token(), "tool_T1", {"payment_id": "different"}, "same").status == "denied"
    assert calls["n"] == 1


def test_capability_checks(sf):
    gw, calls = build(sf)
    assert gw.call("t1", token(tools=("tool_T0",)), "tool_T1", {"payment_id": "p"}, "k").status == "denied"     # tool not granted
    assert gw.call("t1", token(tenant="t2"), "tool_T0", {"payment_id": "p"}, "k").status == "denied"          # wrong tenant
    assert gw.call("t1", token(ttl=-10), "tool_T0", {"payment_id": "p"}, "k").status == "denied"              # expired
    assert gw.call("t1", token() + "x", "tool_T0", {"payment_id": "p"}, "k").status == "denied"               # bad signature
    assert gw.call("t1", "garbage", "tool_T0", {"payment_id": "p"}, "k").status == "denied"
    assert gw.call("t1", token(), "tool_T0", {"wrong": 1}, "k").status == "denied"                            # invalid arguments
    assert gw.call("t1", token(), "no_such_tool", {"payment_id": "p"}, "k").status == "denied"
    assert calls["n"] == 0


def test_token_roundtrip_and_tamper():
    t = mint_capability(SECRET, "t1", "r", ["a"], 60, now=1000)
    assert verify_capability(SECRET, t, now=1001)["tools"] == ["a"]
    with pytest.raises(CapabilityError):
        verify_capability(b"other-secret", t, now=1001)
    with pytest.raises(CapabilityError):
        verify_capability(SECRET, t, now=1061)


def test_every_outcome_lands_in_a_verifiable_ledger(sf):
    gw, _ = build(sf)
    gw.call("t1", token(), "tool_T0", {"payment_id": "p"}, "k0")
    gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k3")
    gw.call("t1", "garbage", "tool_T0", {"payment_id": "p"}, "kx")
    with sf() as s:
        r = ledger.verify(s, "t1")
        kinds = [e.kind for e in ledger.entries(s, "t1")]
    assert r.ok and kinds == ["tool.started", "tool.executed", "tool.approval_required", "tool.denied"]


def test_shadow_mode_never_runs_a_handler_even_with_approval(sf):
    gw, calls = build(sf)
    r = gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k1")
    gw.decide_approval("t1", r.approval_id, "analyst_1", True)
    for tier in ("T0", "T1", "T2", "T3"):
        assert gw.call("t1", token(), f"tool_{tier}", {"payment_id": "p"}, f"s-{tier}", mode="shadow").status in ("shadow_skipped", "approval_required")
    assert calls["n"] == 0
    assert gw.list_approvals("t1", "approved")                       # the approval was not consumed by a shadow run


@settings(max_examples=80, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(["T0", "T1", "T2", "T3"]), st.booleans(), st.booleans(), st.sampled_from(["enforce", "shadow"])), min_size=1, max_size=12))
def test_property_no_t2_t3_execution_without_approval_or_policy_rule(steps):
    """Invariants 1 and 7 over random sequences of calls. Every example gets its own fresh database."""
    engine = make_engine()
    sf = init_db(engine)
    gw, calls = build(sf)
    for i, (tier, pre, approve_first, mode) in enumerate(steps):
        before = calls["n"]
        args = {"payment_id": f"p{i}"}
        if approve_first and tier in ("T2", "T3"):
            r = gw.call("t1", token(), f"tool_{tier}", args, f"ask-{i}")
            if r.approval_id:
                gw.decide_approval("t1", r.approval_id, "analyst", True)
        res = gw.call("t1", token(), f"tool_{tier}", args, f"go-{i}", mode=mode, policy_pre_approved=pre)
        ran = calls["n"] > before
        if mode == "shadow":
            assert not ran
        if ran:
            assert tier in ("T0", "T1") or (tier == "T2" and (pre or approve_first)) or (tier == "T3" and approve_first)
            assert res.status in ("executed", "replayed")


# --- the three-step call: intent is committed, the handler runs with no transaction open, then the result is committed ---

class SimulatedCrash(BaseException):
    """Stands in for the process dying: it is not an Exception, so the gateway's failure handling does not run, exactly as if the process had been killed."""


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def gateway_with(sf, handler, lease_s=300.0, clock=None):
    reg = ToolRegistry()
    for tier in ("T1", "T3"):
        reg.register(Tool(name=f"tool_{tier}", tier=tier, input_model=Args, handler=handler))
    return ToolGateway(sf, reg, SECRET, lease_s=lease_s, clock=clock or Clock())


def kinds_of(sf, tenant="t1"):
    with sf() as s:
        return [e.kind for e in ledger.entries(s, tenant)]


def approve_one(gw, tool="tool_T3", pid="p"):
    first = gw.call("t1", token(), tool, {"payment_id": pid}, "ask")
    gw.decide_approval("t1", first.approval_id, "boss", True)
    return first.approval_id


def test_a_crash_between_intent_and_result_never_runs_the_tool_twice(sf):
    clock, ran = Clock(), []

    def handler(a):
        ran.append(a.payment_id)
        raise SimulatedCrash()

    gw = gateway_with(sf, handler, clock=clock)
    with pytest.raises(SimulatedCrash):
        gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k")
    assert kinds_of(sf) == ["tool.started"]                              # the intent is on the record, the outcome is not
    again = gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k")
    assert again.status == "denied" and "already running" in again.reason and ran == ["p"]
    clock.t += 301                                                       # the lease has passed: the outcome is now unknown, and it stays unknown
    late = gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k")
    assert late.status == "denied" and "unknown" in late.reason and ran == ["p"]
    assert gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k").status == "denied" and kinds_of(sf).count("tool.unknown_outcome") == 1 and ran == ["p"]
    with sf() as s:
        assert ledger.verify(s, "t1").ok


def test_the_recovery_sweep_only_touches_calls_older_than_the_lease(sf):
    clock = Clock()

    def handler(a):
        raise SimulatedCrash()

    gw = gateway_with(sf, handler, lease_s=60, clock=clock)
    with pytest.raises(SimulatedCrash):
        gw.call("t1", token(), "tool_T1", {"payment_id": "old"}, "old")
    clock.t += 50
    with pytest.raises(SimulatedCrash):
        gw.call("t1", token(), "tool_T1", {"payment_id": "new"}, "new")
    clock.t += 20                                                        # old is 70 s old, new is 20 s old
    assert gw.recover_stuck() == 1 and gw.recover_stuck() == 0
    with sf() as s:
        status = {r.idempotency_key: r.status for r in s.scalars(select(ToolCallRow))}
    assert status == {"old": "unknown", "new": "running"}


def test_a_handler_that_raises_frees_the_key_and_the_approval_for_a_retry(sf):
    attempts = []

    def handler(a):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("customer 4111-1111 not found")
        return {"ok": True}

    gw = gateway_with(sf, handler)
    approval_id = approve_one(gw)
    failed = gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k")
    assert failed.status == "failed"
    with sf() as s:
        assert s.get(ApprovalRow, approval_id).status == "approved" and s.scalar(select(ToolCallRow)) is None
        failure = [e for e in ledger.entries(s, "t1") if e.kind == "tool.failed"][0]
    assert "RuntimeError" in failure.payload and "4111" not in failure.payload      # the class name is recorded, the message (which may hold customer data) is not
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k").status == "executed" and len(attempts) == 2
    with sf() as s:
        assert s.get(ApprovalRow, approval_id).status == "used" and ledger.verify(s, "t1").ok
    assert kinds_of(sf) == ["tool.approval_required", "approval.decided", "tool.started", "tool.failed", "tool.started", "tool.executed"]


def test_an_approval_consumed_by_a_crashed_call_is_not_given_back(sf):
    def handler(a):
        raise SimulatedCrash()

    gw = gateway_with(sf, handler)
    approval_id = approve_one(gw)
    with pytest.raises(SimulatedCrash):
        gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k")
    with sf() as s:
        assert s.get(ApprovalRow, approval_id).status == "used"
    assert gw.call("t1", token(), "tool_T3", {"payment_id": "p"}, "k2").status == "approval_required"      # a new key needs a new human decision


def test_a_slow_handler_that_finishes_after_the_sweep_still_records_its_result(sf):
    clock = Clock()
    holder = {}

    def handler(a):
        clock.t += 400                                                   # the tool is slower than the lease
        holder["gw"].recover_stuck()                                     # another process's sweep marks it unknown meanwhile
        return {"done": a.payment_id}

    gw = holder["gw"] = gateway_with(sf, handler, clock=clock)
    assert gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k").status == "executed"
    again = gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "k")
    assert again.status == "replayed" and again.result == {"done": "p"}
    assert kinds_of(sf) == ["tool.started", "tool.unknown_outcome", "tool.executed"]


@pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"), reason="needs a database where a second connection sees only committed data")
def test_while_the_handler_runs_the_intent_is_already_committed_and_no_transaction_is_open(sf):
    seen = {}

    def handler(a):
        with sf() as other:                                              # a different connection: it sees only what the gateway has committed
            row = other.scalar(select(ToolCallRow))
            seen["status"] = row.status if row else None
            seen["kinds"] = [e.kind for e in ledger.entries(other, "t1")]
            ledger.append(other, "t1", "probe", {"during": "handler"})   # and it can write the ledger: no lock is held on it
            other.commit()
        return {"ok": True}

    assert gateway_with(sf, handler).call("t1", token(), "tool_T1", {"payment_id": "p"}, "k").status == "executed"
    assert seen == {"status": "running", "kinds": ["tool.started"]}
    with sf() as s:
        assert ledger.verify(s, "t1").ok and kinds_of(sf) == ["tool.started", "probe", "tool.executed"]


@pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"), reason="needs PostgreSQL")
def test_simultaneous_calls_with_one_key_run_a_slow_tool_once_and_the_rest_are_turned_away(sf):
    ran = []

    def handler(a):
        ran.append(1)
        time.sleep(0.4)
        return {"ok": True}

    gw = gateway_with(sf, handler)
    with ThreadPoolExecutor(6) as ex:
        out = list(ex.map(lambda _: gw.call("t1", token(), "tool_T1", {"payment_id": "p"}, "same").status, range(6)))
    assert len(ran) == 1 and out.count("executed") == 1 and set(out) <= {"executed", "denied", "replayed"}
    with sf() as s:
        assert ledger.verify(s, "t1").ok
