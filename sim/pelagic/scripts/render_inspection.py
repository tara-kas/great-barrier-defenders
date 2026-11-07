#!/usr/bin/env python3
"""Record an offline 15-case robot lighting comparison in the existing reef.

This is a controlled inspection tour, not an autonomous navigation episode or
a genetic assay. The mission engine remains unchanged while renderer-only
robot poses place its inspection camera beside existing reef colonies.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GROUPS = ("violet", "blue", "yellow", "red", "pink")
HEALTH = ("healthy", "bleached_alive", "dead")
MODES = ("white", "blue", "uv")


def select_cases(corals, profiles):
    """Choose one existing reef colony per biological state and colour group."""
    cases = []
    for health in HEALTH:
        for group in GROUPS:
            candidates = [coral for coral in corals if coral["health"] == health
                          and profiles[coral["id"]]["group"] == group]
            if not candidates:
                raise ValueError(f"Existing reef has no {health}/{group} inspection case")
            coral = min(candidates, key=lambda item: item["id"])
            cases.append({"coral_id": coral["id"], "health": health,
                          "profile": copy.deepcopy(profiles[coral["id"]]),
                          "position": list(coral["position"]),
                          "morphology": coral["morphology"]})
    return cases


def mode_frame_counts(fps, case_seconds=3.):
    frames = max(3, round(fps * case_seconds))
    boundaries = [0, round(frames * .20), round(frames * .60), frames]
    return {mode: boundaries[i+1] - boundaries[i] for i, mode in enumerate(MODES)}


def _scene_signature(stage):
    """Mesh positions/topology and colony/cutting poses must stay fixed."""
    import array
    from pxr import Usd, UsdGeom
    digest = hashlib.sha256()
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if not path.startswith(("/World/Corals/", "/World/Fragments/")):
            continue
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            digest.update(path.encode())
            if not prim.GetCustomDataByKey("reefsim:deformable_tissue"):
                digest.update(array.array("f", (float(v) for p in mesh.GetPointsAttr().Get() for v in p)).tobytes())
            digest.update(array.array("i", mesh.GetFaceVertexCountsAttr().Get()).tobytes())
            digest.update(array.array("i", mesh.GetFaceVertexIndicesAttr().Get()).tobytes())
            transform = cache.GetLocalToWorldTransform(prim)
            digest.update(array.array("d", (float(v) for row in transform for v in row)).tobytes())
    return digest.hexdigest()


def _validate_response(case, metadata, mode):
    assert metadata["target_id"] == case["coral_id"]
    assert metadata["mode"] == mode
    assert metadata["profile"]["group"] == case["profile"]["group"]
    emission = metadata["emission_rgb"]
    assert len(emission) == 3 and all(math.isfinite(v) and v >= 0 for v in emission)
    assert 0 <= metadata["exposure"] <= 1
    if mode == "white" or case["health"] == "dead" or case["profile"].get("negative_control"):
        assert max(emission) < 1e-8, "Negative control gained host fluorescence"
    else:
        assert max(emission) > 1e-5, "Expected illuminated host response is absent"


def _camera_poses(stage, paths):
    from pxr import Usd, UsdGeom
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    poses = {}
    for key, path in paths.items():
        camera = UsdGeom.Camera.Get(stage, path)
        matrix = cache.GetLocalToWorldTransform(camera.GetPrim())
        poses[key] = {"matrix": [float(v) for row in matrix for v in row],
                      "focal_length": float(camera.GetFocalLengthAttr().Get())}
    return poses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "reef-inspection-lighting")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--case-seconds", type=float, default=3.)
    parser.add_argument("--preview-stills", action="store_true")
    parser.add_argument("--quality", type=int, default=19)
    args, kit_args = parser.parse_known_args()
    if not 1 <= args.fps <= 60 or args.samples < 1 or not 1 <= args.case_seconds <= 10 or not 0 <= args.quality <= 40:
        parser.error("Use fps 1–60, positive samples, case duration 1–10s and CRF 0–40")
    ffmpeg = shutil.which("ffmpeg")
    if not args.preview_stills and not ffmpeg:
        parser.error("ffmpeg is required for offline movie encoding")
    from reefsim.config import load_config
    config = load_config(args.config)
    config.setdefault("inspection", {})["enabled"] = True
    config["inspection"]["pocillopora_only"] = True
    args.output.mkdir(parents=True, exist_ok=True)
    sys.argv = [sys.argv[0], *kit_args]
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting", "sync_loads": True,
                         "width": 1280, "height": 720})
    encoder = None
    try:
        import numpy as np
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from PIL import Image
        from reefsim.core import ReefSimulation
        from reefsim.isaac_scene import IsaacReefScene
        from reefsim.inspection_compositor import compose_inspection, WIDTH, HEIGHT
        from scripts.render_demo import _capture

        simulation = ReefSimulation(config)
        baseline = simulation.snapshot()
        baseline_json = json.dumps(baseline, sort_keys=True)
        context = omni.usd.get_context()
        context.new_stage()
        stage = context.get_stage()
        scene = IsaacReefScene(stage, config)
        scene.build(baseline)
        cases = select_cases(baseline["corals"], scene.inspection_profiles)
        signature = _scene_signature(stage)
        camera_specs = {"worker": (960, 540), "overview": (640, 360)}
        products = {}
        for key, resolution in camera_specs.items():
            product = rep.create.render_product(scene.CAMERA_PATHS[key], resolution)
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            rgb.attach([product])
            depth.attach([product])
            products[key] = (rgb, depth)
        # Render-product prims are expected additions, authored before checks.
        prim_paths = {str(prim.GetPath()) for prim in stage.Traverse() if str(prim.GetPath()).startswith("/World/")}
        omni.timeline.get_timeline_interface().play()
        counts = mode_frame_counts(args.fps, args.case_seconds)
        full_frames = sum(counts.values()) * len(cases)
        duration = full_frames / args.fps
        if not args.preview_stills:
            encoder = subprocess.Popen([
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
                "-framerate", str(args.fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", str(args.quality), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(args.output / "pelagic-inspection.mp4")], stdin=subprocess.PIPE)
        started = time.monotonic()
        frame = 0
        records = []
        beam_off_checks = []
        geometry_checks = 0
        for number, case in enumerate(cases, 1):
            white_reference = None
            reference_poses = None
            for mode in MODES:
                iterations = 1 if args.preview_stills else counts[mode]
                for within in range(iterations):
                    display_time = frame / args.fps if not args.preview_stills else (number-1) * args.case_seconds + {"white": 0., "blue": .6, "uv": 1.8}[mode]
                    state = copy.deepcopy(baseline)
                    state["time"] = display_time
                    input_copy = json.dumps(state, sort_keys=True)
                    view_state = scene.aim_inspection(state, case["coral_id"], mode)
                    assert json.dumps(state, sort_keys=True) == input_copy, "Inspection mutates its source snapshot"
                    assert view_state["corals"] == baseline["corals"]
                    assert view_state["fragments"] == baseline["fragments"]
                    for _ in range(max(12, args.samples) if within == 0 else args.samples):
                        app.update()
                    images = {key: _capture(*products[key], view_state, key == "overview", seed=frame,scene=scene,camera=key)
                              for key in camera_specs}
                    metadata = scene.inspection_metadata()
                    _validate_response(case, metadata, mode)
                    poses = _camera_poses(stage, {key: scene.CAMERA_PATHS[key] for key in camera_specs})
                    if reference_poses is None:
                        reference_poses = poses
                    assert poses == reference_poses, "Lighting comparison changed camera pose or focal length"
                    if white_reference is None:
                        white_reference = images["worker"].copy()
                    composite = compose_inspection(white_reference, images["worker"], images["overview"],
                                                   case, metadata, case_number=number, case_count=len(cases),
                                                   elapsed=display_time, duration=duration)
                    if args.preview_stills:
                        composite.save(args.output / f"case-{number:02d}-{case['health']}-{case['profile']['group']}-{mode}.png")
                    else:
                        encoder.stdin.write(composite.tobytes())
                    if within == 0:
                        delta = float(np.mean(np.abs(images["worker"].astype(float) - white_reference.astype(float))))
                        record = {"case": number, "coral_id": case["coral_id"], "health": case["health"],
                                  "group": case["profile"]["group"], "frame": frame, "mode": mode,
                                  "metadata": metadata, "mean_rgb_difference_from_white": delta,
                                  "camera_poses": poses,
                                  "wall_seconds": time.monotonic() - started}
                        records.append(record)
                        print("PELAGIC_INSPECTION " + json.dumps(record), flush=True)
                    frame += 1
            scene.set_inspection_mode("blue", target_id=case["coral_id"], strength=0.)
            off = scene.inspection_metadata()
            assert max(off["emission_rgb"]) < 1e-8, "Source-off state retains host fluorescence"
            beam_off_checks.append({"coral_id": case["coral_id"], "emission_rgb": off["emission_rgb"]})
            assert _scene_signature(stage) == signature, "Inspection changed coral or cutting geometry/pose"
            assert {str(prim.GetPath()) for prim in stage.Traverse() if str(prim.GetPath()).startswith("/World/")} == prim_paths, "Inspection created new scene geometry"
            geometry_checks += 1
        if encoder:
            encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError("ffmpeg failed while encoding the inspection movie")
            encoder = None
        assert json.dumps(simulation.snapshot(), sort_keys=True) == baseline_json
        assert len(records) == 45 and len(cases) == 15
        evidence = {"result": "PASS", "case_count": 15, "cases": cases,
                    "health_states": list(HEALTH), "phenotype_groups": list(GROUPS),
                    "modes": list(MODES), "server_started": False,
                    "mission_state_unchanged": True, "coral_fragment_geometry_unchanged": True,
                    "geometry_signature": signature, "geometry_checks": geometry_checks,
                    "beam_off_checks": beam_off_checks, "recording_kind": "fixed-pose in-reef inspection tour",
                    "camera_paths": {key: scene.CAMERA_PATHS[key] for key in camera_specs},
                    "same_camera_white_reference": True, "camera_resolutions": camera_specs,
                    "camera_pose_invariant_across_modes": True,
                    "fps": args.fps, "frames": frame, "composite_resolution": [WIDTH, HEIGHT],
                    "preview_stills": args.preview_stills, "wall_seconds": time.monotonic() - started,
                    "interpretation": "Known scenario labels; RGB fluorescence proxy, not spectral calibration or genetic identification"}
        if not args.preview_stills:
            probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate",
                                    "-show_entries", "format=duration,size", "-of", "json",
                                    str(args.output / "pelagic-inspection.mp4")], capture_output=True, text=True, check=True)
            media = json.loads(probe.stdout)
            stream = media["streams"][0]
            assert [stream["width"], stream["height"]] == [WIDTH, HEIGHT]
            assert int(stream["nb_read_frames"]) == full_frames == frame
            assert abs(float(media["format"]["duration"]) - duration) < .1
            evidence["video"] = media
            evidence["duration_seconds"] = duration
        (args.output / "manifest.json").write_text(json.dumps(records, indent=2))
        (args.output / "validation.json").write_text(json.dumps(evidence, indent=2))
        (args.output / "baseline-state.json").write_text(json.dumps(baseline, indent=2))
        print("PELAGIC_INSPECTION_FINISHED " + json.dumps({"cases": len(cases), "frames": frame, "result": "PASS"}), flush=True)
    finally:
        if encoder:
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()
            encoder.terminate()
            encoder.wait()
        app.close()


if __name__ == "__main__":
    main()
