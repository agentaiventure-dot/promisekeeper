"""Loopback fake of the Token Factory chat completions endpoint (and a Tavily /search) for offline runs and tests.

Scenario selection: the first fixture whose `match` string appears in the user message wins.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))


def load_scenarios() -> List[Dict[str, Any]]:
    with open(os.path.join(HERE, "scenarios.json"), "r", encoding="utf-8") as f:
        return json.load(f)


class FakeServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        scenarios = load_scenarios()
        self.requests: List[Dict[str, Any]] = []
        server = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _send(self, code: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

            def do_POST(self) -> None:
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    return self._send(401, {"error": "unauthorized"})
                n = int(self.headers.get("Content-Length", "0")); req = json.loads(self.rfile.read(n) or b"{}")
                server.requests.append({"path": self.path, "body": req})
                if self.path == "/v1/chat/completions":
                    user = next((m["content"] for m in req.get("messages", []) if m.get("role") == "user"), "")
                    for sc in scenarios:
                        if sc["match"] in user:
                            content = json.dumps(sc["extraction"]) if sc.get("valid", True) else sc["raw"]
                            return self._send(200, {"id": "cmpl_fake", "object": "chat.completion", "model": req.get("model"),
                                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                                                    "usage": {"prompt_tokens": 512, "completion_tokens": 128, "total_tokens": 640}})
                    return self._send(200, {"choices": [{"message": {"role": "assistant", "content": json.dumps({"summary": "No commitments found.", "commitments": [], "offers": [], "customer_actions": []})}}], "usage": {}})
                if self.path == "/search":
                    return self._send(200, {"results": [
                        {"title": "How to make a complaint", "url": "https://www.example.com/complaints", "content": "Formal complaints process and reference numbers."},
                        {"title": "Financial Ombudsman Service", "url": "https://www.example.org/ombudsman", "content": "Escalate after eight weeks or a final response."}]})
                self._send(404, {"error": "not found"})

            def do_GET(self) -> None:
                if self.path == "/v1/models":
                    return self._send(200, {"data": [{"id": "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1"}]})
                self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer((host, port), H)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        h, p = self.httpd.server_address[:2]
        return f"http://{h}:{p}"

    def start(self) -> "FakeServer":
        self.thread.start(); return self

    def stop(self) -> None:
        self.httpd.shutdown(); self.httpd.server_close()


if __name__ == "__main__":
    s = FakeServer(port=int(os.environ.get("PORT", "8799"))).start()
    print(f"fake Token Factory + Tavily at {s.base_url}; Ctrl-C to stop")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.stop()
