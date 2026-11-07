# Validation evidence

Validated on 7 November 2026.

## Wide-area UV-first mission (current)

- Local/Spark movie: `outputs/uv-detection-pip/pelagic-pip.mp4`: **114.917 seconds, 1600×900, 24 fps, 2758 frames, 64,414,675 bytes**. This is a full Isaac mission recording with independent, synchronized director, scout and wrist-camera products; no camera streaming server runs.
- All **four transfers and eight UV approvals** pass the strict recording validator. Each bleached living recipient and compatible healthy donor is scanned before pickup. Both approval receipts precede harvest; all collection, carrying, placement and mechanical verification records use white light. Dead coral remains excluded. Failed exposure, absent host signal and changed/mismatched registry data stop harvesting in the rejection tests.
- Both visible lamps now use a **50° half-angle / 100° full cone**, versus 24° previously: **7.2× geometric area at the same distance**. The eight accepted scan receipts measure **2.6218–2.6219 m footprint diameter** at approximately 1.1 m. The visible violet pilot makes the UV footprint legible; UV itself is invisible. Actual USD light position/direction are asserted against the detection geometry.
- **98 regression tests pass on Spark.** The two accelerated motion comparisons use a 1e-12 vector tolerance to accommodate platform floating-point rounding; geometry/topology/source immutability and other metadata remain exact. No motion-model production changes were needed.
- **44 preview milestones and 65 movie geometry/pose audits pass.** Six persistent cutting identities and the actual natural-branch contact surfaces remain intact; no roots or replacement colony geometry appears. All eight UV scan frames and the four grasp/release sequences were visually reviewed in the preview and decoded movie review sheets.
- SHA-256 comparison and local MP4 validation are recorded alongside the movie in `transfer-integrity.json` and `validation.json`. Render/composition after scene setup took **1428.8 seconds**; this is an offline workload.
- Detection combines an analytical fluorescence/exposure proxy with observed health and known species/genet metadata. It is **not camera-pixel classification or genotype inference from colour**. Mechanical contact is checked; tissue fusion and recovery remain unmodelled.

## Natural-branch reef recording (historical)

- Combined local/Spark movie: `outputs/pelagic-natural-reef/pelagic-natural-reef.mp4`: **101.458 seconds, 1600×900, 24 fps, 2435 frames, 56,814,673 bytes**. Two chapters: the 25-second current/tissue/light reel, then the 76.458-second natural-branch mission. Joined without re-encoding. Local/Spark SHA-256 verification is recorded in `transfer-integrity.json`.
- Mission: all 24 colonies mapped, 4 mechanical placements verified, donor inventory 6→2, 0 collision-guard violations and 0 duplicate assignments. The episode including the final hold ends at 110.65 simulated seconds. Every recipient remains `bleached_alive`; dead coral is excluded.
- **49 rendered USD geometry/pose audits passed.** The planner chooses actual triangles on the unchanged recipient scan; there is no fabricated recipient tissue branch. A small basal securing compound sits below the living contact band. All six cutting identities, shapes and scales remain fixed; no roots, extra cutting or colony appears. Minimum surrounding workspace clearance is 0.5716 m; maximum rendered-jaw pose error is 1.25e-07 m. The closest contact-band gaps on the actual USD surfaces are 0.562, 0.059, -0.007, 0.003 mm; the full contact band is constrained against excessive penetration.
- Close-up living and bleached colonies use the **150,000-triangle original scan with preserved UV seams**. Matte tissue maps retain source calice occlusion contrast. Bleached living tissue has warm ivory areas and irregular residual pigment islands, rather than a uniform grey tint. The source scan supplies skeletal geometry; tissue and bleaching patterns remain artistic proxies.
- Habitat: 24 registered and 528 decorative colonies, 12 moving fans, 12 living polyp patches and 42 fish. The fixed current camera records **10.73 cm** fan-tip excursion and up to **1.23 mm** polyp-tip displacement. Zero-current controls remain still; hard coral skeletons stay rigid. The damped response is a reduced physical model, not calibrated fluid–structure simulation.
- Detail reel: **600 frames / 25 seconds**; 6 hard-geometry/topology checks, five tissue/light cases and five source-off checks passed. White, blue and UV comparisons use the same bleached colony and fixed camera. UV itself is invisible; the co-aligned visible violet pilot produces the flashlight footprint. A depth-clipped analytical single-scattering pass supplements the native RTX surface lighting; source-to-water shadow transport and spectral response are not calibrated.
- Both robot PiPs are independent synchronized Isaac render products. Twelve decoded movie frames cover grasp, release and retreat for every transfer; nine detail samples cover current motion and all five tissue/light cases. Review sheets are `outputs/natural-reef-pip/movie-contact-sheet.jpg` and `outputs/natural-reef-details/movie-detail-sheet.jpg`.
- **86 automated tests pass**, including natural-contact surface checks, two equivalent motion backends, source/negative controls, thin foreground beam occlusion and asset checksums. Compilation and whitespace checks pass. Render/composition after scene setup took 945.1 seconds for the mission and 327.7 seconds for the detail reel; these are offline workloads, not real-time benchmarks.
- Neither recorder nor assembler starts a server or camera stream. All final MP4s were copied only after completion. Mechanical attachment is verified; tissue fusion and biological recovery are unmodelled. See [research, rendering and scale limits](INSPECTION_AND_CONTACT.md).

