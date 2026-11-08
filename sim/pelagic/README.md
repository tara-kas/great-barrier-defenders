# Reef Rescue AUV — mission runtime and simulation

`sim/pelagic` contains the browser mission, its Python gateway, local and hosted model services, and a separate Isaac rendering path. Start with the browser pipeline below for the Gemma-powered loose-fragment mission. Run commands in this guide from `sim/pelagic/` unless a repository-root command is specified.

## Browser mission

The browser inspects and collects registered, already-detached coral stock, transports the same fragment to a compatible recipient and verifies mechanical attachment. Healthy colonies remain intact. Camera appearance and registry eligibility are independent inputs.

```text
Tool-camera image → Gemma visual assessment → validated target-bound evidence
Registered source/recipient eligibility ────────────────┘
                → native cuOpt route → local policy → browser safety/controller
                → collect → transport → place → verify
Held issue → Argon context and visual checks → fresh matching Gemma assessment
```

| Component | Identity and role | Entry point |
| --- | --- | --- |
| Gemma | `gemma-4-E4B-it`, weights `google/gemma-4-E4B-it`; image appearance, fragment visibility and gripper state | `reefsim/lab_server.py`, `scripts/modal_lab_backend.py` |
| Gemini Argon | `gemini-4-argon`; bounded contextual advice, rescan/hold/abort and optional episode review | `ArchitectureAdapters.assist` / `review` in `reefsim/lab_server.py` |
| NVIDIA cuOpt | Native route selection among declared alternatives | `scripts/cuopt_route_adapter.py` |
| Local policy | `reef-local-policy-v1`; registry and visual-evidence checks | `local_mission_decision` in `reefsim/lab_server.py` |
| Controller and physics | Mission progression, motion, grip, identity and attachment checks | `web/lab/simulation.mjs` |
| Camera and UI | Captures, service calls, operator controls and recording | `web/lab/scene.mjs`, `web/lab/app.mjs` |

### Launch and run

Configure actual services using the root [setup guide](../../SETUP.md). The local gateway reads exported environment variables; the hosted gateway uses private runtime secrets.

```bash
python3 scripts/run_lab.py
```

Open `http://127.0.0.1:8090/lab/`. Load [reef_lab_compact_recovery.json](configs/reef_lab_compact_recovery.json) through **Environment builder → Import JSON**, select **Robot + base**, wait for Gemma and cuOpt readiness, and start the mission. **Export** saves the episode and model/solver activity. Use the current, sensor, drop and placement controls to exercise the [documented scenarios](../../docs/SCENARIOS.md).

For service deployment, follow the [Modal gateway guide](docs/ARCHITECTURE.md#integrated-authenticated-modal-deployment), [hosted Site guide](sites/reef-lab/README.md), or [Spark edge guide](../../docs/EDGE_DEPLOYMENT.md). Gemma and cuOpt run on Modal for the hosted path or locally on Spark for the edge path. Argon uses the Google Interactions API. The browser retains local safety authority.

### Test

Install dependencies using [SETUP](../../SETUP.md#regression-checks), then run:

```bash
node --test tests/lab-*.test.mjs
python3 -m unittest tests.test_lab_server tests.test_live_feed tests.test_live_stream_capture
```

The [architecture reference](docs/ARCHITECTURE.md) describes endpoints, contracts, freshness, readiness and assistance. The [file guide](../../docs/CODE_MAP.md) maps browser, Python, edge and research modules. Test providers are controlled doubles; actual service receipts retain their own episode provenance.

## Isaac renderer reference

The Isaac Sim 6.0.x path builds and renders a separate reef scene on NVIDIA hardware. Its Python simulation supplies vehicle poses and analytical visibility observations. An independent camera/state feed can be displayed read-only in the browser; browser mission actuation and reduced physics remain in `web/lab/simulation.mjs`.

The [natural reef preset](configs/natural_reef.json) uses the attached-donor contact scenario: SCOUT-01 surveys, RESTORE-02 inspects a registered donor and recipient, detaches a cutting and secures it to a compatible recipient. This renderer configuration has its own fragment lifecycle and does not select the browser's loose-stock mission. Known species and genet come from the scenario registry. Mechanical placement leaves the recipient's biological state unchanged.

The environment combines reef pavement, coral specimens, rocks, flexible fans and fish. Smithsonian *Pocillopora damicornis* and *Acropora secale* scans supply geometry; tissue colours and reef composition are artistic reconstructions. Hard coral skeletons remain rigid while bounded soft-tissue motion follows the configured current. See [assets and licenses](docs/ASSETS.md), [Pocillopora geometry](docs/POCILLOPORA_SCAN.md), [Acropora geometry](docs/SCANNED_CORALS.md) and [contact mechanics](docs/INSPECTION_AND_CONTACT.md).

### Render a scene

Set `ISAAC_INSTALL` to the installed Isaac directory. Keep the repository's `assets/` directory alongside the code; exported USD stages reference those materials. MP4 output uses ffmpeg.

```bash
export ISAAC_INSTALL=/absolute/path/to/isaacsim
"$ISAAC_INSTALL/python.sh" -u scripts/render_demo.py \
  --config configs/natural_reef.json --fps 24 --max-frames 4000 --samples 4 \
  --quality 17 --output outputs/uv-detection-pip
python3 scripts/validate_demo.py outputs/uv-detection-pip
```

The recorder writes `pelagic-pip.mp4` with survey and tool-camera views through a local ffmpeg pipe. It follows the configured simulation state and labels accelerated transit. `--preview-stills --all-transfers` exports milestone images to the selected output directory. Generated videos, frames and logs stay under ignored `outputs/`.

Render fixed-camera tissue/current/light comparisons with:

```bash
"$ISAAC_INSTALL/python.sh" -u scripts/render_reef_details.py \
  --config configs/natural_reef.json --samples 3 --quality 17 \
  --output outputs/natural-reef-details
```

### Open the native viewport

On the GPU machine with an available desktop display:

```bash
ISAAC_INSTALL=/absolute/path/to/isaacsim bash scripts/run_spark.sh \
  --config configs/natural_reef.json --view follow --no-camera
```

`--no-camera` avoids offscreen capture when using the native viewport. An optional development telemetry server uses explicit `--serve`.

### Configure the Python simulation

JSON overlays define layout seed, registry, current/visibility, vehicle dynamics, inspection cones and manipulation durations:

```bash
python3 -m reefsim --config configs/reef.json --episode 240 --output outputs/episode.json
python3 -m unittest discover -s tests -v
```

Coordinates use metres and Z-up, with public yaw in radians. `gripper_world` is the jaw centre; `gripper_open` ranges from zero closed to one open. Each cutting preserves its ID, shape and size through `attached_to_donor`, `grasped`, `carried` and `placed`. Attachment and gripper geometry determine when the fragment follows the jaws or remains fixed at its placement.

The Python mission core uses the standard library. Rendering and optical tests use NumPy and Pillow. [Scene implementation](docs/ISAAC_SCENE.md), [configuration assumptions](docs/ASSUMPTIONS.md) and [references](docs/REFERENCES.md) describe this rendering path.
