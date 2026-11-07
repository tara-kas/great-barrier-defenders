# CLAUDE.md — Reef Rescue AUV (AgentVerse 2026, Robotics Track)

Context file for coding agents and teammates. Keep it current. If something here conflicts with the organisers' instructions, the organisers win. Update the "Open questions" and "Decisions log" sections as things change.

## 1. What we are building

An autonomous underwater vehicle (hovering AUV) in **NVIDIA Isaac Sim** that treats bleached coral. It surveys the reef, classifies colonies, reads each bleached colony's genet from UV fluorescence, collects a healthy fragment of the same genet from a base station, places it in contact with the colony so symbionts can transfer, verifies contact, and returns to check recovery. The scenario is Moore Reef on the Great Barrier Reef (`data/moore_reef/`).

- **Named user:** a reef restoration team responding to mass bleaching, who today rely on divers limited by depth, time and weather.
- **Pitch hook:** bleached coral can recover in weeks through contact with a healthy clone (Collins et al., *Science Advances*, 2026). A robot can make that contact at reef scale, with every decision traceable to a sensor reading and self-improvement between dives.
- **Not claiming:** that we revive dead coral (dead colonies are skipped), or that this is field-proven. The paper is one species (*Pocillopora damicornis*) in aquaria. UV genet identification is the project's central untested assumption: there is evidence fluorescence varies genetically, none that it identifies genets. Say so if asked; real deployment would confirm with a DNA sample or a pre-mapped reef.

## 2. Event rules and what judges want (READ THIS)

Sources: the Robotics Track slides and the UCL AgentVerse 2026 Builder Guide.

**Timeline.** Hackathon runs Sat 9:00 to Sun 18:00. **Feature freeze: Sun 16:00 at the latest** (at least 2 hours before the deadline). Judging is Sunday afternoon.

**Robotics rubric (weights).**
| Criterion | Weight | What a top score looks like |
|---|---|---|
| Perception-driven action | 25% | Every decision traces to what it perceived, and it corrects mid-run. |
| Adaptation to change | 25% | The scene changes mid-sequence and the agent visibly re-plans. |
| Operational autonomy | 15% | Runs within a stated edge-device budget and behaves sensibly when unsure. |
| Relevance and impact | 20% | A well-evidenced need, with the most critical failure mode handled on screen. |
| Ambition and technical quality | 15% | An original approach to a demanding problem, executed to a high standard. |

**Robotics deliverables.**
1. **Technical summary:** ONE page, PDF. User and problem, key features, system architecture, where each model runs (with hardware and latency), limits, the critical failure mode, and safety.
2. **Simulation video:** up to 1 minute, captured from the stream. Perception on screen next to the actions. **One unscripted change in a single continuous take.**
3. **Pitch:** 5 minutes live. The problem, how it works, what it can and cannot do, and why it matters.

**Builder Guide requirements (apply on top of the above).**
- Judges score **live working software**, not slides. Live demo **under 3 minutes**, opening on working software within 30 seconds, on real inputs. Keep a local screen recording as a Wi-Fi backup.
- **Public GitHub repo, all application code written during the hackathon.** Open-source libraries, public datasets, and starter templates are fine. Do not demo code written before Saturday kickoff.
- A concise **README** stating the named user problem, the exact Gemini 4 Argon and companion model IDs used, and how the verification loop works.
- **No API keys in the repo or commit history.** Use environment variables or the Credentials API. Never paste secrets into prompts.
- Keep people in control of actions affecting physical hardware.
- Not allowed: a chat wrapper with no tools, planning, or verification; mocked screens or hardcoded JSON pretending to call Gemini live; hand-rolled sandboxes or retry state machines when the Interactions API and Antigravity already provide them.

**Google DeepMind "Best Use of Gemini" prize** needs all three:
1. 2+ modalities in one connected loop (for example camera frames + voice/text + simulation state).
2. Gemini outputs verified through a real check (physics solver, test suite, multi-angle screenshot critique, line-cited rules).
3. An interactive experience impossible in a plain text box, with people in control of real-world actions.

**The Robotics slides say** core decisions that depend on a remote service score lowest on autonomy ("keep it on the device"), and the agent must decide "with nothing to phone home to". See section 4 for how we reconcile that with Argon as the verifier.

## 3. Tooling and model IDs

Copy exact strings; do not guess.

