# Judging and repository review guide

Reef Rescue is a simulation prototype for reef-restoration teams handling eligible, already-detached coral fragments. Its current live-model demonstration couples rendered robot-camera evidence, bounded model advice, numerical route evaluation and local safety checks. This guide maps the judging criteria to inspectable implementation and evidence; it does not predict a score.

Start with [README](../README.md), [scenario and verification guide](SCENARIOS.md), [evidence index](EVIDENCE.md), [architecture](../sim/pelagic/docs/ARCHITECTURE.md) and the [completed live episode](../sim/pelagic/docs/evidence/live_stack_completed_placement.json).

The weights and descriptions below follow the [provided judging screenshot](submission/judging-rubric.png).

## Rubric evidence map

| Criterion | Weight | What to inspect | Supported conclusion and limit |
| --- | ---: | --- | --- |
| Perception-driven action | 25% | `ArchitectureAdapters.perceive` in [lab_server.py](../sim/pelagic/reefsim/lab_server.py); capture and packet gates in [simulation.mjs](../sim/pelagic/web/lab/simulation.mjs); the [completed live episode](../sim/pelagic/docs/evidence/live_stack_completed_placement.json). | Real Gemma camera responses can withhold an intervention and trigger a rescan. Fresh accepted evidence precedes local handling approval. Appearance scores do not establish viability or genotype. |
| Adaptation to change | 25% | Argon assistance and rescan wiring in [app.mjs](../sim/pelagic/web/lab/app.mjs); fault/identity tests listed in [SCENARIOS](SCENARIOS.md); live episode events. | The saved live run contains uncertainty-driven rescanning and a sensor-dropout hold, followed by placement; a [separate uncertainty-abort record](evidence/live-model-uncertainty-abort.json) preserves a failed run. Current-induced same-fragment recovery is covered by controller/model-double fixtures; a live-model drop/recovery claim needs its own complete trace. |
| Operational autonomy | 15% | [Modal deployment](../sim/pelagic/scripts/modal_lab_backend.py), readiness/timeout behavior in [lab_server.py](../sim/pelagic/reefsim/lab_server.py), and local physics/hold limits in [simulation.mjs](../sim/pelagic/web/lab/simulation.mjs). | Local safety continues during remote waits and faults. The demonstrated Gemma and cuOpt services run on Modal; this is not demonstrated offline edge autonomy. A measured on-robot memory, power and latency budget is a remaining validation item. |
| Relevance and impact | 20% | Loose-stock eligibility, identity conservation and mechanical verification in [simulation.mjs](../sim/pelagic/web/lab/simulation.mjs); [scenario guide](SCENARIOS.md); [asset provenance](../sim/pelagic/assets/LICENSES.md). | The prototype targets a specific restoration workflow and makes unsafe/uncertain cases inspectable. It demonstrates no field ecological benefit, successful biological recovery or approved field intervention. |
| Ambition and technical quality | 15% | [Cross-language contract test](../sim/pelagic/tests/lab-pipeline-contract.test.mjs), [backend tests](../sim/pelagic/tests/test_lab_server.py), [recorder](../sim/pelagic/web/lab/recorder.mjs), [semantic memory](../sim/pelagic/web/lab/semantic-memory.mjs), and [read-only feed](../sim/pelagic/reefsim/live_feed.py). | The system combines real inference, explicit provenance, route validation, recovery logic and an independent Isaac stream. Regression success is bounded to tested cases, and the browser's reduced physics is not Isaac contact simulation. |

## Relevance, scientific motivation and intended impact

The intended users are reef-restoration researchers and field teams who need traceable handling of eligible fragments. The proposed value is repeatable inspection, identity-preserving transport and reviewable intervention records. Reduced diver workload or better survival are hypotheses to measure, not results established by this prototype.

