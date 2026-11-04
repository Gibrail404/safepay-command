"""The overview is computed only from stored data: counts must match what was done, other tenants must not leak in, and an empty tenant must give zeros, not made-up numbers."""
import json
from test_cases import A, B, GOOD_93, case, import_one, item, make
from test_interception import A as AI_A, SCENARIOS, make as make_icp, start
from safepay.llm.providers import FakeProvider


def test_an_empty_tenant_gets_zeros_and_no_invented_rate():
    o = make().get("/v1/overview", headers=A).json()
    assert o["cases"]["open"] == 0 and o["ledger"]["length"] == 0 and o["decisions"]["total"] == 0 and o["ai_guardrails"]["first_pass_rate"] is None
    assert len(o["activity_by_hour"]) == 24 and sum(h["total"] for h in o["activity_by_hour"]) == 0 and o["recent_open_cases"] == []


def test_counts_match_what_was_actually_done():
    c = make(FakeProvider([GOOD_93]))
    cid = import_one(c, case(items=[item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]))
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    c.post(f"/v1/cases/{cid}/disposition", json={"decision": "escalated"}, headers={**A, "X-Actor": "ana"})
    o = c.get("/v1/overview", headers=A).json()
    assert o["cases"]["dispositioned"] == 1 and o["ledger"]["by_kind"] == {"case.imported": 1, "case.investigated": 1, "case.dispositioned": 1}
    assert o["ai_guardrails"]["reached_the_ai"] == 1 and o["ai_guardrails"]["passed_first_time"] == 1 and o["ai_guardrails"]["first_pass_rate"] == 1.0
    assert sum(h["total"] for h in o["activity_by_hour"]) == 3


def test_a_repaired_ai_answer_does_not_count_as_passing_first_time():
    bad = json.dumps({"recommendation": "review", "sentences": ["The case groups 9 alerts and the score is 0.99. [E1]"]})
    c = make(FakeProvider([bad, GOOD_93]))
    cid = import_one(c, case(items=[item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]))
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    g = c.get("/v1/overview", headers=A).json()["ai_guardrails"]
    assert g["by_path"] == {"llm": 1} and g["reached_the_ai"] == 1 and g["passed_first_time"] == 0 and g["first_pass_rate"] == 0.0


def test_other_tenants_data_never_appears():
    c = make()
    import_one(c)
    assert c.get("/v1/overview", headers=B).json()["cases"]["open"] == 0 and c.get("/v1/overview", headers=A).json()["cases"]["open"] == 1


def test_decisions_and_interceptions_are_counted_with_their_reasons():
    c = make_icp()
    start(c, "scam_uncoached", mode="auto")
    start(c, "ordinary", mode="auto")
    o = c.get("/v1/overview", headers=AI_A).json()
    assert o["decisions"]["total"] == 2 and o["decisions"]["by_outcome"] == {"hold": 1, "allow": 1} and o["decisions"]["top_reasons"][0]["count"] >= 1
    assert o["interceptions"] == {"total": 2, "decided": 2, "held": 1, "questioned": 1}


def test_the_overview_needs_a_key():
    assert make().get("/v1/overview").status_code == 401
