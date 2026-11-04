"""The interception flow: one payment goes through the risk score, up to three customer questions, the flags the answers raise, the policy decision, a message for the customer
and the audit ledger. The AI interprets what the customer says; the model gives the risk score; the policy engine owns the outcome. Flags can only add friction.
Everything the page shows comes from the stored state of one `interceptions` row, so it can be replayed and audited."""
from __future__ import annotations
import json, time, uuid
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from . import ledger
from .agents.evidence import REASON_TEXT, build_evidence
from .agents.explainer import customer_text, explain
from .agents.flags import answer_flags
from .agents.questioner import MAX_QUESTIONS, QuestionState, extract_claims, next_step
from .db import InterceptionRow, LedgerEntry
from .decisions import DecisionRequest, DecisionService
from .llm.gateway import LLMGateway

STALE_S = 90                                 # an answer that has been "being processed" for longer than this is treated as abandoned


class NotFound(Exception):
    pass


class AlreadyDecided(Exception):
    pass


class Busy(Exception):
    pass


class BadAnswer(Exception):
    pass


def needs_questions(amount: float, payee_age_days: int, band: str) -> list[str]:
    """Friction only where there is a reason. An empty list means the payment goes straight to the policy."""
    why = []
    if band in ("elevated", "high"):
        why.append("The risk model rates the payment elevated or high.")
    if amount >= 3000:
        why.append("The amount is large.")
    if payee_age_days < 7 and amount >= 400:
        why.append("A sizeable payment to a payee first seen less than a week ago.")
    return why


