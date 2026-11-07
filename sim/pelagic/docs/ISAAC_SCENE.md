# Isaac Sim reef and visible fragment transfer

`reefsim/isaac_scene.py` authors the OpenUSD world after Isaac Sim 6.0's `SimulationApp` starts. All textures are bundled for offline use. Exported USDA includes material asset references; retain `assets/` or remap paths when moving the stage. Dimensions use metres with Z-up.

## Reef appearance

The scenery is inspired by Great Barrier Reef patch mosaics rather than a surveyed location. Living zones have dense branching, plating and massive coral; bleached living zones are pale; dead zones contain exposed skeleton, algae and rubble with lower live cover. The 24 registered mission colonies have clear operating space. Hundreds of supplementary low-profile specimens provide visual density without being hidden perception targets or tall unmodelled obstacles.

Coral meshes use smooth indexed normals, curved branches, rounded tips and skeletal cups. Living contact colonies use a Smithsonian *Pocillopora damicornis* scan with preserved proportions, original normal detail and scenario tissue colours. Massive scenery forms are low domes with shallow surface relief. Sand and pitted limestone use bundled photographic PBR maps; calice normal/roughness maps add procedural coral microdetail. Sources and licenses are in [ASSETS.md](ASSETS.md).

Blue-green illumination, depth haze and drifting marine snow suggest submerged seawater. The scene omits a surface sheet to avoid an artificial square shadow. RTX fog and depth-based optical processing are artistic approximations; this is not calibrated radiative transfer, fluid simulation or a validated underwater depth sensor.

## No table and no generated roots

The source is a living donor colony. Each small cutting is already visible at a donor branch tip when the scene is built, with a short connection to the parent. After detachment, the donor and its cut stub remain in place.

The renderer maintains one persistent rootless cutting mesh for each fragment ID. In `configs/contact_graft.json`, that same object is held between the jaws, carried across the reef and secured against an existing living recipient branch of the same known genet. A support sits below the tissue interface. The historical `configs/cinematic.json` mode instead uses a separate limestone mount. Placement creates no branch cluster, roots, full colony or scale-growth effect. The cutting's dimensions, seed and yaw continuity remain fixed. Other coral/rock workspaces retain 0.55 m clearance; only the intended recipient contact surface is exempt. See [contact geometry and research limits](INSPECTION_AND_CONTACT.md).

## Explicit manipulation sequence

| State | Visible behaviour |
| --- | --- |
| `NAVIGATE_TO_DONOR` | Travel to an observed healthy source with open/stowed jaws |
| `APPROACH_FRAGMENT` | Reach toward the donor cutting with open jaws |
| `CLOSE_GRIPPER` | Close the padded jaws around the stem |
| `DETACH_FRAGMENT` | Keep the grasp closed while the branch connection is detached |
| `RETRACT_FRAGMENT` | Lift/retract the same cutting clear of the donor |
| `NAVIGATE_TO_SITE` | Carry it visibly in the closed gripper |
| `LOWER_FRAGMENT` | Align the held cutting with the recipient tissue interface |
| `SECURE_FRAGMENT` | Hold tissue contact while securing the basal support |
| `OPEN_GRIPPER` | Open the jaws while the seated cutting stays in place |
| `RETRACT_GRIPPER` | Withdraw the empty tool; the placed cutting remains fixed |
| `VERIFY_ATTACHMENT` | Inspect the released cutting before selecting another task |

The core publishes `gripper_world` as the jaw-centre coordinate and `gripper_open` from 0 closed to 1 open. A fragment's `base_world` identifies its cut base. During carrying, the base is 45 mm below the jaw centre. At release the same base already occupies `planting_point`, avoiding a visible snap or newly generated object. A retained grasp-yaw offset prevents rotation jumps at detachment.

## Cameras and offline composition

| Camera path | Purpose |
| --- | --- |
| `/World/Cameras/Overview` | Reef overview |
| `/World/Cameras/ROV` | Survey ROV downward view |
| `/World/Cameras/Chase` | Restoration vehicle/action follow view |
| `/World/Cameras/Top` | Overhead mission area |
| `/World/Cameras/Director` | External filming camera, clear worksite angle and close-up framing |
| `/World/Cameras/ScoutOptical` | Independent SCOUT-01 downward camera for its PiP |
| `/World/Cameras/WorkerTool` | Independent RESTORE-02 inspection camera for its PiP |

All camera transforms update from the same mission snapshot. The tool camera moves with a visible bracket and pod on the gripper, outside the arm's main plane. A short near clip excludes its own protective housing. The director emphasizes the approach, closed grasp, detachment, carrying, lowering, release and retreat; it is separate from both robot cameras.

`scripts/render_demo.py` pulls three synchronized RGB/depth render products, composites the two robot PiPs and writes the MP4 through a local ffmpeg pipe. It creates no HTTP server. `--preview-stills` renders ten labelled milestone checks; add `--all-transfers` for 34 checks covering all four transfers before the full movie. The `render_review.py` helper forwards to this workflow for compatibility.

## Physics and biological boundary

The core integrates a reduced translational buoyancy/drag/thrust model. The scene displays those vehicle poses, and analytical visual IK fits the arm to the jaw target. Static terrain and reef collision APIs are authored for future physics work, but operational collision guards currently belong to the core.

Twenty-four flexible background fans use bounded, current-driven damped bending with anchored roots and updated normals. Hard coral and transported cuttings stay rigid. Wrist white/blue/UV modes drive cone/range-gated RGB host-emission proxies; UV itself is invisible. The controlled inspection recorder keeps camera poses fixed across modes and checks source-off, nonfluorescent and dead controls. Neither motion nor fluorescence is calibrated physical simulation.

Visible gripping and continuous object transfer do not establish frictional force closure, tissue-safe cutting, adhesive chemistry or fully actuated floating-base manipulation. These remain timed kinematic approximations. No cuRobo/cuMotion integration is required.

Released cuttings are engineering outcomes. Surrounding dead colonies keep their dead biological state; the simulation predicts no fusion, roots, growth, survival or ecological recovery. Debug inspection/path overlays are optional and separate from coral appearance.

## Rendering current milestones

```bash
/home/smint/isaacsim/python.sh -u scripts/render_demo.py \
  --config configs/contact_graft.json --preview-stills --all-transfers \
  --output outputs/contact-graft-review
```

For a movie, omit `--preview-stills`, use `--fps 24 --max-frames 2600 --samples 4`, and choose an output directory. Final media and mission checks are recorded in [VALIDATION.md](VALIDATION.md).

The scene can rebuild its `/World` subtree after reset while preserving `/Render` and stable camera paths. The runner should rebuild when the seed/layout changes. Textures remain offline local assets throughout.
