"""Turn a transcript, chat log or email thread into structured commitments, then validate them in full."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List

from .llm import TokenFactoryClient

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["commitments", "offers", "customer_actions", "summary"],
    "properties": {
        "summary": {"type": "string", "description": "One sentence: current status of the case in the company's own words."},
        "commitments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["who", "action", "by_date", "quote", "confidence"],
            "properties": {
                "who": {"type": "string", "description": "Name and role of the company representative who made the commitment, or 'representative'."},
                "action": {"type": "string", "description": "What the company committed to do, in plain words."},
                "by_date": {"type": "string", "description": "YYYY-MM-DD the company said it would be done by, resolved against the conversation date; empty string if no date was given."},
                "quote": {"type": "string", "description": "The exact words used for the commitment, verbatim from the source."},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            }}},
        "offers": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["quote", "kind"],
            "properties": {"quote": {"type": "string", "description": "Exact words of any settlement, credit, partial refund or fee offer."},
                           "kind": {"type": "string", "enum": ["credit", "partial_refund", "replacement", "fee_waiver", "other"]}}}},
        "customer_actions": {"type": "array", "items": {"type": "string"},
                             "description": "Things the customer was told they must do (send a form, confirm details)."},
    },
}

SYSTEM = (
    "You read customer-service conversations (call transcripts, chat logs, email threads) and extract exactly what the company "
    "committed to do, quoting the representative verbatim. Only record a commitment when the company states it will do something. "
    "Never invent dates: convert relative phrases ('five business days', 'by Friday') to YYYY-MM-DD using the conversation date given, "
    "and use an empty string when no date can be determined. Offers of credits or partial amounts are offers, not commitments. "
    "Answer with a JSON object only."
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(result: Any) -> List[str]:
    """Fail closed: the object must match SCHEMA exactly (no extra keys, right types, enum values, real dates)."""
    problems: List[str] = []
    if not isinstance(result, dict):
        return ["result is not an object"]
    for k in result:
        if k not in SCHEMA["properties"]:
            problems.append(f"unexpected field {k}")
    for k in SCHEMA["required"]:
        if k not in result:
            problems.append(f"missing {k}")
    if not isinstance(result.get("summary", ""), str):
        problems.append("summary must be a string")
    for i, c in enumerate(result.get("commitments") or []):
        if not isinstance(c, dict):
            problems.append(f"commitment {i} is not an object"); continue
        for k in c:
            if k not in SCHEMA["properties"]["commitments"]["items"]["properties"]:
                problems.append(f"commitment {i}: unexpected field {k}")
        for k in ("who", "action", "by_date", "quote", "confidence"):
            if not isinstance(c.get(k), str):
                problems.append(f"commitment {i}: {k} must be a string")
        if c.get("confidence") not in ("high", "medium", "low"):
            problems.append(f"commitment {i}: bad confidence")
        bd = c.get("by_date")
        if isinstance(bd, str) and bd:
            if not DATE_RE.match(bd):
                problems.append(f"commitment {i}: by_date not YYYY-MM-DD")
            else:
                try:
                    datetime.strptime(bd, "%Y-%m-%d")
                except ValueError:
                    problems.append(f"commitment {i}: by_date is not a real date")
        if isinstance(c.get("quote"), str) and not c["quote"].strip():
            problems.append(f"commitment {i}: quote is empty")
    for i, o in enumerate(result.get("offers") or []):
        if not isinstance(o, dict) or not isinstance(o.get("quote"), str) or o.get("kind") not in ("credit", "partial_refund", "replacement", "fee_waiver", "other"):
            problems.append(f"offer {i} malformed")
    if not all(isinstance(a, str) for a in result.get("customer_actions") or []):
        problems.append("customer_actions must be strings")
    return problems


def quotes_present(result: Dict[str, Any], source: str) -> List[int]:
    """Indexes of commitments whose quote does not appear in the source text (guards against invented quotes)."""
    norm = " ".join(source.split()).lower()
    bad = []
    for i, c in enumerate(result.get("commitments") or []):
        q = " ".join(c.get("quote", "").split()).lower().strip('"\'')
        if q and q not in norm:
            bad.append(i)
    return bad


def extract(client: TokenFactoryClient, source_text: str, conversation_date: str, company: str) -> Dict[str, Any]:
    """Run the model, validate the result in full, and verify every quote against the source. Raises ValueError on any problem."""
    date.fromisoformat(conversation_date)
    user = (f"Company: {company}\nConversation date: {conversation_date}\n\nSource:\n\"\"\"\n{source_text.strip()}\n\"\"\"\n\n"
            "Extract the commitments, offers and customer actions as JSON.")
    result = client.chat_json(SYSTEM, user, SCHEMA)
    problems = validate(result)
    if problems:
        raise ValueError("model output rejected: " + "; ".join(problems))
    missing = quotes_present(result, source_text)
    if missing:
        raise ValueError("model output rejected: quote not found in source for commitment(s) " + ", ".join(map(str, missing)))
    return result
