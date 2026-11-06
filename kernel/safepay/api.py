"""HTTP API (v1). Tenant comes from the API key, never from a client-supplied field."""
from __future__ import annotations
import hmac, json, re, threading, time, uuid
from pathlib import Path
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from . import accounts, cases as case_svc, ledger
from .agents.investigator import investigate_traced
from . import interception as icp, interception_deps as icp_deps, overview as overview_svc
from .llm.budget_db import DbBudget
from .llm.gateway import LLMGateway
from .config import ROLE_RANK, PolicyStore, Settings
from .db import DecisionRow, EventRow, LedgerEntry, LedgerHead, init_db, make_engine
from .decisions import DecisionRequest, DecisionResponse, DecisionService, IdempotencyConflict, NotFound, PolicyIntegrityError, ReplayResult
from .policy import Policy, evaluate
from .tools import CallResult, ToolGateway, ToolRegistry, mint_capability


MAX_BODY_BYTES = 256_000                    # one request body, checked from Content-Length before it is read
MAX_JSON_BYTES = 64_000                     # one free-form object once parsed
KEY_FORMAT = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")


def _bounded(v: dict) -> dict:
    if len(json.dumps(v, separators=(",", ":"))) > MAX_JSON_BYTES:
        raise ValueError(f"object larger than {MAX_JSON_BYTES} bytes")
    return v


