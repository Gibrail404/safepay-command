"""The faithfulness checker: deterministic rules that decide whether an explanation says anything the evidence does not support.
It uses no model. Its headline output is the unsupported-claim rate: the share of sentences that break a rule."""
from __future__ import annotations
import re
from dataclasses import dataclass
from .evidence import FORBIDDEN_BY_OUTCOME, Evidence

CITE = re.compile(r"\[\s*(E\d+(?:\s*,\s*E\d+)*)\s*\]")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENSITIVE = re.compile(r"\b(pin|otp|password|passcode|cvv|cvc)\b", re.I)
MONEY_MOVE = re.compile(r"\b(send|transfer|wire)\b.{0,25}\b(money|funds|cash|aed|dirhams?)\b", re.I)
URLISH = re.compile(r"https?://|www\.|\b[\w.+-]+@[\w-]+\.\w+", re.I)
@dataclass(frozen=True)
class Issue:
    sentence: int
    rule: str
    detail: str


def _num(s: str) -> str:
    return s.replace(",", "").rstrip(".")


def cited_ids(sentence: str) -> list[str]:
    return [i.strip() for m in CITE.findall(sentence) for i in m.split(",")]


def strip_citations(sentence: str) -> str:
    """The sentence as a person should read it: citation tags removed and no stray space left before punctuation ("go ahead [E1]." becomes "go ahead.")."""
    return re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", CITE.sub("", sentence))).strip()


def check_sentences(sentences: list[str], evidence: list[Evidence], outcome: str) -> list[Issue]:
    by_id = {e.id: e for e in evidence}
    issues: list[Issue] = []
    for n, sent in enumerate(sentences):
        ids = cited_ids(sent)
        text = strip_citations(sent)
        if not ids:
            issues.append(Issue(n, "R1_no_citation", "sentence cites no evidence id"))
        for i in ids:
            if i not in by_id:
                issues.append(Issue(n, "R1_unknown_evidence", f"{i} does not exist"))
        support = " ".join(by_id[i].text for i in ids if i in by_id)
        supported_numbers = {_num(x) for x in NUM.findall(support)}
        for x in NUM.findall(text):
            if _num(x) not in supported_numbers:
                issues.append(Issue(n, "R2_unsupported_number", f"{x} is not in the cited evidence"))
        low = text.lower()
        for w in FORBIDDEN_BY_OUTCOME[outcome]:
            if w in low:
                issues.append(Issue(n, "R3_contradicts_decision", f"'{w}' contradicts the decision ({outcome})"))
        if SENSITIVE.search(text) or MONEY_MOVE.search(text) or URLISH.search(text):
            issues.append(Issue(n, "R4_forbidden_content", "asks for credentials, tells the customer to move money, or contains a link or address"))
    return issues


def unsupported_rate(sentences: list[str], evidence: list[Evidence], outcome: str) -> float:
    bad = {i.sentence for i in check_sentences(sentences, evidence, outcome)}
    return len(bad) / len(sentences) if sentences else 0.0
