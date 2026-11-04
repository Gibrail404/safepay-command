"""The run trace, the exact audit payload a browser can re-hash, the per-case ledger lookup and the policy frontier."""
import json
import pytest
from safepay import ledger
from safepay.agents.investigator import investigate_traced
from safepay.llm.gateway import LLMGateway
from safepay.llm.providers import FakeProvider
from test_cases import A, B, GOOD_93, case, import_one, item, make

ITEMS = [item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]
BAD = json.dumps({"recommendation": "review", "sentences": ["The case groups 9 alerts and the score is 0.99. [E1]"]})


def ids(trace):
    return [s["id"] for s in trace["steps"]]


def status(trace):
    return {s["id"]: s["status"] for s in trace["steps"]}


def test_a_successful_run_has_every_step_in_order_with_measured_times():
    _, res, _, _, trace = investigate_traced(LLMGateway([FakeProvider([GOOD_93])]), "r", ITEMS)
    assert ids(trace) == ["facts", "screen", "rule", "ai", "fact_check", "priority", "ledger"] and trace["path"] == "llm"
    assert status(trace)["ai"] == "ok" and status(trace)["fact_check"] == "ok" and not next(s for s in trace["steps"] if s["id"] == "fact_check")["detail"]["repaired"]
    starts = [s["start_ms"] for s in trace["steps"]]
    assert starts == sorted(starts) and trace["total_ms"] >= 0 and all(s["ms"] >= 0 for s in trace["steps"])


def test_a_repaired_reply_is_shown_as_checked_and_repaired_with_both_attempts():
    _, res, _, _, trace = investigate_traced(LLMGateway([FakeProvider([BAD, GOOD_93])]), "r", ITEMS)
    ai = next(s for s in trace["steps"] if s["id"] == "ai")["detail"]["attempts"]
    fc = next(s for s in trace["steps"] if s["id"] == "fact_check")
    assert [a["ok"] for a in ai] == [False, True] and ai[0]["kind"] == "check" and fc["status"] == "ok" and fc["detail"]["repaired"] and fc["detail"]["issues"]


def test_two_bad_replies_route_to_the_fallback_and_say_why():
    _, res, _, _, trace = investigate_traced(LLMGateway([FakeProvider([BAD, BAD])]), "r", ITEMS)
    assert res.path == "fallback" and trace["path"] == "fallback" and ids(trace)[-3:] == ["fallback", "priority", "ledger"]
    assert status(trace)["fact_check"] == "failed" and status(trace)["ai"] == "failed" and next(s for s in trace["steps"] if s["id"] == "fact_check")["detail"]["issues"]


def test_no_model_available_skips_the_fact_check_instead_of_pretending():
    _, res, _, _, trace = investigate_traced(LLMGateway([]), "r", ITEMS)
    assert trace["path"] == "fallback" and status(trace)["fact_check"] == "skipped" and status(trace)["ai"] == "failed"


def test_a_thin_case_stops_at_the_rule_and_skips_the_model_steps():
    p = FakeProvider([GOOD_93])
    _, res, _, _, trace = investigate_traced(LLMGateway([p]), "r", [item("t1", 0.5)])
    assert res is None and p.seen == [] and trace["path"] == "rule"
    assert status(trace) == {"facts": "ok", "screen": "skipped", "rule": "stopped", "ai": "skipped", "fact_check": "skipped", "priority": "ok", "ledger": "ok"}


def test_the_trace_is_stored_with_the_investigation_and_returned_by_the_case():
    c = make(FakeProvider([GOOD_93]))
    cid = import_one(c, case(items=[item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]))
    out = c.post(f"/v1/cases/{cid}/investigate", headers=A).json()
    assert ids(out["trace"])[0] == "facts" and c.get(f"/v1/cases/{cid}", headers=A).json()["investigation"]["trace"]["path"] == "llm"


def test_audit_entries_carry_the_exact_hashed_string_so_a_client_can_verify_the_chain():
    c = make()
    cid = import_one(c)
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    c.post(f"/v1/cases/{cid}/disposition", json={"decision": "escalated"}, headers={**A, "X-Actor": "ana"})
    entries = c.get("/v1/audit", headers=A).json()
    prev = ledger.GENESIS
    for e in entries:
        assert e["prev_hash"] == prev and ledger.entry_hash(e["prev_hash"], e["tenant"], e["kind"], e["ts"], e["payload_canonical"]) == e["hash"]
        assert json.loads(e["payload_canonical"]) == e["payload"]
        prev = e["hash"]
    assert len(entries) == 3


def test_case_ledger_lists_only_this_cases_entries_and_hides_other_tenants():
    c = make()
    c.post("/v1/cases/import", json={"cases": [case("x1"), case("x2")]}, headers=A)
    cid, other = [x["id"] for x in c.get("/v1/cases", headers=A).json()["cases"]]
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    kinds = [e["kind"] for e in c.get(f"/v1/cases/{cid}/ledger", headers=A).json()]
    assert kinds == ["case.investigated"] and c.get(f"/v1/cases/{other}/ledger", headers=A).json() == []
    assert c.get(f"/v1/cases/{cid}/ledger", headers=B).status_code == 404


def test_policy_frontier_is_labelled_simulated_and_stops_less_money_as_the_threshold_rises():
    c = make()
    r = c.get("/v1/simulations/frontier?n=20000&seed=1", headers=A).json()
    stopped = [x["scam_money_stopped_share"] for x in r["rows"]]
    assert r["provenance"] == "simulated" and stopped == sorted(stopped, reverse=True) and stopped[-1] == 0
    assert c.get("/v1/simulations/frontier?n=20000&seed=1", headers=A).json() == r
    assert c.get("/v1/simulations/frontier?n=5", headers=A).status_code == 422 and c.get("/v1/simulations/frontier").status_code == 401


def test_verify_exposes_the_saved_head_fingerprint_which_equals_the_last_entry_hash():
    c = make()
    import_one(c)
    v = c.get("/v1/audit/verify", headers=A).json()
    assert v["ok"] and v["head_hash"] == c.get("/v1/audit", headers=A).json()[-1]["hash"]


def test_the_ai_step_records_the_tokens_the_provider_reported():
    _, res, _, _, trace = investigate_traced(LLMGateway([FakeProvider([GOOD_93])]), "r", ITEMS)          # the fake provider reports 10 tokens in and 10 out
    assert next(s for s in trace["steps"] if s["id"] == "ai")["detail"]["tokens"] == {"in": 10, "out": 10}