The AIMS 2025–26 monitoring report surveyed 121 reefs and found hard coral cover generally stable or increasing after recent bleaching, while documenting continuing climate, cyclone and crown-of-thorns pressures. This supports a recovery-monitoring context without implying that all reefs are declining or need intervention. [AIMS annual report, 11 August 2026](https://www.aims.gov.au/monitoring-great-barrier-reef/gbr-condition-summary-2025-26).

Collins and colleagues demonstrated contact-mediated symbiont transfer and bleaching recovery in *Pocillopora damicornis*, with tissue fusion and recovery dependent on same-genet pairing in their experiments; different-genet pairings produced antagonistic interactions. That research motivates the prototype's independent lineage gate. It does not validate autonomous field application, every coral species, or the simulation's attachment method. [Primary study, Science Advances, 14 October 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13665998/).

A useful future field evaluation would measure intervention rejection accuracy, fragment loss/damage, operator time, energy per verified transfer and independently monitored survival. The on-screen critical failure case is loss of a carried fragment: preserve its identity, reacquire fresh evidence and recover or abort. Current measured and regression evidence for that case is listed separately below.

## Models, services and authority

| Component | Exact identifier | Role and execution location | Authority |
| --- | --- | --- | --- |
| Gemma | Served model `gemma-4-E4B-it`; configured weights `google/gemma-4-E4B-it` | Robot-camera appearance and fragment/gripper evidence; vLLM on remote Modal GPUs in the current demo. The deployment lists L4/A10 as configured GPU choices. | Supplies evidence. It does not set thrusters, infer lineage, approve cutting or override the registry. |
| Gemini Argon | `gemini-4-argon` | Google Interactions API; bounded assistance for a held issue and a separate post-mission review operation. | Assistance can return only `rescan`, `hold` or `abort`. It cannot return a handling approval. Post-mission suggestions do not patch or deploy code. |
| NVIDIA cuOpt | Response model `nvidia-cuopt` | Native route-cost solving on Modal; T4 is configured. The saved completed run reports solver version `26.10.0`. | Selects among supplied route alternatives. Local validation still decides whether movement is acceptable. |
| Local policy | `reef-local-policy-v1` | Inspectable Python gateway policy, not a learned model. | Proposes a bounded action/route using registry and fresh perception; browser checks remain authoritative. |
| Local controller | JavaScript mission/physics implementation | Browser host. | Executes the simulated mission, monitors current/grip/clearance, maintains identity, and counts verified mechanical placements. |

The active stack does not use every model mentioned in older experiments. `gemma-4-31b-it` belongs to the separate Python perception client defaults; `gemini-3.5-flash-lite` belongs to a separate optional cloud client; `gemini-nano-banana-2.1` is used by the synthetic image-generation utility. Their existence does not make them part of this live browser episode. Follow [modal_lab_backend.py](../sim/pelagic/scripts/modal_lab_backend.py), the current [gateway](../sim/pelagic/reefsim/lab_server.py), and recorded response identifiers when identifying the active models.

## Questions a reviewer can answer from the repository

**What is the actual problem and scenario?** A registered loose fragment must be moved onto an eligible living, bleached recipient, with inspection, safe transit and attachment verification. The compact scene is a reproducible simulation configuration. Known positions, source/recipient identity and lineage are supplied scenario facts, not a newly discovered real reef survey. See [SCENARIOS](SCENARIOS.md).

**Is Gemma really called?** The gateway constructs a real image request to the served Gemma model; returned packets include a request/capture identity, image hash, model, hosting location and latency. The [completed live trace](../sim/pelagic/docs/evidence/live_stack_completed_placement.json) records actual responses and their effects. Unit tests explicitly use doubles and are a different evidence category.

**Is Gemma on the robot?** That is the field architecture intent. Current evidence says `deployment: modal`; no on-robot residency, latency, power or memory measurement is established. A successful `/v1/models` readiness check is also not, by itself, a successful perception or mission test.

**What happens when Gemma is unsure?** The robot holds. The app sends bounded structured observations and the issue to Argon. Argon can ask for a fresh view, keep the hold or abort. A rescan does not waive the original constraints. See `requestAssistance` in [app.mjs](../sim/pelagic/web/lab/app.mjs) and `ArchitectureAdapters.assist` in [lab_server.py](../sim/pelagic/reefsim/lab_server.py).

**Does Argon see the original image?** The current assistance operation explicitly receives structured observations and telemetry, not the JPEG. Gemma receives the rendered image. Post-mission lab review receives episode/activity data. A general-purpose image-capable client elsewhere in the repo is not proof that these particular operations send images.

**Does Argon control the whole mission?** Normal planning uses the local policy and cuOpt. Argon assists held issues and provides post-mission recommendations. It does not issue arbitrary actuator commands, replace fresh observations, automatically rewrite code or autonomously deploy a next-mission policy. The earlier [safe-abort trace](../sim/pelagic/docs/evidence/live_stack_safe_abort.json) predates this separation and records the historical Argon-planning path.

**What does the confidence threshold mean?** The 0.70 cutoff is an engineering demonstration gate applied to an uncalibrated provider score. It is not a measured 70% probability of correct identification. Biological eligibility and lineage remain independent registered inputs. White or pale RGB appearance cannot establish whether coral is alive, dead or genetically compatible.

**Are UV, sonar and biology real measurements?** The browser supplies simulated exposure markers, range sensing and environment state. The optical assets are rendered from scene geometry. Neither UV nor RGB identifies genotype here; mechanical verification is not simulated tissue fusion or biological recovery.

**Is the robot connected to Isaac Sim?** A real Isaac RTX camera/state stream can be displayed through the read-only feed. The browser mission runs its own reduced physics and controller. That stream must not be presented as the physics engine or model-controlled execution behind a browser result. See [live_feed.py](../sim/pelagic/reefsim/live_feed.py) and [simulator overview](../sim/README.md).

**How is behavior determined?** The mission state machine, safety controls, reproducible scenarios and regression fixtures are deterministic code. Live-model mode requires actual inference evidence at its gates. Model uncertainty triggers bounded assistance and fresh perception; local checks remain authoritative.

**Does it recover from a drop?** Controller/model-double tests exercise current-induced grip loss, same-ID recovery and placement. The saved completed live-model episode has zero drops and zero recoveries. A stronger live claim needs a new continuous run showing all of those events with fresh post-drop inference. See the [scenario matrix](SCENARIOS.md).

**Does it keep working when the internet fails?** Local safety and physics continue; remote model/solver requests can fail and leave the mission held or aborted. Current evidence does not establish offline completion with local Gemma and local route services.

**How are results audited?** Inspect the episode's controller/source labels, capture IDs, image hashes, timestamps, transport events, solver result, fragment IDs and final counters together. A recorder continuity check establishes capture properties, not model quality or task success. Preserve failed runs and do not combine model receipts or outcome counters from different episodes.

**Why does the originally submitted PDF say there were no live placements?** Its evidence cutoff is 8 November 2026 at 13:09. The newer saved live episode records one placement; the [evidence index](EVIDENCE.md) identifies the current technical summary separately. The original PDF's offline on-robot description is field intent; its hardware table correctly identifies Modal hosting in the demo. Its broad wording about next-mission planning and camera review should not be interpreted as implemented autonomous policy deployment or image input to every Argon call.

## Remaining proof obligations

- One continuous actual-model run with an operator-triggered current disturbance, observed fragment loss, fresh recovery perception, the same fragment ID and verified placement.
- Measured edge-device memory, power and latency, plus a disconnected mission test with all required services local.
- Calibrated perception and confidence, force/contact validation and an independently assessed ecological intervention protocol.
- Repeatable held-out scenario evaluation rather than a single successful live episode.

These are explicit implementation/validation targets. The repository should be assessed on the evidence it contains rather than an assertion that every path is complete or failure-free.
