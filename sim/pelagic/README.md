# Reef Rescue AUV — underwater simulation

This standalone simulation checkpoint lives under `sim/pelagic/` in the team repository. Run the commands below from this directory. Generated videos, preview frames and runtime logs remain local in the ignored `outputs/` directory; the bundled geometry, textures and third-party license/provenance records are committed. See [team integration status](../README.md).

An underwater coral-transfer simulation for **Isaac Sim 6.0.x on DGX Spark**, designed for offline video review or viewing directly on the Spark desktop.

SCOUT-01 surveys the reef. In the current `configs/natural_reef.json` scenario, RESTORE-02 provisionally pairs an observed bleached living recipient with a healthy donor of known matching species and genet. It scans both under wide-area UV and requires both approvals before harvesting. Under white light it closes its gripper around a branch cutting, detaches and carries that same cutting, then secures it in direct contact with living tissue on a bleached recipient. **Collection is from living coral, with no nursery table. Planting does not generate roots or a new coral colony.**

The environment is a Great Barrier Reef-inspired artistic reef mosaic: dense branching, plating and massive coral in the living patch; pale bleached living coral; sparse dead skeletons, algae and rubble in degraded patches. It is not a reconstruction of a surveyed location. The 24 registered mission colonies are separate from the hundreds of decorative specimens that give the reef its visual density.

The three health categories have distinct appearance and mission policy:

| Category | Appearance | Robot policy |
| --- | --- | --- |
| Healthy | Coloured living tissue, dense intact thickets and plates | Approved donor source only |
| Bleached, still alive | Warm ivory tissue, residual pigment islands and living polyps on intact branches | Only eligible assistance recipient |
| Dead | Dark algal staining, broken crowns, eroded/chipped skeletons | Excluded from assistance |

The contact scenario is an enlarged engineering adaptation of same-genet *Pocillopora damicornis* contact research. It checks mechanical placement, not tissue fusion or bleaching recovery; the recipient remains `bleached_alive`. Known lineage comes from an explicit scenario registry, not an inference from colour. The historical `configs/cinematic.json` scenario instead demonstrates a separate limestone outplant beside the recipient. See [research basis and limits](docs/INSPECTION_AND_CONTACT.md).

The habitat includes continuous reef pavement, interlocking colonies, pitted limestone boulders, current-driven flexible fans and three schools of small reef fish. Living and bleached contact colonies use a bundled Smithsonian *Pocillopora damicornis* scan, alongside the earlier *Acropora secale* asset. Close-up mission colonies retain the scan’s full 150,000 triangles and original UV seams. Matte tissue maps preserve calice detail; partly bleached colonies retain irregular pigment islands. Hard coral skeletons remain rigid; larger fans and living polyp tentacles respond to oscillating current with bounded damped motion. Fish use deterministic local motion and avoidance rules. All assets and motion run offline. See [Pocillopora provenance](docs/POCILLOPORA_SCAN.md) and [Acropora provenance](docs/SCANNED_CORALS.md).

## Render and review offline

The latest team iteration adds connected gripper slides, central natural tissue contact, and current-driven station keeping. See [the changes and measured checks](docs/CONNECTED_CONTACT_CURRENT.md). Record with `scripts/render_team_demo.py --current-review` to include the fixed-camera flow comparison.

The current **UV-first offline demo is 1:55**, at `outputs/uv-detection-pip/pelagic-pip.mp4` (2758 frames, 1600×900, 24 fps). All four transfers require a UV scan of the living bleached recipient and compatible healthy donor before harvesting; pickup, transport, placement and mechanical verification use white light. Both lamps have a 100-degree full cone; the scan footprint is about 2.62 m across at 1.1 m distance. The movie was rendered on Spark, copied locally, visually reviewed and validated, with matching SHA-256 hashes. Detailed evidence is in [validation evidence](docs/VALIDATION.md).

The previous 1:41 current/tissue review plus natural-branch mission remains at `outputs/pelagic-natural-reef/pelagic-natural-reef.mp4`; it predates the UV-first mission gates.

The current contact recorder writes `outputs/uv-detection-pip/pelagic-pip.mp4`. Contact is chosen on the actual scanned recipient branch; the only added attachment geometry is a small basal securing pad. Its action view includes **two synchronized, independently rendered robot-camera PiPs**:

