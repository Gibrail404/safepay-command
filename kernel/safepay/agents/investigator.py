"""Investigator: summarises a case for a human analyst. It sees only structured evidence (counts, scores, links), never free text from outside, and it never states
that anything is criminal. Every sentence must cite evidence ids and pass the same deterministic faithfulness checker as the Explainer. When the evidence is thin it
abstains, and that decision is made by a fixed rule BEFORE any model is called. Its recommendation can only raise a case's priority, never lower it or close it."""
from __future__ import annotations
import time
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from ..llm.gateway import LLMGateway, LLMRequest, LLMResult
from .evidence import Evidence
from .faithfulness import check_sentences, strip_citations

THIN_SCORE = 0.90                         # a lone alert below this score is too thin to summarise
HIGH_SCORE = 0.95


class CaseSummary(BaseModel):
    recommendation: Literal["escalate", "review", "abstain"]
    sentences: list[str] = Field(min_length=1, max_length=4)

    @field_validator("sentences")
    @classmethod
    def sentence_length(cls, v):
        if any(not (5 <= len(s) <= 300) for s in v):
            raise ValueError("each sentence must be 5 to 300 characters")
        return v


def case_numbers(items: list[dict]) -> dict:
    scores = [i["score"] for i in items]
    steps = sorted({i["time_step"] for i in items if i.get("time_step") is not None})
    return {"alerts": len(items), "max_score": max(scores), "mean_score": sum(scores) / len(scores), "time_step": steps[0] if len(steps) == 1 else None,
            "links": int(sum(i.get("facts", {}).get("linked_alerts", 0) for i in items) // 2), "max_neighbours": max((i.get("facts", {}).get("neighbours", 0) for i in items), default=0)}


def build_case_evidence(items: list[dict]) -> list[Evidence]:
    n = case_numbers(items)
    facts = [("alerts", f"The case groups {n['alerts']} alert{'s' if n['alerts'] != 1 else ''}" + (f" from time step {n['time_step']}." if n["time_step"] is not None else ".")),
             ("score", f"The highest model score is {n['max_score']:.2f} and the average is {n['mean_score']:.2f}, on a scale from 0 to 1."),
             ("links", f"{n['links']} direct link{'s' if n['links'] != 1 else ''} connect the alerts to each other."),
             ("neighbours", f"The busiest alert is directly linked to {n['max_neighbours']} other transaction{'s' if n['max_neighbours'] != 1 else ''}."),
             ("model", "The score comes from a model that looks only at each transaction's own features and was trained on earlier periods."),
             ("decision", "For now, the case is waiting for an analyst.")]
    return [Evidence(f"E{i}", k, t) for i, (k, t) in enumerate(facts, 1)]


def evidence_is_thin(items: list[dict]) -> bool:
    n = case_numbers(items)
    return n["alerts"] == 1 and n["max_score"] < THIN_SCORE


def priority_for(recommendation: str, items: list[dict]) -> str:
    return "high" if recommendation == "escalate" or case_numbers(items)["max_score"] >= HIGH_SCORE else "normal"


def abstain_summary(evidence: list[Evidence]) -> CaseSummary:
    return CaseSummary(recommendation="abstain", sentences=[f"{evidence[1].text} [{evidence[1].id}]", f"There is too little evidence to say more, so an analyst should look at the transaction itself. [{evidence[0].id}]"])


def fallback_summary(evidence: list[Evidence]) -> CaseSummary:
    return CaseSummary(recommendation="review", sentences=[f"{e.text} [{e.id}]" for e in evidence[:3]])


def _task(evidence: list[Evidence]) -> str:
    lines = "\n".join(f"{e.id}: {e.text}" for e in evidence)
    return ("You are the Investigator helping a human analyst. Summarise the case using ONLY the evidence below, in 2 to 4 short factual sentences, each ending with citation tags like [E1] or [E1, E2]. "
            "Choose recommendation: escalate if the scores and links are strong, review if moderate, abstain if the evidence is too thin to say. Do not add any number that is not in the cited evidence. "
            "Do not state or imply that anyone is guilty or that a crime happened; only describe the evidence. Do not mention approving, releasing, blocking or declining anything. "
            "Output JSON with keys recommendation and sentences.\nEvidence:\n" + lines)


def _steps(items, evidence, res, thin, facts_ms, rule_ms, check_ms, check_issues, priority, recommendation, total_ms):
    """Turns what really happened into an ordered list of steps with measured durations. Nothing here is invented: every status and number comes from the run."""
    attempts = list(res.attempts) if res else []
    ai_ms = sum(a.get("ms", 0) for a in attempts)
    ok_attempt = next((a for a in attempts if a.get("ok")), None)
    failed_checks = [a for a in attempts if a.get("kind") == "check" and not a.get("ok")]
    path = "rule" if thin else (res.path if res else "rule")
    steps = [
        {"id": "facts", "label": "Facts from the case", "status": "ok", "ms": facts_ms, "detail": {"facts": [{"id": e.id, "text": e.text} for e in evidence]}},
        {"id": "screen", "label": "Redaction and injection screen", "status": "skipped", "ms": 0, "detail": {"note": "No free text is sent to the AI here. It only sees the structured facts, so there is nothing to redact.", "injection_flags": []}},
        {"id": "rule", "label": "Abstain rule", "status": "stopped" if thin else "ok", "ms": rule_ms, "detail": {"note": "A lone alert with a score below 0.90 is too thin to summarise: stop and ask a person." if thin else "Enough evidence to ask the AI."}},
    ]
    if thin:
        steps += [{"id": "ai", "label": "AI summary", "status": "skipped", "ms": 0, "detail": {"note": "Not called: the abstain rule stopped here."}},
                  {"id": "fact_check", "label": "Fact check", "status": "skipped", "ms": 0, "detail": {"note": "Nothing to check."}}]
    else:
        steps.append({"id": "ai", "label": "AI summary", "status": "ok" if ok_attempt else "failed", "ms": ai_ms,
                      "detail": {"attempts": [{k: a[k] for k in ("provider", "ok", "reason", "kind", "detail", "ms") if k in a} for a in attempts], "model": res.model if res else None, "fallback_reason": getattr(res, "fallback_reason", None),
                                                                                   "tokens": {"in": res.tokens_in, "out": res.tokens_out}}})
        checked = res.path == "llm" or bool(failed_checks)
        steps.append({"id": "fact_check", "label": "Fact check", "status": ("ok" if res.path == "llm" else "failed") if checked else "skipped", "ms": check_ms,
                      "detail": {"repaired": bool(failed_checks) and res.path == "llm", "issues": check_issues[:6], "note": "Every sentence must cite a fact, use only numbers from the cited fact, and avoid forbidden wording." if checked else "The AI gave no reply to check."}})
        if res.path != "llm":
            steps.append({"id": "fallback", "label": "Safe fallback summary", "status": "ok", "ms": 0, "detail": {"note": "Written directly from the facts, so it passes the fact check by construction."}})
    steps.append({"id": "priority", "label": "Priority rule", "status": "ok", "ms": 0, "detail": {"recommendation": recommendation, "priority": priority, "note": "The recommendation can raise a case's priority, never lower it or close it."}})
    steps.append({"id": "ledger", "label": "Audit ledger", "status": "ok", "ms": 0, "detail": {"note": "Written to the tamper-evident chain (see the audit trail)."}})
    t = 0
    for st in steps:
        st["start_ms"] = t
        t += st["ms"]
    return {"path": path, "total_ms": total_ms, "steps": steps}


def investigate_traced(gateway: LLMGateway, run_id: str, items: list[dict]):
    """Same as `investigate`, plus a trace of what happened at each step with measured timings."""
    t_all = time.perf_counter()
    t = time.perf_counter()
    evidence = build_case_evidence(items)
    facts_ms = round((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    thin = evidence_is_thin(items)
    rule_ms = round((time.perf_counter() - t) * 1000)
    check_ms, check_issues, res = 0, [], None
    if thin:
        summary = abstain_summary(evidence)
    else:
        def check(s):
            nonlocal check_ms
            t0 = time.perf_counter()
            issues = [f"sentence {i.sentence + 1}: {i.rule} ({i.detail})" for i in check_sentences(s.sentences, evidence, "hold")]
            check_ms += round((time.perf_counter() - t0) * 1000)
            check_issues.extend(issues)
            return issues
        res = gateway.generate(LLMRequest(task=_task(evidence), output=CaseSummary, check=check, max_tokens=350), run_id, lambda: fallback_summary(evidence))
        summary = res.parsed
    prio = priority_for(summary.recommendation, items)
    total_ms = round((time.perf_counter() - t_all) * 1000)
    trace = _steps(items, evidence, res, thin, facts_ms, rule_ms, check_ms, check_issues, prio, summary.recommendation, total_ms)
    return summary, res, evidence, prio, trace


def investigate(gateway: LLMGateway, run_id: str, items: list[dict]) -> tuple[CaseSummary, LLMResult | None, list[Evidence], str]:
    summary, res, evidence, prio, _ = investigate_traced(gateway, run_id, items)
    return summary, res, evidence, prio


def analyst_text(s: CaseSummary) -> str:
    return " ".join(strip_citations(x) for x in s.sentences)
