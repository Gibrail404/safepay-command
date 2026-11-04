"""Investigation cases, analyst dispositions and the labels they produce. Every change is written to the tenant's hash-chained ledger in the same transaction.
Tenant scoping: every query filters on the tenant taken from the API key, never from the request."""
from __future__ import annotations
import json, uuid
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from . import ledger
from .db import CaseRow, DispositionRow, LabelRow

MAX_JSON = 64_000
Decision = Literal["confirmed_illicit", "dismissed_licit", "escalated"]


def _bounded(v):
    if len(json.dumps(v, separators=(",", ":"))) > MAX_JSON:
        raise ValueError(f"object larger than {MAX_JSON} bytes")
    return v


class Item(BaseModel):
    ref: str = Field(min_length=1, max_length=64)
    score: float
    time_step: int | None = None
    facts: dict = Field(default_factory=dict)

    _cap = field_validator("facts")(_bounded)


class CaseIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    provenance: Literal["real", "simulated"]
    priority: Literal["high", "normal"] = "normal"
    title: str = Field(min_length=1, max_length=200)
    items: list[Item] = Field(min_length=1, max_length=200)
    facts: dict = Field(default_factory=dict)
    truth: dict | None = None            # the dataset's own labels, {ref: 0|1}; hidden from analysts until they decide

    _cap = field_validator("facts", "truth")(lambda v: _bounded(v) if v is not None else v)


class ImportIn(BaseModel):
    cases: list[CaseIn] = Field(min_length=1, max_length=500)


class DispositionIn(BaseModel):
    decision: Decision
    note: str = Field(default="", max_length=500)
    simulated: bool = False              # true when the "analyst" is a simulation (flywheel experiments)


class NotFound(Exception):
    pass


class AlreadyDecided(Exception):
    pass


def import_cases(s: Session, tenant: str, body: ImportIn) -> dict:
    existing = set(s.scalars(select(CaseRow.external_id).where(CaseRow.tenant == tenant, CaseRow.external_id.in_([c.external_id for c in body.cases]))))
    added = []
    for c in body.cases:
        if c.external_id in existing:
            continue
        s.add(CaseRow(id="c_" + uuid.uuid4().hex[:12], tenant=tenant, external_id=c.external_id, source=c.source, provenance=c.provenance, status="open", priority=c.priority, title=c.title,
                      content=ledger.canonical_json({"items": [i.model_dump() for i in c.items], "facts": c.facts}), truth=ledger.canonical_json(c.truth) if c.truth is not None else None))
        added.append(c.external_id)
    if added:
        ledger.append(s, tenant, "case.imported", {"count": len(added), "sha256": ledger.sha256_hex(ledger.canonical_json(sorted(added)))})
    return {"imported": len(added), "skipped_existing": len(body.cases) - len(added)}


def _row_view(r: CaseRow, disposition: DispositionRow | None, detail: bool) -> dict:
    out = {"id": r.id, "title": r.title, "status": r.status, "priority": r.priority, "source": r.source, "provenance": r.provenance, "has_investigation": r.investigation is not None}
    content = json.loads(r.content)
    out["alerts"] = len(content["items"])
    out["max_score"] = max(i["score"] for i in content["items"])
    if disposition:
        out["disposition"] = {"decision": disposition.decision, "actor": disposition.actor, "note": disposition.note, "ts": disposition.ts}
    if detail:
        out["items"], out["facts"] = content["items"], content["facts"]
        out["investigation"] = json.loads(r.investigation) if r.investigation else None
        if disposition and r.truth:                         # only after the analyst has decided
            out["revealed_truth"] = json.loads(r.truth)
    return out


