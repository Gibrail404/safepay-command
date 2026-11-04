import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError
from safepay.policy import Cond, Policy, Rule, evaluate, matches

C = lambda **k: Cond.model_validate(k)


def make_policy():
    return Policy(name="test", rules=[
        Rule(id="r1", code="LARGE_AMOUNT", when=C(field="amount", op=">", value=3000), outcome="warn"),
        Rule(id="r2", code="NEW_PAYEE_LARGE", when=C(all=[C(field="payee_age_days", op="<", value=1), C(field="amount", op=">", value=4000)]), outcome="hold"),
        Rule(id="r3", code="LISTED_COUNTRY", when=C(field="country", op="in", value=["XX", "YY"]), outcome="block"),
    ])


def test_default_is_allow():
    r = evaluate(make_policy(), {"amount": 10})
    assert r.outcome == "allow" and r.risk_tier == "T0" and not r.requires_approval and r.reasons == []


def test_highest_severity_wins_and_all_reasons_are_kept():
    r = evaluate(make_policy(), {"amount": 4800, "payee_age_days": 0})
    assert r.outcome == "hold" and r.risk_tier == "T2" and r.requires_approval
    assert [x.code for x in r.reasons] == ["LARGE_AMOUNT", "NEW_PAYEE_LARGE"]


def test_block_always_requires_approval():
    assert evaluate(make_policy(), {"country": "XX"}).requires_approval


def test_missing_field_never_triggers_a_rule():
    assert evaluate(make_policy(), {}).outcome == "allow"


def test_incomparable_types_do_not_match():
    assert not matches(C(field="amount", op=">", value=3000), {"amount": "lots"})
    assert not matches(C(field="amount", op=">", value=1), {"amount": True})


def test_auto_approved_hold_needs_no_human_but_block_cannot_be_auto():
    p = Policy(name="p", rules=[Rule(id="a", code="SMALL_HOLD", when=C(field="amount", op=">", value=1), outcome="hold", auto_approve=True)])
    assert not evaluate(p, {"amount": 5}).requires_approval
    with pytest.raises(ValidationError):
        Rule(id="b", code="X", when=C(field="amount", op=">", value=1), outcome="block", auto_approve=True)


def test_bad_conditions_are_rejected():
    for bad in ({}, {"field": "a"}, {"field": "a", "op": "~", "value": 1}, {"field": "a", "op": "in", "value": 3}, {"field": "a", "op": ">", "value": 1, "all": []}):
        with pytest.raises(ValidationError):
            Cond.model_validate(bad)
    with pytest.raises(ValidationError):
        Policy(name="d", rules=[Rule(id="x", code="A", when=C(field="a", op="==", value=1), outcome="warn")] * 2)


def test_version_changes_when_a_rule_changes():
    a = make_policy()
    b = Policy(name="test", rules=[*a.rules[:-1], Rule(id="r3", code="LISTED_COUNTRY", when=C(field="country", op="in", value=["XX"]), outcome="block")])
    assert a.version != b.version and a.version == make_policy().version


ctx_strategy = st.fixed_dictionaries({}, optional={"amount": st.integers(0, 10000), "payee_age_days": st.integers(0, 400), "country": st.sampled_from(["XX", "YY", "AE", "IN"])})


@given(ctx_strategy)
def test_evaluation_is_deterministic(ctx):
    p = make_policy()
    assert evaluate(p, ctx) == evaluate(p, dict(ctx))


@given(ctx_strategy)
def test_adding_a_rule_never_lowers_severity(ctx):
    base = make_policy()
    extra = Policy(name="test", rules=[*base.rules, Rule(id="r9", code="EXTRA", when=C(field="amount", op=">=", value=0), outcome="warn")])
    order = {"allow": 0, "warn": 1, "hold": 2, "block": 3}
    assert order[evaluate(extra, ctx).outcome] >= order[evaluate(base, ctx).outcome]
