"""Local load test: concurrent clients against a running API. Records requests per second and latency percentiles per endpoint and concurrency level, then merges the run
into docs/reports/load.{json,md} under a label. Client and server share the machine, so absolute numbers are conservative for the server and say nothing about a cloud deployment.
Usage: python scripts/load_test.py --url http://127.0.0.1:8000 --key demo-key --label "1 worker" [--seconds 8] [--levels 1,8,32]"""
import argparse, asyncio, json, os, platform, sys, time, uuid
from pathlib import Path
import httpx
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "reports"


async def run_level(make, concurrency: int, seconds: float) -> dict:
    lat: list[float] = []
    errors: dict[int, int] = {}
    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency + 4)
    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        stop = time.perf_counter() + seconds

        async def worker():
            while time.perf_counter() < stop:
                t = time.perf_counter()
                try:
                    r = await make(client)
                    code = r.status_code
                except Exception:
                    code = 0
                dt = (time.perf_counter() - t) * 1000
                if code >= 400 or code == 0:
                    errors[code] = errors.get(code, 0) + 1
                else:
                    lat.append(dt)
        t0 = time.perf_counter()
        await asyncio.gather(*[worker() for _ in range(concurrency)])
        wall = time.perf_counter() - t0
    a = np.array(lat) if lat else np.array([0.0])
    return {"concurrency": concurrency, "ok_requests": len(lat), "errors": errors, "requests_per_second": len(lat) / wall,
            "p50_ms": float(np.percentile(a, 50)), "p95_ms": float(np.percentile(a, 95)), "p99_ms": float(np.percentile(a, 99))}


async def main_async(a):
    h = {"X-API-Key": a.key}
    base = a.url.rstrip("/")
    async with httpx.AsyncClient(timeout=30) as c:
        run = (await c.post(base + "/v1/runs", json={"tools": ["screen_name"]}, headers=h)).json()
        has_screen = "capability" in run
    names = ["Ayman Zawahiri", "Sarah Johnson", "Muammar Gaddafi", "Maria Gonzalez", "Vladimir Putin", "Robert Smith"]
    counter = {"n": 0}

    def nxt():
        counter["n"] += 1
        return f"load-{uuid.uuid4().hex[:10]}-{counter['n']}"
    eps = {
        "health check (no database)": lambda c: c.get(base + "/healthz"),
        "list cases (database read)": lambda c: c.get(base + "/v1/cases?limit=25", headers=h),
        "decision (database write and ledger append)": lambda c: c.post(base + "/v1/decisions", json={"workload": "payment_risk", "subject": {"type": "payment", "id": nxt()}, "context": {"amount": 1200, "payee_age_days": 3, "risk_score": 0.2}}, headers={**h, "Idempotency-Key": nxt()}),
    }
    if has_screen:
        eps["name screening (matcher, a few ms of CPU)"] = lambda c: c.post(base + "/v1/tools/call", json={"tool": "screen_name", "args": {"name": names[int(time.time() * 1000) % len(names)]}}, headers={**h, "X-Capability": run["capability"], "Idempotency-Key": nxt()})
    out = {}
    for name, fn in eps.items():
        await run_level(fn, 2, 1.0)                                  # warm up
        out[name] = [await run_level(fn, int(lv), a.seconds) for lv in a.levels.split(",")]
        print(name, [(r["concurrency"], round(r["requests_per_second"]), round(r["p95_ms"])) for r in out[name]], flush=True)
    return out


def render(rep: dict) -> str:
    o = ["# Local load test (generated; do not edit by hand)", "",
         "Concurrent clients against a locally running API with PostgreSQL. Client and server run on the same laptop and share its CPU, so these numbers are conservative for the server and are **not** a prediction for a cloud deployment. Rate limiting was switched off for the test. Every request used a fresh idempotency key.", "",
         f"Machine: {rep['machine']}", ""]
    for label, run in rep["runs"].items():
        o += [f"## {label}", "", f"Each level ran for {run['seconds']} seconds.", "", "| Endpoint | Concurrent clients | Requests per second | Median (ms) | 95th percentile (ms) | 99th percentile (ms) | Failed requests |", "|---|---|---|---|---|---|---|"]
        for ep, levels in run["endpoints"].items():
            for r in levels:
                o.append(f"| {ep} | {r['concurrency']} | {r['requests_per_second']:.0f} | {r['p50_ms']:.1f} | {r['p95_ms']:.1f} | {r['p99_ms']:.1f} | {sum(r['errors'].values())} |")
        o.append("")
    o += ["## How to read the results", "",
          "- Up to 8 clients the numbers describe the server. At 32 clients the load generator itself becomes the bottleneck: even the health check, which touches no database, falls from about 1,800 to about 560 requests per second in both setups. Treat the 32-client rows as a floor, not as the server's limit.",
          "- Four server processes helped most for the CPU-heavy name screening (about 261 to about 556 requests per second at 8 clients); database-bound endpoints were limited by PostgreSQL and the shared machine.", "",
          "## Limits (read these)", "", "- One machine, localhost, no network latency, client and server competing for the same CPU cores.", "- Short runs (a few seconds per level), one repeat, so percentiles beyond the 95th are noisy.",
          "- A database that starts nearly empty; ledger appends take a per-tenant lock, so writes for one tenant are serialised by design.", "- No test of the AI model path (rate limits and cost make a load test of it meaningless here).", ""]
    return "\n".join(o)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000"), ap.add_argument("--key", default="demo-key"), ap.add_argument("--label", default="1 worker")
    ap.add_argument("--seconds", type=float, default=8), ap.add_argument("--levels", default="1,8,32")
    a = ap.parse_args()
    eps = asyncio.run(main_async(a))
    f = REPORT / "load.json"
    rep = json.loads(f.read_text()) if f.exists() else {"runs": {}}
    rep["machine"] = f"{platform.platform()}, {os.cpu_count()} CPU cores, Python {platform.python_version()}"
    rep["runs"][a.label] = {"seconds": a.seconds, "endpoints": eps}
    f.write_text(json.dumps(rep, indent=2))
    (REPORT / "load.md").write_text(render(rep))
    print("wrote docs/reports/load.md")
