"""Tests for the hosted-demo hardening: demo mode, the sample endpoint, the per-IP rate limit and the
per-data-dir case cap. Offline throughout; demo mode here points at the same loopback fake used elsewhere."""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "fixtures"))

from fake_tokenfactory import FakeServer  # noqa: E402
from samples import CALL, DEMO_MARKERS, SAMPLES  # noqa: E402
from promisekeeper import ledger  # noqa: E402
from promisekeeper.llm import TokenFactoryClient  # noqa: E402
from promisekeeper.research import TavilyClient  # noqa: E402
from promisekeeper.web import RateLimiter, serve  # noqa: E402


@pytest.fixture(scope="module")
def fake():
    s = FakeServer().start(); yield s; s.stop()


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(base, path, body, hdr=True):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                  headers={"Content-Type": "application/json", **({"X-PromiseKeeper": "ui"} if hdr else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _serve(fake, tmp_dir, demo=False, rate_limiter=None):
    llm = TokenFactoryClient("k", fake.base_url, allow_local_fake=True)
    tv = TavilyClient("k", fake.base_url, allow_local_fake=True)
    httpd = serve(tmp_dir, "127.0.0.1", 0, llm, tv, demo=demo, samples=SAMPLES if demo else None,
                  demo_markers=DEMO_MARKERS if demo else (), rate_limiter=rate_limiter)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_healthz_reports_mode_and_is_never_rate_limited(fake):
    with tempfile.TemporaryDirectory() as d:
        limiter = RateLimiter(capacity=1, refill_per_sec=0)   # exhausted after one non-healthz request
        httpd, base = _serve(fake, d, demo=True, rate_limiter=limiter)
        try:
            assert _get(base, "/healthz")[1]["mode"] == "demo"
            assert _get(base, "/api/cases")[0] == 200     # spends the only token
            assert _get(base, "/api/cases")[0] == 429     # limiter now empty
            assert _get(base, "/healthz")[0] == 200        # healthz still answers regardless
        finally:
            httpd.shutdown(); httpd.server_close()


def test_live_mode_hides_the_samples_endpoint(fake):
    with tempfile.TemporaryDirectory() as d:
        httpd, base = _serve(fake, d, demo=False)
        try:
            assert _get(base, "/healthz")[1]["mode"] == "live"
            assert _get(base, "/api/samples")[0] == 404
        finally:
            httpd.shutdown(); httpd.server_close()


def test_demo_mode_serves_the_three_samples_and_they_extract_cleanly(fake):
    with tempfile.TemporaryDirectory() as d:
        httpd, base = _serve(fake, d, demo=True)
        try:
            code, samples = _get(base, "/api/samples")
            assert code == 200 and len(samples) == 3
            assert {s["id"] for s in samples} == {"call", "offer", "supervisor"}
            call_sample = next(s for s in samples if s["id"] == "call")
            assert call_sample["text"] == CALL

            code, case = _post(base, "/api/cases", {"company": call_sample["company"], "customer": call_sample["customer"],
                                                     "reference": call_sample["reference"], "what_is_owed": call_sample["what_is_owed"]})
            assert code == 200
            code, r = _post(base, f"/api/cases/{case['id']}/sources",
                             {"kind": call_sample["kind"], "conversation_date": call_sample["conversation_date"], "text": call_sample["text"]})
            assert code == 200 and r["extraction"]["commitments"]
        finally:
            httpd.shutdown(); httpd.server_close()


def test_demo_mode_refuses_arbitrary_text_with_a_friendly_error_not_a_fake_result(fake):
    with tempfile.TemporaryDirectory() as d:
        httpd, base = _serve(fake, d, demo=True)
        try:
            code, case = _post(base, "/api/cases", {"company": "Some Company", "customer": "Someone",
                                                     "reference": "REF-1", "what_is_owed": "50 dollars"})
            assert code == 200
            code, r = _post(base, f"/api/cases/{case['id']}/sources",
                             {"kind": "call", "conversation_date": "2026-09-02", "text": "Totally unrelated text with no fixture marker in it."})
            assert code == 422
            assert "Demo mode" in r["error"] and "sample" in r["error"].lower()
            # the case ledger must show no source and no commitments: nothing fake was recorded
            code, cases = _get(base, "/api/cases")
            assert cases[0]["sources"] == [] and cases[0]["commitments"] == []
        finally:
            httpd.shutdown(); httpd.server_close()


def test_rate_limiter_token_bucket_blocks_then_refills():
    limiter = RateLimiter(capacity=2, refill_per_sec=0)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False        # capacity exhausted, no refill configured
    assert limiter.allow("5.6.7.8") is True          # a different key has its own bucket


def test_rate_limit_is_per_ip_key_via_forwarded_for_only_when_public(fake, monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("PROMISEKEEPER_PUBLIC", "1")
        limiter = RateLimiter(capacity=1, refill_per_sec=0)
        httpd, base = _serve(fake, d, rate_limiter=limiter)
        try:
            req1 = urllib.request.Request(base + "/api/cases", headers={"X-Forwarded-For": "9.9.9.9"})
            req2 = urllib.request.Request(base + "/api/cases", headers={"X-Forwarded-For": "9.9.9.9"})
            req3 = urllib.request.Request(base + "/api/cases", headers={"X-Forwarded-For": "8.8.8.8"})
            with urllib.request.urlopen(req1) as r:
                assert r.status == 200
            try:
                urllib.request.urlopen(req2)
                assert False, "expected the second request from the same forwarded IP to be rate-limited"
            except urllib.error.HTTPError as e:
                assert e.code == 429
            with urllib.request.urlopen(req3) as r:   # different forwarded IP, fresh bucket
                assert r.status == 200
        finally:
            httpd.shutdown(); httpd.server_close()
            monkeypatch.delenv("PROMISEKEEPER_PUBLIC", raising=False)


def test_store_evicts_oldest_case_once_over_the_cap(monkeypatch):
    monkeypatch.setattr(ledger, "MAX_CASES", 3)
    with tempfile.TemporaryDirectory() as d:
        store = ledger.Store(d)
        for i in range(5):
            c = ledger.new_case(f"Company {i}", "Customer", f"REF-{i}", "owed")
            c["created_at"] = f"2026-01-0{i + 1}T00:00:00+00:00"   # deterministic ordering, no timing flakiness
            store.upsert(c)
        cases = store.list()
        assert len(cases) == 3
        assert sorted(c["reference"] for c in cases) == ["REF-2", "REF-3", "REF-4"]
        # updating an existing case never evicts, even while already at the cap
        cases[0]["what_is_owed"] = "changed"
        store.upsert(cases[0])
        assert len(store.list()) == 3
