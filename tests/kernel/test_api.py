"""End-to-end API tests against the real app, real policy file and real ledger (SQLite in memory)."""
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import text
from conftest import TEST_DB_URL, fresh_engine
from safepay.api import create_app
from safepay.config import Settings
from safepay.tools import Tool, ToolRegistry


class Args(BaseModel):
    payment_id: str


HANDLED = []


def build_client():
    HANDLED.clear()
    reg = ToolRegistry()
    reg.register(Tool(name="hold_payment", tier="T2", input_model=Args, handler=lambda a: (HANDLED.append(a.payment_id), {"held": a.payment_id})[1]))
    reg.register(Tool(name="release_payment", tier="T3", input_model=Args, handler=lambda a: (HANDLED.append(a.payment_id), {"released": a.payment_id})[1]))
    fresh_engine().dispose()
    app = create_app(Settings(database_url=TEST_DB_URL, tenants={"key-a": "tenant_a", "key-b": "tenant_b"}), reg)
    return TestClient(app), app


@pytest.fixture()
def client():
    c, _ = build_client()
    return c


A, B = {"X-API-Key": "key-a"}, {"X-API-Key": "key-b"}
REQ = {"workload": "payment_risk", "subject": {"type": "payment", "id": "p1"}, "context": {"amount": 4800, "payee_age_days": 0, "risk_score": 0.4}}


def test_health_needs_no_key_but_everything_else_does(client):
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/v1/policies").status_code == 401
    assert client.get("/v1/policies", headers={"X-API-Key": "nope"}).status_code == 401


def test_decision_uses_the_real_policy_file(client):
    r = client.post("/v1/decisions", json=REQ, headers={**A, "Idempotency-Key": "k1"})
    assert r.status_code == 200
    d = r.json()
    assert d["outcome"] == "hold" and d["risk_tier"] == "T2" and d["requires_approval"] is True
    assert [x["code"] for x in d["reasons"]] == ["LARGE_AMOUNT", "NEW_PAYEE_LARGE_AMOUNT"]


def test_idempotency_over_http(client):
    h = {**A, "Idempotency-Key": "k1"}
    a, b = client.post("/v1/decisions", json=REQ, headers=h).json(), client.post("/v1/decisions", json=REQ, headers=h).json()
    assert a == b
    changed = {**REQ, "context": {"amount": 1}}
    assert client.post("/v1/decisions", json=changed, headers=h).status_code == 409
    assert client.post("/v1/decisions", json=REQ, headers=A).status_code == 400            # key is required
    assert len(client.get("/v1/audit", headers=A).json()) == 1


def test_replay_endpoint(client):
    d = client.post("/v1/decisions", json=REQ, headers={**A, "Idempotency-Key": "k1"}).json()
    r = client.get(f"/v1/decisions/{d['decision_id']}/replay", headers=A).json()
    assert r["same"] is True


def test_invariant_8_tenants_cannot_see_each_other(client):
    d = client.post("/v1/decisions", json=REQ, headers={**A, "Idempotency-Key": "k1"}).json()
    assert client.get(f"/v1/decisions/{d['decision_id']}", headers=B).status_code == 404
    assert client.get(f"/v1/decisions/{d['decision_id']}/replay", headers=B).status_code == 404
    assert client.get("/v1/audit", headers=B).json() == []
    assert client.get("/v1/audit/verify", headers=B).json()["checked"] == 0
    # the same idempotency key under another tenant is a different decision, not a replay
    d2 = client.post("/v1/decisions", json=REQ, headers={**B, "Idempotency-Key": "k1"}).json()
    assert d2["decision_id"] != d["decision_id"]


def test_events_are_idempotent_and_ledgered(client):
    h = {**A, "Idempotency-Key": "e1"}
    a, b = client.post("/v1/events", json={"type": "payment.created", "data": {"id": "p1"}}, headers=h).json(), client.post("/v1/events", json={"type": "payment.created", "data": {"id": "p1"}}, headers=h).json()
    assert a["event_id"] == b["event_id"] and (a["replayed"], b["replayed"]) == (False, True)
    assert client.post("/v1/events", json={"type": "payment.created", "data": {"id": "other"}}, headers=h).status_code == 409


def test_audit_verify_detects_tampering_through_the_api():
    c, app = build_client()
    for i in range(3):
        c.post("/v1/decisions", json=REQ, headers={**A, "Idempotency-Key": f"k{i}"})
    assert c.get("/v1/audit/verify", headers=A).json()["ok"] is True
    sf = app.state.sf
    with sf.begin() as s:
        s.execute(text("UPDATE ledger_entries SET payload = replace(payload, 'hold', 'allow') WHERE seq = 2"))
    r = c.get("/v1/audit/verify", headers=A).json()
    assert r["ok"] is False and r["bad_seq"] == 2


