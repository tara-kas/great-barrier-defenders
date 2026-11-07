#!/usr/bin/env python3
"""Record an offline 25-second current, tissue and robot-light detail reel.

The deterministic mission is never stepped. Renderer-only inspection poses
provide controlled fixed-camera evidence of current motion and appearance.
"""
from __future__ import annotations

import argparse
import array
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def select_detail_cases(corals, profiles):
    cases={}
    for health in ("healthy","bleached_alive","dead"):
        candidates=[c for c in corals if c["health"]==health]
        if not candidates:raise ValueError(f"Missing {health} detail case")
        coral=min(candidates,key=lambda c:c["id"])
        cases[health]={"coral_id":coral["id"],"health":health,
                       "profile":copy.deepcopy(profiles[coral["id"]])}
    return cases


def topology_signature(stage):
    from pxr import UsdGeom
    digest=hashlib.sha256()
    for prim in stage.Traverse():
        if str(prim.GetPath()).startswith("/World/") and prim.IsA(UsdGeom.Mesh):
            mesh=UsdGeom.Mesh(prim)
            digest.update(str(prim.GetPath()).encode())
            digest.update(array.array("i",mesh.GetFaceVertexCountsAttr().Get()).tobytes())
            digest.update(array.array("i",mesh.GetFaceVertexIndicesAttr().Get()).tobytes())
            digest.update(str(len(mesh.GetPointsAttr().Get())).encode())
    return digest.hexdigest()


