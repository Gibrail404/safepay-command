"""Deterministic, versioned policy engine. Rules are data (validated by Pydantic), not code, so a decision can be replayed later."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .ledger import canonical_json, sha256_hex

Outcome = Literal["allow", "warn", "hold", "block"]
SEVERITY: dict[str, int] = {"allow": 0, "warn": 1, "hold": 2, "block": 3}
TIER: dict[str, str] = {"allow": "T0", "warn": "T1", "hold": "T2", "block": "T3"}
OPS = {">", ">=", "<", "<=", "==", "!=", "in", "not_in"}


class Cond(BaseModel):
    """Exactly one of: a comparison (field, op, value), all, any, or not."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    field: str | None = None
    op: str | None = None
    value: Any = None
    all: list["Cond"] | None = None
    any: list["Cond"] | None = None
    not_: "Cond | None" = Field(default=None, alias="not")

    @model_validator(mode="after")
    def one_form(self):
        forms = [self.field is not None, self.all is not None, self.any is not None, self.not_ is not None]
        if sum(forms) != 1:
            raise ValueError("a condition needs exactly one of: field/op/value, all, any, not")
        if self.field is not None and self.op not in OPS:
            raise ValueError(f"op must be one of {sorted(OPS)}")
        if self.op in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError("in / not_in need a list value")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)        # reason code shown to users and analysts
    when: Cond
    outcome: Outcome
    auto_approve: bool = False                            # only a hold may be pre-approved by policy; a block never can

    @model_validator(mode="after")
    def auto_only_for_hold(self):
        if self.auto_approve and self.outcome != "hold":
            raise ValueError("auto_approve is only allowed on hold rules")
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    rules: list[Rule]

    @field_validator("rules")
    @classmethod
    def unique_ids(cls, rules):
        ids = [r.id for r in rules]
        if len(set(ids)) != len(ids):
            raise ValueError("rule ids must be unique")
        return rules

    def content(self) -> dict:
        return self.model_dump(by_alias=True, mode="json")

    @property
    def version(self) -> str:
        """Content-addressed: change any rule and the version changes."""
        return sha256_hex(canonical_json(self.content()))


class Reason(BaseModel):
    rule_id: str
    code: str
    outcome: Outcome


class PolicyResult(BaseModel):
    outcome: Outcome
    risk_tier: str
    requires_approval: bool
    reasons: list[Reason]
    policy_version: str


def _cmp(actual: Any, op: str, expected: Any) -> bool:
    try:
        if op == "in":
            return actual in expected
        if op == "not_in":
            return actual not in expected
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False                                   # ordering a boolean is almost always a mistake
        if op == ">":
            return actual > expected
        if op == ">=":
            return actual >= expected
        if op == "<":
            return actual < expected
        if op == "<=":
            return actual <= expected
    except TypeError:
        return False                                       # incomparable types never match
    return False


def matches(cond: Cond, ctx: dict) -> bool:
    """A comparison on a missing field is False. That choice is deliberate: no data never triggers a rule by accident."""
    if cond.all is not None:
        return all(matches(c, ctx) for c in cond.all)
    if cond.any is not None:
        return any(matches(c, ctx) for c in cond.any)
    if cond.not_ is not None:
        return not matches(cond.not_, ctx)
    if cond.field not in ctx:
        return False
    return _cmp(ctx[cond.field], cond.op, cond.value)


def evaluate(policy: Policy, ctx: dict) -> PolicyResult:
    fired = [r for r in policy.rules if matches(r.when, ctx)]
    outcome: str = max((r.outcome for r in fired), key=lambda o: SEVERITY[o], default="allow")
    top = [r for r in fired if r.outcome == outcome]
    tier = TIER[outcome]
    needs = tier in ("T2", "T3") and not (outcome == "hold" and all(r.auto_approve for r in top))
    return PolicyResult(outcome=outcome, risk_tier=tier, requires_approval=needs,
                        reasons=[Reason(rule_id=r.id, code=r.code, outcome=r.outcome) for r in fired], policy_version=policy.version)
