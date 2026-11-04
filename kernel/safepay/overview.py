"""Everything on the overview page, computed from what is really stored for one tenant: the ledger, decisions, case investigations, interceptions and the AI usage counter.
There is no composite score and nothing invented: each number is a count or a share of counts the page explains."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .cases import list_cases, stats
from .db import CaseRow, DecisionRow, InterceptionRow, LedgerEntry, LlmUsageRow


def _hour(ts: str) -> str:
    return ts[:13] + ":00"


def overview(s: Session, tenant: str, now: datetime | None = None, daily_request_cap: int = 400) -> dict:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=23)).strftime("%Y-%m-%dT%H")
    kinds = dict(s.execute(select(LedgerEntry.kind, func.count()).where(LedgerEntry.tenant == tenant).group_by(LedgerEntry.kind)).all())
    recent = s.execute(select(LedgerEntry.ts, LedgerEntry.kind).where(LedgerEntry.tenant == tenant, LedgerEntry.ts >= since).order_by(LedgerEntry.seq)).all()
    buckets: dict[str, Counter] = {}
    for ts, kind in recent:
        buckets.setdefault(_hour(ts), Counter())[kind] += 1
    hours = [(now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(23, -1, -1)]
    activity = [{"hour": h, "total": sum(buckets.get(h, {}).values()), "by_kind": dict(buckets.get(h, {}))} for h in hours]

    outcomes, reasons = Counter(), Counter()
    for (resp,) in s.execute(select(DecisionRow.response).where(DecisionRow.tenant == tenant).order_by(DecisionRow.id.desc()).limit(1000)):
        d = json.loads(resp)
        outcomes[d["outcome"]] += 1
        for r in d.get("reasons", []):
            reasons[r["code"]] += 1

    paths, first_pass, reached_ai = Counter(), 0, 0
    for (inv,) in s.execute(select(CaseRow.investigation).where(CaseRow.tenant == tenant, CaseRow.investigation.is_not(None)).limit(2000)):
        j = json.loads(inv)
        paths[j.get("path", "?")] += 1
        if j.get("path") != "rule":
            reached_ai += 1
            fc = next((x for x in j.get("trace", {}).get("steps", []) if x["id"] == "fact_check"), None)
            first_pass += j.get("path") == "llm" and not (fc and fc["detail"].get("repaired"))

    icp = Counter()
    for state, result, payment in s.execute(select(InterceptionRow.state, InterceptionRow.result, InterceptionRow.payment).where(InterceptionRow.tenant == tenant).limit(2000)):
        icp["total"] += 1
        if state == "decided" and result:
            icp["decided"] += 1
            icp["held"] += json.loads(result)["decision"]["outcome"] in ("hold", "block")
            icp["questioned"] += bool(json.loads(payment).get("trigger"))

    use = s.get(LlmUsageRow, now.strftime("%Y-%m-%d"))
    top_cases = list_cases(s, tenant, "open", 5, 0)["cases"]
    return {"cases": stats(s, tenant), "ledger": {"length": sum(kinds.values()), "by_kind": kinds}, "activity_by_hour": activity,
            "decisions": {"total": sum(outcomes.values()), "by_outcome": dict(outcomes), "top_reasons": [{"code": c, "count": n} for c, n in reasons.most_common(6)]},
            "ai_guardrails": {"investigations": sum(paths.values()), "by_path": dict(paths), "reached_the_ai": reached_ai, "passed_first_time": int(first_pass),
                              "first_pass_rate": (first_pass / reached_ai) if reached_ai else None},
            "interceptions": dict(icp), "ai_usage_today": {"requests": use.requests if use else 0, "tokens": use.tokens if use else 0, "request_cap": daily_request_cap},
            "recent_open_cases": top_cases}
