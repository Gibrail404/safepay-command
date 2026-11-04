"""Idempotent decisions that can be replayed. A decision and its ledger entry are written in one transaction."""
from __future__ import annotations
import json, uuid
from typing import Callable, Literal
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from . import ledger
from .db import DecisionRow, PolicyRow
from .policy import Policy, PolicyResult, evaluate


class DecisionRequest(BaseModel):
    workload: str = Field(min_length=1, max_length=64)
    subject: dict
    context: dict
    mode: Literal["enforce", "shadow"] = "enforce"

    @field_validator("subject", "context")
    @classmethod
    def _bounded(cls, v: dict) -> dict:
        if len(json.dumps(v, separators=(",", ":"))) > 64_000:
            raise ValueError("object larger than 64000 bytes")
        return v


class DecisionResponse(PolicyResult):
    decision_id: str
    mode: Literal["enforce", "shadow"]


class IdempotencyConflict(Exception):
    """The same idempotency key was reused with a different request body."""


class PolicyIntegrityError(Exception):
    """A stored policy snapshot no longer matches its version hash."""


class NotFound(Exception):
    pass


class ReplayResult(BaseModel):
    decision_id: str
    same: bool
    original_outcome: str
    recomputed_outcome: str
    policy_version: str


PolicyProvider = Callable[[str, str], Policy]      # (tenant, workload) -> Policy


class DecisionService:
    def __init__(self, sf: sessionmaker[Session], policy_for: PolicyProvider):
        self.sf, self.policy_for = sf, policy_for

    def decide(self, tenant: str, idempotency_key: str, req: DecisionRequest) -> tuple[DecisionResponse, bool]:
        """Returns (decision, replayed). replayed=True means the key was already used with the same body: nothing new happened."""
        req_json = ledger.canonical_json(req.model_dump())
        req_hash = ledger.sha256_hex(req_json)
        for attempt in (1, 2):
            try:
                with self.sf.begin() as s:
                    existing = s.scalar(select(DecisionRow).where(DecisionRow.tenant == tenant, DecisionRow.idempotency_key == idempotency_key))
                    if existing:
                        if existing.request_hash != req_hash:
                            raise IdempotencyConflict("this idempotency key was already used with a different request")
                        return DecisionResponse.model_validate_json(existing.response), True
                    policy = self.policy_for(tenant, req.workload)
                    if s.get(PolicyRow, policy.version) is None:
                        s.add(PolicyRow(version=policy.version, content=ledger.canonical_json(policy.content())))
                    result = evaluate(policy, req.context)
                    resp = DecisionResponse(**result.model_dump(), decision_id="d_" + uuid.uuid4().hex[:12], mode=req.mode)
                    s.add(DecisionRow(id=resp.decision_id, tenant=tenant, idempotency_key=idempotency_key, request_hash=req_hash,
                                      request=req_json, response=resp.model_dump_json(), policy_version=policy.version))
                    ledger.append(s, tenant, "decision", {"decision_id": resp.decision_id, "request_hash": req_hash, "outcome": resp.outcome,
                                                          "risk_tier": resp.risk_tier, "policy_version": resp.policy_version, "mode": resp.mode,
                                                          "reasons": [r.model_dump() for r in resp.reasons]})
                    return resp, False
            except IntegrityError:
                if attempt == 2:
                    raise                                     # two writers raced on the same key: the loser re-reads the winner's row

    def get(self, tenant: str, decision_id: str) -> DecisionResponse:
        with self.sf() as s:
            row = s.scalar(select(DecisionRow).where(DecisionRow.tenant == tenant, DecisionRow.id == decision_id))   # tenant is part of the query
            if row is None:
                raise NotFound(decision_id)
            return DecisionResponse.model_validate_json(row.response)

    def replay(self, tenant: str, decision_id: str) -> ReplayResult:
        """Re-run the stored request through the stored policy snapshot and compare with what was decided."""
        with self.sf() as s:
            row = s.scalar(select(DecisionRow).where(DecisionRow.tenant == tenant, DecisionRow.id == decision_id))
            if row is None:
                raise NotFound(decision_id)
            snap = s.get(PolicyRow, row.policy_version)
            if snap is None:
                raise PolicyIntegrityError("policy snapshot is missing")
            policy = Policy.model_validate(json.loads(snap.content))
            if policy.version != row.policy_version:
                raise PolicyIntegrityError("policy snapshot does not match its version hash")
            original = DecisionResponse.model_validate_json(row.response)
            again = evaluate(policy, json.loads(row.request)["context"])
            same = (again.outcome, again.risk_tier, again.requires_approval, [r.model_dump() for r in again.reasons]) == \
                   (original.outcome, original.risk_tier, original.requires_approval, [r.model_dump() for r in original.reasons])
            return ReplayResult(decision_id=decision_id, same=same, original_outcome=original.outcome, recomputed_outcome=again.outcome, policy_version=row.policy_version)