The following sections preserve earlier recording evidence.

## Earlier offline package (historical)

- Combined local/Spark movie: `outputs/pelagic-scuba-demo/pelagic-complete.mp4`, **124.792 seconds, 1600×900, 24 fps, 2995 frames, 62,289,296 bytes**. Two chapters: contact mission at 0:00 and lighting cases at 1:19.792. Assembled without re-encoding by `scripts/assemble_offline_demo.py`; its validation passed on Spark and the copied movie's frame count and chapters passed locally.
- SHA-256 checksums of all three local MP4s match the completed Spark originals. Evidence: `outputs/pelagic-scuba-demo/transfer-integrity.json`, `probe-local.json` and `pelagic-complete.validation.json`. Neither recorder nor assembler starts a streaming server.

## White, blue and UV inspection recording (historical)

- `outputs/reef-inspection-lighting/pelagic-inspection.mp4`: **45 seconds, 1600×900, 24 fps, 1080 frames, 6,037,957 bytes**. All **15 cases / 45 lighting views passed**: five illustrative appearance groups × healthy, bleached living and dead, each under white, blue and UV-response modes. Render/composition took 399.5 seconds after setup.
- The white reference and active view use the same robot camera pose and focal length within each case. The mission input, coral/cutting geometry and their poses remain unchanged. Fifteen geometry checks and fifteen source-off checks passed. Nonfluorescent pigment controls and dead controls have zero added host emission.
- All **45 views were decoded from the finished MP4 and visually reviewed**, grouped in `movie-healthy-sheet.jpg`, `movie-bleached_alive-sheet.jpg` and `movie-dead-sheet.jpg`. The lower emission gain and spatial scan texture preserve surface detail. UV itself is invisible; emitted colours are an illustrative RGB proxy, not spectral calibration, genotype classification or proof of recovery.

## Earlier Pocillopora contact fixture (historical)