```python
MODEL_IDS = {
    "lead_reasoning": "gemini-4-argon",
    "managed_sandbox": "antigravity-preview-09-2026",
    "deep_research": "deep-research-preview-04-2026",
    "fast_subagent": "gemini-3.8-flash",
    "fast_router": "gemini-3.5-flash-lite",
    "live_voice_vision": "gemini-3.8-live",
    "live_extended_thinking": "gemini-3.8-live-extended-thinking",
    "image_4k": "gemini-nano-banana-2.1",
    "image_fast": "gemini-3.1-flash-lite-image",
    "open_model": "gemma-4-31b-it",   # E2B/E4B are the edge sizes: confirm exact IDs / local runtime (see TODO)
}
```

**API conventions (SDK `google-genai>=2.3.0`).**
- Use the **Interactions API** (`client.interactions.create(...)`) for models and managed agents.
- Set reasoning depth with `generation_config={"thinking_level": "low" | "medium" | "high"}`. Default is medium.
- **Remove** legacy params: thinking budget, temperature, top-p, top-k (Argon ignores them). No manual context caching (implicit caching is automatic).
- High-thinking synchronous calls can be slow: raise HTTP timeouts to 15 to 20 minutes, or use `background=True` and poll `client.interactions.get(id=...)`. Default output limit is 65,536 tokens; to go beyond, use background execution plus `max_output_tokens`.
- Argon does **not** support the Live API. For real-time voice or camera use `gemini-3.8-live`.
- Antigravity managed agent: `agent="antigravity-preview-09-2026"`, `agent_config={"type": "antigravity", "model": "gemini-4-argon"}`, `environment="remote"`. Register external tokens with the Credentials API and a network allowlist.
- Introductory pricing noted in the guide: $2 per 1M input tokens and $10 per 1M output tokens through 30 Nov 2026. Do not burn credits on loops; log token use.
- Install the official skills in your coding agent so it writes current code: `npx skills add google-gemini/gemini-skills --skill gemini-api-dev`.
- **GPU compute:** we have access to Modal for GPU compute (e.g. for Gemma inference/eval off the edge device, dataset prep). A teammate owns the Modal account/credentials, not listed here yet — see open questions. Do not provision or spend Modal credits without checking with them first; keep `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` out of the repo the same as the Gemini key.

## 4. Architecture (reconciling "on device" with "Argon as brain")

Two loops. The vehicle never waits on the cloud.

**Loop A: on-device, during the dive (autonomous).**
Status: the reflex layer below is not built (`control/` is empty); the FSM has a simple position controller. Everything else in this list exists.
- **Reflex layer (CPU, fast):** thruster allocation, station keeping, current compensation, carry-aware control (mass and drag change when holding a fragment), collision and depth limits.
- **Perception:** hull and wrist RGB-D, hull UV, gripper force. **Gemma (`gemma-4-31b-it`, self-hosted, zero/few-shot) detects and classifies** coral: type, `LIVE`/`DEAD`/`BLEACHED`, health score. `perception/survey.py` projects detections into the registry. `perception/genet.py` reads each bleached colony's emission across three UV bands and matches it to the genet library; a weak match stays `None`.
- **Map:** `SemanticSeabedRegistry` (`perception/registry.py`), one `SemanticMapEntry` per cluster. This schema is a frozen contract.
- **Optimiser (classical, inspectable):** `agent/pairing.py` pairs open `BLEACHED` colonies with a same-genet base station rack, lowest `J = w1*|x_rov-x_i| + w2*|x_i-x_j| - w3*H_i` first. No confident genet, or no stock, means skip with a logged reason. `DEAD` is never a target. Weights and limits live in `agent/config.py`. `agent/graft_point.py` picks the contact point by PCA surface normals.
- **Agent loop:** a classical FSM (`agent/fsm.py`): `SURVEY_SEABED -> COMPUTE_RESTORATION_PLAN -> NAVIGATE_TO_DONOR (base station) -> HARVEST_FRAGMENT -> NAVIGATE_TO_RECIPIENT -> TRANSPLANT_FRAGMENT`, looping to planning, then `RETURN_VISIT`. Gemma is confined to perception and does not pick actions. Episodic memory stops it retrying rejected sites. Unused fragments go back to the station. It aborts after repeated perception failures.
- **Verify:** after placement, a push test from the sim (`placement_verifier` returns `stable` and `contact`). On failure the colony stays open; three failures reject it. Success means `TREATED`, not recovered. Return visits at day 7 and day 56 (`revisit_days`) leave the fragment in place; lost contact gives `NOT_RECOVERED`, and recovery is judged at the last visit (`RECOVERED`/`NOT_RECOVERED`).
- **Entry point:** `run_mission` in `mission/runner.py` wires all of this and writes live files for the dashboard. It lives outside `agent/` so `agent/` stays free of network code. It refuses to run without `fragment_held` and `placement_verifier`, and refuses a non-local Gemma endpoint, unless explicitly overridden.

