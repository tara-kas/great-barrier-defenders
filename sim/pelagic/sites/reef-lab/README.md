# Reef Rescue AUV hosted lab

This Site publishes the browser simulation plus a server-side Worker gateway. The browser connects to same-origin perception, planning, readiness and telemetry endpoints; the Worker authenticates to the configured Modal backend using a runtime secret. Model credentials never enter the browser bundle.

## Build and source ownership

```sh
node build.mjs
```

Inside the full Reef Rescue AUV repository, `../../web/lab` and `../../web/vendor` are the
authoritative browser source. Each build synchronizes them into this Site's
tracked `src/lab` and `src/vendor`, then builds from that local snapshot. Run the
build after upstream edits before publishing, and commit the synchronized `src`
with the Site. Editing `src` inside the full repository will be overwritten by
the next synchronization.

In an independent checkout of this Site, the parent `web/lab` is absent and the
build uses the committed `src` directly. This makes the Site repository
self-contained and reproducible. Generated output is under `dist/client`; the
root page redirects to `/lab/`. The build also copies the hosting manifest into
`dist/.openai/hosting.json`. Existing third-party asset attribution and licenses
are preserved in the copied source and output.

## Gemini control

For the server-backed local demonstration, use the full Reef Rescue AUV repository:

```sh
python3 scripts/run_lab.py
```

Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the server environment and deliberately
select Gemini in the browser controller menu. That Python server supplies
`/api/lab/health` and `/api/lab/decision`. Cloud decisions receive rendered tool-camera images and structured
sonar/mission telemetry, and never replace deterministic mission
eligibility or outcome checks. Without a configured backend the hosted Site
keeps Gemini unavailable and scripted simulation remains usable.

`worker.mjs` retains an optional Cloudflare Worker implementation of the same
API for future server-backed hosting. It requires private runtime secrets,
an `ASSETS` binding, and an authenticated gateway with account-level quotas.
The manifest omits `static` and the build emits `dist/server/index.js` plus `dist/client` assets. Configure `LAB_ARCHITECTURE_BASE_URL` and secret `LAB_ARCHITECTURE_TOKEN` in Sites before deployment. The gateway reports actual backend readiness; configuration alone is not a live inference.

The browser physics remains a reduced engineering demonstration, separate from
Isaac Sim validation and real-world biological outcomes.
