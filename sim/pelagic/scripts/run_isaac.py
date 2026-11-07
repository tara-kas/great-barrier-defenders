#!/usr/bin/env python3
"""Launch with Isaac Sim 6.0's python.sh. Kit imports follow SimulationApp."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Pelagic · Isaac Sim 6.0 underwater mission")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    server_options = parser.add_mutually_exclusive_group()
    server_options.add_argument("--serve", action="store_true", help="Explicitly enable optional telemetry console")
    server_options.add_argument("--no-server", action="store_false", dest="serve", help="Disable console (default)")
    parser.set_defaults(serve=False)
    parser.add_argument("--steps", type=int, default=0, help="0 runs until interrupted")
    parser.add_argument("--speed", type=float, default=1.)
    parser.add_argument("--camera-hz", type=float, default=3.)
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--export-stage", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "isaac")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--view", choices=("overview", "follow", "rov", "top"), default="overview")
    parser.add_argument("--record-dir", type=Path, help="Save overview PNG sequence for demo recording")
    parser.add_argument("--record-every", type=int, default=3, help="Capture every N render steps")
    parser.add_argument("--allow-other-version", action="store_true")
    args, kit_args = parser.parse_known_args()
    if not math.isfinite(args.speed) or not math.isfinite(args.camera_hz) or args.speed <= 0 or args.camera_hz <= 0 or args.steps < 0 or args.record_every < 1:
        parser.error("Speed/camera rate must be positive; steps must be nonnegative")
    if args.record_dir and args.no_camera:
        parser.error("--record-dir requires camera capture; remove --no-camera")
    # Prevent project flags being interpreted as Kit extension arguments.
    sys.argv = [sys.argv[0], *kit_args]
    try:
        from isaacsim import SimulationApp
    except ImportError:
        raise SystemExit("Use the Isaac Sim 6.0 installation's ./python.sh scripts/run_isaac.py")
    app = SimulationApp({"headless": args.headless, "width": args.width,
                         "height": args.height, "renderer": "RaytracedLighting",
                         "sync_loads": True})
    server = None
    try:
        import carb
        import omni.usd
        import omni.timeline
        from reefsim.config import load_config
        from reefsim.core import ReefSimulation
        from reefsim.server import Runtime, start_server
        from reefsim.isaac_scene import IsaacReefScene

        version_file = Path(sys.executable).resolve()
        # VERSION placement differs between source builds and workstation bundles.
        version = None
        for parent in (Path.cwd(), *version_file.parents):
            candidate = parent / "VERSION"
            if candidate.is_file():
                version = candidate.read_text().strip()
                break
        if version and not version.startswith("6.0") and not args.allow_other_version:
            raise RuntimeError(f"Expected Isaac Sim 6.0.x, found {version}; use --allow-other-version explicitly")
        print(f"PELAGIC_RUNTIME {version or 'Isaac Sim (version file unavailable)'}", flush=True)
        simulation = ReefSimulation(load_config(args.config))
        runtime = Runtime(simulation, "isaac")
        runtime.camera_mode = args.view
        context = omni.usd.get_context()
        context.new_stage()
        stage = context.get_stage()
        scene = IsaacReefScene(stage, simulation.config)
        scene.build(runtime.snapshot())
        scene.set_camera(args.view, runtime.snapshot())
        omni.timeline.get_timeline_interface().play()
        for _ in range(12):
            app.update()
        rgb = depth = overview_rgb = overview_depth = None
        if not args.no_camera:
            import omni.replicator.core as rep
            # Rendered range is available to optical postprocessing only, not mission perception.
            render_product = rep.create.render_product("/World/Cameras/ROV", (640, 400))
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            rgb.attach([render_product])
            depth.attach([render_product])
            overview_product = rep.create.render_product("/World/Cameras/Overview", (960, 600))
            overview_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            overview_rgb.attach([overview_product])
            overview_depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            overview_depth.attach([overview_product])
            for _ in range(12):
                app.update()
        if args.serve:
            server = start_server(runtime, args.host, args.port)
            print(f"PELAGIC_CONSOLE http://{args.host}:{server.server_port}", flush=True)
        args.output.mkdir(parents=True, exist_ok=True)
        if args.record_dir:
            args.record_dir.mkdir(parents=True, exist_ok=True)
        if args.export_stage:
            args.export_stage.parent.mkdir(parents=True, exist_ok=True)
            stage.GetRootLayer().Export(str(args.export_stage))
        print("PELAGIC_READY", flush=True)
        step = 0
        episode_wall_start = time.monotonic()
        previous_wall = episode_wall_start - 1 / 30
        camera_at = 0.
        camera_errors = 0
        last_camera_mode = None
        previous_time = -1.
        while app.is_running() and (not args.steps or step < args.steps):
            started = time.monotonic()
            # Bounded test episodes use deterministic timesteps. Interactive
            # runs track wall time so a slower renderer does not slow the ROVs.
            dt = 1 / 30 if args.steps else min(.5, max(.001, started - previous_wall))
            previous_wall = started
            # The core already integrates stable <= 50 ms substeps internally.
            state = runtime.tick(dt * args.speed)
            # Reset can use a different seed. Rebuild procedural assets accordingly.
            if state["time"] < previous_time:
                scene.build(state)
                camera_at = 0.
                last_camera_mode = None
            previous_time = state["time"]
            scene.update(state)
            if runtime.camera_mode != last_camera_mode:
                scene.set_camera(runtime.camera_mode, state)
                if overview_rgb is not None:
                    from pxr import UsdRender, Sdf
                    product = UsdRender.Product.Get(stage, overview_product.path)
                    product.GetCameraRel().SetTargets([Sdf.Path(scene.CAMERA_PATHS[scene.camera_mode])])
                last_camera_mode = runtime.camera_mode
            app.update()
            if args.record_dir and overview_rgb is not None and step % args.record_every == 0:
                from reefsim.optics import png_bytes, underwater_image
                overview_data = overview_rgb.get_data()
                overview_range = overview_depth.get_data()
                if getattr(overview_data, "size", 0) and getattr(overview_range, "size", 0):
                    image = underwater_image(overview_data, overview_range,
                                             state["water"]["visibility"] * 1.7, int(state["time"] * 30),
                                             attenuation_rgb=state["water"].get("attenuation_rgb"),
                                             backscatter_rgb=state["water"].get("backscatter_rgb"))
                    frame_index = step // args.record_every
                    (args.record_dir / f"frame-{frame_index:05d}.png").write_bytes(png_bytes(image))
            if rgb is not None and time.monotonic() >= camera_at:
                try:
                    from reefsim.optics import png_bytes, underwater_image
                    rgb_data, depth_data = rgb.get_data(), depth.get_data()
                    if getattr(rgb_data, "size", 0) and getattr(depth_data, "size", 0):
                        image = underwater_image(rgb_data, depth_data,
                                                 state["water"]["visibility"], int(state["time"] * 30),
                                                 attenuation_rgb=state["water"].get("attenuation_rgb"),
                                                 backscatter_rgb=state["water"].get("backscatter_rgb"))
                        frame = png_bytes(image)
                        runtime.set_frame(frame, state["time"])
                        (args.output / "rov-camera.png").write_bytes(frame)
                        overview_data = overview_rgb.get_data()
                        overview_range = overview_depth.get_data()
                        if getattr(overview_data, "size", 0) and getattr(overview_range, "size", 0):
                            overview_image = underwater_image(overview_data, overview_range,
                                state["water"]["visibility"] * 1.7, int(state["time"] * 30),
                                attenuation_rgb=state["water"].get("attenuation_rgb"),
                                backscatter_rgb=state["water"].get("backscatter_rgb"))
                            overview_frame = png_bytes(overview_image)
                            runtime.set_overview(overview_frame, state["time"])
                            (args.output / "overview.png").write_bytes(overview_frame)
                except Exception as error:
                    runtime.last_error = str(error)
                    if camera_errors < 3:
                        print(f"PELAGIC_CAMERA_ERROR {error}", flush=True)
                    camera_errors += 1
                camera_at = time.monotonic() + 1 / args.camera_hz
            step += 1
            if step % 150 == 0:
                print("PELAGIC_METRICS " + json.dumps(state.get("metrics", {})), flush=True)
                (args.output / "state.json").write_text(json.dumps(runtime.snapshot(), indent=2))
            # Real-time default; --speed advances mission time with stable substeps.
            time.sleep(max(0., 1 / 30 - (time.monotonic() - started)))
        state = runtime.snapshot()
        state["runtime"]["isaac_version"] = version
        state["runtime"]["rendered_frames"] = step
        state["runtime"]["wall_seconds"] = time.monotonic() - episode_wall_start
        state["runtime"]["average_fps"] = step / max(.001, state["runtime"]["wall_seconds"])
        (args.output / "state.json").write_text(json.dumps(state, indent=2))
        stage.GetRootLayer().Export(str(args.output / "reef.usda"))
        print("PELAGIC_FINISHED " + json.dumps(state.get("metrics", {})), flush=True)
    except Exception:
        # SimulationApp.close can terminate the interpreter before an exception
        # propagates. Emit the traceback first so failures remain diagnosable.
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        if server:
            server.shutdown()
            server.server_close()
        app.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
