# Connected gripper, central contact, and current — 8 November 2026

The current team name in GitHub main is **Reef Rescue AUV**. The offline camera layouts, simulation documentation, and legacy viewer now use it; the existing `sim/pelagic/` directory remains compatible with team imports and scripts.

## Mechanism and continuous motion

The gripper palm was narrower than the opening needed by the scanned cutting. Sliding rails and carriages now physically connect the fingers to the palm, with a wrist knuckle overlapping the forearm endpoint. An independent USD check reads actual primitive transforms, dimensions, overlaps, and arm lengths at mission milestones. A lightweight robot-only check runs before the dense reef build, and the full scene repeats it during recording.

Retraction now tracks the moving hull's stowed pose instead of handing off to an endpoint calculated before station drift. The measured handoff residual after subtracting normal rigid-body movement is 0.099 mm after harvest and 0.140 mm after recovery. Carried-to-placed ownership changes have zero position displacement. The 25 mm final seating takes three seconds and stays below 1 mm per 50 ms simulation step.

## Central natural contact

The planner searches actual upper branch triangles within 40% of the recipient radius, with unchanged donor and recipient scan geometry. It ranks candidates by a geometric tissue-contact area proxy and rejects penetrations and obstructed insertion corridors. Severed cap triangles do not contribute to living-tissue area.

The selected cutting is at 31.96% of the recipient radius, compared with the previous outer-branch placement. It has approximately 111.5 mm² of original tissue surface within the 1.5 mm proximity threshold, including 14 original vertices. This is a proximity-area estimate, not a measured compressed contact patch or proof of biological transfer. Dense checks of all 1,129 cutting vertices found positive minimum separation at 4, 12, and 25 mm above the final pose. The planned endpoint touches the existing recipient mesh without detected penetration.

## Current and physics

The recorded controller trajectory now integrates quadratic current-relative drag and bounded thruster forces on an 18 kg neutrally buoyant vehicle. Station keeping permits finite drift instead of freezing the body. Its maximum position error is 15.185 mm; maximum station-keeping thrust is 2.365 N, and navigation thrust is bounded at 38 N. The arm stabilizes the contact point while the hull responds.

The same mean current and surge drive suspended particles and flexible sea fans. Particles update every frame and fade at wrapping boundaries. Moving fans are placed near the mission work sites. The additional fixed-camera eight-second recording compares a still-water reference with moving soft tissue. Stony coral skeletons remain rigid. See [current dynamics](CURRENT_DYNAMICS.md) for assumptions and controls.

These are reduced dynamics integrated by the mission adapter and flexible-tissue model, then replayed in Isaac's renderer. They are not a full underwater PhysX/CFD or calibrated tissue-contact solver. The mission still uses explicitly labelled pre-mapped offline perception with zero model calls.

## Verification

- 116 simulation tests and 128 subtests passed.
- 11 adapter tests passed, including central contact, current response, same-fragment recovery, push verification, reach, and motion handoffs.
- The final trace contains 1,886 snapshots over 94.25 simulation seconds and ends in `MISSION_COMPLETE`.
- Trace SHA-256: `a08686c39af98307df4a59a74e3c8d62ed640ab9a18c75e7f6dc79dd23482d72` (local and Spark copies match).
- Fresh render artifacts and their final verification are recorded in the ignored `outputs/reef-rescue-connected/` folder.

## Fresh offline recording

The fresh mission capture is 60 seconds (1,440 frames at 24 fps, 1600 × 900) and includes actual director, scout, and wrist-camera views. Its full decode, 98 native geometry checks, and 98 actual USD linkage checks passed. The push test's maximum tissue-to-triangle gap is 0.382 mm. The eight-second fixed-camera current comparison has 192 frames and a measured 106.1 mm fan-tip excursion; its zero-current control and full decode passed.

Visual review found a foreground sea fan obstructing the main recovery camera, while the wrist view stayed clear. The recovery director now chooses a clear side using colony, rock, vehicle, and swept fan envelopes, then holds that viewing angle. A targeted fresh capture replays the same full camera history and replaces only the affected frames plus five seconds of settling, without altering poses, decisions, frame timing, or motion interpolation. `scripts/apply_camera_patch.py` checks trace hashes, schedules, and geometry/linkage reports before assembling those actual captures. The original take is retained for provenance.
