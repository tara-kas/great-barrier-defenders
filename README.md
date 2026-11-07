# da-best-ever — Reef Rescue AUV

AgentVerse 2026, Robotics Track.

An autonomous underwater vehicle in NVIDIA Isaac Sim that rescues loose, living coral fragments and re-seats them on stable reef substrate — built for reef restoration teams who today rely on divers limited by depth, time, and weather.

Full context, rules, architecture, and decisions log: [`CLAUDE.md`](./CLAUDE.md).
Local setup (including how to connect to Isaac Sim without running it yourself): [`SETUP.md`](./SETUP.md).

## Models used

| Role | Model ID |
|---|---|
| Lead reasoning / cloud loop | `gemini-4-argon` |
| Managed sandbox | `antigravity-preview-09-2026` |
| Deep research | `deep-research-preview-04-2026` |
| Fast subagent | `gemini-3.8-flash` |
| Fast router | `gemini-3.5-flash-lite` |
| Live voice/vision | `gemini-3.8-live` |
| Image (4k) | `gemini-nano-banana-2.1` |
| Image (fast) | `gemini-3.1-flash-lite-image` |
| On-device / edge | `gemma-4-31b-it` |

Exact strings and API conventions: CLAUDE.md section 3.

## Verification loop

On-device, the vehicle never phones home: a classical, inspectable optimiser scores and assigns sites, and after every placement a simulated current-push test checks the fragment holds — if it shifts, the agent diagnoses and retries. Between dives, Argon reviews run logs, proposes patches, and a verifier runs those patches against the `/eval` regression suite; a patch is promoted only if nothing regresses **and a human approves**.

## Repo layout

```
/sim        Isaac Sim world (USD), vehicle, sensors, hydrodynamics, director
/control    thrusters, station keeping, carry-aware control, safety limits
/perception classifier / Gemma prompts, semantic map
/agent      on-device agent loop, tools, optimiser
/cloud      Argon debrief, coder, verifier, scene critique
/dashboard  live stream: camera + detections, map, decision log, link status
/eval       scenario suite, metrics, regression harness
/docs       one-page technical summary, README assets
```

No API keys in this repo or its commit history — see `.env.example` and CLAUDE.md section 8.
