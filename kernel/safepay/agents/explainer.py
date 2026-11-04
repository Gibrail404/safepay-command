"""Explainer: turns a policy decision into a short, calm message for the customer. It sees ONLY structured evidence, never customer-written text,
and every sentence it writes must cite evidence ids and pass the deterministic faithfulness checker. Otherwise the deterministic template is used."""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from ..llm.gateway import LLMGateway, LLMRequest, LLMResult
from .evidence import Evidence, build_evidence
from .faithfulness import check_sentences, strip_citations


class Explanation(BaseModel):
    sentences: list[str] = Field(min_length=1, max_length=4)

    @field_validator("sentences")
    @classmethod
    def sentence_length(cls, v):
        if any(not (5 <= len(s) <= 260) for s in v):
            raise ValueError("each sentence must be 5 to 260 characters")
        return v


def customer_text(exp: Explanation) -> str:
    return " ".join(strip_citations(s) for s in exp.sentences)


def fallback_explanation(evidence: list[Evidence]) -> Explanation:
    """Built only from the evidence texts, so it passes the faithfulness checker by construction (and a property test proves it)."""
    ordered = [e for e in evidence if e.kind == "decision"] + [e for e in evidence if e.kind == "reason"] + [e for e in evidence if e.kind in ("amount", "payee")]
    return Explanation(sentences=[f"{e.text} [{e.id}]" for e in ordered[:3]])


def _task(evidence: list[Evidence]) -> str:
    lines = "\n".join(f"{e.id}: {e.text}" for e in evidence)
    return ("You are the Explainer. Write 2 to 4 short, calm, plain-English sentences telling the customer what is happening with their payment and why. "
            "Use ONLY the evidence below. End every sentence with citation tags naming the evidence you used, like [E1] or [E1, E3]. "
            "Do not add any number that is not in the cited evidence. Do not ask for a PIN, OTP, password or card details, do not tell the customer to send or transfer money, "
            "and do not include links. Output JSON with one key, sentences, a list of strings.\nEvidence:\n" + lines)


def explain(gateway: LLMGateway, run_id: str, context: dict, outcome: str, reason_codes: list[str]) -> tuple[Explanation, LLMResult, list[Evidence]]:
    evidence = build_evidence(context, outcome, reason_codes)
    check = lambda exp: [f"sentence {i.sentence + 1}: {i.rule} ({i.detail})" for i in check_sentences(exp.sentences, evidence, outcome)]
    result = gateway.generate(LLMRequest(task=_task(evidence), output=Explanation, check=check, max_tokens=300), run_id, lambda: fallback_explanation(evidence))
    return result.parsed, result, evidence
