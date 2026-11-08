# Reef Rescue AUV hosted lab

This Site publishes the browser mission with a server-side Worker gateway. The browser calls same-origin perception, planning, readiness, assistance and telemetry endpoints. The Worker authenticates to the configured Modal backend; model credentials stay server-side.

## Model pipeline

The tool camera sends fresh rendered images to **Gemma `gemma-4-E4B-it`**. The gateway validates the resulting appearance and fragment/gripper evidence, applies **`reef-local-policy-v1`** registry checks and requests a native **NVIDIA cuOpt** route. The browser enforces local motion, identity and attachment checks.

For a held issue, **Gemini `gemini-4-argon`** supplies bounded context and visual checks for a new Gemma image, with rescan, hold or abort advice. Its advice does not grant handling permission. See the [service contracts](../../docs/ARCHITECTURE.md).

## Configure the hosted gateway

1. Deploy the [Modal backend](../../docs/ARCHITECTURE.md#integrated-authenticated-modal-deployment) with its private model workers and runtime secrets.
2. Set `LAB_ARCHITECTURE_BASE_URL` in the Site runtime to the deployed gateway's HTTPS base URL.
3. Set secret `LAB_ARCHITECTURE_TOKEN` to the same value as the backend's `LAB_GATEWAY_TOKEN`.
4. Build and publish the Site bundle. Open `/lab/`, select **Robot + base**, wait for readiness, then start the mission.

The backend holds `GEMINI_API_KEY` and the Hugging Face model credential. The Site holds only its gateway credential. The Worker serves static assets through the `ASSETS` binding and forwards `/api/lab/*` requests to the fixed authenticated backend. Unavailable services keep mission progression held or paused according to the controller state.

## Build and source ownership

From the repository root:

```sh
node sim/pelagic/sites/reef-lab/build.mjs
```

Or, from this directory:

```sh
node build.mjs
```

Inside the full repository, `../../web/lab` and `../../web/vendor` are the authoritative browser sources. Each build synchronizes them into this Site's `src/lab` and `src/vendor` and builds that snapshot. Publish the synchronized source with the Site; changes made only under `src` are replaced by the next full-repository build.

An independent Site checkout uses its committed `src` directly. The build produces `dist/client`, `dist/server/index.js` and `dist/.openai/hosting.json`. The root page redirects to `/lab/`. Asset attribution and licenses accompany the output.

## Local operation

From the repository root:

```sh
python3 sim/pelagic/scripts/run_lab.py
```

Configure actual Gemma and cuOpt services and the Argon credential using [SETUP](../../../../SETUP.md), then open `http://127.0.0.1:8090/lab/`. This uses the Python gateway directly. The integrated Modal gateway instead connects its GPU workers through private RPC.

The optional legacy `/api/lab/decision` Gemini endpoint is a separate API retained in the server and Worker; the current browser pipeline uses `/perception`, `/plan` and `/assist`.
