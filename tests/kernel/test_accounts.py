"""Sign-up and sign-in: closed by default, never admin, tenant and role come from the account, tokens and passwords are not stored in the clear."""
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from conftest import TEST_DB_URL, fresh_engine
from safepay.api import create_app
from safepay.config import Settings
from safepay.db import SessionRow, UserRow

KEY = {"X-API-Key": "k-admin"}


_APPS = []


@pytest.fixture(autouse=True)
def _close_engines():
    yield
    while _APPS:
        _APPS.pop().state.sf.kw["bind"].dispose()      # each test builds its own app; leaving the connections open exhausts PostgreSQL for the tests that run after


def make(**kw):
    fresh_engine().dispose()
    base = dict(database_url=TEST_DB_URL, tenants={"k-admin": "demo"}, roles={"k-admin": "admin"}, rate_per_s=0, signup_tenant="demo", auth_rate_per_s=0)
    app = create_app(Settings(**{**base, **kw}))
    _APPS.append(app)
    return TestClient(app), app


def signup(c, email="Ana@Example.com", password="correct horse", name="Ana"):
    return c.post("/v1/auth/signup", json={"email": email, "password": password, "name": name})


def bearer(r):
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_signup_is_closed_unless_the_server_names_a_tenant():
    c, _ = make(signup_tenant="")
    assert signup(c).status_code == 403


def test_signup_signs_you_in_as_an_analyst_in_the_shared_tenant():
    c, _ = make()
    r = signup(c)
    assert r.status_code == 200 and r.json()["user"] == {"email": "ana@example.com", "name": "Ana", "tenant": "demo", "role": "analyst"}
    who = c.get("/v1/whoami", headers=bearer(r)).json()
    assert who == {"tenant": "demo", "role": "analyst", "name": "Ana", "email": "ana@example.com"}
    assert c.get("/v1/cases/stats", headers=bearer(r)).status_code == 200


def test_signup_can_never_make_an_admin_even_if_asked():
    c, _ = make()
    r = c.post("/v1/auth/signup", json={"email": "x@example.com", "password": "correct horse", "name": "X", "role": "admin", "tenant": "other"})
    assert r.json()["user"]["role"] == "analyst" and r.json()["user"]["tenant"] == "demo"


def test_the_same_email_cannot_sign_up_twice_whatever_the_case():
    c, _ = make()
    assert signup(c).status_code == 200
    assert signup(c, email="ANA@example.com").status_code == 409


@pytest.mark.parametrize("email,password", [("not-an-email", "correct horse"), ("a@b", "correct horse"), ("a@example.com", "short")])
def test_bad_sign_up_input_is_rejected(email, password):
    c, _ = make()
    assert signup(c, email=email, password=password).status_code == 422


def test_login_works_and_a_wrong_password_and_unknown_email_look_the_same():
    c, _ = make()
    signup(c)
    ok = c.post("/v1/auth/login", json={"email": "ana@EXAMPLE.com", "password": "correct horse"})
    assert ok.status_code == 200 and "token" in ok.json()
    wrong = c.post("/v1/auth/login", json={"email": "ana@example.com", "password": "wrong password"})
    unknown = c.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "correct horse"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


def test_neither_the_password_nor_the_token_is_stored_in_the_clear():
    c, app = make()
    r = signup(c)
    with app.state.sf() as s:
        u, sess = s.scalar(select(UserRow)), s.scalar(select(SessionRow))
    assert "correct horse" not in (u.pw_hash + u.pw_salt) and r.json()["token"] not in sess.token_hash and len(u.pw_hash) == 64


def test_logout_ends_the_session():
    c, _ = make()
    h = bearer(signup(c))
    assert c.post("/v1/auth/logout", headers=h).status_code == 200
    assert c.get("/v1/whoami", headers=h).status_code == 401


def test_an_expired_session_is_refused():
    c, app = make()
    h = bearer(signup(c))
    with app.state.sf.begin() as s:
        s.execute(text("UPDATE sessions SET expires = :t"), {"t": time.time() - 1})
    assert c.get("/v1/whoami", headers=h).status_code == 401


def test_a_bad_token_is_never_rescued_by_an_api_key():
    c, _ = make()
    assert c.get("/v1/whoami", headers={"Authorization": "Bearer sp_forged", **KEY}).status_code == 401


def test_the_decision_carries_the_account_name_not_a_header():
    c, _ = make()
    case = {"external_id": "a1", "source": "t", "provenance": "simulated", "priority": "high", "title": "t", "items": [{"ref": "t1", "score": 0.9, "time_step": 1, "facts": {}}], "facts": {}}
    assert c.post("/v1/cases/import", json={"cases": [case]}, headers=KEY).status_code == 200
    cid = c.get("/v1/cases", headers=KEY).json()["cases"][0]["id"]
    h = {**bearer(signup(c)), "X-Actor": "someone-else"}
    assert c.post(f"/v1/cases/{cid}/disposition", json={"decision": "dismissed_licit"}, headers=h).status_code == 200
    assert c.get(f"/v1/cases/{cid}", headers=KEY).json()["disposition"]["actor"] == "Ana"


def test_only_an_admin_can_add_people_and_a_viewer_cannot_act():
    c, _ = make()
    analyst = bearer(signup(c))
    body = {"email": "view@example.com", "password": "correct horse", "name": "View", "role": "viewer"}
    assert c.post("/v1/auth/users", json=body, headers=analyst).status_code == 403
    assert c.post("/v1/auth/users", json=body, headers=KEY).json() == {"email": "view@example.com", "name": "View", "tenant": "demo", "role": "viewer"}
    viewer = bearer(c.post("/v1/auth/login", json={"email": "view@example.com", "password": "correct horse"}))
    assert c.get("/v1/cases/stats", headers=viewer).status_code == 200
    assert c.post("/v1/events", json={"type": "t", "data": {}}, headers={**viewer, "Idempotency-Key": "e1"}).status_code == 403


def test_the_account_cap_stops_open_signup_from_growing_forever():
    c, _ = make(max_users=2)
    assert signup(c, email="a@example.com").status_code == 200 and signup(c, email="b@example.com").status_code == 200
    assert signup(c, email="c@example.com").status_code == 403


def test_repeated_attempts_from_one_address_are_slowed_down():
    c, _ = make(auth_rate_per_s=0.001, auth_burst=3)
    codes = [c.post("/v1/auth/login", json={"email": "a@example.com", "password": "x" * 8}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429 and 429 in codes[3:]
