"""Answer flags: simple keyword rules over the customer's OWN extracted words. The result can only add friction in the policy.
A customer (or an attacker who writes the customer's messages) can raise these flags, but no flag can lower the outcome."""
from __future__ import annotations

KEYWORDS = {
    "third_party_instructed": ["told me to", "asked me to", "instructed me", "called me", "messaged me", "someone asked", "someone told", "they told me", "he told me", "she told me"],
    "urgency": ["urgent", "hurry", "immediately", "right now", "straight away", "today only", "deadline"],
    "secrecy": ["secret", "don't tell", "do not tell", "dont tell", "keep it quiet", "not to tell", "confidential"],
    "unknown_payee": ["don't know", "do not know", "dont know", "never met", "stranger", "met online", "never paid"],
}


def answer_flags(claims: list[str]) -> dict[str, bool]:
    text = " ".join(claims).lower()
    return {flag: any(k in text for k in words) for flag, words in KEYWORDS.items()}
