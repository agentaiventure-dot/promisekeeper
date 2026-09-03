"""Nebius Token Factory client (OpenAI-compatible chat completions), standard library only.

The API key is only ever sent to the official origin. Tests point the client at a loopback fake.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

OFFICIAL_ORIGIN = "https://api.tokenfactory.nebius.com"
ALLOWED_ORIGINS = (OFFICIAL_ORIGIN, "https://router.huggingface.co")   # Nebius Token Factory, or the Hugging Face inference router
DEFAULT_MODEL = "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class LLMError(RuntimeError):
    pass


def check_origin(base_url: str, allow_local_fake: bool) -> str:
    p = urlparse(base_url)
    origin = f"{p.scheme}://{p.netloc}"
    if p.path not in ("", "/", "/v1", "/v1/") or p.query or p.fragment or p.username or p.password:
        raise LLMError(f"base_url must be a bare origin, got {base_url!r}")
    if origin in ALLOWED_ORIGINS:
        return origin
    if allow_local_fake and p.scheme == "http" and p.hostname in LOOPBACK:
        return origin
    raise LLMError(f"refusing to send the API key to {origin!r}; allowed: {', '.join(ALLOWED_ORIGINS)} or a loopback fake")


class TokenFactoryClient:
    def __init__(self, api_key: str, base_url: str = OFFICIAL_ORIGIN, model: str = DEFAULT_MODEL,
                 timeout: int = 120, allow_local_fake: bool = False):
        if not api_key:
            raise LLMError("NEBIUS_API_KEY is not set")
        self.api_key = api_key
        self.origin = check_origin(base_url, allow_local_fake)
        self.model = model
        self.timeout = timeout
        self.last_usage: Dict[str, Any] = {}

    @classmethod
    def from_env(cls) -> "TokenFactoryClient":
        return cls(os.environ.get("NEBIUS_API_KEY", ""), os.environ.get("NEBIUS_BASE_URL", OFFICIAL_ORIGIN),
                   os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL),
                   allow_local_fake=os.environ.get("PROMISEKEEPER_ALLOW_LOCAL_FAKE") == "1")

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(self.origin + path, data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise LLMError(f"Token Factory {path} failed: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:400]}") from None
        except urllib.error.URLError as e:
            raise LLMError(f"Token Factory unreachable at {self.origin}: {e.reason}") from None

    def chat_json(self, system: str, user: str, schema: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
        """Ask for a JSON object matching `schema`. Uses the OpenAI-style json_schema response format and
        falls back to parsing the first JSON object in the text if the endpoint ignores it."""
        body = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "extraction", "schema": schema, "strict": True}},
        }
        out = self._post("/v1/chat/completions", body)
        self.last_usage = out.get("usage") or {}
        try:
            text = out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("no completion content in response")
        return parse_json_object(text)


def parse_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            raise LLMError("model output is not JSON")
        obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict):
        raise LLMError("model output is not a JSON object")
    return obj
