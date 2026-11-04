"""Evidence: short plain-English facts built from STRUCTURED values only (numbers, bands, policy codes). Raw customer text never becomes evidence,
so the Explainer can be shown evidence without being exposed to customer-written instructions."""
from __future__ import annotations
from dataclasses import dataclass

OUTCOME_PHRASE = {"allow": "the payment can go ahead", "warn": "the payment can go ahead, with a warning", "hold": "the payment is paused for a check", "block": "the payment cannot be sent"}
REASON_TEXT = {
    "LARGE_AMOUNT": "The amount is larger than the limit for automatic approval.",
    "NEW_PAYEE_LARGE_AMOUNT": "A large payment to a brand-new payee is paused for a check.",
    "MODEL_RISK_ELEVATED": "Our fraud model rates this payment as somewhat riskier than usual.",
    "MODEL_RISK_HIGH": "Our fraud model rates this payment as high risk.",
    "SCREENING_HIT_CONFIRMED": "The payee matched a sanctions list entry.",
    "THIRD_PARTY_INSTRUCTED_NEW_PAYEE": "The answers suggest someone else asked for this payment to a new payee.",
    "PRESSURE_OR_SECRECY": "The answers mention pressure to hurry or to keep the payment secret.",
    "UNKNOWN_PAYEE_CLAIM": "The answers suggest the customer does not know the payee.",
}


FORBIDDEN_BY_OUTCOME = {
    "allow": ["paused", "on hold", "held", "blocked", "declined", "rejected", "cannot be sent"],
    "warn": ["paused", "on hold", "held", "blocked", "declined", "rejected", "cannot be sent"],
    "hold": ["blocked", "declined", "rejected", "cannot be sent", "go ahead", "approved", "completed", "has been sent"],
    "block": ["go ahead", "approved", "completed", "has been sent", "paused", "on hold"],
}



@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    text: str


def _days(n: int) -> str:
    return "today" if n == 0 else f"{n} day{'s' if n != 1 else ''} ago"


def build_evidence(context: dict, outcome: str, reason_codes: list[str]) -> list[Evidence]:
    facts: list[tuple[str, str]] = []
    if "amount" in context:
        facts.append(("amount", f"The payment amount is {context.get('currency', 'AED')} {float(context['amount']):,.0f}."))
    if "payee_age_days" in context:
        facts.append(("payee", f"The payee was first seen {_days(int(context['payee_age_days']))}."))
    if "risk_band" in context:
        facts.append(("model", f"Our fraud model rates this payment {context['risk_band']}."))
    for code in reason_codes:
        text = REASON_TEXT.get(code)
        if text and not any(w in text.lower() for w in FORBIDDEN_BY_OUTCOME[outcome]):     # evidence must never contradict the final decision
            facts.append(("reason", text))
    facts.append(("decision", f"For now, {OUTCOME_PHRASE[outcome]}."))
    return [Evidence(f"E{i}", kind, text) for i, (kind, text) in enumerate(facts, 1)]
