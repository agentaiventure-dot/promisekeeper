# Deploying PromiseKeeper to Render (free tier, no card, no key)

Render's free web service tier needs no payment card and runs a Docker image directly, which is why it's the
host used here. This deploys the app in **demo mode**: canned model responses for the three sample transcripts,
so it works with zero secrets. See "Going from demo mode to a real model" below to switch it to a live Nebius
Token Factory key later.

**Not verified locally.** Docker Desktop was not running on the machine that wrote this Dockerfile, so the
image build below has only been reasoned through, not actually run with `docker build`. Check Render's build
log the first time you deploy (step 4) before assuming it worked; if it fails, the log will show which layer
broke and that's the first thing to fix.

## What's in this repo for Render

- `Dockerfile` - `python:3.12-slim`, copies `promisekeeper/` and `fixtures/`, defaults to `PROMISEKEEPER_DEMO=1`,
  `PROMISEKEEPER_PUBLIC=1`, `HOST=0.0.0.0`, and runs `python3 -m promisekeeper`.
- `render.yaml` - a Render Blueprint that declares one free Docker web service pointed at that Dockerfile, with
  a `/healthz` health check.

## Steps in the Render dashboard

1. **Push this repo to GitHub** if you haven't already (it already lives at
   `github.com/agentaiventure-dot/promisekeeper`). Render deploys from a GitHub repo it can read.
2. **Sign in to Render** at [dashboard.render.com](https://dashboard.render.com) (GitHub sign-in is fine; no
   card is required for the Free plan).
3. Click **New +** (top right) -> **Blueprint**.
4. Choose **Connect a repository**, authorize Render's GitHub App for this repo if prompted, then select
   `agentaiventure-dot/promisekeeper` and the `main` branch.
5. Render finds `render.yaml` and shows one service to create: `promisekeeper`, plan **Free**, environment
   **Docker**. Click **Apply** (sometimes labeled **Create New Resources**).
6. Render starts a Docker build from `Dockerfile` immediately. Watch the **Logs** tab on the new service; a
   successful build ends with the `python3 -m promisekeeper` startup line and the service switches to **Live**.
   This is the point where you're actually verifying the build for the first time (see the note above).
7. Open the URL Render assigns (shown at the top of the service page, `https://promisekeeper-<random>.onrender.com`).
   You should see the PromiseKeeper page with the "Demo mode" banner and three "Load sample" buttons.
8. **Free-tier cold starts:** a free web service spins down after 15 minutes with no traffic and takes roughly
   30-60 seconds to wake back up on the next request. That first request will look like it's hanging; it isn't.

## Going from demo mode to a real model

The blueprint declares `NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `NEBIUS_MODEL` and `TAVILY_API_KEY` as
manually-set variables (`sync: false`) so they're never stored in this repo. To point the hosted app at a real
Nebius Token Factory model instead of the canned demo:

1. On the service page, open the **Environment** tab.
2. Change `PROMISEKEEPER_DEMO` from `1` to `0`.
3. Set `NEBIUS_API_KEY` to your real Token Factory key.
4. Optionally set `NEBIUS_BASE_URL` (defaults to `https://api.tokenfactory.nebius.com`) and `NEBIUS_MODEL`
   (defaults to `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1`) if you want a different model from the same
   provider. Optionally set `TAVILY_API_KEY` to turn on the "Find where to escalate" research step.
5. Click **Save Changes**. Render redeploys the service automatically with the new environment; no code change
   or new build is needed, since these are runtime env vars, not build-time ones.
6. Confirm the switch worked by checking `https://<your-service>.onrender.com/healthz`, which reports
   `"mode": "live"` once demo mode is off, or `"mode": "demo"` while it's still on.

`promisekeeper/llm.py` only ever sends the API key to `https://api.tokenfactory.nebius.com` (or the Hugging
Face inference router) - never to an arbitrary `NEBIUS_BASE_URL` you might mistype - so this is safe to set
directly in the Render dashboard.

## If you'd rather run the Docker image yourself first

Once Docker Desktop (or any Docker runtime) is available:

```bash
docker build -t promisekeeper .
docker run --rm -p 8080:7860 -e PORT=7860 promisekeeper
# open http://127.0.0.1:8080 - demo mode, same as the hosted default
```

This is the local equivalent of what Render's build step does, and is worth running once before or after the
first Render deploy to confirm the image behaves the same outside Render's build environment.
