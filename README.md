# PromiseKeeper

**What did they promise, and did they keep it?** Paste a support call transcript, chat log or email thread. NVIDIA Nemotron, served by Nebius Token Factory, extracts every commitment the company made, with the representative's exact words and a real date. PromiseKeeper keeps the ledger, marks promises kept or broken after a grace period, tells you the next step, finds where to escalate, and writes the evidence pack for the complaint that ends most of these cases.

Built for the Nebius x NVIDIA Global AI Hackathon, Best Apps and Agents track.

## Why

"Five business days" said three times is still zero refunds. The failure is not the call; it is that nobody writes the promise down, so nobody notices when it breaks and every call starts from zero. PromiseKeeper turns the conversation you already had into a dated record you can hold them to.

## How Nemotron and Token Factory are used

- `promisekeeper/llm.py` calls the Token Factory OpenAI-compatible endpoint (`POST /v1/chat/completions`) with a strict JSON-schema response format. The model is configurable (`NEBIUS_MODEL`); the default is the NVIDIA Nemotron open model listed in your Token Factory catalog.
- `promisekeeper/extract.py` builds the prompt (conversation date, company, source text) and then **validates the model output in full** before anything is stored: closed field set, exact types, enum values, real calendar dates, and every quote must appear verbatim in the source. A model answer that fails any check is rejected, never trusted.
- Status (pending, kept, broken), the escalation recommendation and the evidence pack are computed from the ledger in plain Python, not by the model, so the record cannot drift.
- `promisekeeper/research.py` makes one runtime **Tavily** search for the company's complaints process and regulator when you ask where to escalate.

## Quick start (offline, no keys)

```bash
git clone https://github.com/agentaiventure-dot/promisekeeper && cd promisekeeper
python3 -m pytest -q                       # 8 tests against a loopback fake of Token Factory and Tavily
PORT=8799 python3 fixtures/fake_tokenfactory.py &      # fake Token Factory + Tavily
NEBIUS_API_KEY=fake NEBIUS_BASE_URL=http://127.0.0.1:8799 TAVILY_API_KEY=fake TAVILY_BASE_URL=http://127.0.0.1:8799 \
PROMISEKEEPER_ALLOW_LOCAL_FAKE=1 python3 -m promisekeeper                        # http://127.0.0.1:8800
```

Paste one of the transcripts from `fixtures/scenarios.json` (they contain the fixture trigger references) to see the full flow.

## Local run with any OpenAI-compatible open model (no cloud account)

```bash
ollama pull qwen2.5:7b && ollama serve &
PROMISEKEEPER_ALLOW_LOCAL_FAKE=1 NEBIUS_API_KEY=local NEBIUS_BASE_URL=http://127.0.0.1:11434 NEBIUS_MODEL=qwen2.5:7b python3 -m promisekeeper
```

Results on the fixture transcripts are in `docs/evaluation.md`.

## Real run (Nebius Token Factory)

```bash
cp .env.example .env      # put NEBIUS_API_KEY (and optionally TAVILY_API_KEY) in it; never commit it
set -a; . ./.env; set +a
python3 -m promisekeeper  # http://127.0.0.1:8800
```

Standard library only; no dependencies to install. The API keys are sent only to `https://api.tokenfactory.nebius.com` and `https://api.tavily.com`; any other base URL is refused.

## Hosted demo

See the Devpost submission for the live URL. Deployed on Render's free tier (no card, no account limits) as a single container (`Dockerfile` + `render.yaml`; see `docs/deploy-render.md`), bound to `0.0.0.0` only with `PROMISEKEEPER_PUBLIC=1` behind Render's HTTPS proxy.

**It runs in demo mode by default**, because there is no hosted Nebius key and Render's free tier accepts no card: `PROMISEKEEPER_DEMO=1` starts the same loopback fake model server the test suite uses (`fixtures/fake_tokenfactory.py`) in-process and points the client at it, so the hosted app needs no `NEBIUS_API_KEY` at all. Concretely, this means:

- The page shows a banner: "Demo mode: canned model responses for the three sample transcripts; run locally with a real model."
- Three "Load sample" buttons create a matching case and paste one of the fixture transcripts from `fixtures/samples.py` (the same insurance-claim, broadband-refund and supervisor-callback scenarios the tests use). Clicking "Extract commitments" on one of these returns the real extraction, validation, quote-guard and date-arithmetic pipeline running against the fixture's canned model response; everything downstream of the model call (schema validation, the ledger, kept/broken status, next step, evidence pack) is the genuine app logic, not mocked.
- Pasting anything else in demo mode is refused with a plain-language 422 error ("Demo mode only recognizes the three sample transcripts...") rather than a fabricated result, so a visitor never mistakes a canned answer for a real one.
- `GET /healthz` reports which mode a given deployment is in: `{"mode": "demo"}` or `{"mode": "live"}`.

To see PromiseKeeper read an arbitrary transcript with a real open model, either run it locally against Nebius Token Factory or Ollama (see "Real run" and "Local run" above), or flip the hosted instance's own `PROMISEKEEPER_DEMO` env var off and supply `NEBIUS_API_KEY`; steps in `docs/deploy-render.md`. The free Render tier also spins down after 15 minutes idle, so the first hit after a while looks slow (30-60s cold start); that is Render, not the model.

## What the app never does

- It never decides for you: offers (credits, partial refunds) are recorded verbatim and wait for your accept/decline.
- It never invents a quote: a commitment whose quote is not in the source text is rejected.
- It never invents a date: relative phrases are resolved against the conversation date you give, or left empty.

## Layout

```text
promisekeeper/llm.py        Token Factory client (origin pinned, JSON-schema responses)
promisekeeper/extract.py    prompt, schema, full validation, quote verification
promisekeeper/ledger.py     cases, commitments, kept/broken status, next step, evidence pack
promisekeeper/research.py   Tavily escalation research
promisekeeper/web.py        one-page UI and JSON API, demo mode, rate limiting, case cap
fixtures/                   loopback fake of Token Factory + Tavily, five scenarios, shared sample transcripts
tests/                      pytest, offline
docs/product-feedback.md    feedback on Token Factory, Nemotron and Tavily (hackathon feedback section)
docs/deploy-render.md       exact steps to deploy the hosted demo on Render's free tier
Dockerfile, render.yaml     container image and Render Blueprint for the hosted demo
```

## License

MIT.
