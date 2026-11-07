#!/usr/bin/env python3
"""Offline three-camera Isaac Sim recording with actual robot-camera PiPs.

This is a recorder, not a server. Rendering happens entirely on the Spark;
the finished video can be copied to a local machine after the process exits.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIM_DT = .05


ACTION_STATES = frozenset({
    "SCAN_RECIPIENT", "SCAN_DONOR",
    "APPROACH_FRAGMENT", "CLOSE_GRIPPER", "DETACH_FRAGMENT", "RETRACT_FRAGMENT",
    "LOWER_FRAGMENT", "SECURE_FRAGMENT", "OPEN_GRIPPER", "RETRACT_GRIPPER",
    "VERIFY_ATTACHMENT",
})


def playback_weight(worker_state, verified):
    """Video seconds per simulated second, emphasizing the first full transfer."""
    if worker_state in {"SCAN_RECIPIENT", "SCAN_DONOR"}:
        return 1.2
    if worker_state == "WAIT_FOR_MAP" and verified == 0:
        return .30
    if worker_state in ACTION_STATES:
        return 1.15 if verified == 0 else .70
    if worker_state == "NAVIGATE_TO_SITE":
        return .60  # Keep the shorter bleached-reef transfer visible on screen.
    if worker_state == "COMPLETE":
        return 1.
    return .15


def build_schedule(config, fps=24, max_frames=2000, all_transfers=False):
    """Replay the authoritative mission with explicit grasp/release milestones.

    One fixed integrator trajectory supplies both the schedule and the render.
    Transit is accelerated; the first complete manipulation cycle remains near
    real time. No fragment or action is invented by the video editor.
    """
    from reefsim.core import ReefSimulation
    simulation = ReefSimulation(config)
    config = simulation.config
    records = [{"time": 0., "video_time": 0., "state": "WAIT_FOR_MAP", "verified": 0}]
    milestones = {"survey": 0}
    weighted = 0.
    completed_at = None
    tick = 0
    previous_state = "WAIT_FOR_MAP"
    state_started = 0.
    action_seen = set()
    transfer_ids = []
    transfer_phases = ("recipient_detection", "donor_detection", "donor_approach", "closed_grasp", "carrying", "placement", "release", "retreat") if config.get("inspection",{}).get("require_detection") else ("donor_approach", "closed_grasp", "carrying", "placement", "release", "retreat")
    for_limit = float(simulation.config.get("mission", {}).get("episode_limit", 600.))
    while simulation.time < for_limit:
        simulation.step(SIM_DT)
        tick += 1
        worker = simulation.robots[1]
        fragment_id = worker.get("fragment_id")
        if all_transfers and fragment_id and fragment_id not in transfer_ids:
            transfer_ids.append(fragment_id)
        phase = worker["state"]
        if phase != previous_state:
            state_started = simulation.time
            previous_state = phase
        verified = sum(coral["task_status"] == "verified" for coral in simulation.corals)
        weight = playback_weight(phase, verified)
        if phase == "WAIT_FOR_MAP" and simulation.config["mission"].get("attachment_method") == "same_genet_contact":
            weight = .8  # Establish the living reef and current-driven fans.
        weighted += SIM_DT * weight
        records.append({"time": simulation.time, "video_time": weighted,
                        "state": phase, "verified": verified})
        if phase in ACTION_STATES:
            action_seen.add(phase)
        progress = float(worker.get("phase_progress", 0.))
        if simulation.time >= 5. and milestones["survey"] == 0:
            milestones["survey"] = tick
        checks = {
            "recipient_detection": phase == "SCAN_RECIPIENT" and progress >= .80,
            "donor_detection": phase == "SCAN_DONOR" and progress >= .80,
            "donor_approach": phase == "APPROACH_FRAGMENT" and progress >= .80,
            "closed_grasp": phase == "CLOSE_GRIPPER" and progress >= .92,
            "detachment": phase == "DETACH_FRAGMENT" and progress >= .75,
            "carrying": phase == "NAVIGATE_TO_SITE" and worker.get("carrying") and simulation.time - state_started >= 2.,
            "placement": phase == "LOWER_FRAGMENT" and progress >= .90,
            "release": phase == "OPEN_GRIPPER" and progress >= .90,
            "retreat": phase == "RETRACT_GRIPPER" and progress >= .85,
            "verification": phase == "VERIFY_ATTACHMENT" and progress >= .50,
        }
        for name, ready in checks.items():
            if ready:
                milestones.setdefault(name, tick)
                if all_transfers and fragment_id and name in transfer_phases:
                    number = transfer_ids.index(fragment_id) + 1
                    milestones.setdefault(f"transfer_{number:02d}_{fragment_id}_{name}", tick)
        if phase == "COMPLETE":
            if completed_at is None:
                completed_at = simulation.time
            if simulation.time >= completed_at + 1.5:
                milestones["complete"] = tick
                break
    if completed_at is None:
        raise RuntimeError(f"Donor-to-reef mission did not complete within {for_limit:g} simulated seconds")
    required = {"survey", "donor_approach", "closed_grasp", "detachment", "carrying", "placement", "release", "retreat", "verification", "complete"}
    if config.get("inspection",{}).get("require_detection"):
        required |= {"recipient_detection", "donor_detection"}
    missing = required - set(milestones)
    if missing:
        raise RuntimeError(f"Missing reviewable manipulation phases: {sorted(missing)}")
    expected = int(simulation.config["mission"]["planting_sites"])
    final = simulation.snapshot()
    if final["metrics"]["verified"] != expected:
        raise RuntimeError(f"Expected {expected} verified sites, got {final['metrics']['verified']}")
    if all_transfers:
        expected_milestones = {f"transfer_{number:02d}_{identifier}_{phase}"
                               for number, identifier in enumerate(transfer_ids, 1)
                               for phase in transfer_phases}
        missing = expected_milestones - set(milestones)
        if len(transfer_ids) != expected or missing:
            raise RuntimeError(f"Incomplete transfer review: {len(transfer_ids)}/{expected} fragments; missing {sorted(missing)}")
    frame_count = min(max_frames, max(2, math.ceil(weighted * fps) + 1))
    clock = [record["video_time"] for record in records]
    ticks = [max(0, min(len(records) - 1, bisect.bisect_left(clock, weighted * i / (frame_count - 1))))
             for i in range(frame_count)]
    ticks[0], ticks[-1] = 0, len(records) - 1
    return {"ticks": ticks, "milestones": milestones, "sim_dt": SIM_DT,
            "fps": fps, "frame_count": frame_count, "duration_seconds": frame_count / fps,
            "simulation_duration": simulation.time, "final_metrics": final["metrics"],
            "action_states_seen": sorted(action_seen), "weighted_duration": weighted,
            "first_carry_video_seconds": sum(records[t]["state"] == "NAVIGATE_TO_SITE" and records[t]["verified"] == 0 for t in ticks) / fps}



class FragmentGeometryAudit:
    """Check real USD geometry/poses, independently of the mission's labels.

    The baseline is captured once after scene build. Every later check hashes
    local points and topology, checks stage identities and world transforms,
    and rejects duplicated/generated fragment, outplant or table geometry.
    """
    def __init__(self, stage, snapshot):
        self.stage = stage
        self.mount_clearances = self._mount_clearances(snapshot)
        self.mount_min_clearance = min(self.mount_clearances.values())
        self.baseline = self._read(snapshot, initial=True)
        self.checks = 0
        self.phases = set()
        self.max_fragment_pose_error = 0.
        self.max_jaw_pose_error = 0.
        self.contact_gaps = {}
        self.natural_surfaces = {}
        self.records = []
        self.baseline_prim_paths = {str(prim.GetPath()) for prim in stage.Traverse()}

    @staticmethod
    def _digest(points, counts, indices):
        import array
        import hashlib
        digest = hashlib.sha256()
        digest.update(array.array("f", (float(v) for point in points for v in point)).tobytes())
        digest.update(array.array("i", (int(v) for v in counts)).tobytes())
        digest.update(array.array("i", (int(v) for v in indices)).tobytes())
        return digest.hexdigest()

    @staticmethod
    def _distance(a, b):
        return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))

    @staticmethod
    def _mount_clearances(snapshot):
        """Audit the complete coral/rock layout, including the mount's owner."""
        colonies = snapshot["corals"]
        blockers = colonies + snapshot.get("obstacles", [])
        clearances = {}
        for target in colonies:
            mount = target.get("planting_point")
            if mount is None:
                continue
            occupied = [colony for colony in blockers if not (target.get("contact_fixture") and colony["id"] == target["id"])]
            clearance = min(math.hypot(float(mount[0]) - float(colony["position"][0]),
                                       float(mount[1]) - float(colony["position"][1]))
                            - float(colony["radius"]) for colony in occupied)
            assert clearance >= .55 - 1e-6, f"Mount {target['id']} overlaps a coral/rock workspace: {clearance:g}m clearance"
            clearances[target["id"]] = clearance
        assert clearances, "No existing bleached-reef assistance mounting points to audit"
        return clearances

    def _read(self, snapshot, initial=False):
        from pxr import Gf, Usd, UsdGeom
        forbidden = ("/nursery", "/outplant", "/carriedfragment", "/livefragment", "/roots")
        paths = {str(prim.GetPath()) for prim in self.stage.Traverse()}
        assert not any(part in path.lower() for path in paths for part in forbidden), "Unexpected table, duplicate fragment or generated outplant/root geometry"
        scope = self.stage.GetPrimAtPath("/World/Fragments")
        assert scope and scope.IsValid(), "Persistent fragment scope missing"
        roots = {str(prim.GetCustomDataByKey("reefsim:fragment_id")): prim for prim in scope.GetChildren()}
        expected = {fragment["id"]: fragment for fragment in snapshot.get("fragments", [])}
        assert len(expected) == 6, "Expected exactly six persistent source cuttings"
        assert set(roots) == set(expected), "USD fragment identities diverged from mission"
        cutting_paths = {path for path in paths if path.startswith("/World/Fragments/") and path.endswith("/Cutting")}
        assert len(cutting_paths) == len(expected), "Missing or duplicated Cutting meshes"
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        result = {}
        for identifier, fragment in expected.items():
            root = roots[identifier]
            mesh_path = root.GetPath().AppendChild("Cutting")
            mesh = UsdGeom.Mesh.Get(self.stage, mesh_path)
            assert mesh and mesh.GetPrim().IsValid(), f"Fragment mesh missing: {identifier}"
            children = list(root.GetChildren())
            assert len(children) == 1 and children[0].GetPath() == mesh_path, "Fragment gained additional geometry"
            points = mesh.GetPointsAttr().Get()
            counts = mesh.GetFaceVertexCountsAttr().Get()
            indices = mesh.GetFaceVertexIndicesAttr().Get()
            assert points and counts and indices and sum(counts) == len(indices)
            assert all(math.isfinite(float(v)) for point in points for v in point)
            minimum = [min(float(point[axis]) for point in points) for axis in range(3)]
            maximum = [max(float(point[axis]) for point in points) for axis in range(3)]
            dimensions = [maximum[i] - minimum[i] for i in range(3)]
            assert minimum[2] >= -.003, "Cutting extends roots below its cut base"
            assert .85 * float(fragment["height"]) <= dimensions[2] <= 1.15 * float(fragment["height"]), "Fragment height changed or uses a whole colony"
            assert max(dimensions[:2]) <= max(.12, float(fragment["radius"]) * 5), "Fragment is wider than a small cutting"
            assert UsdGeom.Imageable(mesh.GetPrim()).ComputeVisibility() != UsdGeom.Tokens.invisible, "Persistent cutting unexpectedly hidden"
            transform = cache.GetLocalToWorldTransform(mesh.GetPrim())
            scales = [transform.TransformDir(Gf.Vec3d(*axis)).GetLength() for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            assert all(abs(scale - 1.) < 2e-6 for scale in scales), "Fragment was scaled/grown during transfer"
            translation = transform.ExtractTranslation()
            error = self._distance(translation, fragment.get("base_world", fragment["position"]))
            assert error < 2e-5, f"USD base pose mismatch for {identifier}: {error:g}m"
            result[identifier] = {"mesh_path": str(mesh_path), "geometry_sha256": self._digest(points, counts, indices),
                                  "point_count": len(points), "face_count": len(counts),
                                  "dimensions_m": dimensions, "world_scale": scales, "world_base": list(translation),
                                  "pose_error_m": error, "stage": fragment["stage"]}
        return result

    def check(self, snapshot, milestone):
        from pxr import Usd, UsdGeom
        clearances = self._mount_clearances(snapshot)
        assert set(clearances) == set(self.mount_clearances), "Mounting point identities changed"
        self.mount_min_clearance = min(self.mount_min_clearance, *clearances.values())
        current = self._read(snapshot)
        assert set(current) == set(self.baseline)
        for identifier, data in current.items():
            assert data["mesh_path"] == self.baseline[identifier]["mesh_path"]
            assert data["geometry_sha256"] == self.baseline[identifier]["geometry_sha256"], f"Fragment geometry was regenerated or grew: {identifier}"
            self.max_fragment_pose_error = max(self.max_fragment_pose_error, data["pose_error_m"])
        current_paths = {str(prim.GetPath()) for prim in self.stage.Traverse()}
        # Render products are allowed outside /World; scene geometry is fixed.
        assert {path for path in current_paths if path.startswith("/World/")} == {path for path in self.baseline_prim_paths if path.startswith("/World/")}, "Scene geometry appeared/disappeared during transfer"
        robot_scope = self.stage.GetPrimAtPath("/World/Robots")
        robot_roots = {str(prim.GetCustomDataByKey("reefsim:robot_id")): prim for prim in robot_scope.GetChildren()}
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        jaw_error = 0.
        for robot in snapshot.get("robots", []):
            if robot.get("role") != "restoration" or robot.get("gripper_world") is None:
                continue
            root = robot_roots[robot["id"]]
            gripper = self.stage.GetPrimAtPath(root.GetPath().AppendChild("Gripper"))
            translation = cache.GetLocalToWorldTransform(gripper).ExtractTranslation()
            error = self._distance(translation, robot["gripper_world"])
            assert error < 2e-5, f"Rendered jaw misses authoritative grasp: {error:g}m"
            jaw_error = max(jaw_error, error)
            opening = max(0., min(1., float(robot.get("gripper_open", 1.))))
            expected_gap = .018 + .038 * opening
            for index, sign in ((0, -1), (1, 1)):
                jaw = UsdGeom.Xformable(self.stage.GetPrimAtPath(gripper.GetPath().AppendChild(f"Jaw{index}")))
                local = jaw.GetOrderedXformOps()[0].Get()
                assert abs(float(local[1]) - sign * expected_gap) < 2e-5, "Rendered fingers do not follow the grasp opening"
            fragment = next((f for f in snapshot.get("fragments", []) if f["id"] == robot.get("fragment_id")), None)
            if fragment and fragment["stage"] in ("grasped", "carried"):
                base = current[fragment["id"]]["world_base"]
                expected_jaw = [base[0], base[1], base[2] + .045]
                assert self._distance(translation, expected_jaw) < .001, "Same fragment is not held between rendered jaws"
        self.max_jaw_pose_error = max(self.max_jaw_pose_error, jaw_error)
        colonies = {c["id"]: c for c in snapshot["corals"]}
        for fragment in snapshot.get("fragments", []):
            if fragment["stage"] != "placed":
                continue
            target = colonies[fragment["target_id"]]
            fixture = target.get("contact_fixture")
            if not fixture:
                continue
            assert target["genet_id"] == fragment["genet_id"] and target["genotype_known"]
            mesh = UsdGeom.Mesh.Get(self.stage, current[fragment["id"]]["mesh_path"])
            matrix = cache.GetLocalToWorldTransform(mesh.GetPrim())
            base_z = target["contact_base"][2]
            distances = []
            from pxr import Gf
            if fixture.get("kind") == "natural_branch":
                from reefsim.natural_contact import SurfaceQuery
                colony_path = "/World/Corals/" + target["id"].replace("-", "_") + "/Colony"
                colony = UsdGeom.Mesh.Get(self.stage, colony_path)
                colony_matrix = cache.GetLocalToWorldTransform(colony.GetPrim())
                pts = [tuple(colony_matrix.Transform(Gf.Vec3d(p))) for p in colony.GetPointsAttr().Get()]
                indices = list(colony.GetFaceVertexIndicesAttr().Get())
                digest = self._digest(pts, colony.GetFaceVertexCountsAttr().Get(), indices)
                if target["id"] not in self.natural_surfaces:
                    self.natural_surfaces[target["id"]] = (SurfaceQuery(pts, indices), digest)
                surface, original = self.natural_surfaces[target["id"]]
                assert digest == original, "Recipient skeleton changed during contact"
                assert len(pts) == fixture["source_vertex_count"]
                offset = fixture["source_triangle_index"]*3
                triangle = [pts[i] for i in indices[offset:offset+3]]
                assert max(self._distance(a,b) for a,b in zip(triangle,fixture["contact_triangle_world"])) < 2e-5
                assert not self.stage.GetPrimAtPath(colony_path.rsplit("/",1)[0] + "/RecipientContactTissue"), "Artificial recipient branch remains"
                for point in mesh.GetPointsAttr().Get():
                    world = matrix.Transform(Gf.Vec3d(point))
                    if base_z+.010 <= world[2] <= base_z+.035:
                        hit = surface.nearest(tuple(world), radius=.025)
                        if hit is not None:
                            distances.append(hit["signed_distance"])
                assert distances and min(distances) >= -.003, "Donor penetrates the natural branch"
                gap = min(distances, key=abs)
                assert abs(gap) <= fixture["contact_tolerance_m"], f"Donor misses natural coral branch: {gap}m"
                self.contact_gaps[fragment["id"]] = gap
                continue
            center = fixture["recipient_stem_base"]
            for point in mesh.GetPointsAttr().Get():
                world = matrix.Transform(Gf.Vec3d(point))
                if base_z + .010 <= world[2] <= base_z + .035:
                    distances.append(math.hypot(world[0]-center[0], world[1]-center[1]) - fixture["recipient_stem_radius"])
            assert distances, "No donor surface in the live tissue contact band"
            gap = min(distances)
            assert -.003 <= gap <= fixture["contact_tolerance_m"], f"Donor misses/penetrates recipient tissue: {gap}m"
            self.contact_gaps[fragment["id"]] = gap
        self.checks += 1
        phase = snapshot["robots"][1]["state"]
        self.phases.add(phase)
        self.records.append({"milestone": milestone, "sim_time": snapshot["time"], "phase": phase,
                             "fragment_count": len(current), "max_fragment_pose_error_m": max(d["pose_error_m"] for d in current.values()),
                             "jaw_pose_error_m": jaw_error})

    def report(self):
        return {"passed": True, "persistent_fragment_count": len(self.baseline), "checks": self.checks,
                "geometry_unchanged": True, "no_generated_outplant_or_table": True,
                "max_fragment_pose_error_m": self.max_fragment_pose_error,
                "mount_min_clearance_m": self.mount_min_clearance,
                "mount_clearances_m": self.mount_clearances,
                "contact_surface_gaps_m": self.contact_gaps,
                "max_jaw_pose_error_m": self.max_jaw_pose_error, "phases_checked": sorted(self.phases),
                "fragments": self.baseline, "records": self.records}


def _capture(rgb, depth, state, spectator, seed, *, scene=None, camera=None):
    from reefsim.optics import underwater_image
    color, ranges = rgb.get_data(), depth.get_data()
    if not getattr(color, "size", 0) or not getattr(ranges, "size", 0):
        raise RuntimeError("Isaac returned an empty camera render product")
    visibility = state["water"]["visibility"] * (1.7 if spectator else 1.)
    result = underwater_image(color, ranges, visibility, seed=seed,
                             attenuation_rgb=state["water"].get("attenuation_rgb"),
                             backscatter_rgb=state["water"].get("backscatter_rgb"))
    if scene is not None and camera and scene.config.get("render",{}).get("visible_beam_scattering",False):
        from pxr import Usd, UsdGeom
        from reefsim.beam_optics import add_visible_beam
        info = scene.inspection_metadata()
        intensity = info.get("visible_light_intensity",0.)
        if intensity>0:
            lens = UsdGeom.Camera.Get(scene.stage,scene.CAMERA_PATHS[camera])
            matrix = UsdGeom.Xformable(lens).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            result = add_visible_beam(result,ranges,camera_world=[list(row) for row in matrix],
                focal_length_mm=float(lens.GetFocalLengthAttr().Get()),
                horizontal_aperture_mm=float(lens.GetHorizontalApertureAttr().Get()),
                light_origin=info["rendered_light_position"],light_direction=info["rendered_light_direction"],
                half_angle_degrees=info["beam_half_angle_degrees"],color_rgb=info["visible_light_rgb"],
                strength=float(scene.config["render"].get("visible_beam_gain",.55))*math.sqrt(intensity/4000.),
                visibility_m=state["water"]["visibility"])
    return result


def main():
    parser = argparse.ArgumentParser(description="Offline PELAGIC action-camera and robot-camera recorder")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "pelagic-pip")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--max-frames", type=int, default=2000)
    parser.add_argument("--samples", type=int, default=1, help="Kit render updates per output frame")
    parser.add_argument("--preview-stills", action="store_true", help="Render grasp/carry/release milestone composites, no movie")
    parser.add_argument("--all-transfers", action="store_true", help="With --preview-stills, review approach/grasp/carry/place/release/retreat for every fragment")
    parser.add_argument("--save-frames", action="store_true", help="Also save composite JPEG frames")
    parser.add_argument("--quality", type=int, default=19, help="H.264 CRF, lower is higher quality")
    args, kit_args = parser.parse_known_args()
    if not 1 <= args.fps <= 60 or args.max_frames < 60 or args.samples < 1 or not 0 <= args.quality <= 40:
        parser.error("Use fps 1–60, at least 60 max frames, positive samples, CRF 0–40")
    if args.all_transfers and not args.preview_stills:
        parser.error("--all-transfers requires --preview-stills")
    ffmpeg = shutil.which("ffmpeg")
    if not args.preview_stills and ffmpeg is None:
        parser.error("ffmpeg must be installed for MP4 recording")
    from reefsim.config import load_config
    config = load_config(args.config)
    schedule = build_schedule(config, args.fps, args.max_frames, all_transfers=args.all_transfers)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "schedule.json").write_text(json.dumps(schedule, indent=2))
    print("PELAGIC_SCHEDULE " + json.dumps({key: value for key, value in schedule.items() if key != "ticks"}), flush=True)
    sys.argv = [sys.argv[0], *kit_args]
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting", "sync_loads": True,
                         "width": 1280, "height": 720})
    encoder = None
    try:
        import omni.usd
        import omni.timeline
        import omni.replicator.core as rep
        from reefsim.core import ReefSimulation
        from reefsim.isaac_scene import IsaacReefScene
        from reefsim.compositor import compose_frame, WIDTH, HEIGHT

        simulation = ReefSimulation(config)
        context = omni.usd.get_context()
        context.new_stage()
        stage = context.get_stage()
        scene = IsaacReefScene(stage, config)
        state = simulation.snapshot()
        scene.build(state)
        geometry_audit = FragmentGeometryAudit(stage, state)
        geometry_audit.check(state, "initial")
        camera_specs = {"director": (1280, 720), "scout": (400, 240), "worker": (400, 240)}
        missing = [key for key in camera_specs if key not in scene.CAMERA_PATHS]
        if missing:
            raise RuntimeError(f"Scene missing required robot/director cameras: {missing}")
        products = {}
        for key, resolution in camera_specs.items():
            product = rep.create.render_product(scene.CAMERA_PATHS[key], resolution)
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            rgb.attach([product])
            depth.attach([product])
            products[key] = (rgb, depth)
        scene.set_camera("director", state)
        omni.timeline.get_timeline_interface().play()
        for _ in range(24):
            app.update()
        if args.preview_stills:
            # Comparable real RTX views of each biological category, separate
            # from the action milestones and without changing mission state.
            from PIL import Image
            for region in state["regions"]:
                if region["policy"] == "avoid":
                    continue
                x, y, _ = region["center"]
                scene._look_at("director", (x - .6, y - 2.1, 1.05), (x, y, .22))
                for _ in range(12):
                    app.update()
                Image.fromarray(_capture(*products["director"], state, True, seed=0,scene=scene,camera="director")).save(
                    args.output / f"habitat-{region['health']}.png")
            scene.update(state)
            targets = sorted((tick, name) for name, tick in schedule["milestones"].items())
        else:
            targets = [(tick, f"frame-{index:05d}") for index, tick in enumerate(schedule["ticks"])]
            movie = args.output / "pelagic-pip.mp4"
            encoder = subprocess.Popen([
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
                "-framerate", str(args.fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", str(args.quality), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(movie)], stdin=subprocess.PIPE)
        tick = 0
        previous_tick = 0
        previous_phase = None
        started = time.monotonic()
        manifest = []
        for index, (target_tick, name) in enumerate(targets):
            while tick < target_tick:
                simulation.step(SIM_DT)
                tick += 1
            state = simulation.snapshot()
            scene.update(state)
            if config.get("inspection", {}).get("enabled"):
                state["inspection"] = scene.inspection_metadata()
            current_phase = state["robots"][1]["state"]
            if args.preview_stills or current_phase != previous_phase or index + 1 == len(targets):
                geometry_audit.check(state, name)
            for _ in range(max(12, args.samples) if args.preview_stills else args.samples):
                app.update()
            # All three products are pulled after the same scene update/render.
            images = {key: _capture(*products[key], state, key == "director", seed=tick,scene=scene,camera=key)
                      for key in camera_specs}
            speed = 1. if args.preview_stills else max(.1, (target_tick - previous_tick) * SIM_DT * args.fps)
            composite = compose_frame(images["director"], images["scout"], images["worker"], state,
                                      speed, keyframe=args.preview_stills)
            if args.preview_stills:
                composite.save(args.output / f"preview-{index + 1:02d}-{name}.png")
                from PIL import Image
                for key in camera_specs:
                    Image.fromarray(images[key]).save(args.output / f"preview-{index + 1:02d}-{name}-{key}.png")
            else:
                try:
                    encoder.stdin.write(composite.tobytes())
                except BrokenPipeError as error:
                    raise RuntimeError("ffmpeg stopped accepting video frames") from error
                if args.save_frames:
                    frames = args.output / "frames"
                    frames.mkdir(exist_ok=True)
                    composite.save(frames / f"frame-{index:05d}.jpg", quality=92)
            current_phase = state["robots"][1]["state"]
            if args.preview_stills or index % 50 == 0 or index + 1 == len(targets) or current_phase != previous_phase:
                record = {"frame": index, "name": name, "sim_time": state["time"],
                          "worker_state": current_phase, "fragment_id": state["robots"][1].get("fragment_id"),
                          "donor_id": state["robots"][1].get("donor_id"),
                          "gripper_open": state["robots"][1].get("gripper_open"),
                          "gripper_world": state["robots"][1].get("gripper_world"),
                          "carrying": state["robots"][1].get("carrying"),
                          "phase_progress": state["robots"][1].get("phase_progress"),
                          "scan_target_id": state["robots"][1].get("scan_target_id"),
                          "scan_target_world": state["robots"][1].get("scan_target_world"),
                          "detection_status": state["robots"][1].get("detection_status"),
                          "uv_detection": state["robots"][1].get("uv_detection"),
                          "inspection": scene.inspection_metadata() if config.get("inspection", {}).get("enabled") else None,
                          "fragments": [{key: fragment.get(key) for key in ("id", "donor_id", "target_id", "stage", "position")} for fragment in state.get("fragments", [])],
                          "metrics": state["metrics"],
                          "elapsed_wall_seconds": time.monotonic() - started}
                manifest.append(record)
                print("PELAGIC_FRAME " + json.dumps(record), flush=True)
            previous_tick = target_tick
            previous_phase = current_phase
        if encoder:
            encoder.stdin.close()
            result = encoder.wait()
            if result:
                raise RuntimeError(f"ffmpeg failed with exit status {result}")
            encoder = None
        final = simulation.snapshot()
        (args.output / "geometry-validation.json").write_text(json.dumps(geometry_audit.report(), indent=2))
        final["mode"] = "isaac-offline-pip"
        from collections import Counter
        final["recording"] = {"camera_paths": {key: scene.CAMERA_PATHS[key] for key in camera_specs},
                              "habitat": {"registered_colonies": len(final["corals"]),
                                          "scenery_colonies": len(scene.scenery),
                                          "scenery_health": dict(Counter(c["health"] for c in scene.scenery)),
                                          "fish_count": len(scene.fauna),
                                          "soft_coral_count": len(scene._soft_corals),
                                          "polyp_patch_count": len(scene._polyp_patches),
                                          "coral_motion": "reduced-order oscillatory drag/damped bending of soft fans and polyp tentacles; hard skeletons rigid",
                                          "scanned_colonies": scene.scanned_colony_count,
                                          "fauna_motion": "deterministic schooling with snapshot avoidance"},
                              "camera_resolutions": camera_specs,
                              "composite_resolution": [WIDTH, HEIGHT], "fps": args.fps,
                              "frames": len(targets), "variable_speed": True,
                              "inspection_config": config.get("inspection", {"enabled": False}),
                              "synchronized_render_products": True, "server_started": False,
                              "geometry_validation": geometry_audit.report(),
                              "wall_seconds": time.monotonic() - started}
        (args.output / "state.json").write_text(json.dumps(final, indent=2))
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print("PELAGIC_OFFLINE_FINISHED " + json.dumps(final["metrics"]), flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        if encoder:
            if encoder.stdin:
                encoder.stdin.close()
            encoder.terminate()
            encoder.wait()
        app.close()


if __name__ == "__main__":
    main()
