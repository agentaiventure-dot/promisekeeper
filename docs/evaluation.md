# Evaluation: extraction on the fixture transcripts

Run 2026-09-03 with a local open model through the same OpenAI-compatible client (`qwen2.5:7b` on Ollama at loopback, `PROMISEKEEPER_ALLOW_LOCAL_FAKE=1`). The Nemotron run on Nebius Token Factory will replace this table once credits are available.

| Transcript | Result | Time | Commitments extracted | Notes |
|---|---|---|---|---|
| first_call (insurer, "within five business days") | accepted | 4.7 s | 1, quote verbatim, date 2026-09-07 | Date resolved as 5 calendar days from 2026-09-02; the correct business-day date is 2026-09-09. The app shows the quote and the date side by side so the person can correct it. |
| offer (broadband goodwill credit) | accepted | 1.0 s | 0 commitments, 1 offer (credit), quote verbatim | The "confirm in writing" request was not captured as a customer action. |
| supervisor (new firm date) | accepted | 3.1 s | 1, quote verbatim, date 2026-09-18 | Correct. |

Guards exercised by the test suite: extra fields, wrong types, bad enum, invalid dates and invented quotes are all rejected before any state change (`python3 -m pytest`, 8 tests).

## Known weaknesses
- Relative dates ("five business days") depend on the model's calendar reasoning; the ledger records the model's date and the exact quote, and the human can edit the date before it becomes a broken-promise trigger.
- Customer actions phrased as requests inside an offer sentence can be missed.
- No multi-language support yet.
