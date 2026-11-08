#!/usr/bin/env python3
"""Record an authoritative team-mission trace through three offline RTX cameras.

The recorder never advances/replans the mission or calls an inference service.
Every frame is an existing snapshot; varying playback speed only emphasizes
inspection, manipulation, the injected drop, same-ID recovery and push checks.
"""
from __future__ import annotations

import argparse
import array
import bisect
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACTION_STATES = frozenset({
    "SCAN_RECIPIENT", "SCAN_DONOR", "APPROACH_FRAGMENT", "CLOSE_GRIPPER",
    "DETACH_FRAGMENT", "RETRACT_FRAGMENT", "LOWER_FRAGMENT", "SECURE_FRAGMENT",
    "OPEN_GRIPPER", "RETRACT_GRIPPER", "VERIFY_ATTACHMENT", "FRAGMENT_LOST",
    "RECOVER_FRAGMENT", "RECOVERY_APPROACH", "RECOVERY_GRASP", "RECOVERY_LIFT",
    "PUSH_APPROACH", "PUSH_TEST", "ORIENT_FRAGMENT",
})


def worker_of(state):
    robots = state.get("robots", [])
    return next((r for r in robots if r.get("role") == "restoration"), robots[-1] if robots else {})


def playback_weight(phase):
    if phase in {"FRAGMENT_LOST", "RECOVERY_GRASP", "PUSH_TEST"}:
        return 1.35
    if phase in ACTION_STATES:
        return 1.10
    if phase == "COMPLETE":
        return 1.
    return .18


def build_schedule(frames, fps=24, max_frames=2400):
    """Return bounded sampling with every phase occurrence's midpoint retained."""
    if len(frames) < 2 or not 1 <= fps <= 60 or max_frames < 2:
        raise ValueError("Need at least two snapshots/frames and fps in 1..60")
    times = [float(f["time"]) for f in frames]
    if any(not math.isfinite(t) for t in times) or any(b < a for a,b in zip(times,times[1:])):
        raise ValueError("Trace times must be finite and nondecreasing")
    phases = [str(worker_of(f).get("state", "UNKNOWN")) for f in frames]
    clock = [0.]
    for i in range(1,len(frames)):
        clock.append(clock[-1] + (times[i]-times[i-1])*playback_weight(phases[i]))
    if clock[-1] <= 0:
        raise ValueError("Trace must span positive simulation time")
    milestones = {"initial": 0, "complete" if phases[-1] == "COMPLETE" else "final": len(frames)-1}
    phase_runs = []
    first = 0
    for end in range(1,len(frames)+1):
        if end < len(frames) and phases[end] == phases[first]:
            continue
        middle = (first+end-1)//2
        label = re.sub(r"[^a-z0-9_-]", "_", phases[first].lower())
        name = f"phase_{len(phase_runs)+1:03d}_{label}"
        milestones[name] = middle
        phase_runs.append({"name": name, "state": phases[first], "start_tick": first,
                           "end_tick": end-1, "midpoint_tick": middle})
        first = end
    mandatory = sorted(set(milestones.values()))
    frame_count = min(max_frames,max(len(mandatory),math.ceil(clock[-1]*fps)+1))
    if len(mandatory) > max_frames:
        raise ValueError("max_frames is too small to retain all phase milestones")
    ticks = [min(len(frames)-1,bisect.bisect_left(clock,clock[-1]*i/(frame_count-1)))
             for i in range(frame_count)]
    # Replace a neighbouring uniform sample, preserving count. Even a
    # one-tick loss transition therefore appears in the resulting movie.
    reserved = set()
    for tick in mandatory:
        preferred = round(clock[tick]/clock[-1]*(frame_count-1))
        index = min((i for i in range(frame_count) if i not in reserved),key=lambda i:abs(i-preferred))
        reserved.add(index)
        ticks[index] = tick
    ticks.sort()
    return {"ticks": ticks, "milestones": milestones, "phase_runs": phase_runs,
            "fps": fps, "frame_count": frame_count, "duration_seconds": frame_count/fps,
            "simulation_duration": times[-1]-times[0], "weighted_duration": clock[-1],
            "sim_dt": .05, "action_states_seen": sorted(set(phases)&ACTION_STATES),
            "final_metrics": frames[-1].get("metrics", {}),
            "interpretation": "existing team-mission snapshots; variable playback speed only"}


