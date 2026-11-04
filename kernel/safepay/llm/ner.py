"""Optional named-entity layer for the redactor: people's names and street addresses, which patterns cannot find.
Uses spaCy's small English model when it is installed. If it is not installed the redactor still works (patterns only) and reports that the layer is off.
Cities and countries are left readable on purpose: they are not identifying on their own and the model often needs them."""
from __future__ import annotations
import os, re, sys, threading

_lock = threading.Lock()
_nlp = None
_tried = False
STREET = re.compile(r"\b\d{1,5}\s+(?:[A-Z][\w'\-]+\s+){1,3}(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|Way|Place|Pl)\b\.?", re.I)
POBOX = re.compile(r"\bP\.?\s?O\.?\s?Box\s+\d+\b", re.I)
LABELS = {"PERSON": "NAME", "FAC": "ADDRESS"}


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
    """(start, end, kind) for addresses (patterns, always) and people (the model, when available and wanted), non-overlapping, sorted by start."""
    found: list[tuple[int, int, str]] = [(m.start(), m.end(), "ADDRESS") for rx in (STREET, POBOX) for m in rx.finditer(text)]
    nlp = _load() if with_model else None
    if nlp is not None and text.strip():
        for e in nlp(text[:5000]).ents:
            if e.label_ in LABELS:
                found.append((e.start_char, e.end_char, LABELS[e.label_]))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    merged: list[tuple[int, int, str]] = []
    for st, en, k in found:
        if merged and st < merged[-1][1]:
            if en > merged[-1][1]:
                merged[-1] = (merged[-1][0], en, merged[-1][2])
            continue
        merged.append((st, en, k))
    return merged
