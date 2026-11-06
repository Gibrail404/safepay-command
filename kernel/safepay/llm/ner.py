"""Optional named-entity layer for the redactor: people's names and street addresses, which patterns cannot find.
Uses spaCy's small English model when it is installed. If it is not installed the redactor still works (patterns only) and reports that the layer is off.
Cities and countries are left readable on purpose: they are not identifying on their own and the model often needs them."""
from __future__ import annotations
import os, re, sys, threading
from pathlib import Path

_lock = threading.Lock()
_nlp = None
_tried = False
STREET = re.compile(r"\b\d{1,5}\s+(?:[A-Z][\w'\-]+\s+){1,3}(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|Way|Place|Pl)\b\.?", re.I)
POBOX = re.compile(r"\bP\.?\s?O\.?\s?Box\s+\d+\b", re.I)
LABELS = {"PERSON": "NAME", "FAC": "ADDRESS"}
GAZETTEER_PATH = Path(__file__).resolve().parents[3] / "config" / "name_gazetteer.txt"
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
CUES = {"named", "called", "to", "pay", "from", "with", "mr", "mrs", "ms", "miss", "dr", "landlord", "friend", "cousin", "uncle", "aunt", "brother", "sister", "manager", "agent", "officer",
        "contractor", "builder", "supplier", "payee", "beneficiary", "name", "dear", "hi", "hello", "hey", "regards", "by", "ask", "tell", "told"}
_gaz: set[str] | None = None


def gazetteer() -> set[str]:
    """Lower-case name tokens from real public lists (see scripts/build_name_gazetteer.py). Empty, and the second pass off, if the file is missing or SAFEPAY_GAZETTEER=off."""
    global _gaz
    with _lock:
        if _gaz is None:
            path = Path(os.environ.get("SAFEPAY_GAZETTEER", GAZETTEER_PATH))
            off = os.environ.get("SAFEPAY_GAZETTEER", "").lower() in ("0", "off", "false")
            _gaz = set(path.read_text().split()) if (not off and path.exists()) else set()
    return _gaz


def set_gazetteer(tokens: set[str] | None) -> None:
    """For tests and evaluations: replace the list (None reloads it from the file on next use)."""
    global _gaz
    with _lock:
        _gaz = tokens


def _is_name_token(tok: str, gaz: set[str]) -> bool:
    if len(tok) < 3 or not tok[0].isupper():                          # names are written with a capital; this alone removes most ordinary words
        return False
    return any(len(part) >= 3 and part.lower().strip("'") in gaz for part in tok.split("-"))


def gazetteer_spans(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(strong, weak) spans of name tokens. Strong: a run of two or more consecutive name tokens, or one name token right after a cue word ("my landlord Ahmed", "pay Ahmed").
    Weak: a lone name token with no cue; it is only used when it touches a name the language model already found."""
    gaz = gazetteer()
    if not gaz:
        return [], []
    toks = [(m.start(), m.end(), m.group()) for m in WORD.finditer(text)]
    strong, weak, run = [], [], []

    def close():
        if not run:
            return
        span = (run[0][0], run[-1][1])
        if len(run) >= 2:
            strong.append(span)
        else:
            prev = [t for t in toks if t[1] <= run[0][0]]
            (strong if prev and prev[-1][2].lower().strip("'.") in CUES and text[prev[-1][1]:run[0][0]].strip() == "" else weak).append(span)
        run.clear()
    for t in toks:
        if _is_name_token(t[2], gaz) and (not run or text[run[-1][1]:t[0]] == " "):
            run.append(t)
        else:
            close()
            if _is_name_token(t[2], gaz):
                run.append(t)
    close()
    return strong, weak


def _load():
    global _nlp, _tried
    with _lock:
        if not _tried:
            _tried = True
            if os.environ.get("SAFEPAY_NER", "auto").lower() in ("0", "off", "false"):
                return None
            hide_torch = "torch" not in sys.modules
            if hide_torch:
                sys.modules["torch"] = None          # spaCy's backend optionally imports torch, whose OpenMP runtime clashes with LightGBM's (see ml/safepay_ml/scorers.py). Blocking the import makes it fall back to numpy.
            try:
                import spacy
                _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "parser", "attribute_ruler"])
            except Exception:
                _nlp = None
            finally:
                if hide_torch and sys.modules.get("torch", 0) is None:
                    del sys.modules["torch"]
    return _nlp


def available() -> bool:
    return _load() is not None


def spans(text: str, with_model: bool = True) -> list[tuple[int, int, str]]:
    """(start, end, kind) for addresses (patterns, always) and people (the language model, then the name list, when available and wanted), non-overlapping, sorted by start."""
    found: list[tuple[int, int, str]] = [(m.start(), m.end(), "ADDRESS") for rx in (STREET, POBOX) for m in rx.finditer(text)]
    nlp = _load() if with_model else None
    if nlp is not None and text.strip():
        for e in nlp(text[:5000]).ents:
            if e.label_ in LABELS:
                found.append((e.start_char, e.end_char, LABELS[e.label_]))
    if with_model:
        strong, weak = gazetteer_spans(text)
        found += [(a, b, "NAME") for a, b in strong]
        names = [(a, b) for a, b, k in found if k == "NAME"]
        for a, b in weak:                                               # a lone, cue-less name token only if it touches a name already found ("Ahmed" found, "Al-Rashid" left over)
            if any(text[y:a].strip(" -") == "" and a - y <= 1 or text[b:x].strip(" -") == "" and x - b <= 1 for x, y in names):
                found.append((a, b, "NAME"))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    merged: list[tuple[int, int, str]] = []
    for st, en, k in found:
        if merged and (st < merged[-1][1] or (k == "NAME" == merged[-1][2] and st - merged[-1][1] <= 1 and text[merged[-1][1]:st].strip() == "")):
            if en > merged[-1][1]:
                merged[-1] = (merged[-1][0], en, merged[-1][2])
            continue
        merged.append((st, en, k))
    return merged