class EventIn(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    data: dict

    _cap = field_validator("data")(_bounded)


class RunIn(BaseModel):
    tools: list[str]
    ttl_s: int = Field(default=300, ge=1, le=3600)


class ToolCallIn(BaseModel):
    tool: str
    args: dict
    mode: Literal["enforce", "shadow"] = "enforce"
    decision_id: str | None = None        # a policy pre-approval can only come from a stored decision, never from the caller


class ApprovalIn(BaseModel):
    approve: bool


class InterceptionIn(BaseModel):
    kind: Literal["ordinary", "large_new_payee", "vague_customer", "scam_uncoached", "scam_coached"]
    seed: int = Field(default=0, ge=0, le=1_000_000)
    mode: Literal["play", "auto"] = "play"


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class NewUserIn(SignupIn):
    role: Literal["viewer", "analyst", "admin"] = "analyst"


class SimulationIn(BaseModel):
    warn_from: float = Field(ge=-10, le=100)
    hold_from: float = Field(ge=-10, le=100)
    n: int = Field(default=100_000, ge=1_000, le=300_000)
    seed: int = Field(default=0, ge=0, le=10**9)
    scam_rate: float = Field(default=0.02, gt=0, le=0.2)

    @field_validator("hold_from")
    @classmethod
    def hold_not_below_warn(cls, v, info):
        if "warn_from" in info.data and v < info.data["warn_from"]:
            raise ValueError("hold_from must be at least warn_from")
        return v


class SimulateIn(BaseModel):
    policy: Policy
    contexts: list[dict] = Field(max_length=500)


def create_app(settings: Settings | None = None, registry: ToolRegistry | None = None, llm: LLMGateway | None = None, interception_deps: "icp_deps.InterceptionDeps | None" = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    sf = init_db(engine)
    store = PolicyStore(settings.policy_dir)
    registry = registry or ToolRegistry()
    for module in ("risk_tool", "text_tool", "screening_tool"):           # each optional tool is registered on its own: a missing package for one must not hide the others
        try:
            __import__(f"{__package__}.{module}", fromlist=["register_if_available"]).register_if_available(registry)
        except ImportError:
            pass
    decisions = DecisionService(sf, store.for_workload)
    gateway = ToolGateway(sf, registry, settings.capability_secret)
    app = FastAPI(title="SafePay Command kernel", version="0.3.0")
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"], allow_headers=["X-API-Key", "Authorization", "X-Actor", "Idempotency-Key", "Content-Type", "X-Capability"])
    if llm is None:
        from .llm.providers import OllamaCloudProvider
        chain = [OllamaCloudProvider(settings.ollama_api_key, m) for m in ("gemma4:31b", "deepseek-v4.1-flash")] if settings.ollama_api_key else []
        llm = LLMGateway(chain, budget=DbBudget(sf, max_requests_per_day=400, max_tokens_per_day=400_000, max_requests_per_run=6), timeout_s=12.0, deadline_s=24.0)

    interceptions = icp.InterceptionService(sf, llm, decisions)
    deps_cache: dict = {"deps": interception_deps}

    def get_deps() -> "icp_deps.InterceptionDeps":
        if deps_cache["deps"] is None:
            try:
                deps_cache["deps"] = icp_deps.default_deps(llm)
            except ImportError:
                raise HTTPException(501, "the interception demo needs the simulation and model packages on this server")
        return deps_cache["deps"]
    app.state.llm = llm

    @app.middleware("http")
    async def limit_body(request, call_next):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse({"detail": f"request body larger than {MAX_BODY_BYTES} bytes"}, status_code=413)
        return await call_next(request)
    app.state.sf = sf                       # exposed so tests can reach the database directly

    class _Limiter:
        """Token bucket per API key, in this process. With several instances the effective limit is per instance; a shared limiter belongs at the proxy."""
        def __init__(self, rate: float, burst: int):
            self.rate, self.burst, self.state, self.lock = rate, burst, {}, threading.Lock()

        def wait_needed(self, key: str) -> float:
            if self.rate <= 0:
                return 0.0
            now = time.monotonic()
            with self.lock:
                tokens, last = self.state.get(key, (float(self.burst), now))
                tokens = min(float(self.burst), tokens + (now - last) * self.rate)
                if tokens < 1.0:
                    self.state[key] = (tokens, now)
                    return (1.0 - tokens) / self.rate
                self.state[key] = (tokens - 1.0, now)
                return 0.0

    limiter = _Limiter(settings.rate_per_s, settings.rate_burst)

    def bearer(authorization: str | None) -> str | None:
        return authorization[7:].strip() if authorization and authorization[:7].lower() == "bearer " else None

    def principal(x_api_key: str | None, authorization: str | None = None) -> tuple[str, str]:
        token = bearer(authorization)
        if token is not None:                                      # a signed-in person: the tenant and role come from their account, never from the request
            who = accounts.session_user(sf, token)
            if who is None:
                raise HTTPException(401, "your session has ended; sign in again")
            wait = limiter.wait_needed("user:" + who["id"])
            if wait > 0:
                raise HTTPException(429, "too many requests", headers={"Retry-After": str(max(1, int(wait + 0.999)))})
            return who["tenant"], who["role"]
        tenant, matched = None, ""
        for known, t in settings.tenants.items():          # constant-time comparison so response time does not reveal how much of a key matched
            if hmac.compare_digest(known.encode(), (x_api_key or "").encode()):
                tenant, matched = t, known
        if tenant is None:
            raise HTTPException(401, "missing or unknown API key")
        wait = limiter.wait_needed(matched)
        if wait > 0:
            raise HTTPException(429, "too many requests", headers={"Retry-After": str(max(1, int(wait + 0.999)))})
        return tenant, settings.roles.get(matched, "admin")

    def auth(minimum: str):
        def dep(x_api_key: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> str:
            tenant, role = principal(x_api_key, authorization)
            if ROLE_RANK[role] < ROLE_RANK[minimum]:
                raise HTTPException(403, f"this action needs the {minimum} role")
            return tenant
        return dep

    tenant_of, analyst_of, admin_of = auth("viewer"), auth("analyst"), auth("admin")

    @app.get("/v1/whoami")
    def whoami(x_api_key: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        tenant, role = principal(x_api_key, authorization)
        token = bearer(authorization)
        who = accounts.session_user(sf, token) if token else None
        return {"tenant": tenant, "role": role, **({"name": who["name"], "email": who["email"]} if who else {})}

    auth_limiter = _Limiter(settings.auth_rate_per_s, settings.auth_burst)

    def sign_in_limit(request: Request) -> None:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()       # the last entry is the one our own proxy recorded; earlier entries can be forged by the client
        wait = auth_limiter.wait_needed("ip:" + (forwarded or (request.client.host if request.client else "?")))
        if wait > 0:
            raise HTTPException(429, "too many sign-in attempts; wait a minute and try again", headers={"Retry-After": str(max(1, int(wait + 0.999)))})

    def session_reply(user: dict) -> dict:
        return {"token": accounts.start_session(sf, user), "expires_in": accounts.SESSION_TTL_S, "user": {k: user[k] for k in ("email", "name", "tenant", "role")}}

    def make_user(body: SignupIn, tenant: str, role: str) -> dict:
        try:
            return accounts.create_user(sf, body.email, body.name, body.password, tenant, role, settings.max_users)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except accounts.EmailTaken:
            raise HTTPException(409, "an account with this email already exists; sign in instead")
        except accounts.SignupFull:
            raise HTTPException(403, "this demo has reached its account limit")

    @app.post("/v1/auth/signup", dependencies=[Depends(sign_in_limit)])
    def signup(body: SignupIn):
        if not settings.signup_tenant:
            raise HTTPException(403, "sign-up is not open on this server")
        return session_reply(make_user(body, settings.signup_tenant, "analyst"))      # open sign-up never grants admin

    @app.post("/v1/auth/login", dependencies=[Depends(sign_in_limit)])
    def login(body: LoginIn):
        try:
            return session_reply(accounts.login(sf, body.email, body.password))
        except accounts.BadLogin:
            raise HTTPException(401, "wrong email or password")

    @app.post("/v1/auth/logout")
    def logout(authorization: str | None = Header(default=None)):
        token = bearer(authorization)
        if token:
            accounts.end_session(sf, token)
        return {"ok": True}

    @app.post("/v1/auth/users")
    def add_user(body: NewUserIn, tenant: str = Depends(admin_of)):
        u = make_user(body, tenant, body.role)                  # an admin adds people to their own tenant only
        return {k: u[k] for k in ("email", "name", "tenant", "role")}

    def actor_of(x_actor: str | None, authorization: str | None) -> str | None:
        token = bearer(authorization)
        who = accounts.session_user(sf, token) if token else None
        return who["name"] if who else x_actor                  # a signed-in person's decisions carry their account name, not a header they could change

    def need_key(idempotency_key: str | None) -> str:
        if not idempotency_key or not KEY_FORMAT.match(idempotency_key):
            raise HTTPException(400, "Idempotency-Key header is required (1 to 128 characters: letters, digits and . _ : -)")
        return idempotency_key

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/v1/events")
    def post_event(body: EventIn, tenant: str = Depends(analyst_of), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        data_json = ledger.canonical_json(body.model_dump())
        h = ledger.sha256_hex(data_json)
        try:
            with sf.begin() as s:
                row = s.scalar(select(EventRow).where(EventRow.tenant == tenant, EventRow.idempotency_key == key))
                if row:
                    if row.event_hash != h:
                        raise HTTPException(409, "idempotency key reused with a different event")
                    return {"event_id": row.id, "replayed": True}
                row = EventRow(id="e_" + uuid.uuid4().hex[:12], tenant=tenant, idempotency_key=key, event_hash=h, type=body.type, data=data_json)
                s.add(row)
                ledger.append(s, tenant, "event", {"event_id": row.id, "type": body.type, "event_hash": h})
                return {"event_id": row.id, "replayed": False}
        except IntegrityError:
            raise HTTPException(409, "concurrent request with the same idempotency key")

    @app.post("/v1/decisions", response_model=DecisionResponse)
    def post_decision(body: DecisionRequest, tenant: str = Depends(analyst_of), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        try:
            decision, _ = decisions.decide(tenant, key, body)
        except IdempotencyConflict as e:
            raise HTTPException(409, str(e))
        except KeyError as e:
            raise HTTPException(422, str(e))
        return decision

    @app.get("/v1/decisions/{decision_id}", response_model=DecisionResponse)
    def get_decision(decision_id: str, tenant: str = Depends(tenant_of)):
        try:
            return decisions.get(tenant, decision_id)
        except NotFound:
            raise HTTPException(404, "decision not found")

    @app.get("/v1/decisions/{decision_id}/replay", response_model=ReplayResult)
    def replay_decision(decision_id: str, tenant: str = Depends(tenant_of)):
        try:
            return decisions.replay(tenant, decision_id)
        except NotFound:
            raise HTTPException(404, "decision not found")
        except PolicyIntegrityError as e:
            raise HTTPException(409, str(e))

    @app.get("/v1/audit")
    def audit(tenant: str = Depends(tenant_of), after_seq: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        with sf() as s:
            return [{"seq": e.seq, "tenant": e.tenant, "kind": e.kind, "ts": e.ts, "hash": e.hash, "prev_hash": e.prev_hash, "payload": json.loads(e.payload), "payload_canonical": e.payload}
                    for e in ledger.entries(s, tenant, after_seq, limit)]      # payload_canonical is the exact string that was hashed, so a client can recompute the hash itself

    @app.get("/v1/audit/verify")
    def audit_verify(tenant: str = Depends(tenant_of)):
        with sf() as s:
            r = ledger.verify(s, tenant)
            head = s.get(LedgerHead, tenant)
        return {"ok": r.ok, "checked": r.checked, "reason": r.reason, "bad_seq": r.bad_seq, "head_hash": head.head_hash if head else ledger.GENESIS}

    @app.get("/v1/policies")
    def list_policies(tenant: str = Depends(tenant_of)):
        return [{"workload": w, "name": p.name, "version": p.version, "rules": len(p.rules)} for w, p in store.policies.items()]

    @app.post("/v1/policies/simulate")
    def simulate(body: SimulateIn, tenant: str = Depends(tenant_of)):
        """Run a candidate policy over supplied contexts. Nothing is stored and no ledger entry is written."""
        return {"policy_version": body.policy.version, "results": [evaluate(body.policy, c).model_dump() for c in body.contexts]}

    @app.post("/v1/simulations")
    def simulate_policy(body: SimulationIn, tenant: str = Depends(tenant_of)):
        """Run a threshold policy on SIMULATED payments with known ground truth. Read-only: nothing is stored and nothing touches the ledger or real data."""
        try:
            from dataclasses import asdict, replace
            from safepay_lab.experiments import policy_truth
            from safepay_lab.simulator import SimConfig, sample_population
        except ImportError:
            raise HTTPException(501, "the simulation package is not installed on this server")
        cfg = replace(SimConfig(), scam_rate=body.scam_rate)
        return {"provenance": "simulated", "note": "Simulated payments with assumed scam behaviour; amounts follow the real ULB card data. Not evidence about real customers.",
                "assumptions": asdict(cfg), "n": body.n, "seed": body.seed, "result": policy_truth(sample_population(body.n, body.seed, cfg), cfg, body.warn_from, body.hold_from)}

    # ---------------- interception: payment, risk, questions, flags, policy, message, ledger ----------------
    @app.get("/v1/interceptions/scenarios")
    def interception_scenarios(tenant: str = Depends(tenant_of)):
        return icp_deps.scenario_catalog()

    @app.post("/v1/interceptions")
    def start_interception(body: InterceptionIn, tenant: str = Depends(analyst_of)):
        deps = get_deps()
        try:
            sc = deps.scenario(body.kind, body.seed)
            risk = deps.risk(sc)
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        payment = {"amount": sc.amount, "payee_age_days": sc.payee_age_days, "currency": "EUR", "row_ref": sc.row_ref, "kind": sc.kind,
                   "provenance": "Payment features: a real transaction from the held-out ULB data, scored by the real model. Payee age and everything the customer says: simulated."}
        iid = interceptions.start(tenant, payment, risk, body.mode, {"is_scam": sc.is_scam, "kind": sc.kind})
        if body.mode == "auto":
            for turn in range(icp.MAX_QUESTIONS):
                state = interceptions.get(tenant, iid)
                if state["state"] != "asking":
                    break
                interceptions.answer(tenant, iid, deps.victim(llm, f"{iid}-v{turn}", sc, state["transcript"][-1]["question"], turn))
        return interceptions.get(tenant, iid)

    @app.post("/v1/interceptions/{iid}/answer")
    def answer_interception(iid: str, body: AnswerIn, tenant: str = Depends(analyst_of)):
        try:
            interceptions.answer(tenant, iid, body.text)
        except icp.NotFound:
            raise HTTPException(404, "interception not found")
        except icp.AlreadyDecided:
            raise HTTPException(409, "this payment already has a decision")
        except icp.Busy:
            raise HTTPException(409, "an answer for this payment is already being processed")
        except icp.BadAnswer as e:
            raise HTTPException(422, str(e))
        return interceptions.get(tenant, iid)

    @app.get("/v1/interceptions/{iid}")
    def get_interception(iid: str, tenant: str = Depends(tenant_of)):
        try:
            return interceptions.get(tenant, iid)
        except icp.NotFound:
            raise HTTPException(404, "interception not found")

    # ---------------- cases, investigation, dispositions, labels ----------------
    @app.post("/v1/cases/import")
    def import_cases(body: case_svc.ImportIn, tenant: str = Depends(admin_of)):
        with sf.begin() as s:
            return case_svc.import_cases(s, tenant, body)

    @app.get("/v1/cases")
    def list_cases(tenant: str = Depends(tenant_of), status: str | None = Query(None, pattern="^(open|dispositioned)$"), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as s:
            return case_svc.list_cases(s, tenant, status, limit, offset)

    @app.get("/v1/cases/stats")
    def case_stats(tenant: str = Depends(tenant_of)):
        with sf() as s:
            return case_svc.stats(s, tenant)

    @app.get("/v1/cases/{case_id}")
    def get_case(case_id: str, tenant: str = Depends(tenant_of)):
        try:
            with sf() as s:
                return case_svc.get_case(s, tenant, case_id)
        except case_svc.NotFound:
            raise HTTPException(404, "case not found")

    @app.get("/v1/cases/{case_id}/ledger")
    def case_ledger(case_id: str, tenant: str = Depends(tenant_of)):
        """The ledger entries about one case (investigation and decision), for the case's trace view."""
        try:
            with sf() as s:
                case_svc.case_content(s, tenant, case_id)           # 404 for another tenant's case
                rows = s.scalars(select(LedgerEntry).where(LedgerEntry.tenant == tenant, LedgerEntry.kind.in_(("case.investigated", "case.dispositioned")),
                                                          LedgerEntry.payload.contains(f'"case_id":"{case_id}"')).order_by(LedgerEntry.seq)).all()
                return [{"seq": e.seq, "kind": e.kind, "ts": e.ts, "hash": e.hash} for e in rows]
        except case_svc.NotFound:
            raise HTTPException(404, "case not found")

    @app.post("/v1/cases/{case_id}/investigate")
    def investigate_case(case_id: str, tenant: str = Depends(analyst_of)):
        try:
            with sf() as s:
                items = case_svc.case_content(s, tenant, case_id)["items"]
        except case_svc.NotFound:
            raise HTTPException(404, "case not found")
        summary, res, evidence, priority, trace = investigate_traced(llm, f"inv-{case_id}", items)
        meta = {"path": res.path if res else "rule", "provider": res.provider if res else None, "model": res.model if res else None,
                "evidence": [{"id": e.id, "text": e.text} for e in evidence], "injection_flags": res.injection_flags if res else [], "trace": trace}
        with sf.begin() as s:
            case_svc.save_investigation(s, tenant, case_id, {**summary.model_dump(), "priority": priority}, meta)
        return {**summary.model_dump(), "priority": priority, **meta}

    @app.post("/v1/cases/{case_id}/disposition")
    def disposition_case(case_id: str, body: case_svc.DispositionIn, tenant: str = Depends(analyst_of), x_actor: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        x_actor = actor_of(x_actor, authorization)
        if not x_actor or len(x_actor) > 64:
            raise HTTPException(400, "X-Actor header is required to record who decided (max 64 characters)")
        try:
            with sf.begin() as s:
                return case_svc.disposition(s, tenant, case_id, x_actor, body)
        except case_svc.NotFound:
            raise HTTPException(404, "case not found")
        except case_svc.OverrideReasonRequired:
            raise HTTPException(422, f"Dismissing a case the AI recommended escalating needs a written reason of at least {case_svc.MIN_REASON} characters.")
        except (case_svc.AlreadyDecided, IntegrityError):
            raise HTTPException(409, "this case already has a disposition")

    @app.get("/v1/labels")
    def labels(tenant: str = Depends(tenant_of), limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
        with sf() as s:
            return case_svc.export_labels(s, tenant, limit, offset)

    frontier_cache: dict = {}

    @app.get("/v1/simulations/frontier")
    def simulation_frontier(tenant: str = Depends(tenant_of), n: int = Query(100_000, ge=10_000, le=300_000), seed: int = Query(0, ge=0, le=10**9)):
        """Reference curve for the policy slider: a family of threshold policies on simulated payments, each with its true outcome. Cached per (n, seed)."""
        try:
            from dataclasses import asdict
            from safepay_lab.experiments import frontier
            from safepay_lab.simulator import SimConfig
        except ImportError:
            raise HTTPException(501, "the simulation package is not installed on this server")
        key = (n, seed)
        if key not in frontier_cache:
            if len(frontier_cache) > 8:
                frontier_cache.clear()
            frontier_cache[key] = frontier(SimConfig(), n=n, seed=seed)
        return {"provenance": "simulated", "note": "Simulated payments with assumed scam behaviour; amounts follow the real ULB card data. Not evidence about real customers.", "assumptions": asdict(SimConfig()), "n": n, "seed": seed, "rows": frontier_cache[key]}

    @app.get("/v1/overview")
    def get_overview(tenant: str = Depends(tenant_of)):
        with sf() as s:
            return overview_svc.overview(s, tenant)

    # ---------------- generated reports (the UI's metrics pages read these) ----------------
    reports_dir = Path(__file__).resolve().parents[2] / "docs" / "reports"
    REPORTS = {"risk_model": ("Transaction risk model", "real"), "text_model": ("Scam-text model", "real"), "screening": ("Name screening", "real"), "graph": ("Graph and cases", "real"), "flywheel": ("Analyst feedback flywheel", "mixed"), "investigator": ("Investigator summaries", "mixed"), "redaction": ("Name and address redaction", "mixed"), "interception": ("Interception: does the AI questioning add anything?", "mixed"), "load": ("Local load test", "simulated"),
               "decision_lab": ("Decision Lab", "simulated"), "uplift": ("Uplift", "simulated"), "sandbox": ("Questioner under pressure", "simulated"), "llm_eval": ("LLM provider evaluation", "mixed")}

    @app.get("/v1/reports")
    def list_reports(tenant: str = Depends(tenant_of)):
        return [{"name": n, "title": t, "provenance": p, "available": (reports_dir / f"{n}.md").exists()} for n, (t, p) in REPORTS.items()]

    @app.get("/v1/reports/{name}")
    def get_report(name: str, tenant: str = Depends(tenant_of)):
        if name not in REPORTS or not (reports_dir / f"{name}.md").exists():
            raise HTTPException(404, "report not found")
        t, p = REPORTS[name]
        return {"name": name, "title": t, "provenance": p, "markdown": (reports_dir / f"{name}.md").read_text()}

    @app.get("/v1/tools")
    def list_tools(tenant: str = Depends(tenant_of)):
        return registry.describe()

    @app.post("/v1/runs")
    def start_run(body: RunIn, tenant: str = Depends(analyst_of)):
        unknown = [t for t in body.tools if registry.get(t) is None]
        if unknown:
            raise HTTPException(422, f"unknown tools: {unknown}")
        run_id = "r_" + uuid.uuid4().hex[:12]
        with sf.begin() as s:
            ledger.append(s, tenant, "run.started", {"run_id": run_id, "tools": sorted(body.tools)})
        return {"run_id": run_id, "capability": mint_capability(settings.capability_secret, tenant, run_id, body.tools, body.ttl_s)}

    @app.post("/v1/tools/call", response_model=CallResult)
    def call_tool(body: ToolCallIn, tenant: str = Depends(analyst_of), x_capability: str | None = Header(default=None), idempotency_key: str | None = Header(default=None)):
        key = need_key(idempotency_key)
        pre = False
        if body.decision_id:
            try:
                d = decisions.get(tenant, body.decision_id)
                pre = d.mode == "enforce" and d.outcome == "hold" and not d.requires_approval
            except NotFound:
                raise HTTPException(404, "decision not found")
        return gateway.call(tenant, x_capability or "", body.tool, body.args, key, body.mode, pre)

    @app.get("/v1/approvals")
    def approvals(tenant: str = Depends(tenant_of), status: str | None = None):
        return gateway.list_approvals(tenant, status)

    @app.post("/v1/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: ApprovalIn, tenant: str = Depends(analyst_of), x_actor: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        x_actor = actor_of(x_actor, authorization)
        if not x_actor:
            raise HTTPException(400, "X-Actor header is required to record who decided")
        try:
            return gateway.decide_approval(tenant, approval_id, x_actor, body.approve)
        except KeyError:
            raise HTTPException(404, "pending approval not found")

    return app
