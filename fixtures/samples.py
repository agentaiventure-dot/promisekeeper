"""Shared sample transcripts: the single source of truth for both the test suite and the demo-mode UI.

Each sample's text contains one of the fixture reference markers that fake_tokenfactory.py's scenarios.json
matches on (EXAMPLE-CLAIM-0001, EXAMPLE-REFUND-0002, SUPERVISOR-CALL). Demo mode refuses to extract any text
that does not contain one of DEMO_MARKERS, so a public visitor never gets a fabricated result for arbitrary text.
"""
from __future__ import annotations

from typing import Any, Dict, List

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

# One "Load sample" button per entry. company/customer/reference/what_is_owed let the UI create a matching
# case in one click; kind/conversation_date/text are then pasted into the source form.
SAMPLES: List[Dict[str, Any]] = [
    {
        "id": "call",
        "label": "Insurance claim: reimbursement promised",
        "company": "Example Home Insurance",
        "customer": "Alex Example",
        "reference": "EXAMPLE-CLAIM-0001",
        "what_is_owed": "4,200 dollars",
        "kind": "call",
        "conversation_date": "2026-09-02",
        "text": CALL,
    },
    {
        "id": "offer",
        "label": "Broadband refund: goodwill credit offered instead",
        "company": "Example Broadband",
        "customer": "Jordan Sample",
        "reference": "EXAMPLE-REFUND-0002",
        "what_is_owed": "140 dollar refund",
        "kind": "chat",
        "conversation_date": "2026-09-02",
        "text": OFFER,
    },
    {
        "id": "supervisor",
        "label": "Supervisor callback: promise broken, new date given",
        "company": "Example Home Insurance",
        "customer": "Alex Example",
        "reference": "EXAMPLE-CLAIM-0001",
        "what_is_owed": "4,200 dollars",
        "kind": "call",
        "conversation_date": "2026-09-15",
        "text": SUPERVISOR,
    },
]

# Substrings that identify text as one of the known demo samples (matches fixtures/scenarios.json).
DEMO_MARKERS = ("EXAMPLE-CLAIM-0001", "EXAMPLE-REFUND-0002", "SUPERVISOR-CALL")
