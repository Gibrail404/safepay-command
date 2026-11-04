"""Sanctions-list name matcher: candidate generation with character n-gram TF-IDF, then token-aware fuzzy reranking.
No LLM is involved in matching. The score is a number between 0 and 100 that the policy engine can threshold."""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from .normalise import clean, fold


@dataclass(frozen=True)
class Hit:
    ent_num: str
    matched_name: str          # the primary name or alias that matched
    is_alias: bool
    score: float


def _tok_score(q: list[str], c: list[str], idf: dict[str, float], default_idf: float) -> float:
    """Each token is matched to its best partner on the other side; the match quality is averaged with weights that favour rare tokens.
    A shared very common token (Muhammad, John) therefore adds little, a missing or unmatched token costs its full weight."""
    if not q or not c:
        return 0.0
    wq = [idf.get(t, default_idf) for t in q]
    wc = [idf.get(t, default_idf) for t in c]
    num = sum(w * max(fuzz.ratio(a, b) for b in c) for a, w in zip(q, wq)) + sum(w * max(fuzz.ratio(b, a) for a in q) for b, w in zip(c, wc))
    return num / (sum(wq) + sum(wc))


def _joined_score(a: str, b: str) -> float:
    """Catches a name written with the spaces moved ("AL ZOMOR" and "ALZOMOR"). Only used when the token counts differ, and only for long strings."""
    ta, tb = a.split(), b.split()
    if len(ta) == len(tb):
        return 0.0
    ja, jb = "".join(sorted(ta)), "".join(sorted(tb))
    return fuzz.ratio(ja, jb) if min(len(ja), len(jb)) >= 8 else 0.0


def _idf(docs: list[list[str]]) -> tuple[dict[str, float], float]:
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    return {t: math.log((n + 1) / (v + 1)) + 1.0 for t, v in df.items()}, math.log(n + 1) + 1.0


class NameIndex:
    """names: list of (ent_num, name, is_alias). Every name, primary or alias, is one row; hits are reduced to the best row per list entry."""
    def __init__(self, names: list[tuple[str, str, bool]], fold_level: int = 2, use_candidates: bool = True):
        self.names, self.fold_level, self.use_candidates = names, fold_level, use_candidates
        self.use_fold = fold_level > 0
        self.clean = [clean(n) for _, n, _ in names]
        self.fold = [fold(n, fold_level) if fold_level else "" for _, n, _ in names]
        self.clean_tok = [c.split() for c in self.clean]
        self.fold_tok = [f.split() for f in self.fold]
        self.idf_clean = _idf(self.clean_tok)
        self.idf_fold = _idf(self.fold_tok)
        key = self.fold if self.use_fold else self.clean
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=1, sublinear_tf=True, dtype=np.float32)
        self.matrix = self.vec.fit_transform(key)

    def search(self, query: str, k: int = 50, top: int = 10) -> list[Hit]:
        qc, qf = clean(query), (fold(query, self.fold_level) if self.fold_level else "")
        if not qc:
            return []
        if self.use_candidates:
            sims = (self.matrix @ self.vec.transform([qf if self.use_fold else qc]).T).toarray().ravel()
            idx = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
        else:
            idx = range(len(self.names))
        best: dict[str, Hit] = {}
        best_lit: dict[str, float] = {}
        for i in idx:
            ent, name, alias = self.names[i]
            lit = s = _tok_score(qc.split(), self.clean_tok[i], *self.idf_clean)      # literal similarity, used to break ties so the analyst sees the spelling that matched
            if self.use_fold:
                s = max(s, _tok_score(qf.split(), self.fold_tok[i], *self.idf_fold))
            s = max(s, _joined_score(qc, self.clean[i]))
            if ent not in best or (round(s, 2), lit) > (best[ent].score, best_lit[ent]):
                best[ent], best_lit[ent] = Hit(ent, name, alias, round(float(s), 2)), lit
        return sorted(best.values(), key=lambda h: -h.score)[:top]
