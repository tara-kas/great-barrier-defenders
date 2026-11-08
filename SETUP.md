# Setup and verification

## Local browser mission

Python 3.10+ runs the lab server; a current Node.js with the built-in test runner runs the JavaScript regressions. Isaac Sim, npm and a local GPU are not needed to view the browser mission.

```bash
git clone https://github.com/tara-kas/great-barrier-defenders.git
cd great-barrier-defenders
python3 sim/pelagic/scripts/run_lab.py
```

Open `http://127.0.0.1:8090`. For actual model use, configure the gateway before starting it, then select **Robot + base**. Unconfigured endpoints must report unavailable; a running viewer is not proof of inference.

## Real model services

Copy `.env.example` to `.env` and fill in server-side endpoints and credentials. The browser gateway reads process environment, so explicitly export the file before launching (only source a local file you control):

```bash
cp .env.example .env
# Edit .env, then:
set -a
. ./.env
set +a
python3 sim/pelagic/scripts/run_lab.py
```

- `GEMMA_BASE_URL`: a separately exposed OpenAI-compatible vLLM endpoint including `/v1`. The integrated Modal gateway is not such an endpoint: it calls its private Gemma worker internally. For that deployment, use the hosted gateway/worker configuration below.
- `GEMMA_MODEL=gemma-4-E4B-it`: must match the server's served model name.
- `GEMMA_API_KEY`: model service credential if required.
- `GEMMA_DEPLOYMENT`: accurate hosting metadata (`modal`, `robot`, `base_station`, or `unverified`). This label does not verify hardware residency.
- `GEMINI_API_KEY` and `ARGON_MODEL=gemini-4-argon`: bounded assistance and optional review.
- `CUOPT_ADAPTER_URL`, `CUOPT_API_KEY`, `CUOPT_DEPLOYMENT`: actual native route service and its hosting location.

The integrated [Modal backend](sim/pelagic/scripts/modal_lab_backend.py) wires Gemma/cuOpt directly and protects its gateway using `LAB_GATEWAY_TOKEN`. Its dependencies, GPU choices and secrets are declared in that deployment file. The [worker](sim/pelagic/sites/reef-lab/worker.mjs) proxies authenticated requests without exposing service credentials to the browser. Follow the [integrated Modal deployment guide](sim/pelagic/docs/ARCHITECTURE.md#integrated-authenticated-modal-deployment) for the hosted path; deployment provisions paid GPU resources.

Check readiness, obtain an actual valid Gemma response, then run a complete mission and export the episode. These are separate checks. Use [SCENARIOS](docs/SCENARIOS.md) for acceptance cases and preserve all failure outcomes.

## Spark edge deployment

[Edge setup and measurements](docs/EDGE_DEPLOYMENT.md) documents the pinned Gemma model, isolated container, resource limits, image benchmark and loopback service configuration. Use `sim/pelagic/scripts/edge_serve.sh` with explicit image/cache/evidence settings. The network-disabled benchmark runs requests inside the same container; loopback serving is a separate mode for gateway integration.

## Regression checks

From the repository root, install the declared Python dependencies in an isolated environment first:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/verify_submission.py
cd sim/pelagic
node --test tests/lab-*.test.mjs
python3 -m unittest tests.test_lab_server tests.test_live_feed tests.test_live_stream_capture
```

The tests use provider doubles and local HTTP servers. They do not provision services or establish live model availability. HTTP tests need permission to bind a local ephemeral port.

## Separate Python research stack

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q agent/tests perception/tests eval cloud dashboard
```

Dependencies declare supported minimum versions, not a fully locked reproducible environment. [Agent](agent/README.md), [perception](perception/README.md) and [mission](mission/README.md) document this separate path. The Python Gemma client loads `.env` when python-dotenv is installed; its default model is `gemma-4-31b-it`, unless explicitly overridden. Do not infer that this default ran in the browser demonstration.

## Isaac camera/state feed

Isaac runs on a supported NVIDIA machine, while this checkout can receive its read-only camera/state feed. Use [simulator setup](sim/README.md) and [Pelagic setup](sim/pelagic/README.md) for the configured version and launch commands. Set the host/install paths for your machine; do not rely on a developer's home directory. The stream and browser controller are separate integration paths.

Keep `.env` and all credentials out of Git and evidence exports. Do not print secrets during readiness checks.
