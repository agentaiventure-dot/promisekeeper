import json, os, sys, tempfile, threading, urllib.request, urllib.error
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "fixtures"))

from fake_tokenfactory import FakeServer  # noqa: E402
from promisekeeper import ledger  # noqa: E402
from promisekeeper.extract import extract, validate  # noqa: E402
from promisekeeper.llm import LLMError, TokenFactoryClient, parse_json_object  # noqa: E402
from promisekeeper.research import ResearchError, TavilyClient, escalation_research  # noqa: E402
from promisekeeper.web import serve  # noqa: E402

GOOD_RESULT = {"summary": "The claim is approved and is in payment processing.", "commitments": [], "offers": [], "customer_actions": []}

CALL = """Conversation about claim EXAMPLE-CLAIM-0001.
Agent: Hello, I'm an AI assistant calling on behalf of Alex Example about claim EXAMPLE-CLAIM-0001.
Representative (Maria, Claims): The claim is approved and is in payment processing.
Agent: When can Alex expect the payment?
Representative: You should see the payment within five business days."""
OFFER = """Chat about refund EXAMPLE-REFUND-0002.
Priya (Billing): The refund request was reviewed and a goodwill credit is offered instead.
Priya: We can offer a goodwill credit of 60 dollars to the account today instead of the refund. Please confirm in writing whether you accept the credit."""
SUPERVISOR = """SUPERVISOR-CALL for claim EXAMPLE-CLAIM-0001.
Daniel (Claims supervisor): The payment was held by a system flag and has now been released for processing. It will be in the account by Friday the 18th, I have escalated it myself."""


@pytest.fixture(scope="module")
def fake():
    s = FakeServer().start(); yield s; s.stop()


@pytest.fixture
def llm(fake):
    return TokenFactoryClient("test-key", fake.base_url, allow_local_fake=True)


def test_key_only_goes_to_official_origin_or_loopback_fake(fake):
    assert TokenFactoryClient("k").origin == "https://api.tokenfactory.nebius.com"
    assert TokenFactoryClient("k", "https://api.tokenfactory.nebius.com/v1/").origin == "https://api.tokenfactory.nebius.com"
    for bad in ("http://api.tokenfactory.nebius.com", "https://api.tokenfactory.nebius.com.evil.example", "https://evil.example", fake.base_url):
        with pytest.raises(LLMError):
            TokenFactoryClient("k", bad)
    with pytest.raises(LLMError):
        TokenFactoryClient("")
    with pytest.raises(ResearchError):
        TavilyClient("k", "https://api.tavily.com.evil.example")


def test_extraction_records_dated_quoted_commitment(llm, fake):
    r = extract(llm, CALL, "2026-09-02", "Example Home Insurance")
    assert r["commitments"][0]["by_date"] == "2026-09-09"
    assert r["commitments"][0]["quote"] == "You should see the payment within five business days."
    sent = fake.requests[-1]["body"]
    assert sent["model"] == TokenFactoryClient("k").model and sent["response_format"]["type"] == "json_schema"
    assert "2026-09-02" in sent["messages"][1]["content"]


def test_offers_are_not_commitments(llm):
    r = extract(llm, OFFER, "2026-09-02", "Example Broadband")
    assert r["commitments"] == [] and r["offers"][0]["kind"] == "credit" and r["customer_actions"]


def test_explicit_day_counts_are_computed_in_code():
    from promisekeeper.extract import date_from_quote
    assert date_from_quote("You should see the payment within five business days.", "2026-09-02") == "2026-09-09"   # Wed + 5 business days
    assert date_from_quote("within 10 days", "2026-09-02") == "2026-09-12"
    assert date_from_quote("by Friday the 18th", "2026-09-15") is None


def test_one_retry_with_feedback_then_success():
    class Stub:
        model = "stub"; last_usage = {}
        def __init__(self): self.calls = []
        def chat_json(self, system, user, schema):
            self.calls.append(user)
            if len(self.calls) == 1:
                return {**GOOD_RESULT, "commitments": [{"who": "Maria", "action": "pay", "by_date": "2026-09-09", "quote": "not in the source", "confidence": "high"}]}
            return {**GOOD_RESULT, "commitments": [{"who": "Maria", "action": "pay", "by_date": "2026-09-09", "quote": "You should see the payment within five business days.", "confidence": "high"}]}
    st = Stub()
    r = extract(st, CALL, "2026-09-02", "Example Home Insurance")
    assert len(st.calls) == 2 and "rejected" in st.calls[1] and r["commitments"][0]["by_date"] == "2026-09-09"


def test_invented_quote_is_rejected(llm):
    with pytest.raises(ValueError, match="quote not found"):
        extract(llm, "INVENTED-QUOTE: the rep said nothing specific about a date.", "2026-09-02", "X")


def test_malformed_model_output_is_rejected_not_trusted(llm):
    with pytest.raises(ValueError, match="rejected"):
        extract(llm, "MALFORMED-OUTPUT please", "2026-09-02", "X")
    good = {"summary": "s", "commitments": [], "offers": [], "customer_actions": []}
    assert validate(good) == []
    assert validate({**good, "extra": 1}) == ["unexpected field extra"]
    assert "commitment 0: by_date not YYYY-MM-DD" in validate({**good, "commitments": [{"who": "a", "action": "b", "by_date": "soon", "quote": "q", "confidence": "high"}]})
    assert "commitment 0: by_date is not a real date" in validate({**good, "commitments": [{"who": "a", "action": "b", "by_date": "2026-02-30", "quote": "q", "confidence": "high"}]})
    assert "commitment 0: bad confidence" in validate({**good, "commitments": [{"who": "a", "action": "b", "by_date": "", "quote": "q", "confidence": "sure"}]})
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure: {"a": 1} done') == {"a": 1}


