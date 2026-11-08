# Compact loose-fragment recovery scene

Import `reef_lab_compact_recovery.json` through the paused lab scene importer. Select Robot + base for actual model-backed operation. The scene file does not enable a controller or supply model responses.

This seed-42 scenario shortens travel by moving the registered G1 stock-source colony to (-4, -3.2) and its compatible living, bleached recipient to (-2.6, -3.2). Both retain the same species; radius is 0.43 m and height 0.68 m. Their base elevations come from the existing terrain sampler. Other colonies have unknown lineage, so they remain habitat rather than alternative restoration targets. Mission goal is one mechanically verified placement. Loose-fragment mode uses an already detached, scenario-permitted fragment; no healthy colony is harvested.

All 84 registered colonies, 812 generated habitat proxies, terrain, wildlife, current 0.08 m/s, visibility 8 m, collision checks, motion limits, sensing gates and phase durations remain active. The engine finds one accessible loose fragment, `donor-1-fragment-1`; inaccessible stock is excluded by the existing clearance checks. No engine parameters, simulation speed or camera output were modified.

## Offline timing checks, not live performance

Measured with the current engine after the fragment-capture freshness fix, 0.05-second caller steps and its unchanged 1/60-second physics substeps. Successful visual packets were **explicit test doubles**, delivered 2.5 simulation seconds after each ready camera request. Local policy and cuOpt replies were zero-latency doubles, not actual solver calls. The wave was injected automatically on first transport for reproducibility; a recorded demonstration must use its actual operator-triggered change and preserve that evidence.

| Scenario | Start-to-verification time | Visual requests | Result |
| --- | ---: | ---: | --- |
| No wave | 39.43 s | 3 | One placement, no collisions |
| Current wave, fresh recovery scan | 62.57 s | 4 | Same fragment dropped, recovered and placed; no collisions |
| Wave plus 17-second uncertainty-assistance hold | 68.62 s | 4 | Same fragment recovered and placed; no collisions |

The assistance check uses the real `set_assistance_hold` command immediately after grip loss, keeps physics running for 17 seconds, then releases the hold. It stands in for Argon assistance latency; it does not claim an Argon response. The 17 seconds overlap fragment settling and environmental recovery, so they do not add 17 seconds to the measured total. Successful scripted baselines were 35.23 seconds without a wave and 52.02 seconds with a wave.

**A cold-start full mission does not fit 60 seconds with these latency assumptions.** A continuous recording that starts at the initial pickup approach, after the three initial inspections, has a plausible window: approach begins at 21.10 seconds and verification completes at 68.62 seconds in the assistance timing check, a 47.52-second span. This leaves roughly 12 seconds of a 60-second take for actual runtime variation. It omits the initial inspections from that take; disclose the warm-up and retain their trace separately. Actual inference, solver, rendering and network latency can exceed this margin. Do not accelerate, splice, replay responses or label these timing doubles as live evidence.

Verification here is mechanical placement only, not tissue fusion or biological recovery. The config is a compact demonstration scenario, not a reconstruction of a surveyed reef or a guarantee of live completion.