**Loop B: cloud, between dives (Argon).**
Status: only the debrief of decision logs is built (`cloud/debrief.py`). The items below it, and video review, are planned.
- **Debrief:** Argon reviews run logs and video, labels failures, scores segments (agentic video analysis).
- **Coder:** proposes patches to planner weights, behaviour tree, or controller.
- **Verifier:** runs patches against a scenario regression suite (Antigravity sandbox or local pytest), promotes only if nothing regresses and a **human approves**.
- **Scene generation and critique:** Argon can generate robot descriptions and scene scripts and critique multi-angle renders to repair collisions or floating geometry (the guide's examples are MuJoCo, URDF and Three.js; for Isaac Sim, go via URDF and Python scene scripts, and verify the import path early).
- **Safety constraints:** when connectivity returns, Argon verifies recovery plans against safety constraints (matches the Builder Guide's "offline-first Gemma planner" blueprint for Robotics).
- Other uses: Nano Banana 2.1 for textures and restyling sim assets; Deep Research for cited evidence of need; optional `gemini-3.8-live` for an operator voice console (never in the dive loop).

**Human in the loop (optional, never blocking).** Roles: set mission goals and no-go zones before the dive; advisory approval for uncertain cases over a **simulated acoustic link** (bandwidth cap plus latency; thumbnails and short summaries only) with a timeout and safe default; emergency recall; sign-off on Argon patches before promotion. Demo must also work with the link cut.

## 5. Simulation notes (Isaac Sim)

**Platform.** Isaac Sim needs an NVIDIA RTX-class GPU (NVENC for streaming) on Linux or Windows. It does not run on macOS. Macs can only be the viewer: the WebRTC Streaming Client has macOS builds (Intel and Apple Silicon) and connects to a headless Isaac Sim on a remote GPU host. Latest release seen at time of writing: 6.1.0 (Sept 2026); pin the exact version the team uses in this file.

**Run and stream.**
- Headless with livestream: container `./runheadless.sh -v`, or Isaac Lab / standalone with `LIVESTREAM=1` (public network) or `LIVESTREAM=2` (private/local network).
- Container needs `--network=host`. Ports: TCP 49100 (signalling), UDP 47998 (media), TCP 8210 (web viewer if using the Docker Compose option). Open them in the host firewall.
- **One streaming client per Isaac Sim instance.** Plan who is watching; others use the web viewer or recordings, or run their own instance.
- Reports exist of headless WebRTC slowing the sim loop. Test throughput early; do not tie control timing to wall-clock `sleep`.
- Our dashboard (camera with detections, map, decision log, link status) can be a separate window or web page alongside the stream, so perception shows next to actions in the video.

**Underwater physics: simplified.** The team spec says to fake the water: zero gravity plus damping, not real hydrodynamics. Do not spend hours on Fossen-style physics. Isaac Sim has no built-in buoyancy, drag, added mass or currents, so damping and any current push are applied as external forces each physics step (Python or OmniGraph callback). Currents only need to be good enough for the push test and the dislodgement perturbation. Say in the PDF that the physics is simplified. The third-party "lighthill" package is pre-alpha: do not depend on it.

**Perception advantage.** RTX cameras give photoreal RGB and depth. Turbidity: fog or post-process on the camera feed plus noise; keep it a controllable variable the director can change.

**Manipulation.** Prefer a simple, reliable grasp: kinematic attach/joint when the gripper is aligned within tolerance and closed. Do not model a soft gripper.

**Scene.** Reef from USD assets (hard rock, sand, rubble, algae patches) with distinct materials; fragments as free rigid bodies. Import the vehicle via URDF if useful.

**Perturbation director.** A separate process or hotkey that injects surprises (current surge or reversal, dislodged fragment, visibility drop, site proves unsuitable, wildlife crossing). The agent must not know the schedule. For the video, a teammate triggers it live.

**Pose.** If we use simulator pose with injected noise and a filter, say so in the PDF.

**Numbers for the PDF must be measured.** State the edge budget as a target (for example "Jetson Orin Nano class, 8 GB") and say what hardware the measurements came from. Isaac Sim itself will not run on that edge device; only the on-device agent stack (control, perception, Gemma) is budgeted against it.

## 6. Data

- **Coralscapes** (Hugging Face `EPFL-ECEO/coralscapes`, Apache 2.0): 2075 images, 39 classes including sand, bleached, dead, unknown hard substrate. Use for real-world evaluation and class definitions.
- Health-only sets (Kaggle bleached vs healthy, `esahit/coral-health-classification` on Hugging Face). Quality varies; check licences.
- No public dataset of loose fragments on sand was found. Any synthetic fragments (Nano Banana edits) must be labelled synthetic and treated as unverified.
- Real photos and sim renders differ: do not claim real-world accuracy from a model trained only on sim.
- **Moore Reef scenario** (`data/moore_reef/`, built by `eval/generate_moore_reef.py`): the project's labelled dataset. Team decision: no "synthetic" labels on it or on screen when using it. Treat it as the scenario, do not attribute it to a real survey, and report results on it as scenario results.

## 7. Domain facts to keep straight

- Coral colonies are polyps with symbiotic algae. Bleaching = loss of algae under stress (often marine heatwaves); bleached coral is alive but starving and can recover if stress ends. Dead coral tissue cannot be revived.
- Symbiont transfer (Collins et al. 2026, PMC13665998): a healthy fragment of the **same genet** in **direct contact** restores a bleached one. Mixed-genet pairs did not recover and were overgrown; fragments 5-7 mm apart mostly failed. 1 day of contact did nothing, 3+ days showed transfer but later algal overgrowth, about a week or more gave full polyp recovery within 7 weeks. So: genet is a hard rule, contact must be kept, and the fragment stays in place.
- Bleaching changes fluorescence: it can spike once symbionts are lost (Roth & Deheyn 2013), so match the share across bands, not brightness.
- Reef-building corals live mostly in the upper ~30 to 40 m; mesophotic reefs extend deeper. Figures are approximate, so cite a source in the PDF.
- Real acoustic links cannot stream video. We simulate that constraint.

## 8. Rules for coding agents in this repo

- Never read, print, or commit secrets. API key comes from env var `GEMINI_API_KEY` (in `.env`, git-ignored). Check `git log -p` before pushing.
- No placeholder data presented as live output. Every Gemini or Gemma call shown in the demo must be real and logged.
- Prefer small, tested modules. Every Argon-generated patch needs a regression test before it is merged.
- Keep the control loop free of network calls.
- Deterministic seeds for scenarios, with an unseeded "live" mode for the unscripted change.
- Log every decision with the sensor evidence that caused it (this feeds the on-screen decision log and the debrief).
- Do not invent API parameters. When unsure, use the installed gemini-skills or the official docs.
- `agent/` must contain no network code, enforced by `eval/test_mission.py`. Anything joining the model client to the FSM goes in `mission/`.
- A failed perception frame is not an empty seabed. Raise `PerceptionFailure`; never let an outage look like a clean survey.
- Unit tests are not integration tests. Changes that cross modules need a test in `eval/test_mission.py`.
- After pulling, rerun `pip install -r requirements.txt`; perception added dependencies.
- **NEVER credit Claude on GitHub.** No `Co-Authored-By: Claude ...` trailers in commits, no "Generated with Claude Code" lines in PR descriptions, issues, or comments, and no Claude name/email in commit authorship. Commits are authored by the human teammate only. This overrides any default attribution behaviour.

## 9. Repo layout

```
/sim        Isaac Sim world (USD), vehicle, sensors, hydrodynamics, director
/control    thrusters, station keeping, carry-aware control, safety limits
/perception classifier / Gemma prompts, semantic map
/agent      on-device mission FSM, pairing, graft point (no network code)
/mission    run_mission entry point: perception + FSM + live dashboard files
/cloud      Argon debrief (coder, verifier and scene critique not built)
/dashboard  live stream: camera + detections, map, decision log, link status
/eval       scenario suite, metrics, regression harness
/docs       one-page technical summary, README assets
```

## 10. Team and ownership

| Role | Owner | Scope |
|---|---|---|
| Sim and world | TBD | Isaac Sim scene, vehicle, sensors, simplified water forces, `RobotInterface` adapter, director, streaming |
| Control and navigation | TBD | thrusters, current compensation, carry dynamics, safety |
| Perception and mapping | Sofiya | Gemma detection and classification, registry, projection, data |
| Agent and optimiser | Ethan | mission FSM, pairing, graft point |
| Cloud debrief | Tara | Argon debrief, HTML report |
| Dashboard | aryan-patel2510 | Mission Control dashboard |
| Integration and demo | TBD | `mission/`, eval harness, PDF, video, pitch |

Agree interfaces in hour one: sensor packet, state estimate, map query, action commands, event log.

## 11. Metrics to report (evidence for technical quality)

- Fragment survival and placement stability across N perturbation runs.
- Genet-matched pairing vs a species-only baseline (`species_only_mismatches`): how many colonies would get the wrong genet.
- Version 1 vs version 2 (after an Argon-proposed patch, human-approved).
- Abstention quality: how often it declined, and how often that was right.
- Latency per component and energy used.

## 12. Critical failure mode and safety (for the PDF and pitch)

- **Primary failure to show handled on screen:** a fragment is dislodged mid-carry (current surge). Detect via `fragment_held`, re-plan, collect another of the same genet.
- **Do no harm:** a wrong-genet pairing harms the colony, so anything short of a confident in-stock match is skipped, and contact must survive the push test before a colony counts as treated.
- Force-limited handling, depth floor, abstain when unsure, yield to wildlife, hold or abort on lost localisation.
- Human approval gate for any change to the vehicle's code or policy; recall always available.

## 13. Open questions (ask organisers or the DeepMind booth)

- Where will Isaac Sim run (organiser GPU instance, cloud GPU, or a team NVIDIA machine)? Who has an RTX-class GPU with NVENC?
- Are the Robotics deliverables (video, PDF, pitch) in addition to the Sunday live demo and public repo, or in place of parts of them? Plan for both.
- Do our keys include `gemini-4-argon`, Antigravity, and Nano Banana 2.1? What are the rate limits?
- Exact IDs and runtime for Gemma 4 E2B/E4B (the guide lists only `gemma-4-31b-it`).
- Can more than one teammate stream at once? (One streaming client per Isaac Sim instance.)
- Who owns the Modal account/credentials, and what exactly runs there (Gemma eval batches? dataset preprocessing? it's not a substitute for Isaac Sim's RTX requirement)?

- Does the poster say 5 days? Evidence supports about 7+, so the poster and `revisit_days` should agree.
- Which machine serves Gemma for the demo? It must be local to the agent stack. `gemma-4-31b-it` is not edge-sized, so the PDF needs the edge budget stated separately (section 5).

## 14. Schedule (Sat 7 Nov to Sun 8 Nov 2026)

- Sat afternoon: **get Isaac Sim streaming to a laptop first (slides: first hour, before agent code)**, then contract and vertical slice, vertical slice (one vehicle, 2 to 3 fragments, one reef patch, three perturbations), core verification loop.
- Sat evening: multimodal layer, push a clean checkpoint to GitHub, **sleep**.
- Sun morning: polish, rehearse, record backup takes.
- **Sun 16:00: feature freeze.** Then: fresh-input end-to-end test, secrets audit of source and history, README, rehearsal under 3 minutes.

## 15. Decisions log

- 2026-11-07: Gemma does detection and classification, replacing HSV/YOLOv8. Self-hosted, never the cloud Interactions API.
- 2026-11-07: The team spec's 6-state FSM, registry schema and algorithms are canonical, replacing the Gemma ~1 Hz tool-picking loop.
- 2026-11-07: **Premise change.** The robot treats `BLEACHED` coral by same-genet contact and skips `DEAD`, replacing grafting onto dead coral. Donors come from a base station of propagated coral. Genets come from UV fluorescence. Statuses `TREATED`, `RECOVERED`, `NOT_RECOVERED` replace `RESTORED`. Contract changes: registry gains `genet_id` and `uv_signature`, `RobotInterface` gains `get_uv_frame()`.
- 2026-11-07: Physics simplified to zero gravity plus damping (section 5).
- 2026-11-07: `run_mission` in `mission/` is the single entry point. `RobotInterface` stays frozen; `fragment_held` and `placement_verifier` are required arguments to `run_mission`.
- 2026-11-07: No Claude attribution anywhere on GitHub (commits, PRs, comments). See section 8.