def _ms(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def _llm_meta(res) -> dict:
    if res is None:
        return {"path": "rule"}
    return {"path": res.path, "model": res.model, "tokens_in": res.tokens_in, "tokens_out": res.tokens_out, "fallback_reason": res.fallback_reason,
            "attempts": [{k: a[k] for k in ("provider", "ok", "reason", "kind", "detail", "ms") if k in a} for a in res.attempts], "injection_flags": res.injection_flags, "redactions": res.redactions}


class InterceptionService:
    def __init__(self, sf: sessionmaker[Session], llm: LLMGateway, decisions: DecisionService):
        self.sf, self.llm, self.decisions = sf, llm, decisions

    # ------------------------------------------------------------------ start
    def start(self, tenant: str, payment: dict, risk: dict, mode: str, truth: dict | None) -> str:
        iid = "i_" + uuid.uuid4().hex[:12]
        why = needs_questions(payment["amount"], payment["payee_age_days"], risk["risk_band"])
        payment = {**payment, "risk": risk, "trigger": why}
        transcript: list[dict] = []
        if why:
            t = time.perf_counter()
            step, res = next_step(self.llm, f"{iid}-q0", build_evidence(self._facts(payment), "hold", []), QuestionState())
            transcript.append({"question": step.question, "answer": None, "ms": _ms(t), "llm": _llm_meta(res)})
        with self.sf.begin() as s:
            s.add(InterceptionRow(id=iid, tenant=tenant, state="asking" if why else "decided", mode=mode, payment=ledger.canonical_json(payment), transcript=ledger.canonical_json(transcript),
                                  truth=ledger.canonical_json(truth) if truth else None, created=ledger.now_iso(), busy_since=0.0))
        if not why:
            self._finalize(tenant, iid)
        return iid

    @staticmethod
    def _facts(payment: dict) -> dict:
        return {"amount": payment["amount"], "payee_age_days": payment["payee_age_days"], "currency": payment.get("currency", "EUR")}

    # ----------------------------------------------------------------- answer
    def answer(self, tenant: str, iid: str, text: str) -> None:
        text = text.strip()
        if not (1 <= len(text) <= 500):
            raise BadAnswer("an answer must be 1 to 500 characters")
        now = time.time()
        with self.sf.begin() as s:
            # Claim first, read afterwards. The claim is one conditional UPDATE, so of several simultaneous answers exactly one wins; reading the row only AFTER winning means
            # the winner never works from a stale copy (reading first let a late request overwrite an earlier answer).
            claimed = s.execute(update(InterceptionRow).where(InterceptionRow.id == iid, InterceptionRow.tenant == tenant, InterceptionRow.state == "asking",
                                                              (InterceptionRow.busy_since == 0.0) | (InterceptionRow.busy_since < now - STALE_S)).values(busy_since=now)).rowcount
            if claimed != 1:
                row = s.scalar(select(InterceptionRow).where(InterceptionRow.tenant == tenant, InterceptionRow.id == iid))
                if row is None:
                    raise NotFound(iid)
                if row.state != "asking":
                    raise AlreadyDecided(iid)
                raise Busy(iid)                                         # another answer for this payment is being processed
            row = self._row(s, tenant, iid)
            transcript = json.loads(row.transcript)
            if not transcript or transcript[-1]["answer"] is not None:
                s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(busy_since=0.0))
                raise Busy(iid)
            transcript[-1]["answer"] = text
            payment = json.loads(row.payment)
            s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(transcript=ledger.canonical_json(transcript)))      # the answer is saved before any AI call
        try:
            if len(transcript) < MAX_QUESTIONS:
                t = time.perf_counter()
                state = QuestionState(asked=[x["question"] for x in transcript], answers=[x["answer"] for x in transcript])
                step, res = next_step(self.llm, f"{iid}-q{len(transcript)}", build_evidence(self._facts(payment), "hold", []), state)
                transcript.append({"question": step.question, "answer": None, "ms": _ms(t), "llm": _llm_meta(res)})
                with self.sf.begin() as s:
                    s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(transcript=ledger.canonical_json(transcript), busy_since=0.0))
            else:
                with self.sf.begin() as s:
                    s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(transcript=ledger.canonical_json(transcript)))
                self._finalize(tenant, iid)
        except Exception:
            with self.sf.begin() as s:
                s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(busy_since=0.0))
            raise

    # --------------------------------------------------------------- finalize
    def _finalize(self, tenant: str, iid: str) -> None:
        with self.sf() as s:
            row = self._row(s, tenant, iid)
            payment, transcript = json.loads(row.payment), json.loads(row.transcript)
        answers = [x["answer"] for x in transcript if x["answer"]]
        t = time.perf_counter()
        claims, claims_res = extract_claims(self.llm, f"{iid}-read", QuestionState(asked=[x["question"] for x in transcript], answers=answers))
        read_ms = _ms(t)
        flags_ai, flags_raw = answer_flags(claims), answer_flags(answers)          # phrases the AI quoted, and the customer's own words checked by the same keyword rules
        flags = {k: flags_ai[k] or flags_raw[k] for k in flags_ai}                # either can only ADD friction, so using both is safe
        ctx = {**self._facts(payment), "risk_band": payment["risk"]["risk_band"], "risk_score": round(payment["risk"]["risk_score"], 6), **flags}
        t = time.perf_counter()
        decision, _ = self.decisions.decide(tenant, f"icp-{iid}", DecisionRequest(workload="payment_risk", subject={"type": "payment", "id": iid}, context=ctx))
        policy_ms = _ms(t)
        t = time.perf_counter()
        exp, exp_res, _ = explain(self.llm, f"{iid}-say", ctx, decision.outcome, [r.code for r in decision.reasons])
        say_ms = _ms(t)
        with self.sf.begin() as s:
            entry = s.scalar(select(LedgerEntry).where(LedgerEntry.tenant == tenant, LedgerEntry.kind == "decision", LedgerEntry.payload.contains(f'"decision_id":"{decision.decision_id}"')))
            result = {"claims": claims, "claims_llm": _llm_meta(claims_res), "read_ms": read_ms, "flags": flags, "flags_from_ai_phrases": flags_ai, "flags_from_customer_words": flags_raw, "context": ctx, "decision": decision.model_dump(), "reason_text": {r.code: REASON_TEXT.get(r.code, "") for r in decision.reasons}, "policy_ms": policy_ms,
                      "explanation": {"text": customer_text(exp), "llm": _llm_meta(exp_res), "ms": say_ms}, "ledger": {"seq": entry.seq, "hash": entry.hash, "ts": entry.ts} if entry else None}
            s.execute(update(InterceptionRow).where(InterceptionRow.id == iid).values(state="decided", result=ledger.canonical_json(result), decision_id=decision.decision_id, busy_since=0.0))

    # ------------------------------------------------------------------- read
    @staticmethod
    def _row(s: Session, tenant: str, iid: str) -> InterceptionRow:
        row = s.scalar(select(InterceptionRow).where(InterceptionRow.tenant == tenant, InterceptionRow.id == iid))
        if row is None:
            raise NotFound(iid)
        return row

    def get(self, tenant: str, iid: str) -> dict:
        with self.sf() as s:
            row = self._row(s, tenant, iid)
            payment, transcript = json.loads(row.payment), json.loads(row.transcript)
            result = json.loads(row.result) if row.result else None
            out = {"id": row.id, "state": row.state, "mode": row.mode, "created": row.created, "payment": {k: v for k, v in payment.items() if k != "features"},
                   "transcript": [{"question": x["question"], "answer": x["answer"]} for x in transcript], "result": result, "trace": trace(payment, transcript, result)}
            if row.state == "decided" and row.truth:                    # hidden until the decision exists
                out["revealed_truth"] = json.loads(row.truth)
            return out


