"""Cases, investigation, dispositions and labels: tenant isolation, hidden truth, audit, abstain and friction-only behaviour."""
import json
import pytest
from fastapi.testclient import TestClient
from conftest import TEST_DB_URL, fresh_engine
from safepay.agents.faithfulness import check_sentences
from safepay.agents.investigator import abstain_summary, build_case_evidence, evidence_is_thin, fallback_summary, priority_for
from safepay.api import create_app
from safepay.config import Settings
from safepay.llm.gateway import LLMGateway
from safepay.llm.providers import FakeProvider

A, B = {"X-API-Key": "key-a"}, {"X-API-Key": "key-b"}


def item(ref, score, **facts):
    return {"ref": ref, "score": score, "time_step": 40, "facts": {"neighbours": 3, "linked_alerts": 0, **facts}}


def case(ext="x1", items=None, **kw):
    return {"external_id": ext, "source": "test", "provenance": "real", "title": f"Case {ext}", "items": items or [item("t1", 0.97), item("t2", 0.93, linked_alerts=1)], "facts": {}, "truth": {"t1": 1, "t2": 1}, **kw}


GOOD = json.dumps({"recommendation": "escalate", "sentences": ["The case groups 2 alerts from time step 40. [E1]", "The highest model score is 0.97 and the average is 0.95, on a scale from 0 to 1. [E2]"]})


GOOD_93 = json.dumps({"recommendation": "escalate", "sentences": ["The case groups 2 alerts from time step 40. [E1]", "The highest model score is 0.93 and the average is 0.92, on a scale from 0 to 1. [E2]"]})


def make(provider=None):
    fresh_engine().dispose()
    llm = LLMGateway([provider or FakeProvider([GOOD] * 20)])
    return TestClient(create_app(Settings(database_url=TEST_DB_URL, tenants={"key-a": "tenant_a", "key-b": "tenant_b"}), llm=llm))


def import_one(c, body=None, headers=A):
    r = c.post("/v1/cases/import", json={"cases": [body or case()]}, headers=headers)
    assert r.status_code == 200
    return c.get("/v1/cases", headers=headers).json()["cases"][0]["id"]


def test_import_is_idempotent_by_external_id():
    c = make()
    c.post("/v1/cases/import", json={"cases": [case()]}, headers=A)
    r = c.post("/v1/cases/import", json={"cases": [case(), case("x2")]}, headers=A).json()
    assert r == {"imported": 1, "skipped_existing": 1} and c.get("/v1/cases", headers=A).json()["total"] == 2


def test_cases_are_invisible_to_other_tenants_in_every_endpoint():
    c = make()
    cid = import_one(c)
    assert c.get("/v1/cases", headers=B).json() == {"total": 0, "cases": []}
    for method, url, body in (("get", f"/v1/cases/{cid}", None), ("post", f"/v1/cases/{cid}/investigate", None), ("post", f"/v1/cases/{cid}/disposition", {"decision": "dismissed_licit"})):
        r = getattr(c, method)(url, headers={**B, "X-Actor": "mallory"}, **({"json": body} if body else {}))
        assert r.status_code == 404
    assert c.get("/v1/labels", headers=B).json() == [] and c.get(f"/v1/cases/{cid}", headers=A).json()["status"] == "open"


def test_truth_is_hidden_until_a_disposition_exists_and_never_in_the_list():
    c = make()
    cid = import_one(c)
    assert "revealed_truth" not in c.get(f"/v1/cases/{cid}", headers=A).json() and "truth" not in json.dumps(c.get("/v1/cases", headers=A).json())
    c.post(f"/v1/cases/{cid}/disposition", json={"decision": "confirmed_illicit"}, headers={**A, "X-Actor": "ana"})
    assert c.get(f"/v1/cases/{cid}", headers=A).json()["revealed_truth"] == {"t1": 1, "t2": 1}


def test_disposition_needs_an_actor_is_final_and_writes_labels_with_provenance():
    c = make()
    cid = import_one(c)
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit"}, headers=A).status_code == 400
    ok = c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit", "note": "looks like an exchange"}, headers={**A, "X-Actor": "ana"})
    assert ok.status_code == 200 and ok.json()["labels_written"] == 2
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "confirmed_illicit"}, headers={**A, "X-Actor": "bob"}).status_code == 409
    labels = c.get("/v1/labels", headers=A).json()
    assert [(x["subject_ref"], x["label"], x["actor"], x["source"]) for x in labels] == [("t1", 0, "ana", "analyst"), ("t2", 0, "ana", "analyst")]