- SCOUT-01: downward hull camera for surveying.
- RESTORE-02: wrist-mounted tool camera showing the jaws, cutting and work surface.

Render on Spark without a desktop window or live feed:

```bash
cd /path/to/great-barrier-defenders/sim/pelagic
/home/smint/isaacsim/python.sh -u scripts/render_demo.py \
  --config configs/natural_reef.json --fps 24 --max-frames 4000 --samples 4 \
  --quality 17 --output outputs/uv-detection-pip
python3 scripts/validate_demo.py outputs/uv-detection-pip
```

The recorder creates **no server and no network camera stream**. It writes the completed MP4 through a local ffmpeg pipe. Copy that file after the process exits. The first full transfer is emphasized at near real time; transit and later operations are accelerated and labelled. The schedule follows the actual mission state rather than inventing actions in the editor.

For 44 milestone camera checks covering all four transfers before the movie:

```bash
/home/smint/isaacsim/python.sh -u scripts/render_demo.py \
  --config configs/natural_reef.json --max-frames 4000 --preview-stills --all-transfers \
  --output outputs/uv-detection-review
```

These stills cover survey, recipient/donor UV scans, approach, closed grasp, detachment, carrying, placement, release, retreat, verification and completion. Three additional `habitat-*.png` views compare the healthy, bleached living and dead regions. The `render_review.py` compatibility entry point forwards to this same current recorder.

For the fixed-camera current comparison and tissue/light close-ups:

```bash
/home/smint/isaacsim/python.sh -u scripts/render_reef_details.py \
  --config configs/natural_reef.json --samples 3 --quality 17 \
  --output outputs/natural-reef-details
```

This writes `pelagic-reef-details.mp4`: eight seconds of moving soft tissue beside a zero-current reference, followed by healthy, partly bleached and dead close-ups. White, blue and UV comparisons use the same bleached colony and camera pose. UV is invisible; the co-aligned visible violet aiming light supplies the flashlight footprint. Host fluorescence is a spatially gated RGB proxy. Neither colour nor brightness establishes genotype or recovery. The recorder checks fixed cameras, unchanged hard coral geometry, fixed soft-mesh topology, source-off response and zero-current controls.

The earlier combined package used the following assembly command. Keep the current UV-first mission as its own clip so its detection-before-action sequence remains explicit:

```bash
python3 scripts/assemble_offline_demo.py \
  --details outputs/natural-reef-details --mission outputs/natural-reef-pip \
  --output outputs/pelagic-natural-reef/pelagic-natural-reef.mp4
```

The detail reel comes first, followed by the complete natural-branch contact mission. The assembler checks both input validation files, matching video formats, frame count and duration, and records SHA-256 hashes.

The validated 72.7-second `outputs/bleached-reef-habitat/pelagic-pip.mp4` preserves the earlier separate limestone outplant. `outputs/pelagic-overview.mp4`, `outputs/pelagic-realistic-pip/` and `outputs/donor-transfer-pip/` are older iterations. None demonstrates the current direct-contact protocol. Recording-specific completion evidence belongs in [docs/VALIDATION.md](docs/VALIDATION.md).

## View directly on the Spark desktop

The installed runtime detected for this project is `/home/smint/isaacsim`, version `6.0.1-rc.7+release.42383.32955d8d.gl`. Use its Python launcher.

In a terminal on the **Spark desktop**, where a local display is available:

```bash
cd /path/to/great-barrier-defenders/sim/pelagic
bash scripts/run_spark.sh --config configs/natural_reef.json --view follow --no-camera
```

`--no-camera` avoids unnecessary offscreen capture when using the native viewport. The launcher starts no HTTP server by default. An optional development telemetry server requires explicit `--serve`; it is not used for offline review. No cuRobo, cuMotion, ROS installation or OceanSim extension is required.

For another installation location:

```bash
ISAAC_INSTALL=/path/to/isaacsim bash scripts/run_spark.sh --config configs/natural_reef.json --view follow --no-camera
```

