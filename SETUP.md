# Setup

You are developing on macOS and are **not** the one running Isaac Sim — it needs an NVIDIA RTX-class GPU on Linux or Windows and does not run on Mac. A teammate runs it headless on that box; you connect as a viewer, or work entirely off recordings/logs for the modules that don't need a live sim.

## 1. Clone and configure secrets

```
git clone <repo-url>
cd da-best-ever
cp .env.example .env
```

Fill in `.env`:
- `GEMINI_API_KEY` — your own key or the team's shared key (ask the team lead; never commit it)
- `ISAAC_SIM_HOST` and ports — ask whoever is running the sim (see step 3)

`.env` is git-ignored. Never paste the key into a prompt or a committed file (CLAUDE.md section 8).

## 2. Python environment

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Connecting to Isaac Sim as a viewer (not running it)

The sim owner runs it headless with livestream enabled:
```
./runheadless.sh -v          # container, or
LIVESTREAM=1 ...             # standalone/Isaac Lab, public network
LIVESTREAM=2 ...             # standalone/Isaac Lab, private/local network
```
Their container needs `--network=host` and these ports open on their host firewall:
- TCP 49100 — signalling
- UDP 47998 — media
- TCP 8210 — web viewer (only if they're using the Docker Compose option)

To watch the stream yourself:
1. Install the NVIDIA Omniverse **WebRTC Streaming Client** (macOS build — Intel or Apple Silicon).
2. Get the sim owner's host/IP and put it in `ISAAC_SIM_HOST` in your `.env`.
3. **Only one streaming client can connect per Isaac Sim instance.** Coordinate in team chat before connecting — if someone else is already watching, use the web viewer (port 8210) or a recording instead.

## 4. Working without a live sim connection

Most of this repo doesn't need a live Isaac Sim session day-to-day:
- `/agent`, `/perception`, `/control` can be developed and unit-tested against logged sensor packets / recorded clips.
- `/eval` holds the scenario fixtures and regression harness — run those locally.
- `/dashboard` can run against a recorded or synthetic event log.
- `/cloud` (Argon debrief/coder/verifier) consumes run logs and video after the fact, not a live stream.

## 5. GPU compute (Modal)

The team has access to Modal for GPU workloads (e.g. Gemma eval off the edge device). A teammate owns that account — ask them for `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` if your work needs it; don't provision anything on Modal yourself without checking in first.

## 6. Run tests

```
pytest
```

## 7. Before pushing: secrets audit

```
git log -p | grep -iE "AIza|api[_-]?key|sk-"
```
No API keys in the repo or commit history, ever (CLAUDE.md section 8).