def test_escalation_writes_no_labels_and_simulated_analysts_are_marked():
    c = make()
    cid1 = import_one(c)
    c.post("/v1/cases/import", json={"cases": [case("x2")]}, headers=A)
    cid2 = [x["id"] for x in c.get("/v1/cases", headers=A).json()["cases"] if x["id"] != cid1][0]
    assert c.post(f"/v1/cases/{cid1}/disposition", json={"decision": "escalated"}, headers={**A, "X-Actor": "ana"}).json()["labels_written"] == 0
    c.post(f"/v1/cases/{cid2}/disposition", json={"decision": "confirmed_illicit", "simulated": True}, headers={**A, "X-Actor": "sim-analyst"})
    assert {x["source"] for x in c.get("/v1/labels", headers=A).json()} == {"simulated_analyst"}


def test_every_change_is_in_the_ledger_and_the_chain_still_verifies():
    c = make()
    cid = import_one(c)
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    c.post(f"/v1/cases/{cid}/disposition", json={"decision": "confirmed_illicit"}, headers={**A, "X-Actor": "ana"})
    kinds = [e["kind"] for e in c.get("/v1/audit", headers=A).json()]
    assert kinds == ["case.imported", "case.investigated", "case.dispositioned"] and c.get("/v1/audit/verify", headers=A).json()["ok"]


def test_oversized_or_empty_cases_are_rejected():
    c = make()
    assert c.post("/v1/cases/import", json={"cases": [case(items=[item(f"t{i}", 0.9) for i in range(201)])]}, headers=A).status_code == 422
    assert c.post("/v1/cases/import", json={"cases": [{**case(), "facts": {"x": "a" * 70_000}}]}, headers=A).status_code == 422
    assert c.post("/v1/cases/import", json={"cases": [{**case(), "items": []}]}, headers=A).status_code == 422


def test_investigation_uses_the_model_when_it_passes_the_checker_and_can_raise_priority():
    c = make(FakeProvider([GOOD_93]))
    cid = import_one(c, case(items=[item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]))
    out = c.post(f"/v1/cases/{cid}/investigate", headers=A).json()
    assert out["path"] == "llm" and out["recommendation"] == "escalate" and out["priority"] == "high"
    assert c.get(f"/v1/cases/{cid}", headers=A).json()["priority"] == "high"


def test_a_lone_weak_alert_abstains_without_calling_any_model():
    p = FakeProvider([GOOD])
    c = make(p)
    cid = import_one(c, case(items=[item("t1", 0.6)]))
    out = c.post(f"/v1/cases/{cid}/investigate", headers=A).json()
    assert out["recommendation"] == "abstain" and out["path"] == "rule" and p.seen == []


def test_unsupported_claims_fall_back_to_a_safe_summary_and_never_lower_priority():
    bad = json.dumps({"recommendation": "review", "sentences": ["The case groups 9 alerts and the score is 0.99. [E1]"]})
    c = make(FakeProvider([bad, bad]))
    cid = import_one(c, case(priority="high"))
    out = c.post(f"/v1/cases/{cid}/investigate", headers=A).json()
    assert out["path"] == "fallback" and c.get(f"/v1/cases/{cid}", headers=A).json()["priority"] == "high"


def test_no_model_configured_still_gives_a_summary():
    fresh_engine().dispose()
    c = TestClient(create_app(Settings(database_url=TEST_DB_URL, tenants={"key-a": "tenant_a"}), llm=LLMGateway([])))
    cid = import_one(c)
    assert c.post(f"/v1/cases/{cid}/investigate", headers=A).json()["path"] == "fallback"


def test_fallback_and_abstain_summaries_pass_the_faithfulness_checker():
    items = [item("t1", 0.97), item("t2", 0.93, linked_alerts=1)]
    ev = build_case_evidence(items)
    assert check_sentences(fallback_summary(ev).sentences, ev, "hold") == []
    thin = build_case_evidence([item("t1", 0.5)])
    assert evidence_is_thin([item("t1", 0.5)]) and check_sentences(abstain_summary(thin).sentences, thin, "hold") == []