def trace(payment: dict, transcript: list[dict], result: dict | None) -> dict:
    """The recorded steps with measured times. A step that has not happened yet is simply absent, so the page never shows something that did not occur."""
    risk = payment["risk"]
    asked = [x for x in transcript]
    q_ms = sum(x.get("ms", 0) for x in asked)
    steps = [
        {"id": "payment", "label": "Payment arrives", "status": "ok", "ms": 0, "detail": {"amount": payment["amount"], "currency": payment.get("currency", "EUR"), "payee_age_days": payment["payee_age_days"], "reference": payment.get("row_ref"), "note": payment.get("provenance", "")}},
        {"id": "risk", "label": "Risk model", "status": "ok", "ms": risk.get("ms", 0), "detail": {"score": risk["risk_score"], "band": risk["risk_band"], "model_version": risk.get("model_version"), "model_type": risk.get("model_type")}},
        {"id": "trigger", "label": "Do we need to ask?", "status": "ok" if payment["trigger"] else "skipped", "ms": 0,
         "detail": {"reasons": payment["trigger"], "note": "Questions are asked only when there is a reason." if payment["trigger"] else "No reason to add friction: the payment goes straight to the policy."}},
    ]
    if payment["trigger"]:
        steps.append({"id": "questions", "label": "Questions to the customer", "status": "ok", "ms": q_ms,
                      "detail": {"turns": [{"question": x["question"], "answer": x["answer"], "ms": x.get("ms", 0), "llm": x.get("llm", {})} for x in asked]}})
    if result:
        steps.append({"id": "flags", "label": "What the answers show", "status": "ok" if payment["trigger"] else "skipped", "ms": result.get("read_ms", 0),
                      "detail": {"claims": result["claims"], "flags": result["flags"], "from_ai_phrases": result.get("flags_from_ai_phrases", {}), "from_customer_words": result.get("flags_from_customer_words", {}), "llm": result.get("claims_llm", {}), "note": "Flags can only add friction. They can never lower the outcome."}})
        d = result["decision"]
        steps.append({"id": "policy", "label": "Policy decision", "status": "ok", "ms": result.get("policy_ms", 0),
                      "detail": {"outcome": d["outcome"], "risk_tier": d["risk_tier"], "requires_approval": d["requires_approval"], "policy_version": d["policy_version"], "reasons": d["reasons"], "decision_id": d["decision_id"]}})
        steps.append({"id": "explain", "label": "Message to the customer", "status": "ok", "ms": result["explanation"]["ms"], "detail": {"text": result["explanation"]["text"], "llm": result["explanation"]["llm"]}})
        steps.append({"id": "ledger", "label": "Audit ledger", "status": "ok" if result.get("ledger") else "failed", "ms": 0, "detail": result.get("ledger") or {"note": "no ledger entry found"}})
    t = 0
    for st in steps:
        st["start_ms"] = t
        t += st["ms"]
    return {"total_ms": t, "steps": steps}
