# Mission Control dashboard

A standalone file-based diagnostic view for the Python research stack. The
current browser mission interface is under `sim/pelagic/web/lab`; see the
[project README](../README.md) and [system architecture](../docs/ARCHITECTURE.md).

This view reads the shared `SemanticSeabedRegistry.dump()` JSON shape and `DecisionLog.save()` JSONL shape. It does not call a model or the vehicle. The browser polls the source files every two seconds, so an agent writing a new registry dump or decision log updates the view without rebuilding it.

## Run the synthetic demo

From the repository root:

```sh
python3 dashboard/server.py
```

Open `http://127.0.0.1:8765`. Python 3.10+ is sufficient; there are no dashboard package dependencies. The generated camera asset, illustrative detection boxes, sample registry, sample decision log, and ROV location are visibly labelled as synthetic or illustrative. They are for dashboard development, not evidence of a live Isaac Sim run or live Gemma inference.

## Connect file output from a mission

```sh
python3 dashboard/server.py \
  --registry /path/to/registry.json \
  --log /path/to/decisions.jsonl \
  --frame /path/to/latest-frame.jpg
```

`mission/runner.py` writes these files during a run. Add `--synthetic-frame` when the frames are mock renders, so they are labelled as synthetic.

The registry file can be a JSON array from `SemanticSeabedRegistry.dump()`, or an object with `entries` and optional `detections`. The log file is one `DecisionLogEntry` object per line, with `timestamp`, `state`, `action`, `evidence`, and `outcome`. The frame can be PNG or JPEG. Every poll rereads the registry and log and checks the frame's modification time, including changes made after the server starts. If a source is temporarily unavailable or malformed while being written, the dashboard shows a source error and retries. Writing registry and frame files with an atomic rename avoids partial reads.

Detection coordinates are optional because the frozen registry contract has no image-space bounding boxes. When available, use normalized fractions in `[left, top, width, height]` format:

```json
{
  "entries": [
    {"cluster_id": "C-01", "species_class": "Acropora cervicornis", "health_status": "LIVE", "health_score": 0.94, "position_world": [1.2, 2.1, -18.4], "bounding_box_extent": [0.8, 0.6, 0.7], "optimal_graft_pose_world": null, "sampled_or_restored": false}
  ],
  "detections": [{"cluster_id": "C-01", "box": [0.12, 0.30, 0.25, 0.35]}]
}
```

When using the built-in demo, the two boxes are illustrative and labelled as such. With a file source, no boxes appear unless `detections` are supplied. The reef viewport is a spatial preview generated from world positions; it is not the Isaac Sim stream. The ROV position and acoustic link control remain explicitly simulated until those sources are integrated.

## Controls

- Select a map pin to inspect health, species, score, and world position. The same cluster is highlighted in the spatial preview.
- Filter the map by health status; counts always show the full registry.
- Toggle camera overlays, pause/resume file polling, and inspect any decision's evidence and outcome.
- Toggle the simulated acoustic link indicator. This affects only the dashboard display and never sends a vehicle command.

The server binds to `127.0.0.1` only. No API keys or credentials are needed.

## Verify

```sh
python3 -m unittest discover -s dashboard -p 'test_*.py'
node --check dashboard/app.js
```

The server tests cover the frozen registry/log format, file updates, optional detection boxes, and a malformed source. Node is needed only for the JavaScript syntax check, not to run the dashboard.