def test_ledger_marks_broken_after_grace_and_recommends_next_step(llm):
    case = ledger.new_case("Example Home Insurance", "Alex Example", "EXAMPLE-CLAIM-0001", "4,200 dollars")
    ledger.add_source(case, "call", "2026-09-02", CALL, extract(llm, CALL, "2026-09-02", case["company"]), llm.model, llm.last_usage)
    ledger.refresh_status(case, date(2026, 9, 10))
    assert case["status"] == "waiting_on_company" and case["commitments"][0]["status"] == "pending"
    ledger.refresh_status(case, date(2026, 9, 11))
    assert case["commitments"][0]["status"] == "broken" and case["status"] == "promise_broken"
    assert "supervisor" in ledger.next_step(case)
    ledger.add_source(case, "call", "2026-09-15", SUPERVISOR, extract(llm, SUPERVISOR, "2026-09-15", case["company"]), llm.model)
    assert [c["status"] for c in case["commitments"]] == ["broken", "pending"]
    ledger.refresh_status(case, date(2026, 9, 16))
    assert case["status"] == "waiting_on_company"
    pack = ledger.evidence_pack(case)
    assert "[broken]" in pack and "Friday the 18th" in pack and "Next step:" in pack
    ledger.resolve(case)
    assert case["commitments"][1]["status"] == "kept" and case["status"] == "resolved"


def test_overdue_promise_is_broken_not_superseded_by_a_newer_one(llm):
    case = ledger.new_case("Example Home Insurance", "Alex Example", "EXAMPLE-CLAIM-0001", "4,200 dollars")
    ledger.add_source(case, "call", "2026-09-02", CALL, extract(llm, CALL, "2026-09-02", case["company"]), llm.model)
    case["commitments"][0]["by_date"] = "2026-08-20"
    ledger.add_source(case, "call", "2026-09-15", SUPERVISOR, extract(llm, SUPERVISOR, "2026-09-15", case["company"]), llm.model)
    assert [c["status"] for c in case["commitments"]] == ["broken", "pending"]
    case2 = ledger.new_case("X", "Y", "R", "owed")
    ledger.add_source(case2, "call", "2026-09-02", CALL, extract(llm, CALL, "2026-09-02", "X"), llm.model)
    ledger.add_source(case2, "call", "2026-09-03", SUPERVISOR, extract(llm, SUPERVISOR, "2026-09-03", "X"), llm.model)
    assert [c["status"] for c in case2["commitments"]] == ["superseded", "pending"]


def test_tavily_research_is_a_runtime_call(fake):
    t = TavilyClient("tv", fake.base_url, allow_local_fake=True)
    r = escalation_research(t, "Example Home Insurance", "insurance claim")
    assert r["results"] and all(x["url"].startswith("https://") for x in r["results"])
    assert fake.requests[-1]["path"] == "/search" and "Example Home Insurance" in fake.requests[-1]["body"]["query"]


def test_web_api_end_to_end(fake):
    with tempfile.TemporaryDirectory() as d:
        llm = TokenFactoryClient("k", fake.base_url, allow_local_fake=True)
        tv = TavilyClient("k", fake.base_url, allow_local_fake=True)
        httpd = serve(d, "127.0.0.1", 0, llm, tv)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(path, body, hdr=True):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", **({"X-PromiseKeeper": "ui"} if hdr else {})})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            assert post("/api/cases", {"company": "X"}, hdr=False)[0] == 403
            code, c = post("/api/cases", {"company": "Example Broadband", "customer": "Jordan Sample", "reference": "EXAMPLE-REFUND-0002", "what_is_owed": "140 dollar refund"})
            assert code == 200
            code, r = post(f"/api/cases/{c['id']}/sources", {"kind": "chat", "conversation_date": "2026-09-02", "text": OFFER})
            assert code == 200 and r["case"]["status"] == "decision_needed" and r["case"]["offers"][0]["decision"] is None
            code, r = post(f"/api/cases/{c['id']}/offers/0", {"decision": "decline"})
            assert code == 200 and r["offers"][0]["decision"] == "decline"
            code, r = post(f"/api/cases/{c['id']}/sources", {"kind": "chat", "conversation_date": "2026-09-02", "text": "MALFORMED-OUTPUT"})
            assert code == 422 and "rejected" in r["error"]
            code, r = post(f"/api/cases/{c['id']}/research", {})
            assert code == 200 and r["research"]["results"]
            page = urllib.request.urlopen(base + "/").read().decode()
            assert "PromiseKeeper" in page and "onclick=\"sel=" not in page
            ev = urllib.request.urlopen(base + f"/api/evidence/{c['id']}").read().decode()
            assert "goodwill credit" in ev and "Where to escalate" in ev
            assert json.loads(urllib.request.urlopen(base + "/healthz").read())["ok"] is True
        finally:
            httpd.shutdown(); httpd.server_close()
