"""Cases and their commitments, persisted as one JSON file. Status is computed, never trusted from the model."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

GRACE_DAYS = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def new_case(company: str, customer: str, reference: str, what_is_owed: str) -> Dict[str, Any]:
    return {"id": new_id("case"), "created_at": now_iso(), "company": company, "customer": customer, "reference": reference,
            "what_is_owed": what_is_owed, "status": "open", "sources": [], "commitments": [], "offers": [], "customer_actions": [],
            "research": None, "closed_at": None}


def add_source(case: Dict[str, Any], kind: str, conversation_date: str, text: str, extraction: Dict[str, Any], model: str,
               usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    src = {"id": new_id("src"), "kind": kind, "conversation_date": conversation_date, "added_at": now_iso(),
           "chars": len(text), "text": text, "summary": extraction.get("summary", ""), "model": model, "usage": usage or {}}
    case["sources"].append(src)
    for c in case["commitments"]:
        if c["status"] == "pending":
            c["status"] = "superseded"
    for c in extraction.get("commitments", []):
        case["commitments"].append({"id": new_id("cmt"), "source_id": src["id"], "who": c["who"], "action": c["action"],
                                    "by_date": c["by_date"] or None, "quote": c["quote"], "confidence": c["confidence"],
                                    "recorded_at": now_iso(), "status": "pending"})
    for o in extraction.get("offers", []):
        case["offers"].append({"source_id": src["id"], "quote": o["quote"], "kind": o["kind"], "decision": None})
    for a in extraction.get("customer_actions", []):
        case["customer_actions"].append({"source_id": src["id"], "action": a, "done": False})
    return src


def refresh_status(case: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Mark commitments broken when the promised date plus grace has passed and the case is still open."""
    today = today or datetime.now(timezone.utc).date()
    if case["status"] in ("resolved", "abandoned"):
        return case
    for c in case["commitments"]:
        if c["status"] == "pending" and c.get("by_date"):
            due = date.fromisoformat(c["by_date"])
            if (today - due).days >= GRACE_DAYS:
                c["status"] = "broken"
    broken = [c for c in case["commitments"] if c["status"] == "broken"]
    pending = [c for c in case["commitments"] if c["status"] == "pending"]
    if broken and not pending:
        case["status"] = "promise_broken"
    elif pending:
        case["status"] = "waiting_on_company"
    elif any(o["decision"] is None for o in case["offers"]):
        case["status"] = "decision_needed"
    else:
        case["status"] = "open"
    return case


def resolve(case: Dict[str, Any]) -> Dict[str, Any]:
    for c in case["commitments"]:
        if c["status"] == "pending":
            c["status"] = "kept"
    case["status"] = "resolved"
    case["closed_at"] = now_iso()
    return case


def next_step(case: Dict[str, Any]) -> str:
    """Plain-language recommendation, computed from the ledger (no model call)."""
    broken = [c for c in case["commitments"] if c["status"] == "broken"]
    pending = [c for c in case["commitments"] if c["status"] == "pending"]
    if case["status"] == "resolved":
        return "Resolved. Keep the evidence pack for your records."
    if len(broken) >= 2:
        return "Two commitments broken. Send the written complaint with the evidence pack, quoting both broken promises, and ask for the complaints reference number."
    if broken:
        return f"The promise of {broken[-1]['by_date']} was not kept. Contact them again, ask for a supervisor, state the broken commitment with its date, and get a firm new date."
    if pending:
        return f"Wait until {pending[-1]['by_date'] or 'the promised date'} plus {GRACE_DAYS} days. If nothing arrives, this becomes a broken promise."
    if any(o["decision"] is None for o in case["offers"]):
        return "An offer is on the table. Decide whether to accept it or hold out for what you are owed; record the decision here."
    return "No commitment on record yet. Add the next call transcript or email."


def evidence_pack(case: Dict[str, Any]) -> str:
    lines = [f"# Evidence pack: {case['company']} case {case['reference']}", "",
             f"Customer: {case['customer']}  |  Owed: {case['what_is_owed']}  |  Status: {case['status']}", "", "## Sources", ""]
    for i, s in enumerate(case["sources"], 1):
        lines.append(f"{i}. {s['conversation_date']} ({s['kind']}): {s['summary']}")
    lines += ["", "## Commitments", ""]
    for c in case["commitments"]:
        lines.append(f"- [{c['status']}] {c['action']} by {c['by_date'] or 'unspecified'}: \"{c['quote']}\" ({c['who']}, confidence {c['confidence']})")
    if case["offers"]:
        lines += ["", "## Offers", ""]
        for o in case["offers"]:
            lines.append(f"- {o['kind']}: \"{o['quote']}\" (decision: {o['decision'] or 'pending'})")
    if case["customer_actions"]:
        lines += ["", "## Actions requested of the customer", ""]
        for a in case["customer_actions"]:
            lines.append(f"- [{'done' if a['done'] else 'open'}] {a['action']}")
    if case.get("research"):
        r = case["research"]
        lines += ["", "## Where to escalate (researched)", ""]
        for item in r.get("results", []):
            lines.append(f"- {item['title']}: {item['url']}")
    lines += ["", f"Next step: {next_step(case)}", ""]
    return "\n".join(lines)


class Store:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "cases.json")
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"cases": []})

    def _read(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, payload: Dict[str, Any]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def list(self) -> List[Dict[str, Any]]:
        return self._read()["cases"]

    def get(self, case_id: str) -> Dict[str, Any]:
        for c in self.list():
            if c["id"] == case_id:
                return c
        raise KeyError(case_id)

    def upsert(self, case: Dict[str, Any]) -> None:
        payload = self._read()
        for i, c in enumerate(payload["cases"]):
            if c["id"] == case["id"]:
                payload["cases"][i] = case
                break
        else:
            payload["cases"].append(case)
        self._write(payload)
