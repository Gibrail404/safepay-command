"""TF-IDF (word 1-2 grams) + logistic regression for scam-like text, with a pure-numpy scorer so no pickle is ever loaded.
The scorer reproduces scikit-learn's TfidfVectorizer + LogisticRegression exactly (tested to 1e-9)."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path

TOKEN = re.compile(r"(?u)\b\w\w+\b")        # scikit-learn's default token pattern


def tokens_with_bigrams(text: str) -> list[str]:
    toks = TOKEN.findall(text.lower())
    return toks + [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)]


class TfidfLogRegScorer:
    def __init__(self, params: dict):
        self.vocab = params["vocab"]                          # term -> index
        self.idf = params["idf"]                              # index -> idf (stored as a dict keyed by the term for compactness)
        self.coef = params["coef"]                            # term -> weight
        self.intercept = float(params["intercept"])

    def _vector(self, text: str) -> dict[str, float]:
        counts: dict[str, float] = {}
        for t in tokens_with_bigrams(text):
            if t in self.vocab:
                counts[t] = counts.get(t, 0.0) + 1.0
        tfidf = {t: c * self.idf[t] for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in tfidf.values()))
        return {t: v / norm for t, v in tfidf.items()} if norm > 0 else {}

    def raw_one(self, text: str) -> float:
        return sum(self.coef[t] * v for t, v in self._vector(text).items()) + self.intercept

    def raw(self, texts) -> "object":
        import numpy as np
        return np.array([self.raw_one(t) for t in texts], dtype=float)

    def top_terms(self, text: str, k: int = 3) -> list[dict]:
        """The terms in THIS message that pushed the score up most. Only words from the message itself are returned."""
        contrib = [(t, self.coef[t] * v) for t, v in self._vector(text).items() if self.coef[t] * v > 0]
        return [{"term": t, "weight": round(w, 4)} for t, w in sorted(contrib, key=lambda x: -x[1])[:k]]

    @staticmethod
    def from_sklearn(vectorizer, lr) -> dict:
        inv = {i: t for t, i in vectorizer.vocabulary_.items()}
        terms = [inv[i] for i in range(len(inv))]
        return {"vocab": {t: i for i, t in enumerate(terms)}, "idf": {t: float(vectorizer.idf_[i]) for i, t in enumerate(terms)},
                "coef": {t: float(lr.coef_[0, i]) for i, t in enumerate(terms)}, "intercept": float(lr.intercept_[0])}

    @staticmethod
    def load(directory: Path) -> "TfidfLogRegScorer":
        return TfidfLogRegScorer(json.loads((directory / "tfidf_logreg.json").read_text()))