def test_tool_flow_over_http_enforces_approval_and_one_use(client):
    run = client.post("/v1/runs", json={"tools": ["hold_payment", "release_payment"]}, headers=A).json()
    cap = {**A, "X-Capability": run["capability"]}
    call = lambda tool, key, **extra: client.post("/v1/tools/call", json={"tool": tool, "args": {"payment_id": "p1"}, **extra}, headers={**cap, "Idempotency-Key": key}).json()
    first = call("release_payment", "c1")
    assert first["status"] == "approval_required" and HANDLED == []
    assert client.post(f"/v1/approvals/{first['approval_id']}/decision", json={"approve": True}, headers=A).status_code == 400   # needs X-Actor
    assert client.post(f"/v1/approvals/{first['approval_id']}/decision", json={"approve": True}, headers={**A, "X-Actor": "analyst_1"}).json()["status"] == "approved"
    assert call("release_payment", "c2")["status"] == "executed" and HANDLED == ["p1"]
    assert call("release_payment", "c3")["status"] == "approval_required"
    assert client.get("/v1/approvals", headers=B).json() == []


def test_a_caller_cannot_forge_a_policy_pre_approval(client):
    run = client.post("/v1/runs", json={"tools": ["hold_payment"]}, headers=A).json()
    h = {**A, "X-Capability": run["capability"], "Idempotency-Key": "c1"}
    r = client.post("/v1/tools/call", json={"tool": "hold_payment", "args": {"payment_id": "p1"}, "decision_id": "d_doesnotexist"}, headers=h)
    assert r.status_code == 404 and HANDLED == []
    d = client.post("/v1/decisions", json=REQ, headers={**A, "Idempotency-Key": "kd"}).json()      # a hold that requires approval, so not pre-approved
    r = client.post("/v1/tools/call", json={"tool": "hold_payment", "args": {"payment_id": "p1"}, "decision_id": d["decision_id"]}, headers=h).json()
    assert r["status"] == "approval_required" and HANDLED == []


def test_run_with_unknown_tool_is_rejected(client):
    assert client.post("/v1/runs", json={"tools": ["nope"]}, headers=A).status_code == 422


def test_policy_simulation_writes_nothing(client):
    pol = {"name": "candidate", "rules": [{"id": "x", "code": "BIG", "when": {"field": "amount", "op": ">", "value": 100}, "outcome": "block"}]}
    r = client.post("/v1/policies/simulate", json={"policy": pol, "contexts": [{"amount": 50}, {"amount": 500}]}, headers=A).json()
    assert [x["outcome"] for x in r["results"]] == ["allow", "block"]
    assert client.get("/v1/audit", headers=A).json() == []


def test_shadow_mode_over_http(client):
    run = client.post("/v1/runs", json={"tools": ["hold_payment"]}, headers=A).json()
    h = {**A, "X-Capability": run["capability"]}
    first = client.post("/v1/tools/call", json={"tool": "hold_payment", "args": {"payment_id": "p9"}, "mode": "shadow"}, headers={**h, "Idempotency-Key": "s1"}).json()
    assert first["status"] == "approval_required"                    # shadow still respects the approval requirement
    assert HANDLED == []


def test_unknown_workload_is_a_clean_422(client):
    r = client.post("/v1/decisions", json={**REQ, "workload": "nope"}, headers={**A, "Idempotency-Key": "z"})
    assert r.status_code == 422


def test_simulation_endpoint_returns_labelled_simulated_truth_and_is_deterministic(client):
    body = {"warn_from": 0.8, "hold_from": 1.6, "n": 20000, "seed": 3}
    r1, r2 = client.post("/v1/simulations", json=body, headers=A), client.post("/v1/simulations", json=body, headers=A)
    assert r1.status_code == 200 and r1.json() == r2.json()
    out = r1.json()
    assert out["provenance"] == "simulated" and 0 <= out["result"]["scam_money_stopped_share"] <= 1 and out["assumptions"]["scam_rate"] == 0.02


def test_simulation_endpoint_rejects_bad_input_and_needs_a_key(client):
    assert client.post("/v1/simulations", json={"warn_from": 2, "hold_from": 1}, headers=A).status_code == 422
    assert client.post("/v1/simulations", json={"warn_from": 0, "hold_from": 1, "n": 10**9}, headers=A).status_code == 422
    assert client.post("/v1/simulations", json={"warn_from": 0, "hold_from": 1}).status_code == 401
    assert client.post("/v1/simulations", json={"warn_from": 0, "hold_from": 1, "n": 5000}, headers=B).status_code == 200


def test_reports_are_listed_with_provenance_and_unknown_names_are_refused(client):
    names = {r["name"]: r for r in client.get("/v1/reports", headers=A).json()}
    assert names["decision_lab"]["provenance"] == "simulated" and names["screening"]["provenance"] == "real"
    assert client.get("/v1/reports/../../README", headers=A).status_code == 404 and client.get("/v1/reports/nope", headers=A).status_code == 404
    assert client.get("/v1/reports/graph").status_code == 401
    if names["graph"]["available"]:
        assert "Graph evaluation" in client.get("/v1/reports/graph", headers=A).json()["markdown"]
