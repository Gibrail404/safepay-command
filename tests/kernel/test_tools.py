"""Invariants 1 (no T2/T3 without approval or rule) and 7 (shadow mode has no side effects), plus capability checks and idempotency."""
import time
import pytest
from hypothesis import given, settings, strategies as st
from pydantic import BaseModel
from safepay import ledger
from safepay.db import init_db, make_engine
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
    assert r.ok and kinds == ["tool.executed", "tool.approval_required", "tool.denied"]


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
