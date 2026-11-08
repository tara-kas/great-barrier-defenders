# Repository instructions

Read [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/EVIDENCE.md](docs/EVIDENCE.md) and [SETUP.md](SETUP.md) before changing mission behavior or describing the system.

## Current implementation

The current demonstration is `sim/pelagic`: browser controller/physics, Python gateway, Gemma E4B on Modal, native cuOpt on Modal and bounded Argon assistance. The root Python agent/perception/mission packages are a separate research stack. Do not transfer claims between paths without tracing the actual call chain.

## Invariants

- Fresh, target-bound visual evidence and independent registry eligibility are required for handling.
- Appearance is not viability or lineage. Simulated UV is not a genetic assay.
- Loose-fragment missions preserve fragment identity and do not cut healthy colonies.
- Provider errors, malformed packets and uncertainty must hold, rescan or abort; never fabricate successful perception or silently bypass a configured solver.
- Local safety remains authoritative over model advice. Argon advice cannot grant handling permission.
- Keep scenario configuration and deterministic regression fixtures reproducible. Do not turn fixture outputs into production fallbacks.
- Preserve evidence source labels, raw logs and hashes. Report test outcomes separately from measured live-model outcomes.
- Keep credentials server-side and out of source, logs and documentation.

## Working practices

Respect uncommitted work and coordinate shared files. Independent work may be delegated to at most three concurrent subagents including descendants, with non-overlapping edit ownership. Verify the combined result. Do not alter CI/CD for this documentation and pipeline review.

Run `python3 tools/verify_submission.py` after editing submission evidence/docs. Browser/runtime changes require the Node lab suite and relevant Python gateway tests in SETUP. Python navigation changes require the agent and mission regressions. Tests must exercise the actual safety boundary, not merely repeat implementation constants.

Use [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for remaining acceptance work. Historical planning files under `docs/tasks` describe earlier intentions, not current deployment evidence.