- Completed recording: `outputs/contact-graft-pip/pelagic-pip.mp4`, rendered on DGX Spark using Isaac Sim 6.0.1, copied locally and independently validated: **1600×900, 24 fps, 1915 frames, 79.791667 seconds**, H.264, 56,250,826 bytes. Render/composition took 715.8 seconds after scene setup; this is an offline workload, not a real-time benchmark.
- **48 USD geometry/pose audits passed** across every manipulation phase. All six cutting identities, point/topology hashes and scales remain fixed. Four cuttings are placed and two remain on donors. No roots, new colony or duplicate cutting appears at release. Maximum fragment pose error is 0 m; maximum rendered-jaw error is 1.05×10⁻⁷ m.
- All four recipients remain `bleached_alive`; all donors are observed healthy colonies with matching known genet and species. Dead coral receives no cutting. All 24 colonies are mapped, with four verified mechanical placements, zero duplicate assignments and zero collision-guard violations. The episode including the final hold ends at 118.4 simulated seconds.
- The measured contact-band gaps are −0.676, −0.341, −0.561 and −0.283 mm: small intentional proxy overlaps, within the allowed −3 to +1.5 mm tolerance. The recipient's permanent tissue branch is the sole contact-clearance exception. Other coral/rock workspaces retain at least 0.5568 m clearance. This verifies geometric alignment, not contact forces, tissue fusion or adhesive performance.
- **Twelve frames decoded from the completed MP4** cover closed grasp, release and empty-hand retreat for all four transfers. See `outputs/contact-graft-pip/movie-contact-sheet.jpg` and `decoded-review/frames.json`. The same rootless cutting stays visible against the recipient branch after withdrawal. Both robot PiPs are independent synchronized render products. Survey markers and stakes are hidden when diagnostic telemetry is off.
- Habitat: **604 registered/decorative colonies**, including 88 scan-based instances, plus **24 flexible fans and 42 fish**. Smithsonian *Pocillopora damicornis* geometry supplies natural skeletal proportions; scenario tissue colours distinguish living, bleached and dead controls. Original scan normal detail, textured branchlets, pitted grounded boulders, reef pavement and sand maps remain bundled offline.
- Flexible fans use deterministic current-driven damped bending with fixed roots and bounded deformation. Stony skeletons and carried cuttings remain rigid. The three wrist modes—white, blue and UV-response proxy—are all witnessed in the mission recording.
- **66 automated tests passed**, including same-genet pairing and incompatible/unknown-lineage holds, contact geometry, retained grasp stems, source-off/negative fluorescence controls, fan response, substrate bounds and previous mission regressions. All eight Pocillopora asset checksums passed; three health-state variants retained natural aspect, requested bounds and unit normals. Compilation and whitespace checks passed.
- The contact mechanism follows the experimental principle in [Collins et al. 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13665998/). The enlarged 14 cm cutting and in-situ robot fixture remain engineering proxies. Biological recovery is unmodelled, and RGB fluorescence is illustrative rather than a spectral/genetic measurement. See [research and rendering boundaries](INSPECTION_AND_CONTACT.md).

## Three-state reef and bleached-only assistance (historical limestone outplant)

- Recording: `outputs/bleached-reef-habitat/pelagic-pip.mp4`; category and action reviews: `outputs/bleached-reef-review/`.
- Completed Isaac render: **1600×900, 24 fps, 1744 frames, 72.666667 seconds**, H.264 MP4, 48,684,136 bytes. Passed `validate_demo.py` on Spark and after local copy. Rendering/composition took 286.3 seconds after setup; no server or camera stream was started.
- **50 USD geometry/pose audits passed** through every manipulation phase. All six cutting meshes retain their topology and size; mounts have at least 0.55 m clearance; no generated roots or duplicate coral appear. Twelve grasp/release/retreat frames decoded from the completed MP4 were inspected across all four transfers.
- The habitat contains **604 colonies**: 24 registered mission colonies and 580 decorative specimens (320 healthy, 140 bleached living, 120 dead). Connected limestone pavement, clustered branching thickets, layered plates and massive forms replace sparse individual placements. 82 colonies include bundled Smithsonian scan geometry; the original museum plinth is removed.
- Healthy donors retain colour and intact structure; bleached living colonies retain pale intact skeletons; dead colonies have dark algae pigments, truncated branches, eroded massive surfaces and chipped plates. These are artistic state cues, not a field diagnostic classifier.
- **42 fish** in three deterministic schools use continuous local motion, tail animation, reef/vehicle avoidance and worksite exclusions. Their meshes are authored once and only transforms change. Default and smaller-world tests exercise clearance, spacing and motion continuity.
- Only `bleached_alive` recipients are eligible. All four placements target coral-007 through coral-010; fragments originate from healthy donors. Dead coral is excluded even under an erroneous planting-region policy, and no operation changes biological health.
- The cinematic episode completes at 111.50 simulated seconds, with a final recording hold to 113.05 seconds: all 24 colonies observed, four assistance placements verified, six original cuttings conserved (four placed, two still on donors), no duplicate assignment and zero collision-guard violations.
- **43 automated tests pass**, including three checks for bundled scan checksums, indexed geometry integrity, dimensions, finite attributes, unit normals and independent returned meshes. Python compilation and whitespace checks pass.
- Visual review covers 34 milestone composites across all four transfers plus three category views. The director avoids foreground reef geometry and predicted arm occlusion. The same rootless cutting and fixed limestone mount remain visible through release and empty-hand withdrawal; the robot tool camera provides the complementary close view.
- Healthy cutting placement beside a bleached colony is an engineering assistance demonstration, not a cure for bleaching. Perception remains synthetic, manipulation kinematic and biological recovery unmodelled. See [ASSUMPTIONS.md](ASSUMPTIONS.md).

## Living-donor transfer recording (historical, superseded target policy)

