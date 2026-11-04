"""Questioner: asks at most three short questions when a payment is risky and extracts what the customer SAID.
It cannot decide anything. What it extracts is only ever used to ADD friction (see flags.py), never to remove it."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from ..llm.gateway import LLMGateway, LLMRequest, LLMResult
from .evidence import Evidence
from .faithfulness import SENSITIVE

MAX_QUESTIONS = 3
QUESTION_BANK = [
    "Did someone ask you to make this payment, or did you decide to make it yourself?",
    "Do you know the person or business you are paying, and have you paid them before?",
    "Has anyone told you to hurry or to keep this payment secret?",
]
DONE_TEXT = "Thank you, that is all I need to ask."
ACCUSATION = re.compile(r"\b(scam(mer)?|fraudster|liar|lying|criminal)\b", re.I)
ACTION = re.compile(r"\b(release|approve|transfer|send the money|wire)\b", re.I)


class QuestionStep(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    claims: list[str] = Field(max_length=5)
    done: bool


@dataclass
class QuestionState:
    asked: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def question_issues(step: QuestionStep, answers_text: str, asked: list[str]) -> list[str]:
    issues = []
    q = step.question.strip()
    if len(q) > 200 or q.count("?") != 1 or not q.endswith("?"):
        issues.append("the question must be one sentence of at most 200 characters ending with a single question mark")
    if SENSITIVE.search(q) or re.search(r"\bcard number\b", q, re.I):
        issues.append("the question asks for credentials or card details")
    if ACCUSATION.search(q):
        issues.append("the question accuses the customer")
    if ACTION.search(q):
        issues.append("the question mentions moving or releasing money")
    if _norm(q) in {_norm(a) for a in asked}:
        issues.append("the question repeats an earlier question")
    hay = _norm(answers_text)
    for c in step.claims:
        if len(c) > 120 or _norm(c) not in hay:
            issues.append(f"claim not copied word for word from the customer's messages: {c[:40]!r}")
    return issues


def fallback_step(state: QuestionState) -> QuestionStep:
    q = next((q for q in QUESTION_BANK if _norm(q) not in {_norm(a) for a in state.asked}), DONE_TEXT)
    return QuestionStep(question=q, claims=[], done=False)


def next_step(gateway: LLMGateway, run_id: str, evidence: list[Evidence], state: QuestionState) -> tuple[QuestionStep, LLMResult | None]:
    if len(state.asked) >= MAX_QUESTIONS:
        return QuestionStep(question=DONE_TEXT, claims=[], done=True), None
    answers_text = "\n".join(state.answers)
    facts = "\n".join(f"- {e.text}" for e in evidence if e.kind in ("amount", "payee"))
    asked = "\n".join(f"- {q}" for q in state.asked) or "- (none yet)"
    task = ("You are the Questioner. A customer is making a payment that needs a quick safety check. Ask ONE short, polite, neutral question (one sentence, one question mark) "
            "that helps understand whether they are being pressured or misled. Never ask for a PIN, OTP, password, CVV or card number, never accuse, never mention releasing or sending money, "
            "and do not repeat a question already asked. In claims, list short phrases copied WORD FOR WORD from the customer's messages that describe their situation; if there are none, use an empty list. "
            f"Set done to false. Output JSON with keys question, claims, done.\nFacts:\n{facts}\nQuestions already asked:\n{asked}")
    check = lambda step: question_issues(step, answers_text, state.asked)
    result = gateway.generate(LLMRequest(task=task, output=QuestionStep, untrusted=answers_text, check=check, max_tokens=250), run_id, lambda: fallback_step(state))
    step = result.parsed
    return QuestionStep(question=step.question, claims=step.claims, done=False), result
