"""Tool gateway: the only way an agent can act. Checks a signed capability, validates arguments, enforces risk tiers and approvals,
honours shadow mode, and makes every call idempotent and ledgered.

A call runs in three steps so that no database transaction is open while a tool runs (an outbox-style intent record):
  1. one short transaction claims the idempotency key, consumes the approval and ledgers `tool.started` (the intent);
  2. the handler runs with no transaction open;
  3. a second short transaction stores the result and ledgers `tool.executed` (or `tool.failed` and releases the claim).
If the process dies between 1 and 3 the call stays `running`; once the lease passes it is marked `unknown` and is never run again by itself:
a payment tool cannot know whether its effect happened, so a person checks and retries with a new idempotency key (at most once, never twice).
A handler must raise only when it did nothing, because a raise releases the key for a retry."""
from __future__ import annotations
import base64, hashlib, hmac, json, time, uuid
from dataclasses import dataclass
from typing import Callable, Literal
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select, update
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
    status: Literal["executed", "replayed", "approval_required", "denied", "shadow_skipped", "failed"]
    result: dict | None = None
    approval_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _Claimed:
    """Step 1 finished: this caller owns the key and may run the handler."""
    approval_id: str | None


class ToolGateway:
    def __init__(self, sf: sessionmaker[Session], registry: ToolRegistry, secret: bytes, lease_s: float = 300.0, clock: Callable[[], float] = time.time):
        self.sf, self.registry, self.secret, self.lease_s, self.clock = sf, registry, secret, lease_s, clock

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

        step1 = self._claim(tenant, tool, cap["run"], args_hash, idempotency_key, mode, policy_pre_approved)
        if isinstance(step1, CallResult):
            return step1
        try:
            result_json = ledger.canonical_json(tool.handler(parsed))        # no transaction is open here: a slow tool holds no connection and no lock
        except Exception as e:
            return self._release(tenant, tool, cap["run"], args_hash, idempotency_key, step1.approval_id, e)
        with self.sf.begin() as s:
            row = s.scalar(select(ToolCallRow).where(ToolCallRow.tenant == tenant, ToolCallRow.tool == tool.name, ToolCallRow.idempotency_key == idempotency_key))
            row.status, row.result = "done", result_json                      # also fixes a row the recovery sweep had already marked unknown: the result is now known
            self._log(s, tenant, "tool.executed", {"tool": tool.name, "tier": tool.tier, "run": cap["run"], "args_hash": args_hash,
                                                   "result_hash": ledger.sha256_hex(result_json), "approval_id": step1.approval_id})
        return CallResult(status="executed", result=json.loads(result_json))

    def _claim(self, tenant: str, tool: Tool, run: str, args_hash: str, key: str, mode: str, pre_approved: bool) -> "CallResult | _Claimed":
        """Step 1: decide whether this call may run and, if so, record the intent. One short transaction."""
        with self.sf.begin() as s:
            prior = s.scalar(select(ToolCallRow).where(ToolCallRow.tenant == tenant, ToolCallRow.tool == tool.name, ToolCallRow.idempotency_key == key))
            if prior:
                if prior.args_hash != args_hash:
                    self._log(s, tenant, "tool.denied", {"tool": tool.name, "run": run, "reason": "idempotency key reused with different arguments"})
                    return CallResult(status="denied", reason="idempotency key reused with different arguments")
                if prior.status == "done":
                    return CallResult(status="replayed", result=json.loads(prior.result))
                if prior.status == "running" and self.clock() - prior.started >= self.lease_s:
                    prior.status = "unknown"
                    self._log(s, tenant, "tool.unknown_outcome", {"tool": tool.name, "run": run, "args_hash": args_hash, "started": prior.started})
                if prior.status == "running":
                    return CallResult(status="denied", reason="a call with this idempotency key is already running")
                return CallResult(status="denied", reason="an earlier attempt with this key never reported back, so whether it acted is unknown; check, then retry with a new idempotency key")

            approval = None
            allowed = tool.tier in ("T0", "T1") or (tool.tier == "T2" and pre_approved)     # T3 is never allowed by policy alone
            if not allowed:
                approval = s.scalar(select(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.tool == tool.name,
                                                              ApprovalRow.args_hash == args_hash, ApprovalRow.status == "approved"))
                allowed = approval is not None
            if not allowed:
                pending = s.scalar(select(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.tool == tool.name,
                                                             ApprovalRow.args_hash == args_hash, ApprovalRow.status == "pending"))
                if pending is None:
                    pending = ApprovalRow(id="a_" + uuid.uuid4().hex[:12], tenant=tenant, tool=tool.name, args_hash=args_hash, status="pending")
                    s.add(pending)
                self._log(s, tenant, "tool.approval_required", {"tool": tool.name, "tier": tool.tier, "run": run, "args_hash": args_hash, "approval_id": pending.id})
                return CallResult(status="approval_required", approval_id=pending.id, reason=f"{tool.tier} action needs a human approval")

            if mode == "shadow":                                  # a shadow run decides everything except it never acts
                self._log(s, tenant, "tool.shadow", {"tool": tool.name, "tier": tool.tier, "run": run, "args_hash": args_hash})
                return CallResult(status="shadow_skipped")

            s.add(ToolCallRow(tenant=tenant, tool=tool.name, idempotency_key=key, args_hash=args_hash, result="", status="running", started=self.clock()))   # claim the key first
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                return CallResult(status="denied", reason="a call with this idempotency key is already running")
            if approval is not None:
                # An approval covers exactly one execution: claim it atomically BEFORE acting, so two simultaneous calls cannot both use it.
                used = s.execute(update(ApprovalRow).where(ApprovalRow.id == approval.id, ApprovalRow.status == "approved").values(status="used")).rowcount
                if used != 1:
                    s.rollback()
                    return CallResult(status="denied", reason="the approval was already used")
            self._log(s, tenant, "tool.started", {"tool": tool.name, "tier": tool.tier, "run": run, "args_hash": args_hash, "approval_id": approval.id if approval else None})
            return _Claimed(approval.id if approval else None)

    def _release(self, tenant: str, tool: Tool, run: str, args_hash: str, key: str, approval_id: str | None, error: Exception) -> CallResult:
        """The handler raised, so by contract it did nothing: free the key and give the approval back so the call can be retried, and ledger the failure."""
        with self.sf.begin() as s:
            s.execute(delete(ToolCallRow).where(ToolCallRow.tenant == tenant, ToolCallRow.tool == tool.name, ToolCallRow.idempotency_key == key, ToolCallRow.status == "running"))
            if approval_id:
                s.execute(update(ApprovalRow).where(ApprovalRow.id == approval_id, ApprovalRow.status == "used").values(status="approved"))
            self._log(s, tenant, "tool.failed", {"tool": tool.name, "run": run, "args_hash": args_hash, "error": type(error).__name__})      # the class name only: messages can carry customer data
        return CallResult(status="failed", reason="the tool failed; nothing was recorded as done and the call can be retried with the same idempotency key")

    def recover_stuck(self) -> int:
        """Marks calls that began longer than the lease ago and never reported back as `unknown`. Run at start-up; a call is also checked when its key is used again."""
        n = 0
        with self.sf.begin() as s:
            for row in s.scalars(select(ToolCallRow).where(ToolCallRow.status == "running", ToolCallRow.started <= self.clock() - self.lease_s)):
                row.status = "unknown"
                self._log(s, row.tenant, "tool.unknown_outcome", {"tool": row.tool, "args_hash": row.args_hash, "started": row.started})
                n += 1
        return n

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
        new = "approved" if approve else "rejected"
        with self.sf.begin() as s:
            # One conditional UPDATE decides the race: of several simultaneous deciders exactly one changes a row that is still pending.
            won = s.execute(update(ApprovalRow).where(ApprovalRow.tenant == tenant, ApprovalRow.id == approval_id, ApprovalRow.status == "pending").values(status=new, decided_by=approver)).rowcount
            if won != 1:
                raise KeyError(approval_id)
            tool = s.scalar(select(ApprovalRow.tool).where(ApprovalRow.id == approval_id))
            self._log(s, tenant, "approval.decided", {"approval_id": approval_id, "tool": tool, "status": new, "decided_by": approver})
            return {"id": approval_id, "status": new}
