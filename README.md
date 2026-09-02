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

See the Devpost submission for the live URL. Deployed as a single container (`Dockerfile`), bound to `0.0.0.0` only with `PROMISEKEEPER_PUBLIC=1` behind the platform's HTTPS proxy.

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
promisekeeper/web.py        one-page UI and JSON API
fixtures/                   loopback fake of Token Factory + Tavily, five scenarios
tests/                      pytest, offline
docs/product-feedback.md    feedback on Token Factory, Nemotron and Tavily (hackathon feedback section)
```

## License

MIT.
