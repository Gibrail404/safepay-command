"""Checks which LLM providers work with the keys in .env and whether they return JSON that matches a schema.
It prints status codes, model names, latency and token counts. It NEVER prints a key, a header or a request URL with a key.
Usage:  python scripts/check_llm_providers.py          (reads GEMINI_API_KEY and OLLAMA_API_KEY from .env or the environment)"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
OLLAMA = "https://ollama.com"
CANDIDATES = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
SCHEMA = {"type": "object", "properties": {"question": {"type": "string"}, "claims": {"type": "array", "items": {"type": "string"}}, "done": {"type": "boolean"}}, "required": ["question", "claims", "done"]}
PROMPT = "A customer is about to send AED 4,800 to a payee seen for the first time today. Write ONE short follow-up question to ask them, list any claims they have made so far (none yet), and say whether you are done."
SECRETS: list[str] = []


def load_env() -> None:
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    SECRETS.extend(v for k in ("GEMINI_API_KEY", "OLLAMA_API_KEY") if (v := os.environ.get(k)))


def clean(text: str) -> str:
    for s in SECRETS:
        text = text.replace(s, "***")
    return text[:300].replace("\n", " ")


def valid(obj) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("question"), str) and isinstance(obj.get("claims"), list) and isinstance(obj.get("done"), bool)


def check_gemini() -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY: not set, skipped"); return
    h = {"x-goog-api-key": key, "Content-Type": "application/json"}
    r = httpx.get(f"{GEMINI}/models", params={"pageSize": 200}, headers=h, timeout=30)
    print(f"Gemini model list: HTTP {r.status_code}")
    if r.status_code != 200:
        print("  error:", clean(r.text)); return
    models = {m["name"].split("/")[-1]: m for m in r.json().get("models", [])}
    gen = sorted(n for n, m in models.items() if "generateContent" in m.get("supportedGenerationMethods", []))
    print(f"  {len(models)} models visible, {len(gen)} support generateContent")
    print("  candidates visible to this key:", [c for c in CANDIDATES if c in models] or "none of the candidates")
    for name in [c for c in CANDIDATES if c in models]:
        body = {"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0}}
        t = time.perf_counter()
        try:
            r = httpx.post(f"{GEMINI}/models/{name}:generateContent", headers=h, json=body, timeout=60)
        except httpx.HTTPError as e:
            print(f"  {name}: network error {type(e).__name__}"); continue
        ms = (time.perf_counter() - t) * 1000
        if r.status_code != 200:
            print(f"  {name}: HTTP {r.status_code} in {ms:.0f} ms: {clean(r.text)}"); continue
        j = r.json()
        try:
            out = json.loads(j["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            out = None
        u = j.get("usageMetadata", {})
        print(f"  {name}: HTTP 200 in {ms:.0f} ms, schema-valid JSON: {valid(out)}, tokens in/out: {u.get('promptTokenCount')}/{u.get('candidatesTokenCount')}")


def check_ollama() -> None:
    key = os.environ.get("OLLAMA_API_KEY")
    if not key:
        print("OLLAMA_API_KEY: not set, skipped"); return
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = httpx.get(f"{OLLAMA}/api/tags", headers=h, timeout=30)
    print(f"Ollama Cloud model list: HTTP {r.status_code}")
    if r.status_code != 200:
        print("  error:", clean(r.text)); return
    names = [m.get("name") for m in r.json().get("models", [])]
    print(f"  {len(names)} models; first 12: {names[:12]}")
    for name in [n for n in ("gemma4:31b", "nemotron-3-nano:30b", "deepseek-v4.1-flash") if n in names][:3]:
        body = {"model": name, "messages": [{"role": "user", "content": PROMPT}], "stream": False, "format": SCHEMA, "options": {"temperature": 0}}
        t = time.perf_counter()
        r = httpx.post(f"{OLLAMA}/api/chat", headers=h, json=body, timeout=120)
        ms = (time.perf_counter() - t) * 1000
        if r.status_code != 200:
            print(f"  {name}: HTTP {r.status_code} in {ms:.0f} ms: {clean(r.text)}"); continue
        try:
            out = json.loads(r.json()["message"]["content"])
        except Exception:
            out = None
        print(f"  {name}: HTTP 200 in {ms:.0f} ms, schema-valid JSON: {valid(out)} (cloud has no constrained decoding, so this is the model following instructions)")


if __name__ == "__main__":
    load_env()
    if not SECRETS:
        print("No keys found. Put GEMINI_API_KEY=... (and optionally OLLAMA_API_KEY=...) in .env, then rerun."); sys.exit(0)
    check_gemini()
    check_ollama()
