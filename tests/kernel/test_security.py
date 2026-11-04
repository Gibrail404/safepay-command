"""Roles, rate limits and the database-backed LLM budget."""
import os
import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from conftest import TEST_DB_URL, fresh_engine
from safepay.api import create_app
from safepay.config import Settings
from safepay.db import init_db
from safepay.llm.budget_db import DbBudget
from safepay.llm.gateway import LLMGateway
from safepay.llm.providers import FakeProvider
from test_cases import case

V, AN, AD = {"X-API-Key": "viewer-key"}, {"X-API-Key": "analyst-key", "X-Actor": "ana"}, {"X-API-Key": "admin-key"}


def make(**kw):
    fresh_engine().dispose()
    s = Settings(database_url=TEST_DB_URL, tenants={"viewer-key": "t", "analyst-key": "t", "admin-key": "t"}, roles={"viewer-key": "viewer", "analyst-key": "analyst", "admin-key": "admin"}, **kw)
    return TestClient(create_app(s, llm=LLMGateway([])))


def test_roles_limit_what_each_key_can_do():
    c = make()
    assert c.post("/v1/cases/import", json={"cases": [case()]}, headers=V).status_code == 403
    assert c.post("/v1/cases/import", json={"cases": [case()]}, headers={**AN}).status_code == 403
    assert c.post("/v1/cases/import", json={"cases": [case()]}, headers=AD).status_code == 200
    cid = c.get("/v1/cases", headers=V).json()["cases"][0]["id"]
    assert c.get(f"/v1/cases/{cid}", headers=V).status_code == 200
    assert c.post(f"/v1/cases/{cid}/investigate", headers=V).status_code == 403
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "escalated"}, headers={**V, "X-Actor": "v"}).status_code == 403
    assert c.post(f"/v1/cases/{cid}/investigate", headers=AN).status_code == 200
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "escalated"}, headers=AN).status_code == 200


def test_a_viewer_cannot_write_through_any_other_door_either():
    c = make()
    assert c.post("/v1/events", json={"type": "x", "data": {}}, headers={**V, "Idempotency-Key": "k"}).status_code == 403
    assert c.post("/v1/runs", json={"tools": []}, headers=V).status_code == 403
    assert c.post("/v1/decisions", json={"workload": "payment_risk", "subject": {}, "context": {}}, headers={**V, "Idempotency-Key": "k"}).status_code == 403
    assert c.get("/v1/audit/verify", headers=V).status_code == 200 and c.get("/v1/labels", headers=V).status_code == 200


def test_whoami_reports_tenant_and_role():
    c = make()
    assert c.get("/v1/whoami", headers=V).json() == {"tenant": "t", "role": "viewer"} and c.get("/v1/whoami").status_code == 401


def test_roles_are_parsed_from_the_environment_and_a_typo_is_refused(monkeypatch):
    monkeypatch.setenv("SAFEPAY_TENANTS", "acme:k1:analyst,acme:k2:viewer,beta:k3")
    s = Settings.from_env()
    assert s.roles == {"k1": "analyst", "k2": "viewer"} and s.tenants == {"k1": "acme", "k2": "acme", "k3": "beta"}
    monkeypatch.setenv("SAFEPAY_TENANTS", "acme:k1:analist")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_rate_limit_returns_429_with_retry_after_and_is_per_key():
    c = make(rate_per_s=1.0, rate_burst=3)
    codes = [c.get("/v1/cases/stats", headers=V).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    r = c.get("/v1/cases/stats", headers=V)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert c.get("/v1/cases/stats", headers=AD).status_code == 200


def test_rate_limit_can_be_turned_off():
    c = make(rate_per_s=0)
    assert all(c.get("/healthz").status_code == 200 for _ in range(100)) and all(c.get("/v1/cases/stats", headers=V).status_code == 200 for _ in range(100))


# ---------------- database-backed budget ----------------
def budget(sf, **kw):
    return DbBudget(sf, **kw)


def test_the_daily_request_cap_is_enforced_and_shared_between_instances(sf):
    a, b = budget(sf, max_requests_per_day=3), budget(sf, max_requests_per_day=3)        # two instances, as with two server processes
    assert [a.reserve("r1"), b.reserve("r2"), a.reserve("r3")] == [None, None, None]
    assert b.reserve("r4") == "daily request cap reached" and a.reserve("r5") == "daily request cap reached"


def test_the_token_cap_and_a_new_day_reset(sf):
    now = [1_700_000_000.0]
    b = budget(sf, max_tokens_per_day=100, clock=lambda: now[0])
    assert b.reserve("r1") is None
    b.add_tokens(150)
    assert b.reserve("r2") == "daily token cap reached"
    now[0] += 86_400
    assert b.reserve("r3") is None


def test_the_cap_survives_a_restart(sf):
    budget(sf, max_requests_per_day=1).reserve("r1")
    assert budget(sf, max_requests_per_day=1).reserve("r2") == "daily request cap reached"


def test_per_run_cap_stays_local():
    from safepay.db import make_engine
    sf = init_db(make_engine("sqlite+pysqlite:///:memory:"))
    b = budget(sf, max_requests_per_run=2)
    assert [b.reserve("run"), b.reserve("run"), b.reserve("run")] == [None, None, "per-run request cap reached"] and b.reserve("other") is None


@pytest.mark.skipif(not TEST_DB_URL.startswith("postgresql"), reason="needs PostgreSQL")
def test_simultaneous_callers_cannot_exceed_the_cap(sf):
    b = budget(sf, max_requests_per_day=5)
    with ThreadPoolExecutor(12) as ex:
        out = list(ex.map(lambda i: budget(sf, max_requests_per_day=5).reserve(f"r{i}"), range(12)))
    assert out.count(None) == 5


def test_the_gateway_stops_calling_the_model_when_the_shared_budget_is_spent(sf):
    from pydantic import BaseModel
    from safepay.llm.gateway import LLMRequest

    class Out(BaseModel):
        text: str
    p = FakeProvider(['{"text": "hello there"}'] * 5)
    gw = LLMGateway([p], budget=budget(sf, max_requests_per_day=1))
    ask = lambda run: gw.generate(LLMRequest(task="say hello", output=Out), run, lambda: Out(text="fallback")).path
    assert [ask("a"), ask("b")] == ["llm", "fallback"] and len(p.seen) == 1