class NativeScanAudit:
    """Independent USD checks for persistent natural scanned branch geometry."""
    def __init__(self, stage, snapshot):
        self.stage = stage
        self.baseline = self._read(snapshot)
        self.checks = 0
        self.records = []
        self.phases = set()
        self.contact_gaps = {}
        self.max_fragment_pose_error = 0.
        self.max_grasp_error = 0.
        self.grasp_headings = {}

    @staticmethod
    def _digest(points, counts, indices):
        digest = hashlib.sha256()
        digest.update(array.array("f",(float(v) for p in points for v in p)).tobytes())
        digest.update(array.array("i",map(int,counts)).tobytes())
        digest.update(array.array("i",map(int,indices)).tobytes())
        return digest.hexdigest()

    @staticmethod
    def _distance(a,b):
        return math.sqrt(sum((float(a[i])-float(b[i]))**2 for i in range(3)))

    def _roots(self, scope, field):
        prim = self.stage.GetPrimAtPath(scope)
        assert prim and prim.IsValid(), f"Missing geometry scope {scope}"
        roots = list(prim.GetChildren())
        result = {str(root.GetCustomDataByKey("reefsim:"+field)):root for root in roots}
        assert len(result) == len(roots), f"Duplicated identities in {scope}"
        return result

    def _read(self, snapshot):
        from pxr import Gf, Usd, UsdGeom
        roots = self._roots("/World/Fragments", "fragment_id")
        expected = {f["id"]:f for f in snapshot.get("fragments", [])}
        assert expected and set(roots) == set(expected), "Persistent fragment identities changed"
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        result = {}
        for identifier,fragment in expected.items():
            root = roots[identifier]
            mesh = UsdGeom.Mesh.Get(self.stage,root.GetPath().AppendChild("Cutting"))
            assert mesh and mesh.GetPrim().IsValid(), f"Missing native cutting {identifier}"
            assert len(list(root.GetChildren())) == 1, f"Extra/generated fragment geometry: {identifier}"
            points,counts,indices = mesh.GetPointsAttr().Get(),mesh.GetFaceVertexCountsAttr().Get(),mesh.GetFaceVertexIndicesAttr().Get()
            assert points and counts and sum(counts) == len(indices)
            assert all(math.isfinite(float(v)) for p in points for v in p)
            assert all(0 <= int(i) < len(points) for i in indices)
            assert UsdGeom.Imageable(mesh.GetPrim()).ComputeVisibility() != UsdGeom.Tokens.invisible
            matrix = cache.GetLocalToWorldTransform(mesh.GetPrim())
            scales = [matrix.TransformDir(Gf.Vec3d(*axis)).GetLength() for axis in ((1,0,0),(0,1,0),(0,0,1))]
            assert all(abs(scale-1.) < 2e-6 for scale in scales), "Fragment grew/scaled during transfer"
            origin = matrix.Transform(Gf.Vec3d(0.,0.,0.))
            pose_error = self._distance(origin,fragment.get("base_world",fragment["position"]))
            assert pose_error < 2e-5, f"Fragment world origin mismatch: {identifier}: {pose_error}"
            yaw = float(fragment.get("yaw",0.))
            heading = matrix.TransformDir(Gf.Vec3d(1.,0.,0.))
            assert self._distance(heading,(math.cos(yaw),math.sin(yaw),0.)) < 2e-5, "Fragment yaw mismatch"
            result[identifier] = {"mesh_path":str(mesh.GetPath()),"geometry_sha256":self._digest(points,counts,indices),
                                  "point_count":len(points),"face_count":len(counts),"pose_error_m":pose_error,
                                  "stage":fragment["stage"],"natural_cutting":bool(fragment.get("natural_cutting"))}
        return result

    def check(self, snapshot, milestone):
        from pxr import Gf, Usd, UsdGeom
        from reefsim.natural_contact import closest_point_on_triangle
        current = self._read(snapshot)
        assert set(current) == set(self.baseline)
        for identifier,data in current.items():
            assert data["mesh_path"] == self.baseline[identifier]["mesh_path"]
            assert data["geometry_sha256"] == self.baseline[identifier]["geometry_sha256"], f"Native geometry changed: {identifier}"
            self.max_fragment_pose_error = max(self.max_fragment_pose_error,data["pose_error_m"])
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        robots = self._roots("/World/Robots", "robot_id")
        fragments = {f["id"]:f for f in snapshot.get("fragments",[])}
        grasp_error = 0.
        for robot in snapshot.get("robots",[]):
            if robot.get("gripper_world") is None:
                continue
            root = robots[robot["id"]]
            gripper = self.stage.GetPrimAtPath(root.GetPath().AppendChild("Gripper"))
            if not gripper or not gripper.IsValid():
                assert robot.get("role") != "restoration", "Restoration gripper missing"
                continue
            grip_matrix = cache.GetLocalToWorldTransform(gripper)
            actual_grip = grip_matrix.ExtractTranslation()
            axis=grip_matrix.TransformDir(Gf.Vec3d(1,0,0))
            actual_heading=math.atan2(axis[1],axis[0])
            expected_heading=robot.get('yaw',0.)+robot.get('wrist_yaw',0.)
            assert abs((actual_heading-expected_heading+math.pi)%(2*math.pi)-math.pi)<2e-5, 'Rendered wrist orientation differs from controller'
            error = self._distance(actual_grip,robot["gripper_world"])
            assert error < 2e-5, f"Rendered gripper differs from authoritative pose: {error}"
            fragment = fragments.get(robot.get("fragment_id"))
            if fragment and fragment["stage"] in ("grasped","carried"):
                relative_heading=(actual_heading-fragment['yaw'])%(2*math.pi)
                initial_heading=self.grasp_headings.setdefault(fragment['id'],relative_heading)
                assert abs((relative_heading-initial_heading+math.pi)%(2*math.pi)-math.pi)<2e-5, 'Cutting twisted inside the closed jaws'
                matrix = cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(current[fragment["id"]]["mesh_path"]))
                local = fragment.get("grasp_point",(0.,0.,fragment.get("grasp_z",.045)))
                grasp = matrix.Transform(Gf.Vec3d(*local))
                error = max(error,self._distance(grasp,actual_grip))
                assert error < .001, f"Native branch is not held at its measured grasp: {error}"
            grasp_error = max(grasp_error,error)
        self.max_grasp_error = max(self.max_grasp_error,grasp_error)
        colonies = {c["id"]:c for c in snapshot.get("corals",[])}
        coral_roots = self._roots("/World/Corals", "coral_id")
        frame_gaps = {}
        for fragment in fragments.values():
            if fragment["stage"] != "placed":
                continue
            target = colonies[fragment["target_id"]]
            fixture = target.get("contact_fixture",{})
            assert "natural_fragment_contact_local" in fixture, "Placed native cutting lacks measured tissue contact"
            mesh = UsdGeom.Mesh.Get(self.stage,current[fragment["id"]]["mesh_path"])
            points = mesh.GetPointsAttr().Get()
            index = int(fixture["natural_fragment_contact_index"])
            assert 0 <= index < len(points), "Contact vertex is absent from native geometry"
            local = fixture["natural_fragment_contact_local"]
            assert self._distance(points[index],local) < 2e-6, "Contact metadata differs from actual branch vertex"
            matrix = cache.GetLocalToWorldTransform(mesh.GetPrim())
            world = tuple(matrix.Transform(Gf.Vec3d(points[index])))
            root = coral_roots[target["id"]]
            assert not self.stage.GetPrimAtPath(root.GetPath().AppendChild("RecipientContactTissue")), "Artificial recipient branch remains"
            recipient = UsdGeom.Mesh.Get(self.stage,root.GetPath().AppendChild("Colony"))
            recipient_matrix = cache.GetLocalToWorldTransform(recipient.GetPrim())
            recipient_points = recipient.GetPointsAttr().Get()
            recipient_indices = recipient.GetFaceVertexIndicesAttr().Get()
            offset = int(fixture["source_triangle_index"])*3
            tri_indices = recipient_indices[offset:offset+3]
            assert len(tri_indices) == 3, "Recorded recipient triangle missing"
            triangle = [tuple(recipient_matrix.Transform(Gf.Vec3d(recipient_points[i]))) for i in tri_indices]
            assert max(self._distance(a,b) for a,b in zip(triangle,fixture["contact_triangle_world"])) < 2e-5, "Actual recipient triangle changed"
            nearest = closest_point_on_triangle(world,*triangle)
            gap = self._distance(world,nearest)
            tolerance = float(fixture.get("contact_tolerance_m",.0015))
            assert gap <= tolerance+2e-5, f"Native tissue misses actual recipient triangle: {gap}m"
            frame_gaps[fragment["id"]] = gap
            self.contact_gaps[fragment["id"]] = max(gap,self.contact_gaps.get(fragment["id"],0.))
        self.checks += 1
        phase = worker_of(snapshot).get("state","UNKNOWN")
        self.phases.add(phase)
        self.records.append({"milestone":milestone,"sim_time":snapshot["time"],"phase":phase,
                             "max_fragment_pose_error_m":max(d["pose_error_m"] for d in current.values()),
                             "grasp_error_m":grasp_error,"contact_gaps_m":frame_gaps})

    def report(self):
        return {"passed":True,"checks":self.checks,"persistent_fragment_count":len(self.baseline),
                "geometry_unchanged":True,"fragment_world_pose_and_yaw_verified":True,
                "max_fragment_pose_error_m":self.max_fragment_pose_error,"max_grasp_error_m":self.max_grasp_error,
                "max_contact_surface_gaps_m":self.contact_gaps,"phases_checked":sorted(self.phases),
                "fragments":self.baseline,"records":self.records,
                "scope":"rendered geometry/kinematic contact checks; not biological recovery or physical force validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/team-mission-video")
    parser.add_argument("--preview-stills",action="store_true")
    parser.add_argument("--patch-recovery",action="store_true",help="Render only loss/recovery camera replacements as indexed PNGs")
    parser.add_argument("--current-review",action="store_true",help="Also capture an eight-second fixed-camera flow comparison")
    parser.add_argument("--fps",type=int,default=24)
    parser.add_argument("--max-frames",type=int,default=2400)
    parser.add_argument("--samples",type=int,default=4)
    parser.add_argument("--quality",type=int,default=18)
    args,kit_args = parser.parse_known_args()
    if args.samples < 1 or not 0 <= args.quality <= 40:
        parser.error("samples must be positive and quality CRF in 0..40")
    if args.patch_recovery and args.preview_stills:
        parser.error("patch-recovery requires the full movie schedule, not preview-stills")
    opener = gzip.open if args.trace.suffix == ".gz" else open
    with opener(args.trace,"rt",encoding="utf-8") as handle:
        trace = json.load(handle)
    config,frames = trace["config"],trace["frames"]
    schedule = build_schedule(frames,args.fps,args.max_frames)
    patch_indices = []
    if args.patch_recovery:
        losses = [i for i,tick in enumerate(schedule["ticks"]) if worker_of(frames[tick]).get("state") == "FRAGMENT_LOST"]
        lifts = [i for i,tick in enumerate(schedule["ticks"]) if worker_of(frames[tick]).get("state") == "RECOVERY_LIFT"]
        if not losses or not lifts or lifts[-1] < losses[0]:
            parser.error("patch-recovery requires a complete loss/recovery sequence")
        patch_indices = list(range(losses[0],min(len(schedule["ticks"]),lifts[-1]+121)))
    patch_index_set = set(patch_indices)
    ffmpeg = shutil.which("ffmpeg")
    if not args.preview_stills and not args.patch_recovery and not ffmpeg:
        parser.error("ffmpeg is required for offline MP4 recording")
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"schedule.json").write_text(json.dumps(schedule,indent=2))
    print("PELAGIC_TEAM_SCHEDULE "+json.dumps({k:v for k,v in schedule.items() if k not in ("ticks","phase_runs")}),flush=True)
    sys.argv = [sys.argv[0],*kit_args]
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True)
    from isaacsim import SimulationApp
    app = SimulationApp({"headless":True,"renderer":"RaytracedLighting","sync_loads":True,"width":1280,"height":720})
    faulthandler.cancel_dump_traceback_later()
    encoder = None
    try:
        import omni.usd
        import omni.timeline
        import omni.replicator.core as rep
        from PIL import Image
        from reefsim.isaac_scene import IsaacReefScene
        from reefsim.compositor import compose_frame,WIDTH,HEIGHT
        from scripts.render_demo import _capture
        from scripts.validate_linkage import check_linkage, preflight_linkages
        early_linkage = preflight_linkages(config,[frames[t] for t in sorted(set(schedule["milestones"].values()))])
        (args.output/"linkage-preflight.json").write_text(json.dumps(early_linkage,indent=2))
        print("REEF_RESCUE_LINKAGE_PREFLIGHT_PASSED",flush=True)
        context = omni.usd.get_context()
        context.new_stage()
        stage = context.get_stage()
        scene = IsaacReefScene(stage,config)
        state = copy.deepcopy(frames[0])
        scene.build(state)
        scene.update(state)
        audit = NativeScanAudit(stage,state)
        audit.check(state,"initial")
        linkage_checks = [check_linkage(scene,state)]
        for name,tick in sorted(schedule['milestones'].items(),key=lambda item:item[1]):
            preflight=frames[tick]
            scene.update(preflight)
            audit.check(preflight,'preflight_'+name)
            linkage_checks.append(check_linkage(scene,preflight))
        scene.update(state)
        print('PELAGIC_TEAM_PREFLIGHT_PASSED',flush=True)
        specs = {"director":(1280,720),"scout":(400,240),"worker":(400,240)}
        products = {}
        for key,resolution in specs.items():
            product = rep.create.render_product(scene.CAMERA_PATHS[key],resolution)
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            rgb.attach([product]); depth.attach([product])
            products[key] = rgb,depth
        scene.set_camera("director",state)
        omni.timeline.get_timeline_interface().play()
        for _ in range(24):
            app.update()
        if args.preview_stills:
            for region in state.get("regions",[]):
                if region.get("policy") == "avoid":
                    continue
                x,y = region["center"][:2]
                scene._look_at("director",(x-.6,y-2.1,1.05),(x,y,.22))
                for _ in range(12):
                    app.update()
                Image.fromarray(_capture(*products["director"],state,True,seed=0,scene=scene,camera="director")).save(args.output/f"habitat-{region['health']}.png")
            scene.update(state)
            targets = sorted((tick,name) for name,tick in schedule["milestones"].items())
        else:
            targets = [(tick,f"frame-{i:05d}") for i,tick in enumerate(schedule["ticks"])]
            if not args.patch_recovery:
                encoder = subprocess.Popen([ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y",
                    "-f","rawvideo","-pixel_format","rgb24","-video_size",f"{WIDTH}x{HEIGHT}",
                    "-framerate",str(args.fps),"-i","pipe:0","-an","-c:v","libx264","-preset","veryfast",
                    "-crf",str(args.quality),"-pix_fmt","yuv420p","-movflags","+faststart",str(args.output/"reef-rescue-mission.mp4")],stdin=subprocess.PIPE)
        started = time.monotonic()
        manifest = []
        previous_tick,previous_phase = 0,None
        milestone_ticks = set(schedule["milestones"].values())
        for index,(tick,name) in enumerate(targets):
            state = copy.deepcopy(frames[tick])
            if not args.preview_stills:
                state["_presentation_dt"] = 1. / args.fps
            if args.patch_recovery and index not in patch_index_set:
                # Preserve the full director filter history at presentation
                # cadence, including identical/repeated trace timestamps.
                scene._update_cameras(state)
                previous_tick,previous_phase = tick,worker_of(state).get("state","UNKNOWN")
                continue
            scene.update(state)
            if config.get("inspection",{}).get("enabled"):
                state["inspection"] = scene.inspection_metadata()
            state["motion"] = scene.motion_metadata()
            worker = worker_of(state)
            phase = worker.get("state","UNKNOWN")
            check = (args.preview_stills or phase != previous_phase or tick in milestone_ticks or index == len(targets)-1
                     or (args.patch_recovery and index in (patch_indices[0],patch_indices[-1])))
            if check:
                audit.check(state,name)
                linkage_checks.append(check_linkage(scene,state))
            for _ in range(max(12,args.samples) if args.preview_stills else args.samples):
                app.update()
            images = {key:_capture(*products[key],state,key=="director",seed=tick,scene=scene,camera=key) for key in specs}
            speed = 1. if args.preview_stills else max(.1,(state["time"]-frames[previous_tick]["time"])*args.fps)
            composite = compose_frame(images["director"],images["scout"],images["worker"],state,speed,keyframe=args.preview_stills)
            if not args.preview_stills and tick in milestone_ticks:
                review_dir = args.output/"render-review"
                review_dir.mkdir(exist_ok=True)
                composite.save(review_dir/f"{index:04d}-{phase}.jpg",quality=92)
            if args.patch_recovery:
                composite.save(args.output/f"patch-{index:05d}.png")
            elif args.preview_stills:
                composite.save(args.output/f"preview-{index+1:03d}-{name}.png")
                for key in specs:
                    Image.fromarray(images[key]).save(args.output/f"preview-{index+1:03d}-{name}-{key}.png")
            else:
                try:
                    encoder.stdin.write(composite.tobytes())
                except BrokenPipeError as error:
                    raise RuntimeError("ffmpeg stopped accepting video frames") from error
            if check or index % 50 == 0:
                record = {"frame":index,"tick":tick,"name":name,"sim_time":state["time"],"worker_state":phase,
                          "fragment_id":worker.get("fragment_id"),"carrying":worker.get("carrying"),
                          "gripper_world":worker.get("gripper_world"),"gripper_open":worker.get("gripper_open"),
                          "team_mission":state.get("team_mission"),"metrics":state.get("metrics"),
                          "inspection":state.get("inspection"),"motion":state.get("motion"),
                          "hydrodynamics":worker.get("hydrodynamics"),"elapsed_wall_seconds":time.monotonic()-started}
                manifest.append(record)
                print("PELAGIC_TEAM_FRAME "+json.dumps(record),flush=True)
            previous_tick,previous_phase = tick,phase
        if encoder:
            encoder.stdin.close()
            code = encoder.wait()
            if code:
                raise RuntimeError(f"ffmpeg exited with status {code}")
            encoder = None
        final = copy.deepcopy(frames[-1])
        final["mode"] = "isaac-team-offline-pip"
        final["recording"] = {"camera_paths":{k:scene.CAMERA_PATHS[k] for k in specs},"camera_resolutions":specs,
                              "composite_resolution":[WIDTH,HEIGHT],"fps":args.fps,"frames":len(targets),
                              "preview_stills":args.preview_stills,"samples":args.samples,
                              "scenery_quality":getattr(scene,"scenery_quality_stats",{}),
                              "scanned_colonies":scene.scanned_colony_count,"variable_speed":True,
                              "synchronized_render_products":True,"server_started":False,
                              "trace_summary":trace.get("summary",trace.get("report",{})),"geometry_validation":audit.report(),
                              "wall_seconds":time.monotonic()-started}
        for filename,value in (("geometry-validation.json",audit.report()),("linkage-validation.json",{"passed":True,"checks":linkage_checks}),("state.json",final),("manifest.json",manifest)):
            (args.output/filename).write_text(json.dumps(value,indent=2))
        if args.patch_recovery:
            patch_manifest = {"mode":"native Isaac recovery camera replacement",
                              "trace":str(args.trace.resolve()),"trace_sha256":hashlib.sha256(args.trace.read_bytes()).hexdigest(),
                              "full_schedule_frame_count":schedule["frame_count"],"fps":args.fps,
                              "patch_indices":patch_indices,"rendered_frame_count":len(patch_indices),
                              "pattern":"patch-{index:05d}.png","camera_history":"all schedule entries stepped in order",
                              "geometry_validation":audit.report(),"linkage_validation":{"passed":True,"checks":linkage_checks},
                              "current_review":False,"mp4_encoder_started":False}
            (args.output/"patch-manifest.json").write_text(json.dumps(patch_manifest,indent=2))
        if args.current_review and not args.preview_stills and not args.patch_recovery:
            from reefsim.reef_detail_compositor import compose_current
            source = frames[0]
            zero = scene.aim_current(source, 0., current_override=[0.,0.,0.])
            assert scene.motion_metadata()["max_tip_displacement_m"] < 1e-9
            for _ in range(16): app.update()
            reference = _capture(*products["director"],zero,True,seed=0,scene=scene,camera="director")
            current_movie = args.output / "reef-rescue-current.mp4"
            encoder = subprocess.Popen([ffmpeg,"-v","error","-y","-f","rawvideo","-pix_fmt","rgb24",
                "-s",f"{WIDTH}x{HEIGHT}","-r",str(args.fps),"-i","pipe:0","-an","-c:v","libx264",
                "-preset","fast","-crf",str(args.quality),"-pix_fmt","yuv420p","-movflags","+faststart",str(current_movie)],stdin=subprocess.PIPE)
            motion_records = []
            for index in range(8*args.fps):
                elapsed = index/args.fps
                state = scene.aim_current(source, elapsed)
                for _ in range(args.samples): app.update()
                active = _capture(*products["director"],state,True,seed=index,scene=scene,camera="director")
                macro = _capture(*products["worker"],state,False,seed=index,scene=scene,camera="worker")
                metadata = scene.motion_metadata()
                motion_records.append(dict(metadata,time=elapsed))
                encoder.stdin.write(compose_current(reference,active,macro,metadata,elapsed=elapsed,duration=8.).tobytes())
                if index % 48 == 0: print("REEF_RESCUE_CURRENT_FRAME "+str(index),flush=True)
            encoder.stdin.close()
            if encoder.wait(): raise RuntimeError("Current review encoding failed")
            encoder = None
            tips = [r["tracked_tip_world"] for r in motion_records]
            excursion = max(math.dist(a,b) for a in tips for b in tips)
            assert excursion > .02, "Current review shows insufficient flexible fan movement"
            (args.output/"current-validation.json").write_text(json.dumps({"zero_current_rest_passed":True,
                "fan_tip_excursion_m":excursion,"records":motion_records,"seconds":8,"frames":8*args.fps,
                "scope":"controlled renderer inspection; reduced damped flexible-tissue physics"},indent=2))
        print("PELAGIC_TEAM_OFFLINE_FINISHED "+json.dumps(final.get("metrics",{})),flush=True)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        if encoder:
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()
            encoder.terminate()
            encoder.wait()
        app.close()


if __name__ == "__main__":
    main()