def peak_to_peak(points):
    if not points:return 0.
    return max(math.dist(a,b) for i,a in enumerate(points) for b in points[i:])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=ROOT/"configs/natural_reef.json")
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/reef-natural-details")
    parser.add_argument("--fps",type=int,default=24)
    parser.add_argument("--samples",type=int,default=3)
    parser.add_argument("--quality",type=int,default=17)
    parser.add_argument("--preview-stills",action="store_true")
    args,kit_args=parser.parse_known_args()
    if not 1<=args.fps<=60 or args.samples<1 or not 0<=args.quality<=40:
        parser.error("Use fps1–60, positive samples and CRF0–40")
    ffmpeg=shutil.which("ffmpeg")
    if not args.preview_stills and not ffmpeg:parser.error("ffmpeg is required")
    from reefsim.config import load_config
    config=load_config(args.config)
    config.setdefault("inspection",{})["enabled"]=True
    args.output.mkdir(parents=True,exist_ok=True)
    sys.argv=[sys.argv[0],*kit_args]
    from isaacsim import SimulationApp
    app=SimulationApp({"headless":True,"renderer":"RaytracedLighting","sync_loads":True,
                       "width":1280,"height":720})
    encoder=None
    try:
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from reefsim.core import ReefSimulation
        from reefsim.isaac_scene import IsaacReefScene
        from reefsim.reef_detail_compositor import compose_current,compose_tissue,WIDTH,HEIGHT
        from scripts.render_demo import _capture
        from scripts.render_inspection import _scene_signature,_camera_poses,_validate_response

        simulation=ReefSimulation(config)
        baseline=simulation.snapshot()
        baseline_json=json.dumps(baseline,sort_keys=True)
        context=omni.usd.get_context();context.new_stage();stage=context.get_stage()
        scene=IsaacReefScene(stage,config);scene.build(baseline)
        cases=select_detail_cases(baseline["corals"],scene.inspection_profiles)
        cameras={"director":(960,540),"worker":(960,540),"overview":(640,360)}
        products={}
        for key,resolution in cameras.items():
            product=rep.create.render_product(scene.CAMERA_PATHS[key],resolution)
            rgb=rep.AnnotatorRegistry.get_annotator("rgb")
            depth=rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
            rgb.attach([product]);depth.attach([product]);products[key]=(rgb,depth)
        paths={str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith("/World/")}
        hard_signature=_scene_signature(stage)
        topology=topology_signature(stage)
        omni.timeline.get_timeline_interface().play()
        duration=25.
        full_frames=25*args.fps
        if not args.preview_stills:
            encoder=subprocess.Popen([ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-y",
                "-f","rawvideo","-pixel_format","rgb24","-video_size",f"{WIDTH}x{HEIGHT}",
                "-framerate",str(args.fps),"-i","pipe:0","-an","-c:v","libx264","-preset","veryfast",
                "-crf",str(args.quality),"-pix_fmt","yuv420p","-movflags","+faststart",
                str(args.output/"pelagic-reef-details.mp4")],stdin=subprocess.PIPE)
        started=time.monotonic();frame=0;rendered=0;records=[];motion_records=[];checks=0

        def verify_scene():
            nonlocal checks
            assert _scene_signature(stage)==hard_signature,"Hard coral/cutting geometry or pose changed"
            assert topology_signature(stage)==topology,"Scene mesh topology changed"
            assert {str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith("/World/") }==paths,"New scene geometry appeared"
            assert json.dumps(simulation.snapshot(),sort_keys=True)==baseline_json,"Mission state changed"
            checks+=1

        def capture(state,warm=False):
            for _ in range(max(12,args.samples) if warm else args.samples):app.update()
            return {key:_capture(*products[key],state,key!="worker",seed=frame,scene=scene,camera=key) for key in cameras}

        def check_input(state):
            assert state["corals"]==baseline["corals"] and state["fragments"]==baseline["fragments"]
            assert json.dumps(baseline,sort_keys=True)==baseline_json,"View helper mutated input snapshot"

        def write(composite,name):
            nonlocal rendered
            if args.preview_stills:composite.save(args.output/(name+".png"))
            else:encoder.stdin.write(composite.tobytes())
            rendered+=1

        # The reference is independently rendered with zero current, at a time
        # where the analytic model would otherwise show established flow.
        state=scene.aim_current(baseline,4.,current_override=[0.,0.,0.]);check_input(state)
        reference=capture(state,True)["director"].copy()
        zero_before=scene.motion_metadata()
        assert zero_before["max_tip_displacement_m"]<1e-9
        assert zero_before["max_polyp_displacement_m"]<1e-9
        reference_poses=_camera_poses(stage,{k:scene.CAMERA_PATHS[k] for k in ("director","worker")})
        selected={0,4*args.fps,8*args.fps-1}
        for index in range(8*args.fps):
            elapsed=index/args.fps
            state=scene.aim_current(baseline,elapsed);check_input(state)
            motion=scene.motion_metadata()
            tip=motion["tracked_tip_world"]
            assert len(tip)==3 and all(math.isfinite(v) for v in tip)
            motion_records.append(dict(motion,time=elapsed))
            poses=_camera_poses(stage,{k:scene.CAMERA_PATHS[k] for k in ("director","worker")})
            assert poses==reference_poses,"Current comparison moved the fixed camera"
            if not args.preview_stills or index in selected:
                images=capture(state,index==0)
                composite=compose_current(reference,images["director"],images["worker"],motion,elapsed=elapsed,duration=duration)
                write(composite,f"current-{index:03d}")
            if index%args.fps==0:
                print("PELAGIC_DETAIL_CURRENT "+json.dumps({"frame":frame,"time":elapsed,"motion":motion}),flush=True)
            frame+=1
        spread=peak_to_peak([r["tracked_tip_world"] for r in motion_records])
        assert spread>.02,f"Visible fan motion too small: {spread:.4f}m peak-to-peak"
        state=scene.aim_current(baseline,8.,current_override=[0.,0.,0.]);check_input(state)
        zero_after=scene.motion_metadata()
        assert zero_after["max_tip_displacement_m"]<1e-9
        assert zero_after["max_polyp_displacement_m"]<1e-9
        verify_scene()

        segments=(("healthy","white",3),("bleached_alive","white",3),
                  ("bleached_alive","blue",4),("bleached_alive","uv",4),("dead","white",3))
        white_references={};white_poses={};beam_off=[]
        for number,(health,mode,seconds) in enumerate(segments,1):
            case=cases[health];count=seconds*args.fps
            preview_at=count//2
            for index in range(count):
                elapsed=frame/args.fps
                if args.preview_stills and index!=preview_at:
                    frame+=1;continue
                source=copy.deepcopy(baseline);source["time"]=elapsed
                source_json=json.dumps(source,sort_keys=True)
                state=scene.aim_inspection(source,case["coral_id"],mode)
                assert json.dumps(source,sort_keys=True)==source_json
                check_input(state)
                images=capture(state,index in (0,preview_at) if args.preview_stills else index==0)
                metadata=scene.inspection_metadata();_validate_response(case,metadata,mode)
                poses=_camera_poses(stage,{k:scene.CAMERA_PATHS[k] for k in ("worker","overview")})
                if mode=="white":
                    if health not in white_references:
                        white_references[health]=images["worker"].copy();white_poses[health]=poses
                else:assert poses==white_poses[health],"Optical mode comparison changed camera pose"
                composite=compose_tissue(images["worker"],images["overview"],white_references.get(health),
                    case,metadata,elapsed=elapsed,duration=duration)
                write(composite,f"case-{number:02d}-{health}-{mode}")
                if index==0 or args.preview_stills:
                    record={"segment":number,"health":health,"mode":mode,"frame":frame,"case":case,
                            "metadata":metadata,"camera_poses":poses,"wall_seconds":time.monotonic()-started}
                    records.append(record);print("PELAGIC_DETAIL_CASE "+json.dumps(record),flush=True)
                frame+=1
            scene.set_inspection_mode(mode,target_id=case["coral_id"],strength=0.)
            off=scene.inspection_metadata();assert max(off["emission_rgb"])<1e-8
            beam_off.append({"health":health,"mode":mode,"emission_rgb":off["emission_rgb"]})
            verify_scene()
        assert frame==full_frames
        if encoder:
            encoder.stdin.close()
            if encoder.wait():raise RuntimeError("ffmpeg encoding failed")
            encoder=None
        evidence={"result":"PASS","server_started":False,"recording_kind":"fixed-camera current and tissue detail tour",
            "mission_state_unchanged":True,"hard_coral_fragment_geometry_unchanged":True,
            "scene_topology_unchanged":True,"geometry_checks":checks,"hard_geometry_signature":hard_signature,
            "topology_signature":topology,"fan_tip_peak_to_peak_m":spread,
            "max_polyp_displacement_m":max(r["max_polyp_displacement_m"] for r in motion_records),
            "zero_current_before":zero_before,"zero_current_after":zero_after,"beam_off_checks":beam_off,
            "current_camera_pose_invariant":True,"bleached_camera_pose_invariant_across_modes":True,
            "cases":cases,"segments":[{"health":h,"mode":m,"seconds":s} for h,m,s in segments],
            "camera_paths":{k:scene.CAMERA_PATHS[k] for k in cameras},"camera_resolutions":cameras,
            "fps":args.fps,"frames":frame,"rendered_images":rendered,"duration_seconds":duration,
            "composite_resolution":[WIDTH,HEIGHT],"preview_stills":args.preview_stills,
            "wall_seconds":time.monotonic()-started,
            "interpretation":"Reduced-order soft-tissue response; UV invisible and visible violet aiming cone labelled; RGB fluorescence proxy; no biological recovery"}
        if not args.preview_stills:
            probe=subprocess.run(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
                "-show_entries","stream=width,height,nb_read_frames,r_frame_rate","-show_entries","format=duration,size",
                "-of","json",str(args.output/"pelagic-reef-details.mp4")],capture_output=True,text=True,check=True)
            media=json.loads(probe.stdout);stream=media["streams"][0]
            assert [stream["width"],stream["height"]]==[WIDTH,HEIGHT]
            assert int(stream["nb_read_frames"])==full_frames==rendered
            assert abs(float(media["format"]["duration"])-duration)<.1
            evidence["video"]=media
        (args.output/"validation.json").write_text(json.dumps(evidence,indent=2))
        (args.output/"manifest.json").write_text(json.dumps(records,indent=2))
        (args.output/"motion-samples.json").write_text(json.dumps(motion_records,indent=2))
        (args.output/"baseline-state.json").write_text(json.dumps(baseline,indent=2))
        print("PELAGIC_DETAILS_FINISHED "+json.dumps({"result":"PASS","frames":frame,"fan_tip_peak_to_peak_m":spread}),flush=True)
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
    finally:
        if encoder:
            if encoder.stdin and not encoder.stdin.closed:encoder.stdin.close()
            encoder.terminate();encoder.wait()
        app.close()


if __name__=="__main__":main()
