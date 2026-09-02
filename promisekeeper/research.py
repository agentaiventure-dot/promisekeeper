"""Escalation research: one runtime Tavily search for the company's complaints channel and the relevant regulator."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List
from urllib.parse import urlparse

OFFICIAL_ORIGIN = "https://api.tavily.com"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class ResearchError(RuntimeError):
    pass


class TavilyClient:
    def __init__(self, api_key: str, base_url: str = OFFICIAL_ORIGIN, allow_local_fake: bool = False, timeout: int = 30):
        if not api_key:
            raise ResearchError("TAVILY_API_KEY is not set")
        p = urlparse(base_url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin != OFFICIAL_ORIGIN and not (allow_local_fake and p.scheme == "http" and p.hostname in LOOPBACK):
            raise ResearchError(f"refusing to send the Tavily key to {origin!r}")
        self.origin, self.api_key, self.timeout = origin, api_key, timeout

    @classmethod
    def from_env(cls) -> "TavilyClient":
        return cls(os.environ.get("TAVILY_API_KEY", ""), os.environ.get("TAVILY_BASE_URL", OFFICIAL_ORIGIN),
                   allow_local_fake=os.environ.get("PROMISEKEEPER_ALLOW_LOCAL_FAKE") == "1")

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        body = {"query": query, "max_results": max_results, "search_depth": "basic", "include_answer": False}
        req = urllib.request.Request(self.origin + "/search", data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ResearchError(f"Tavily search failed: HTTP {e.code}") from None
        except urllib.error.URLError as e:
            raise ResearchError(f"Tavily unreachable: {e.reason}") from None
        results = []
        for r in out.get("results", [])[:max_results]:
            if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"].startswith("https://"):
                results.append({"title": str(r.get("title", ""))[:200], "url": r["url"], "snippet": str(r.get("content", ""))[:300]})
        return results


def escalation_research(client: TavilyClient, company: str, case_type_hint: str = "") -> Dict[str, Any]:
    q = f"{company} formal complaint process escalate ombudsman regulator {case_type_hint}".strip()
    return {"query": q, "results": client.search(q)}
