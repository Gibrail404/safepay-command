"""What the interception demo needs from outside the kernel: a scenario source, a risk scorer and a simulated customer. Kept separate so tests can supply fakes and so the kernel
still starts when the simulation and model packages are not installed."""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Callable
from .llm.gateway import LLMGateway


@dataclass
class InterceptionDeps:
    scenario: Callable[[str, int], Any]                                   # (kind, seed) -> object with amount, payee_age_days, features, row_ref, kind, is_scam
    risk: Callable[[Any], dict]                                           # scenario -> {risk_score, risk_band, model_version, model_type, ms}
    victim: Callable[[LLMGateway, str, Any, str, int], str]               # (gateway, run id, scenario, question, turn) -> the customer's answer


def scenario_catalog() -> list[dict]:
    try:
        from safepay_lab.scenarios import KINDS, LABEL, IS_SCAM
    except ImportError:
        return []
    return [{"kind": k, "label": LABEL[k], "simulated_customer": True} for k in KINDS]      # whether a scenario is a scam stays hidden until the decision


def default_deps(llm: LLMGateway) -> InterceptionDeps:
    """Real model and real held-out ULB transactions for the payment, the sandbox customer (an AI model, or fixed scripted lines when no model is configured) for the answers."""
    from safepay_lab import sandbox
    from safepay_lab.scenarios import build, scripted_answer
    from . import risk_tool

    def risk(sc) -> dict:
        t = time.perf_counter()
        try:
            out = risk_tool.score_payment_risk(risk_tool.PaymentFeatures(amount=sc.amount, **sc.features))
        except Exception as e:                                           # no trained model on this machine
            raise RuntimeError(f"the risk model is not available on this server ({type(e).__name__})")
        return {**out, "ms": round((time.perf_counter() - t) * 1000)}

    def victim(gw: LLMGateway, run_id: str, sc, question: str, turn: int) -> str:
        if not gw.chain:
            return scripted_answer(sc.kind, turn)
        return sandbox.answer(gw, run_id, sc.persona, question, turn)

    return InterceptionDeps(build, risk, victim)
