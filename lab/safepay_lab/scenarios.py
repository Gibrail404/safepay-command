"""Reproducible customer scenarios for the interception flow. Payment features are REAL transactions from the held-out period of the ULB data, scored by the real model;
the payee's age and everything the customer says are SIMULATED and labelled so. Scams are built on ordinary-looking real payments on purpose: in an authorised-push scam the
customer sends the money themselves, so the payment itself looks normal and only the customer's story reveals the problem."""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
import numpy as np
from .sandbox import COVER_STORY, SITUATION, Persona

KINDS = ("ordinary", "large_new_payee", "vague_customer", "scam_uncoached", "scam_coached")
IS_SCAM = {"scam_uncoached": True, "scam_coached": True}
LABEL = {"ordinary": "Ordinary payment to a known payee", "large_new_payee": "Large payment to a new payee (genuine)", "vague_customer": "Genuine customer who gives short answers",
         "scam_uncoached": "Scam victim who answers honestly", "scam_coached": "Scam victim following the scammer's cover story"}
LEGIT_SITUATION = ["You are paying a builder you hired last week for a bathroom renovation. You have the written quote and have met him several times.",
                   "You are paying a car dealer for a second-hand car you inspected in person yesterday. You have the sales agreement.",
                   "You are paying a school for next term's fees, from the invoice the school emailed you after you called their office."]
ORDINARY_SITUATION = ["You are paying your landlord the monthly rent, as you have for two years.", "You are paying a supplier you have used for years, against an invoice you checked."]
VAGUE_SITUATION = "You are paying a friend's small business. You are busy, so you answer in very few words and give no details."
AMOUNT_BAND = {"ordinary": (20, 400), "large_new_payee": (400, 3000), "vague_customer": (400, 3000), "scam_uncoached": (400, 3000), "scam_coached": (400, 3000)}
SCRIPTED = {   # offline customer answers, used when no AI model is available and in browser tests; the same three questions are answered in order
    "scam_uncoached": ["A man from my bank called and told me to move my savings to a safe account today.", "No, I have never met him, he only phoned me.", "Yes, he said it is urgent and I must not tell anyone."],
    "scam_coached": ["It is a payment to a contractor I already know.", "Yes, he does work for me from time to time.", "No, nobody is pressuring me."],
    "large_new_payee": ["I am paying my builder for the bathroom work, I have the written quote.", "Yes, I have met him several times.", "No, there is no rush at all."],
    "vague_customer": ["Paying a friend.", "Yes.", "No."],
    "ordinary": ["Monthly rent for my flat.", "Yes, I have paid him for two years.", "No."],
}


@dataclass(frozen=True)
class Scenario:
    kind: str
    seed: int
    row_ref: str
    amount: float
    payee_age_days: int
    features: dict = field(repr=False)                 # V1 to V28 of the real transaction
    persona: Persona = field(repr=False, default=None)
    is_scam: bool = False


@lru_cache(maxsize=1)
def _pool():
    """Real held-out non-fraud transactions, loaded once per process. The full held-out period of the ULB data is used whenever it is available (so evaluations never change silently);
    only when it is not (the deployed container) the 3,000-row sample data/processed/scenario_pool.parquet from scripts/build_scenario_pool.py is used. For the same seed, scenarios
    therefore differ between the two sources."""
    import pandas as pd
    from pathlib import Path
    processed = Path(__file__).resolve().parents[2] / "data" / "processed"
    if (processed / "ulb_creditcard.parquet").exists():
        from safepay_ml.data import load_ulb, temporal_split
        frame = temporal_split(load_ulb())["test"].frame
        return frame[frame["Class"] == 0].reset_index(drop=False)
    if (processed / "scenario_pool.parquet").exists():
        return pd.read_parquet(processed / "scenario_pool.parquet")
    raise RuntimeError("no scenario data: download the ULB data or provide scenario_pool.parquet")


def build(kind: str, seed: int) -> Scenario:
    if kind not in KINDS:
        raise ValueError(f"unknown scenario kind {kind!r}")
    rng = np.random.default_rng([seed, KINDS.index(kind)])
    pool = _pool()
    lo, hi = AMOUNT_BAND[kind]
    rows = pool[(pool["Amount"] >= lo) & (pool["Amount"] < hi)]
    r = rows.iloc[int(rng.integers(len(rows)))]
    age = {"ordinary": int(rng.integers(60, 1500)), "large_new_payee": int(rng.integers(0, 2)), "vague_customer": int(rng.integers(0, 7)),
           "scam_uncoached": int(rng.integers(0, 3)), "scam_coached": int(rng.integers(0, 3))}[kind]
    scam_kind = list(SITUATION)[int(rng.integers(len(SITUATION)))]
    persona = {"ordinary": Persona("benign", ORDINARY_SITUATION[int(rng.integers(2))], label="ordinary"),
               "large_new_payee": Persona("benign", LEGIT_SITUATION[int(rng.integers(3))], label="large_new_payee"),
               "vague_customer": Persona("benign", VAGUE_SITUATION, label="vague_customer"),
               "scam_uncoached": Persona("uncoached_victim", SITUATION[scam_kind], label=scam_kind),
               "scam_coached": Persona("coached_victim", SITUATION[scam_kind], COVER_STORY[scam_kind], label=scam_kind)}[kind]
    return Scenario(kind, seed, f"ulb-test-{int(r['index'])}", float(r["Amount"]), age, {f"V{i}": float(r[f"V{i}"]) for i in range(1, 29)}, persona, IS_SCAM.get(kind, False))


def scripted_answer(kind: str, turn: int) -> str:
    return SCRIPTED[kind][min(turn, 2)]
