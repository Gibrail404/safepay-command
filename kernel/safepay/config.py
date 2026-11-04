"""Settings come from the environment. Nothing secret is stored in the repository."""
from __future__ import annotations
import json, os, secrets
from dataclasses import dataclass, field
from pathlib import Path
from .policy import Policy

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    database_url: str = "sqlite+pysqlite:///:memory:"
    tenants: dict[str, str] = field(default_factory=dict)         # api key -> tenant id
    capability_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    policy_dir: Path = ROOT / "config" / "policies"
    ollama_api_key: str = ""
    cors_origins: tuple = ()

    @classmethod
    def from_env(cls) -> "Settings":
        pairs = [p.split(":", 1) for p in os.environ.get("SAFEPAY_TENANTS", "").split(",") if ":" in p]   # "tenant:key,tenant2:key2"
        secret = os.environ.get("SAFEPAY_CAPABILITY_SECRET")
        return cls(database_url=os.environ.get("DATABASE_URL", cls.database_url), tenants={k: t for t, k in pairs},
                   capability_secret=secret.encode() if secret else secrets.token_bytes(32),
                   policy_dir=Path(os.environ.get("SAFEPAY_POLICY_DIR", ROOT / "config" / "policies")), ollama_api_key=os.environ.get("OLLAMA_API_KEY", ""),
                   cors_origins=tuple(o for o in os.environ.get("SAFEPAY_CORS_ORIGINS", "").split(",") if o))


class PolicyStore:
    """Policies live in config/policies/<workload>.json, version-controlled, and are loaded and validated at startup."""
    def __init__(self, directory: Path):
        self.policies = {f.stem: Policy.model_validate(json.loads(f.read_text())) for f in sorted(Path(directory).glob("*.json"))}

    def for_workload(self, tenant: str, workload: str) -> Policy:
        if workload not in self.policies:
            raise KeyError(f"no policy for workload {workload!r}")
        return self.policies[workload]