def test_priority_rule():
    assert priority_for("escalate", [item("t", 0.5)]) == "high" and priority_for("review", [item("t", 0.96)]) == "high" and priority_for("review", [item("t", 0.5)]) == "normal"


# ---------------- overriding the AI with a recorded reason ----------------
def investigated_case(c, recommendation_json):
    cid = import_one(c, case(items=[item("t1", 0.93), item("t2", 0.91, linked_alerts=1)]))
    c.post(f"/v1/cases/{cid}/investigate", headers=A)
    return cid


def test_dismissing_a_case_the_ai_recommended_escalating_needs_a_written_reason():
    c = make(FakeProvider([GOOD_93]))
    cid = investigated_case(c, GOOD_93)
    assert c.get(f"/v1/cases/{cid}", headers=A).json()["investigation"]["recommendation"] == "escalate"
    h = {**A, "X-Actor": "ana"}
    for reason in ("", "no", "too short"):
        r = c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit", "override_reason": reason}, headers=h)
        assert r.status_code == 422 and "reason" in r.json()["detail"]
    assert c.get(f"/v1/cases/{cid}", headers=A).json()["status"] == "open"                    # a refused override changed nothing
    ok = c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit", "override_reason": "Known exchange hot wallet, confirmed with the compliance desk."}, headers=h)
    assert ok.status_code == 200
    d = c.get(f"/v1/cases/{cid}", headers=A).json()["disposition"]
    assert d["overrode_ai"] is True and d["ai_recommendation"] == "escalate" and "exchange" in d["override_reason"]


def test_the_override_is_in_the_ledger_with_a_fingerprint_of_the_reason_and_the_chain_verifies():
    c = make(FakeProvider([GOOD_93]))
    cid = investigated_case(c, GOOD_93)
    reason = "Known exchange hot wallet, confirmed with the compliance desk."
    c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit", "override_reason": reason}, headers={**A, "X-Actor": "ana"})
    last = c.get("/v1/audit", headers=A).json()[-1]
    from safepay import ledger
    assert last["kind"] == "case.dispositioned" and last["payload"]["overrode_ai"] is True and last["payload"]["override_reason_sha256"] == ledger.sha256_hex(reason)
    assert c.get("/v1/audit/verify", headers=A).json()["ok"]


def test_agreeing_with_or_escalating_the_ai_needs_no_reason_and_other_recommendations_never_do():
    c = make(FakeProvider([GOOD_93]))
    cid = investigated_case(c, GOOD_93)
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "confirmed_illicit"}, headers={**A, "X-Actor": "ana"}).status_code == 200
    d = c.get(f"/v1/cases/{cid}", headers=A).json()["disposition"]
    assert d["overrode_ai"] is False and d["override_reason"] is None
    c2 = make()                                                                                  # no model: the safe fallback says "review", which a person may dismiss freely
    cid2 = investigated_case(c2, None)
    assert c2.get(f"/v1/cases/{cid2}", headers=A).json()["investigation"]["recommendation"] == "review"
    assert c2.post(f"/v1/cases/{cid2}/disposition", json={"decision": "dismissed_licit"}, headers={**A, "X-Actor": "ana"}).status_code == 200


def test_a_case_nobody_investigated_can_be_dismissed_without_a_reason():
    c = make()
    cid = import_one(c)
    r = c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit"}, headers={**A, "X-Actor": "ana"})
    assert r.status_code == 200 and c.get(f"/v1/cases/{cid}", headers=A).json()["disposition"]["ai_recommendation"] is None


@pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"), reason="needs PostgreSQL")
def test_a_database_created_before_the_override_columns_gets_them_added_in_place():
    from sqlalchemy import inspect, text
    from safepay.db import Base, init_db, make_engine
    engine = make_engine(TEST_DB_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:                      # the old shape of the table, without the three new columns
        conn.execute(text("CREATE TABLE dispositions (id VARCHAR(40) PRIMARY KEY, tenant VARCHAR(64), case_id VARCHAR(40) UNIQUE, actor VARCHAR(64), decision VARCHAR(24), note VARCHAR(500), ts VARCHAR(40))"))
    init_db(engine)
    init_db(engine)                                   # repeating it must be harmless
    cols = {c["name"] for c in inspect(engine).get_columns("dispositions")}
    assert {"ai_recommendation", "overrode_ai", "override_reason"} <= cols
    Base.metadata.drop_all(engine)
    engine.dispose()
