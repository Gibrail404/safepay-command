"""HTTP API (v1). Tenant comes from the API key, never from a client-supplied field."""
from __future__ import annotations
import json, uuid
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from . import ledger
from .config import PolicyStore, Settings
from .db import DecisionRow, EventRow, init_db, make_engine
from .decisions import DecisionRequest, DecisionResponse, DecisionService, IdempotencyConflict, NotFound, PolicyIntegrityError, ReplayResult
from .policy import Policy, evaluate
from .tools import CallResult, ToolGateway, ToolRegistry, mint_capability


class EventIn(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    data: dict


class RunIn(BaseModel):
    tools: list[str]
    ttl_s: int = Field(default=300, ge=1, le=3600)


class ToolCallIn(BaseModel):
    tool: str
    args: dict
    mode: Literal["enforce", "shadow"] = "enforce"
    decision_id: str | None = None        # a policy pre-approval can only come from a stored decision, never from the caller


class ApprovalIn(BaseModel):
    approve: bool


class SimulateIn(BaseModel):
    policy: Policy
    contexts: list[dict] = Field(max_length=500)


def create_app(settings: Settings | None = None, registry: ToolRegistry | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    sf = init_db(engine)
    store = PolicyStore(settings.policy_dir)
    registry = registry or ToolRegistry()
    try:
        from . import risk_tool, text_tool
        risk_tool.register_if_available(registry)
        text_tool.register_if_available(registry)
    except ImportError:                       # the ml package is optional for the kernel
        pass
    decisions = DecisionService(sf, store.for_workload)
    gateway = ToolGateway(sf, registry, settings.capability_secret)
    app = FastAPI(title="SafePay Command kernel", version="0.2.0")
    app.state.sf = sf                       # exposed so tests can reach the database directly

    def tenant_of(x_api_key: str | None = Header(default=None)) -> str:
        tenant = settings.tenants.get(x_api_key or "")
        if tenant is None:
            raise HTTPException(401, "missing or unknown API key")
        return tenant

    def need_key(idempotency_key: str | None) -> str:
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(400, "Idempotency-Key header is required (max 128 characters)")
        return idempotency_key

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/v1/events")
    def post_event(body: EventIn, tenant: str = Depends(tenant_of), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        data_json = ledger.canonical_json(body.model_dump())
        h = ledger.sha256_hex(data_json)
        try:
            with sf.begin() as s:
                row = s.scalar(select(EventRow).where(EventRow.tenant == tenant, EventRow.idempotency_key == key))
                if row:
                    if row.event_hash != h:
                        raise HTTPException(409, "idempotency key reused with a different event")
                    return {"event_id": row.id, "replayed": True}
                row = EventRow(id="e_" + uuid.uuid4().hex[:12], tenant=tenant, idempotency_key=key, event_hash=h, type=body.type, data=data_json)
                s.add(row)
                ledger.append(s, tenant, "event", {"event_id": row.id, "type": body.type, "event_hash": h})
                return {"event_id": row.id, "replayed": False}
        except IntegrityError:
            raise HTTPException(409, "concurrent request with the same idempotency key")

    @app.post("/v1/decisions", response_model=DecisionResponse)
    def post_decision(body: DecisionRequest, tenant: str = Depends(tenant_of), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        try:
            decision, _ = decisions.decide(tenant, key, body)
        except IdempotencyConflict as e:
            raise HTTPException(409, str(e))
        except KeyError as e:
            raise HTTPException(422, str(e))
        return decision

    @app.get("/v1/decisions/{decision_id}", response_model=DecisionResponse)
    def get_decision(decision_id: str, tenant: str = Depends(tenant_of)):
        try:
            return decisions.get(tenant, decision_id)
        except NotFound:
            raise HTTPException(404, "decision not found")

    @app.get("/v1/decisions/{decision_id}/replay", response_model=ReplayResult)
    def replay_decision(decision_id: str, tenant: str = Depends(tenant_of)):
        try:
            return decisions.replay(tenant, decision_id)
        except NotFound:
            raise HTTPException(404, "decision not found")
        except PolicyIntegrityError as e:
            raise HTTPException(409, str(e))

    @app.get("/v1/audit")
    def audit(tenant: str = Depends(tenant_of), after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        with sf() as s:
            return [{"seq": e.seq, "kind": e.kind, "ts": e.ts, "hash": e.hash, "prev_hash": e.prev_hash, "payload": json.loads(e.payload)} for e in ledger.entries(s, tenant, after_seq, limit)]

    @app.get("/v1/audit/verify")
    def audit_verify(tenant: str = Depends(tenant_of)):
        with sf() as s:
            r = ledger.verify(s, tenant)
        return {"ok": r.ok, "checked": r.checked, "reason": r.reason, "bad_seq": r.bad_seq}

    @app.get("/v1/policies")
    def list_policies(tenant: str = Depends(tenant_of)):
        return [{"workload": w, "name": p.name, "version": p.version, "rules": len(p.rules)} for w, p in store.policies.items()]

    @app.post("/v1/policies/simulate")
    def simulate(body: SimulateIn, tenant: str = Depends(tenant_of)):
        """Run a candidate policy over supplied contexts. Nothing is stored and no ledger entry is written."""
        return {"policy_version": body.policy.version, "results": [evaluate(body.policy, c).model_dump() for c in body.contexts]}

    @app.get("/v1/tools")
    def list_tools(tenant: str = Depends(tenant_of)):
        return registry.describe()

    @app.post("/v1/runs")
    def start_run(body: RunIn, tenant: str = Depends(tenant_of)):
        unknown = [t for t in body.tools if registry.get(t) is None]
        if unknown:
            raise HTTPException(422, f"unknown tools: {unknown}")
        run_id = "r_" + uuid.uuid4().hex[:12]
        with sf.begin() as s:
            ledger.append(s, tenant, "run.started", {"run_id": run_id, "tools": sorted(body.tools)})
        return {"run_id": run_id, "capability": mint_capability(settings.capability_secret, tenant, run_id, body.tools, body.ttl_s)}

    @app.post("/v1/tools/call", response_model=CallResult)
    def call_tool(body: ToolCallIn, tenant: str = Depends(tenant_of), x_capability: str | None = Header(default=None), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        pre = False
        if body.decision_id:
            try:
                d = decisions.get(tenant, body.decision_id)
                pre = d.mode == "enforce" and d.outcome == "hold" and not d.requires_approval
            except NotFound:
                raise HTTPException(404, "decision not found")
        return gateway.call(tenant, x_capability or "", body.tool, body.args, key, body.mode, pre)

    @app.get("/v1/approvals")
    def approvals(tenant: str = Depends(tenant_of), status: str | None = None):
        return gateway.list_approvals(tenant, status)

    @app.post("/v1/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: ApprovalIn, tenant: str = Depends(tenant_of), x_actor: str | None = Header(default=None)):
        if not x_actor:
            raise HTTPException(400, "X-Actor header is required to record who decided")
        try:
            return gateway.decide_approval(tenant, approval_id, x_actor, body.approve)
        except KeyError:
            raise HTTPException(404, "pending approval not found")

    return app
