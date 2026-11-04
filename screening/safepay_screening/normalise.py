"""Turn a personal or company name into forms that can be compared.
`clean` removes typography (accents, case, punctuation, titles). `fold` also collapses common spelling variation between languages,
because the same person is written Mohammed, Muhammad or Mohamad depending on who transliterated the name."""
from __future__ import annotations
import re, unicodedata

TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "shaykh", "sheikh", "sheik", "haji", "hajji", "hajj", "eng", "col", "gen"}
PARTICLES = {"al", "el", "ul", "ad", "ar", "as", "at", "an", "ash", "az", "bin", "ibn", "bint", "abu", "de", "da", "van", "von", "the"}   # connective words that are often dropped or attached

_MUHAMMAD = re.compile(r"\b(?:m[ou]h?a?m+[ae]d+|m[ou]h?a?m+ad|mohd|muhd|mhd|md)\b")
_MILD_RULES = [("ph", "f"), ("ck", "k"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("ai", "i"), ("ay", "i"), ("ei", "i"), ("ey", "i"), ("aa", "a"), ("w", "v"), ("y", "i")]
_STRONG_RULES = _MILD_RULES + [("q", "k"), ("kh", "h"), ("gh", "g"), ("sh", "s"), ("ch", "c"), ("th", "t"), ("dh", "d"), ("zh", "j"), ("ts", "s"), ("x", "ks"), ("z", "s"), ("g", "k")]


def clean(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf")
    text = text.casefold().replace("ß", "ss").replace("æ", "ae").replace("ø", "o").replace("đ", "d").replace("ł", "l")
    text = re.sub(r"[^\w\s]|_", " ", text)
    tokens = [t for t in text.split() if t not in TITLES]
    return " ".join(tokens)


def fold(name: str, level: int = 2) -> str:
    """level 1 (mild): vowel and doubled-letter variation only. level 2 (strong): also merges consonant sounds (q/k/g, sh/s, z/s). Phonetic-ish key: same letters sounds map to one letter, vowels are reduced, doubled letters collapse. It is deliberately lossy; it is only used to compare."""
    text = _MUHAMMAD.sub("muhammad", clean(name))
    tokens = [t for t in text.split() if t not in PARTICLES] or text.split()
    out = []
    for tok in tokens:
        if level >= 2 and len(tok) >= 6 and tok.startswith(("al", "el")):          # "Alzomor" written as one word
            tok = tok[2:]
        for a, b in (_STRONG_RULES if level >= 2 else _MILD_RULES):
            tok = tok.replace(a, b)
        tok = re.sub(r"(.)\1+", r"\1", tok)                       # doubled letters
        tok = tok[:1] + re.sub(r"[aeiou]", "a", tok[1:])         # keep the first letter, reduce later vowels to one symbol
        tok = tok[:1] + re.sub(r"a+", "a", tok[1:])
        out.append(tok)
    return " ".join(out)