Bundled materials require no runtime downloads. Keep the repository's `assets/` directory with the project. Exported USD references these material files, so remap asset paths when moving a stage. Sources and licenses are in [docs/ASSETS.md](docs/ASSETS.md).

## Mission and fragment lifecycle

The survey vehicle follows reef transects and a second-angle rubble inspection. Only observations inside the analytical camera cone, within water visibility and outside rock occlusion enter the shared map. The contact planner pairs an observed bleached living recipient with an observed healthy donor of the same known genet and species that still has an available cutting. Unknown or incompatible lineages hold without harvesting; dead colonies are excluded.

The operation is explicit:

```text
UV-scan bleached recipient → UV-scan compatible healthy donor → approve both
→ switch to white → approach with open jaws → close on stem → detach
→ retract the held cutting → carry to compatible bleached living colony
→ align tissue contact → secure base → open jaws → withdraw empty gripper → verify
```

Each cutting exists from scene creation and retains one ID, seed, shape and size throughout this sequence. Its record moves through `attached_to_donor`, `grasped`, `carried` and `placed`. The base follows the closed gripper during transport; it stays fixed in the contact fixture while the jaws open and the arm retreats. Placement does not create a second specimen, grow roots or change the recipient's biological health.

The donor parent colony remains alive. Dead and unstable regions are not used as sources. Bleached living colonies are monitored, and unsafe rubble is excluded from planting.

## Configure the experiment

Use JSON overlays with `--config`:

```bash
python3 -m reefsim --config configs/reef.json --episode 240 --output outputs/episode.json
```

Important controls include layout seed, region policies, water visibility/current, vehicle mass/displacement, drag and thrust limits, camera cone, `donors.fragments_per_colony`, `donors.max_fragments`, and the individual `mission.*_duration` manipulation timings. [configs/cinematic.json](configs/cinematic.json) lengthens the visible manipulation phases for the historical limestone outplant. [configs/contact_graft.json](configs/contact_graft.json) selects `mission.attachment_method="same_genet_contact"`, compatible lineage pairing, contact fixtures and automatic wrist inspection modes.

[configs/natural_reef.json](configs/natural_reef.json) is the current visual preset. Tune `water.current` (m/s), `render.soft_coral_height` / `soft_coral_radius`, `inspection.half_angle_degrees`, the three lamp intensities and `render.visible_beam_gain`. `inspection.auto_light_power` adjusts power with target distance; `render.visible_beam_scattering` controls the offline depth-clipped water glow. These remain illustrative physical/optical controls, not calibrated biological measurements.

Coordinates use **metres, Z-up**, with the seabed around Z=0 and surface at Z=8. Public vehicle yaw is in radians. `gripper_world` is the authoritative jaw-centre coordinate; `gripper_open` ranges from 0 closed to 1 open. `planting_point` identifies the chosen natural-branch attachment base (or limestone mount in the baseline mode), and each fragment's `base_world` gives its cut-base position.

Vehicle translation integrates a reduced buoyancy/drag/thrust model. Isaac renders those poses, while an analytical visual arm follows the jaw target. Perception uses synthetic visibility-limited labels. Frictional contact, cutter forces, glue chemistry, full six-degree-of-freedom hydrodynamics and biological recovery are not simulated.

See [variables and assumptions](docs/ASSUMPTIONS.md), [scene implementation](docs/ISAAC_SCENE.md), [validation evidence](docs/VALIDATION.md) and [references](docs/REFERENCES.md).

## Test

```bash
python3 -m unittest discover -s tests -v
python3 -m reefsim --episode 240 --output outputs/episode.json
```

Tests cover deterministic replay, observation limits, source/target eligibility, same-genet contact pairing and mismatch holds, inspection controls, bounded coral motion, stock conservation, closure before detachment, continuous fragment position/orientation, carrying pose, release before retreat and complete four-placement missions. The default scenario has six available donor cuttings; a completed four-placement mission leaves two attached to their donors.

The mission core uses the Python standard library. Rendering and optical/composition tests use NumPy and Pillow; MP4 recording uses ffmpeg. The portable WebGL console remains a development preview and is not the authoritative view of the current manipulation or dense reef geometry. Use the native Isaac viewport or offline MP4 for visual review.
