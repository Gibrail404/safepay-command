"""Providers behind one interface. A provider returns raw text and usage, or raises ProviderError with a reason the gateway can act on."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Protocol
import httpx


class ProviderError(Exception):
    def __init__(self, reason: str, retryable: bool = True, status: int | None = None):
        super().__init__(reason)
        self.reason, self.retryable, self.status = reason, retryable, status


@dataclass
class RawReply:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, schema: dict | None, max_tokens: int, timeout_s: float) -> RawReply: ...


def _check(r: httpx.Response) -> None:
    if r.status_code == 429:
        raise ProviderError("rate limited (429)", True, 429)
    if r.status_code >= 500:
        raise ProviderError(f"provider unavailable ({r.status_code})", True, r.status_code)
    if r.status_code in (401, 403):
        raise ProviderError(f"not authorised ({r.status_code})", False, r.status_code)
    if r.status_code >= 400:
        raise ProviderError(f"request rejected ({r.status_code})", False, r.status_code)


class OllamaCloudProvider:
    """Ollama Cloud ignores a JSON schema, so the schema is described in the prompt and the reply is validated by the gateway."""
    name = "ollama_cloud"

    def __init__(self, api_key: str, model: str, base_url: str = "https://ollama.com"):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def complete(self, system, user, schema, max_tokens, timeout_s) -> RawReply:
        body = {"model": self.model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": 0, "num_predict": max_tokens}}
        try:
            r = httpx.post(f"{self.base_url}/api/chat", headers={"Authorization": f"Bearer {self.api_key}"}, json=body, timeout=timeout_s)
        except httpx.TimeoutException as e:
            raise ProviderError("timeout") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"network error ({type(e).__name__})") from e
        _check(r)
        j = r.json()
        return RawReply(j.get("message", {}).get("content", ""), j.get("prompt_eval_count"), j.get("eval_count"))


class GeminiProvider:
    """Gemini supports a response schema natively, so replies are valid JSON by construction (the gateway still validates)."""
    name = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta"):
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")

    def complete(self, system, user, schema, max_tokens, timeout_s) -> RawReply:
        cfg = {"temperature": 0, "maxOutputTokens": max_tokens}
        if schema:
            cfg.update({"responseMimeType": "application/json", "responseSchema": schema})
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": cfg}
        try:
            r = httpx.post(f"{self.base_url}/models/{self.model}:generateContent", headers={"x-goog-api-key": self.api_key}, json=body, timeout=timeout_s)
        except httpx.TimeoutException as e:
            raise ProviderError("timeout") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"network error ({type(e).__name__})") from e
        _check(r)
        j = r.json()
        try:
            text = j["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise ProviderError("empty or blocked reply", True)
        u = j.get("usageMetadata", {})
        return RawReply(text, u.get("promptTokenCount"), u.get("candidatesTokenCount"))


@dataclass
class FakeProvider:
    """Scripted provider for tests: each call pops the next item. A str is a reply; an Exception is raised; a callable receives the prompt."""
    script: list
    name: str = "fake"
    model: str = "fake-1"
    seen: list = field(default_factory=list)
    delay_s: float = 0.0

    def complete(self, system, user, schema, max_tokens, timeout_s) -> RawReply:
        self.seen.append({"system": system, "user": user, "schema": schema})
        if self.delay_s:
            time.sleep(self.delay_s)
        item = self.script.pop(0) if self.script else ProviderError("script exhausted")
        if isinstance(item, Exception):
            raise item
        return RawReply(item(user) if callable(item) else item, 10, 10)
