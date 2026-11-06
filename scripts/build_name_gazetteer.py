"""Builds the name gazetteer: a list of lower-case NAME TOKENS (not full names, no records) from real public lists: US Census first names and surnames, and the OFAC list's individuals
and aliases. Tokens that are also ordinary English words are removed, using the real SMS corpus (a token is 'ordinary' if it appears in lower case at least 2 times and more often
than capitalised), so that "will", "mark" or "rose" are not redacted as names. Writes config/name_gazetteer.txt. The evaluation uses a held-out half (--holdout) so that
performance on names the list has NOT seen can be measured honestly. Usage: python scripts/build_name_gazetteer.py [--holdout PATH]"""
import argparse, re, sys, zlib
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "screening"))
import pandas as pd
from safepay_screening.data import PROCESSED, load_aliases, load_sdn

TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")


def parity(token: str) -> int:
    return zlib.crc32(token.encode()) & 1                           # stable split of tokens into two halves, used only for the honest evaluation


def collect() -> Counter:
    c: Counter = Counter()
    for g in ("male", "female"):
        for n in pd.read_parquet(PROCESSED / f"census_first_{g}.parquet")["name"]:
            c[n.lower()] += 3
    sur = pd.read_parquet(PROCESSED / "census_surnames.parquet")
    for n, k in zip(sur["name"], sur["count"]):
        if k >= 200:                                                 # frequent surnames only: keeps the list small and the false positives low
            c[n.lower()] += 3
    sdn, alias = load_sdn(), load_aliases()
    people = set(sdn.loc[sdn["sdn_type"] == "individual", "ent_num"])                # entities (companies, ships) are left out: their words are not names
    names = list(sdn.loc[sdn["sdn_type"] == "individual", "name"]) + list(alias.loc[alias["ent_num"].isin(people), "alt_name"])
    for raw in names:
        for t in TOKEN.findall(raw):
            if t.lower() not in ("and", "the", "bin", "abu", "ibn", "bint", "van", "von", "del", "den", "der", "dos", "los"):
                c[t.lower()] += 1
    return c


def ordinary_words() -> set[str]:
    low, cap = Counter(), Counter()
    for text in pd.read_parquet(PROCESSED / "sms_spam.parquet")["text"]:
        for t in TOKEN.findall(text):
            (cap if t[0].isupper() else low)[t.lower()] += 1
    return {t for t, n in low.items() if n >= 2 and n > cap[t]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", help="write a gazetteer containing only tokens of parity 0 to this path (for the evaluation)")
    a = ap.parse_args()
    tokens = collect()
    common = ordinary_words()
    keep = sorted(t for t in tokens if t not in common and len(t) >= 3)
    out = ROOT / "config" / "name_gazetteer.txt"
    out.write_text("\n".join(keep) + "\n")
    print(f"{len(tokens)} name tokens, {len(tokens) - len(keep)} removed as ordinary words or too short, {len(keep)} kept -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    if a.holdout:
        Path(a.holdout).write_text("\n".join(t for t in keep if parity(t) == 0) + "\n")
        print("held-out gazetteer (parity 0 only):", sum(parity(t) == 0 for t in keep), "tokens ->", a.holdout)
