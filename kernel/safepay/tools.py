"""Tool gateway: the only way an agent can act. Checks a signed capability, validates arguments, enforces risk tiers and approvals,
honours shadow mode, and makes every call idempotent and ledgered."""
from __future__ import annotations
import base64, hashlib, hmac, json, time, uuid
from dataclasses import dataclass
from typing import Callable, Literal
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from . import ledger
from .db import ApprovalRow, ToolCallRow

Tier = Literal["T0", "T1", "T2", "T3"]


@dataclass(frozen=True)
class Tool:
    name: str
    tier: Tier
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], dict]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def describe(self) -> list[dict]:
        return [{"name": t.name, "tier": t.tier, "input_schema": t.input_model.model_json_schema()} for t in self._tools.values()]


class CapabilityError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_capability(secret: bytes, tenant: str, run_id: str, tools: list[str], ttl_s: int = 300, now: float | None = None) -> str:
    """A capability token names one tenant, one run and the exact tools it may call, and expires. Signed with HMAC-SHA256."""
    payload = json.dumps({"tenant": tenant, "run": run_id, "tools": sorted(tools), "exp": int((now or time.time()) + ttl_s)}, sort_keys=True, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{hmac.new(secret, payload, hashlib.sha256).hexdigest()}"


def verify_capability(secret: bytes, token: str, now: float | None = None) -> dict:
    try:
        body, sig = token.split(".", 1)
        payload = _unb64(body)
    except Exception as e:
        raise CapabilityError("malformed token") from e
    if not hmac.compare_digest(hmac.new(secret, payload, hashlib.sha256).hexdigest(), sig):
        raise CapabilityError("bad signature")
    cap = json.loads(payload)
    if (now or time.time()) > cap["exp"]:
        raise CapabilityError("token expired")
    return cap


class CallResult(BaseModel):
    status: Literal["executed", "replayed", "approval_required", "denied", "shadow_skipped"]
    result: dict | None = None
    approval_id: str | None = None
    reason: str | None = None


class ToolGateway:
    def __init__(self, sf: sessionmaker[Session], registry: ToolRegistry, secret: bytes):
        self.sf, self.registry, self.secret = sf, registry, secret

    def _log(self, s: Session, tenant: str, kind: str, payload: dict) -> None:
        ledger.append(s, tenant, kind, payload)

    def call(self, tenant: str, token: str, tool_name: str, args: dict, idempotency_key: str,
             mode: Literal["enforce", "shadow"] = "enforce", policy_pre_approved: bool = False) -> CallResult:
        tool = self.registry.get(tool_name)
        try:
            cap = verify_capability(self.secret, token)
        except CapabilityError as e:
            return self._deny(tenant, tool_name, str(e), None)
        if cap["tenant"] != tenant:
            return self._deny(tenant, tool_name, "token belongs to another tenant", cap["run"])
        if tool is None or tool_name not in cap["tools"]:
            return self._deny(tenant, tool_name, "tool not in this capability", cap["run"])
        try:
            parsed = tool.input_model.model_validate(args)
        except ValidationError:
            return self._deny(tenant, tool_name, "invalid arguments", cap["run"])
        args_hash = ledger.sha256_hex(ledger.canonical_json(parsed.model_dump(mode="json")))

        with self.sf.begin() as s:
            prior = s.scalar(select(ToolCallRow).where(ToolCallRow.tenant == tenant, ToolCallRow.tool == tool_name, ToolCallRow.idempotency_key == idempotency_key))
            if prior:
                if prior.args_hash != args_hash:
                    self._log(s, tenant, "tool.denied", {"tool": tool_name, "run": cap["run"], "reason": "idempotency key reused with different arguments"})
                    return CallResult(status="denied", reason="idempotency key reused with different arguments")
                return CallResult(status="replayed", result=json.loads(prior.result))

            approval = None
            allowed = tool.tier in ("T0", "T1") or (tool.tier == "T2" and policy_pre_approved)     # T3 is never allowed by policy alone
            if not allowed:
                approval = s.scalar(select(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.tool == tool_name,
                                                              ApprovalRow.args_hash == args_hash, ApprovalRow.status == "approved"))
                allowed = approval is not None
            if not allowed:
                pending = s.scalar(select(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.tool == tool_name,
                                                             ApprovalRow.args_hash == args_hash, ApprovalRow.status == "pending"))
                if pending is None:
                    pending = ApprovalRow(id="a_" + uuid.uuid4().hex[:12], tenant=tenant, tool=tool_name, args_hash=args_hash, status="pending")
                    s.add(pending)
                self._log(s, tenant, "tool.approval_required", {"tool": tool_name, "tier": tool.tier, "run": cap["run"], "args_hash": args_hash, "approval_id": pending.id})
                return CallResult(status="approval_required", approval_id=pending.id, reason=f"{tool.tier} action needs a human approval")

            if mode == "shadow":                                  # a shadow run decides everything except it never acts
                self._log(s, tenant, "tool.shadow", {"tool": tool_name, "tier": tool.tier, "run": cap["run"], "args_hash": args_hash})
                return CallResult(status="shadow_skipped")

            s.add(ToolCallRow(tenant=tenant, tool=tool_name, idempotency_key=idempotency_key, args_hash=args_hash, result=""))   # claim the key first
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                return CallResult(status="denied", reason="a call with this idempotency key is already running")
            result = tool.handler(parsed)
            row = s.scalar(select(ToolCallRow).where(ToolCallRow.tenant == tenant, ToolCallRow.tool == tool_name, ToolCallRow.idempotency_key == idempotency_key))
            row.result = ledger.canonical_json(result)
            if approval is not None:
                approval.status = "used"                           # an approval covers exactly one execution
            self._log(s, tenant, "tool.executed", {"tool": tool_name, "tier": tool.tier, "run": cap["run"], "args_hash": args_hash,
                                                   "result_hash": ledger.sha256_hex(row.result), "approval_id": approval.id if approval else None})
            return CallResult(status="executed", result=result)

    def _deny(self, tenant: str, tool: str, reason: str, run: str | None) -> CallResult:
        with self.sf.begin() as s:
            self._log(s, tenant, "tool.denied", {"tool": tool, "run": run, "reason": reason})
        return CallResult(status="denied", reason=reason)

    def list_approvals(self, tenant: str, status: str | None = None) -> list[dict]:
        with self.sf() as s:
            q = select(ApprovalRow).where(ApprovalRow.tenant == tenant)
            if status:
                q = q.where(ApprovalRow.status == status)
            return [{"id": a.id, "tool": a.tool, "status": a.status, "decided_by": a.decided_by} for a in s.scalars(q)]

    def decide_approval(self, tenant: str, approval_id: str, approver: str, approve: bool) -> dict:
        with self.sf.begin() as s:
            a = s.scalar(select(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.id == approval_id, ApprovalRow.status == "pending"))
            if a is None:
                raise KeyError(approval_id)
            a.status, a.decided_by = ("approved" if approve else "rejected"), approver
            self._log(s, tenant, "approval.decided", {"approval_id": a.id, "tool": a.tool, "status": a.status, "decided_by": approver})
            return {"id": a.id, "status": a.status}
