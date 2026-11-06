"""Settings come from the environment. Nothing secret is stored in the repository."""
from __future__ import annotations
import json, os, secrets
from dataclasses import dataclass, field
from pathlib import Path
from .policy import Policy

ROOT = Path(__file__).resolve().parents[2]
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}


@dataclass
class Settings:
    database_url: str = "sqlite+pysqlite:///:memory:"
    tenants: dict[str, str] = field(default_factory=dict)         # api key -> tenant id
    roles: dict[str, str] = field(default_factory=dict)           # api key -> viewer | analyst | admin (a key with no entry is admin, to keep simple setups working)
    rate_per_s: float = 30.0                                      # requests per second allowed per API key (0 turns the limit off)
    rate_burst: int = 60
    capability_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    policy_dir: Path = ROOT / "config" / "policies"
    ollama_api_key: str = ""
    cors_origins: tuple = ()
    signup_tenant: str = ""                                       # sign-up is open only when this names the tenant new accounts join (always as analyst); empty means sign-up is closed
    max_users: int = 500                                          # a hard cap on accounts, so open sign-up cannot grow the database without limit
    auth_rate_per_s: float = 0.1                                  # sign-in and sign-up attempts per second per client address (0 turns the limit off)
    auth_burst: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        pairs = [p.split(":") for p in os.environ.get("SAFEPAY_TENANTS", "").split(",") if p.count(":") in (1, 2)]   # "tenant:key[:role],tenant2:key2[:role]"
        for x in pairs:
            if len(x) == 3 and x[2] not in ROLE_RANK:
                raise ValueError(f"unknown role {x[2]!r} for tenant {x[0]!r}; use one of {sorted(ROLE_RANK)}")     # a typo must never silently become admin
        secret = os.environ.get("SAFEPAY_CAPABILITY_SECRET")
        return cls(database_url=os.environ.get("DATABASE_URL", cls.database_url), tenants={x[1]: x[0] for x in pairs}, roles={x[1]: x[2] for x in pairs if len(x) == 3 and x[2] in ROLE_RANK},
                   rate_per_s=float(os.environ.get("SAFEPAY_RATE_PER_S", 30)), rate_burst=int(os.environ.get("SAFEPAY_RATE_BURST", 60)),
                   capability_secret=secret.encode() if secret else secrets.token_bytes(32),
                   policy_dir=Path(os.environ.get("SAFEPAY_POLICY_DIR", ROOT / "config" / "policies")), ollama_api_key=os.environ.get("OLLAMA_API_KEY", ""),
                   cors_origins=tuple(o for o in os.environ.get("SAFEPAY_CORS_ORIGINS", "").split(",") if o),
                   signup_tenant=os.environ.get("SAFEPAY_SIGNUP_TENANT", ""), max_users=int(os.environ.get("SAFEPAY_MAX_USERS", 500)),
                   auth_rate_per_s=float(os.environ.get("SAFEPAY_AUTH_RATE_PER_S", 0.1)), auth_burst=int(os.environ.get("SAFEPAY_AUTH_BURST", 8)))


class PolicyStore:
    """Policies live in config/policies/<workload>.json, version-controlled, and are loaded and validated at startup."""
    def __init__(self, directory: Path):
        self.policies = {f.stem: Policy.model_validate(json.loads(f.read_text())) for f in sorted(Path(directory).glob("*.json"))}

    def for_workload(self, tenant: str, workload: str) -> Policy:
        if workload not in self.policies:
            raise KeyError(f"no policy for workload {workload!r}")
        return self.policies[workload]