- Local and Spark file: `outputs/donor-transfer-pip/pelagic-pip.mp4`.
- Actual Isaac Sim 6.0.1 / GB10 render: **1600×900, 24 fps, 1820 frames, 75.83 seconds**; H.264 MP4, 36,043,223 bytes. Completed movie copied locally; no live feed, HTTP server or SSH tunnel.
- Dense Great Barrier Reef-inspired artistic mosaic: **285 coral colonies**, comprising 24 registered mission colonies and 261 low-profile scenery specimens. Scenery includes 136 healthy, 60 bleached living and 65 dead colonies, across branching, massive and plating forms.
- Collection occurs on observed **living donor colonies**, with no nursery table. Source branch cuttings exist from scene creation. A single persistent rootless mesh follows explicit approach, close, detach, retract, carry, lower, secure, open, retreat and verify phases.
- Each cutting is seated on a **pre-existing limestone surface**. Mounts reserve at least 0.55 m beyond every coral/rock footprint and stay 0.70 m apart. The jaws open while the cutting stays seated; the empty hand withdraws. Planting creates no roots, colony, duplicate carried mesh, growth or scale change. Dead-zone biological health remains unchanged.
- Independent synchronized cameras: Director 1280×720, ScoutOptical 400×240, WorkerTool 400×240. The worker camera is mounted on a visible wrist bracket. Both PiPs are real render products with their own depth-based underwater processing.
- Complete cinematic mission: **160.50 simulated seconds**, 24/24 colonies mapped, four transfers verified, finite donor stock 6→2, zero duplicate reservations and zero collision-guard violations. Transferred IDs are fragment-005, fragment-006, fragment-004 and fragment-003.
- **48 actual USD geometry/pose audits passed** across every manipulation phase: all six Cutting paths and point/topology hashes unchanged; fixed world scale; no new `/World` scene geometry; fragment base error 0 m and maximum rendered-jaw error 8.54×10⁻⁸ m. See `geometry-validation.json`.
- **32 automated tests pass**, including persistent IDs, stock conservation, donor/recipient health, continuous pose/yaw handoffs, clamp-before-detach, jaw-coupled carrying, opening-before-withdrawal, mesh topology and independent PiP composition. Python compilation and whitespace checks pass.
- `scripts/validate_demo.py` passed on Spark and on the locally copied movie: dimensions/rate/frame count, completed mission, independent cameras, no server, conserved fragment identities and full-phase geometry evidence.
- Visual QA inspected 34 milestone composites covering all four transfers and release/retreat frames for all four transfers decoded from the finished MP4. The cutting is small in the wider carry shot; the worker's camera provides the close view.
- Offline rendering/composition took approximately **281.7 seconds** after setup. This is not a real-time renderer benchmark.

Useful video positions: first closed grasp at 9.29 s, visible carry around 13.83 s, first open-jaw release at 23.00 s and empty-hand retreat at 25.25 s. Final release/retreat: 71.75/73.13 s. Use `--preview-stills --all-transfers` to reproduce the 34 review composites.

Reproduce:

```bash
/home/smint/isaacsim/python.sh -u scripts/render_demo.py --config configs/cinematic.json \
  --fps 24 --max-frames 2000 --samples 2 --save-frames --output outputs/donor-transfer-pip
python3 scripts/validate_demo.py outputs/donor-transfer-pip
```

Manipulation is a kinematic visual approximation with timed detachment/attachment. This evidence does not establish force closure, tissue-safe harvesting, adhesive chemistry, full hydrodynamics or biological recovery. Variables and assumptions are documented in [ASSUMPTIONS.md](ASSUMPTIONS.md).

The older sections below preserve earlier recording evidence and describe earlier scene versions.

## Improved offline PiP recording

