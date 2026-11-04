"""Redaction of personal data and screening of prompt-injection attempts. Both run BEFORE any text reaches a provider.
Redaction is the real protection for personal data; injection screening is only a heuristic signal, because the real defences are that the LLM
has no tools, its output is schema-validated, and the policy engine decides."""
from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass, field

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
EMIRATES_ID = re.compile(r"\b784[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.I)
LONG_DIGITS = re.compile(r"(?<![\w.])\+?\d(?:[\d\s\-().]{6,}\d)(?![\w])")        # candidates for cards and phone numbers


def normalise(text: str) -> str:
    """Fold look-alike forms (fullwidth letters and digits) and drop invisible format characters (zero-width spaces and joiners),
    so that neither redaction nor injection screening can be dodged by typography. Applied before both."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total, flip = total + d, not flip
    return total % 10 == 0


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)      # token -> original; lives only in memory, never sent anywhere

    @property
    def count(self) -> int:
        return len(self.mapping)


def redact(text: str) -> Redaction:
    text = normalise(text)
    mapping: dict[str, str] = {}

    def put(kind: str, original: str) -> str:
        for tok, val in mapping.items():
            if val == original:
                return tok
        tok = f"[{kind}_{sum(1 for t in mapping if t.startswith(f'[{kind}_')) + 1}]"
        mapping[tok] = original
        return tok

    def digits_sub(m: re.Match) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return put("CARD", raw)
        if 8 <= len(digits) <= 15:
            return put("PHONE", raw)
        return raw

    out = EMAIL.sub(lambda m: put("EMAIL", m.group(0)), text)
    out = EMIRATES_ID.sub(lambda m: put("ID", m.group(0)), out)
    out = IBAN.sub(lambda m: put("IBAN", m.group(0)), out)
    out = LONG_DIGITS.sub(digits_sub, out)
    return Redaction(out, mapping)


INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|rules)", r"disregard (all |any |the )?(previous|prior|above)", r"you are now\b",
    r"\bsystem prompt\b", r"\bdeveloper message\b", r"reveal (your|the) (instructions|prompt|rules)", r"\b(release|approve|send|transfer|refund)\b.{0,40}\b(payment|funds|money|account)\b",
    r"act as\b", r"jailbreak", r"</?(system|assistant|instructions?)>", r"new instructions?:",
]
_INJECTION = [re.compile(p, re.I | re.S) for p in INJECTION_PATTERNS]


def injection_flags(text: str) -> list[str]:
    text = normalise(text)
    return [p.pattern for p in _INJECTION if p.search(text)]


def wrap_untrusted(text: str) -> str:
    """Delimit untrusted text so the model is told it is data. The delimiter itself cannot be forged from inside the text."""
    cleaned = normalise(text).replace("<untrusted>", "").replace("</untrusted>", "")
    return f"<untrusted>\n{cleaned}\n</untrusted>"