def list_cases(s: Session, tenant: str, status: str | None, limit: int, offset: int) -> dict:
    q = select(CaseRow).where(CaseRow.tenant == tenant)
    if status:
        q = q.where(CaseRow.status == status)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.scalars(q.order_by(CaseRow.priority.asc(), CaseRow.id).limit(limit).offset(offset)).all()      # "high" sorts before "normal"
    disp = {d.case_id: d for d in s.scalars(select(DispositionRow).where(DispositionRow.tenant == tenant, DispositionRow.case_id.in_([r.id for r in rows])))} if rows else {}
    return {"total": total, "cases": [_row_view(r, disp.get(r.id), False) for r in rows]}


def _get(s: Session, tenant: str, case_id: str) -> CaseRow:
    r = s.scalar(select(CaseRow).where(CaseRow.tenant == tenant, CaseRow.id == case_id))
    if r is None:
        raise NotFound(case_id)
    return r


def get_case(s: Session, tenant: str, case_id: str) -> dict:
    r = _get(s, tenant, case_id)
    d = s.scalar(select(DispositionRow).where(DispositionRow.tenant == tenant, DispositionRow.case_id == case_id))
    return _row_view(r, d, True)


def case_content(s: Session, tenant: str, case_id: str) -> dict:
    return json.loads(_get(s, tenant, case_id).content)


def save_investigation(s: Session, tenant: str, case_id: str, summary: dict, meta: dict) -> None:
    r = _get(s, tenant, case_id)
    r.investigation = ledger.canonical_json({**summary, **meta})
    if summary.get("priority") == "high":
        r.priority = "high"                                  # friction-only: an investigation can raise a case's priority, never lower it
    ledger.append(s, tenant, "case.investigated", {"case_id": case_id, "path": meta.get("path"), "recommendation": summary.get("recommendation"), "summary_sha256": ledger.sha256_hex(r.investigation)})


def disposition(s: Session, tenant: str, case_id: str, actor: str, body: DispositionIn) -> dict:
    r = _get(s, tenant, case_id)
    if s.scalar(select(DispositionRow.id).where(DispositionRow.tenant == tenant, DispositionRow.case_id == case_id)):
        raise AlreadyDecided(case_id)
    ts = ledger.now_iso()
    s.add(DispositionRow(id="d_" + uuid.uuid4().hex[:12], tenant=tenant, case_id=case_id, actor=actor, decision=body.decision, note=body.note, ts=ts))
    r.status = "dispositioned"
    labelled = 0
    if body.decision in ("confirmed_illicit", "dismissed_licit"):
        value = 1 if body.decision == "confirmed_illicit" else 0
        for it in json.loads(r.content)["items"]:
            s.add(LabelRow(tenant=tenant, case_id=case_id, subject_ref=it["ref"], label=value, actor=actor, source="simulated_analyst" if body.simulated else "analyst", ts=ts))
            labelled += 1
    ledger.append(s, tenant, "case.dispositioned", {"case_id": case_id, "actor": actor, "decision": body.decision, "labels_written": labelled, "simulated": body.simulated})
    return {"case_id": case_id, "decision": body.decision, "labels_written": labelled}


def export_labels(s: Session, tenant: str, limit: int, offset: int) -> list[dict]:
    rows = s.scalars(select(LabelRow).where(LabelRow.tenant == tenant).order_by(LabelRow.id).limit(limit).offset(offset))
    return [{"subject_ref": x.subject_ref, "label": x.label, "case_id": x.case_id, "actor": x.actor, "source": x.source, "ts": x.ts} for x in rows]


def stats(s: Session, tenant: str) -> dict:
    by = dict(s.execute(select(CaseRow.status, func.count()).where(CaseRow.tenant == tenant).group_by(CaseRow.status)).all())
    hi = s.scalar(select(func.count()).where(CaseRow.tenant == tenant, CaseRow.status == "open", CaseRow.priority == "high"))
    labels = s.scalar(select(func.count()).select_from(LabelRow).where(LabelRow.tenant == tenant))
    return {"open": by.get("open", 0), "dispositioned": by.get("dispositioned", 0), "open_high_priority": hi, "labels": labels}