- File: `outputs/pelagic-realistic-pip/pelagic-pip.mp4`, copied to the same relative path in the local workspace.
- Actual Isaac Sim 6.0.1 Spark render: **1600×900, 24 fps, 1012 frames, 42.166667 seconds**; H.264 MP4, approximately 20.54 MB.
- Three independent synchronized render products: `/World/Cameras/Director` (1280×720), `/World/Cameras/ScoutOptical` (400×240), `/World/Cameras/WorkerTool` (400×240). Two Kit updates per output frame reduce temporal lag.
- Complete mission: 142.2 simulated seconds, all 24 colonies mapped, four verified attachments, inventory 6→2, distinct source fragment indices 5/4/3/2. Biological health remains unchanged by attachment.
- Offline-only execution: recorder imports no HTTP server and reports `server_started: false`; no console listener was present. The completed MP4 was transferred as a file.
- Variable-speed replay accelerates transit and emphasizes collection/attachment. Cinematic configuration lengthens the collection/adhesive dwells so gripper motion and contact pose can be reviewed clearly.
- Visual QA: inspected collection/planting main-camera previews and both PiPs, corrected a tool-camera arm occlusion, added obstruction-aware director angles and close-up push-in, and checked a frame from the actual final recording.
- Materials: bundled CC0 photographic sand/reef substrate maps and original coral microdetail, with indexed smooth coral geometry. Exported USD requires these assets/path remapping; it is no longer a single-file asset.
- **26 automated tests pass**, including mesh winding/normal/topology contracts, full-mission scheduling and distinct PiP composition. Python compilation and whitespace checks pass.
- `scripts/validate_demo.py` verifies frame count/rate/dimensions, camera independence, synchronized metadata, no server, mission completion and source-fragment identity. It passed on Spark and the locally copied video.

Reproduce:

```bash
/home/smint/isaacsim/python.sh -u scripts/render_demo.py --config configs/cinematic.json \
  --fps 24 --max-frames 1200 --samples 2 --output outputs/pelagic-realistic-pip
python3 scripts/validate_demo.py outputs/pelagic-realistic-pip
```

The sections below preserve the earlier baseline's validation history.

## Actual DGX Spark renderer run

- Hardware: NVIDIA GB10, aarch64, driver 580.178.04.
- Installed runtime: `6.0.1-rc.7+release.42383.32955d8d.gl` at `/home/smint/isaacsim`.
- Project: `/home/smint/pelagic-reef`.
- Full run: 1200 renderer steps, fixed 1/30-second mission ticks at speed 4, 160 simulated seconds.
- Result: **PASS**. All 24 colonies observed; four attachments verified; six nursery fragments reduced to two; no duplicate task assignments; collision guards prevented penetrations. Dead colonies retain their biological state.
- Real camera outputs: processed spectator PNG 960×600 and downward ROV PNG 640×400, both nonempty; camera error is null. Full self-contained USD scene exported.
- Backup video: 400 actual rendered spectator frames encoded as a 40-second H.264 MP4 at 10 fps. Review is offline; no optical-flow-generated frames or external footage.
- Final offline-default smoke test passed with the follow camera, real ROV/spectator capture and no open console port on 8765. Five separate review stills were rendered at survey, collection, attachment and completion milestones without any server.
- The cold first startup took around three minutes; the next initialization completed in roughly ten seconds. Offline rendering and encoding speed are distinct from video playback speed. This is not a real-time frame-rate benchmark.

Reproduce evidence validation:

```bash
python3 scripts/validate_output.py outputs/validated
```

Evidence is in `outputs/validated/`, `outputs/isaac-full-v2.log`, `outputs/pelagic-overview.mp4` on Spark. The movie and final state are also copied to the local workspace `outputs/`.

## USD integration

CPU-only validation using Spark's bundled USD libraries exercised the full mission through COMPLETE at approximately 128.3 simulated seconds. Checked every mesh topology, finite coordinates and authored normals, both vehicle transforms, four camera transforms, target-aware visual arm link lengths, null preattachment target handling, and reset/rebuild preserving `/Render`.

## Automated tests

20 tests pass via `python3 -m unittest discover -s tests -v`: deterministic replay, full default mission, visibility/occlusion-limited observations, safe obstacle routing, stock conservation, strong current and finite bounds, pause/reset, invalid water rejection, disabled worker hold/resume, depth-based optics, HTTP controls and camera reset invalidation. Python compilation, JavaScript syntax checking and Git whitespace checks pass.

## Browser development checks

The optional WebGL console was tested in Chrome at desktop and mobile widths. Live telemetry, observed-only map, water controls, pause/resume/reset, view controls and explicit mode labelling were checked. The actual Isaac spectator image and ROV feed were also observed in the in-app browser during validation. **The live feed and its SSH tunnel were then closed at the user's request. The Isaac launcher now defaults to no server.**

## Practical limits

Mission perception is analytical synthetic sensing, vehicle dynamics use a reduced translational model, and manipulation uses a visual analytical arm with abstract attachment. This validates the implemented demo loop, not full underwater sensor realism, floating-base contact physics or biological restoration efficacy. See `ASSUMPTIONS.md`.
