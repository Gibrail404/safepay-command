"""Write the generated OpenAPI document. It is generated from the code, so it can never drift from the API."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kernel"))
from safepay.api import create_app
from safepay.config import Settings

app = create_app(Settings(tenants={"x": "x"}))
out = ROOT / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print("wrote", out, "paths:", len(app.openapi()["paths"]))
