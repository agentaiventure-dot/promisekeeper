# Standard-library only; no requirements.txt / pip install needed.
# NOTE: this image build has NOT been verified locally (Docker Desktop was not running on the build machine).
# Render builds and runs it directly from this Dockerfile; verify the build log on first deploy.
FROM python:3.12-slim
WORKDIR /app
COPY promisekeeper ./promisekeeper
COPY fixtures ./fixtures

# Defaults for a hosted, key-free demo: PROMISEKEEPER_DEMO=1 serves canned responses for the three sample
# transcripts with no NEBIUS_API_KEY required. Render injects its own PORT at runtime, overriding the default
# below. To run against a real model instead, set PROMISEKEEPER_DEMO=0 and NEBIUS_API_KEY (see docs/deploy-render.md).
ENV HOST=0.0.0.0 \
    PORT=7860 \
    PROMISEKEEPER_PUBLIC=1 \
    PROMISEKEEPER_DEMO=1 \
    PROMISEKEEPER_DATA=/tmp/data

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','7860') + '/healthz', timeout=2)" || exit 1

CMD ["python3", "-m", "promisekeeper"]
