"""Tamper-evident decision ledger: each record's hash covers the previous record's hash (a hash chain), per tenant."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import LedgerEntry, LedgerHead

GENESIS = "0" * 64


def canonical_json(obj) -> str:
    """The one JSON form we hash: sorted keys, no spaces, no NaN. Same data always gives the same string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry_hash(prev_hash: str, tenant: str, kind: str, ts: str, payload_json: str) -> str:
    return sha256_hex(f"{prev_hash}|{tenant}|{kind}|{ts}|{payload_json}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    reason: str = ""
    bad_seq: int | None = None


def append(session: Session, tenant: str, kind: str, payload: dict, ts: str | None = None) -> LedgerEntry:
    """Add one record. Runs inside the caller's transaction so a decision and its ledger entry commit together."""
    head = session.get(LedgerHead, tenant, with_for_update=True)   # row lock: two writers cannot fork the chain
    if head is None:
        head = LedgerHead(tenant=tenant, head_hash=GENESIS, length=0)
        session.add(head)
        session.flush()
    payload_json = canonical_json(payload)
    ts = ts or now_iso()
    h = entry_hash(head.head_hash, tenant, kind, ts, payload_json)
    entry = LedgerEntry(tenant=tenant, kind=kind, payload=payload_json, ts=ts, prev_hash=head.head_hash, hash=h)
    session.add(entry)
    head.head_hash, head.length = h, head.length + 1
    session.flush()
    return entry


def verify(session: Session, tenant: str) -> VerifyResult:
    """Recompute the whole chain. Detects edited, deleted, reordered, forged and truncated records."""
    prev, count = GENESIS, 0
    for e in session.scalars(select(LedgerEntry).where(LedgerEntry.tenant == tenant).order_by(LedgerEntry.seq)):
        if e.prev_hash != prev:
            return VerifyResult(False, count, "broken link: a record before this one was removed or changed", e.seq)
        if entry_hash(e.prev_hash, e.tenant, e.kind, e.ts, e.payload) != e.hash:
            return VerifyResult(False, count, "record content does not match its hash", e.seq)
        prev, count = e.hash, count + 1
    head = session.get(LedgerHead, tenant)
    head_hash, head_len = (head.head_hash, head.length) if head else (GENESIS, 0)
    if head_hash != prev or head_len != count:
        return VerifyResult(False, count, "ledger head does not match the records: entries were removed or added outside the ledger")
    return VerifyResult(True, count)


def entries(session: Session, tenant: str, after_seq: int = 0, limit: int = 100) -> list[LedgerEntry]:
    q = select(LedgerEntry).where(LedgerEntry.tenant == tenant, LedgerEntry.seq > after_seq).order_by(LedgerEntry.seq).limit(limit)
    return list(session.scalars(q))
