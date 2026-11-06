"""Checks a running SafePay API (local container or deployed) and prints PASS / FAIL for each thing that matters. Exit code 0 only if everything required passes.
Usage: python scripts/check_deploy.py --url https://your-space.hf.space --key YOUR_KEY [--origin https://your-console.vercel.app] [--try-interception]
The key is only sent in the X-API-Key header to the URL you give; it is never printed."""
import argparse, sys, time
import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--key", required=True)
    ap.add_argument("--origin", help="the console's address, to check that the browser is allowed to call the API (CORS)")
    ap.add_argument("--try-interception", action="store_true", help="start one simulated payment (needs an analyst or admin key and the demo assets)")
    a = ap.parse_args()
    base, h = a.url.rstrip("/"), {"X-API-Key": a.key}
    results: list[tuple[str, bool, str, bool]] = []                 # name, passed, detail, required
    c = httpx.Client(timeout=90)

    def check(name, fn, required=True):
        t = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {str(e)[:120]}"
        results.append((name, bool(ok), f"{detail} ({(time.perf_counter() - t) * 1000:.0f} ms)", required))

    def up():
        r = c.get(base + "/healthz")
        return r.status_code == 200 and r.json().get("ok") is True, f"HTTP {r.status_code}"

    who: dict = {}

    def whoami():
        r = c.get(base + "/v1/whoami", headers=h)
        who.update(r.json() if r.status_code == 200 else {})
        return r.status_code == 200, f"HTTP {r.status_code}, role {who.get('role')}, tenant {who.get('tenant')}"

    def wrong_key():
        r = c.get(base + "/v1/whoami", headers={"X-API-Key": "definitely-wrong"})
        return r.status_code == 401, f"HTTP {r.status_code}"

    def chain():
        j = c.get(base + "/v1/audit/verify", headers=h).json()
        return j.get("ok") is True, f"{j.get('checked')} records checked"

    def reports():
        rows = c.get(base + "/v1/reports", headers=h).json()
        n = sum(1 for x in rows if x["available"])
        return n > 0, f"{n} of {len(rows)} available"

    tools: list[str] = []

    def get_tools():
        tools[:] = [t["name"] for t in c.get(base + "/v1/tools", headers=h).json()]
        return "screen_name" in tools, f"tools: {', '.join(tools) or 'none'}"

    def risk_loaded():
        return "score_payment_risk" in tools, "present" if "score_payment_risk" in tools else "absent: build the image with the demo assets"

    def simulation():
        r = c.post(base + "/v1/simulations", headers=h, json={"warn_from": 0.8, "hold_from": 1.6, "n": 5000})
        return r.status_code == 200 and r.json().get("provenance") == "simulated", f"HTTP {r.status_code}"

    def cors():
        r = c.options(base + "/v1/cases/stats", headers={"Origin": a.origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-api-key"})
        got = r.headers.get("access-control-allow-origin")
        return got == a.origin, f"allow-origin: {got}"

    def interception():
        r = c.post(base + "/v1/interceptions", headers=h, json={"kind": "scam_uncoached", "seed": 1, "mode": "auto"})
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:120]}"
        j = r.json()
        return j["state"] == "decided", f"decision {j['result']['decision']['outcome']}"

    check("server is up (may take a minute if the instance was asleep)", up)
    check("the key is accepted", whoami)
    check("a wrong key is refused", wrong_key)
    check("the audit chain verifies", chain)
    check("reports are served", reports)
    check("the name-screening tool is loaded", get_tools)
    check("the risk model is loaded (needed for the Interception page)", risk_loaded, required=False)
    check("simulation endpoint answers", simulation, required=False)
    if a.origin:
        check("the console's address is allowed by CORS", cors)
    if a.try_interception:
        check("one simulated payment runs end to end", interception, required=False)
    c.close()
    width = max(len(n) for n, *_ in results)
    for name, ok, detail, required in results:
        print(f"{'PASS' if ok else ('FAIL' if required else 'WARN')}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _, req in results if not ok and req]
    print("\nALL REQUIRED CHECKS PASSED" if not failed else f"\n{len(failed)} REQUIRED CHECK(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
