#!/usr/bin/env python3
"""Run the genuine team mission controller and save an offline renderer trace."""
from pathlib import Path
import argparse, copy, dataclasses, gzip, json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parents[1])]
from reefsim.config import load_config
from reefsim.team_adapter import ReefRobotAdapter
from agent.base_station import BaseStation,Rack
from agent.config import FSMConfig,NavConfig
from mission.runner import run_mission
from perception.registry import SemanticMapEntry,SemanticSeabedRegistry
from perception.gemma_client import GemmaReply

class ExplicitOfflineDemo:
    model='offline-premapped-demo'; calls=0
    def ask(self,prompt,image_png,json_schema=None):
        self.calls+=1
        return GemmaReply('{"objects": []}',0.,{'backend':'offline_demo','model_call':False})

def plan(output,config_path=None,inject_drop=True):
    config=load_config(config_path or ROOT/'configs/natural_reef.json')
    config['mission']['planting_sites']=1
    config['render'].update(natural_cuttings=True,reef_quality=True,smooth_transitions=True,reef_hero_colonies=48,reef_triangle_budget=20_000_000, recovery_clearings=[{'center':[-.9,-1.67],'radius':.28}])
    config['assumptions']['scale']='Natural 5–9 cm branch clusters extracted from the donor scan; geometric cutting and reduced attachment physics, not a validated field harvesting device.'
    robot=ReefRobotAdapter(config,inject_drop=inject_drop)
    registry=SemanticSeabedRegistry()
    for c in robot.sim.corals:
        health={'healthy':'LIVE','bleached_alive':'BLEACHED','dead':'DEAD'}[c['health']]
        registry.upsert(SemanticMapEntry(c['id'],'pocillopora',health,.9 if health=='LIVE' else .3,
            (c['position'][0],c['position'][1],c['height']/2),(c['radius']*2,c['radius']*2,c['height']),
            genet_id=c.get('genet_id') if c['substrate_suitable'] or c['donor_capacity'] else None))
        c['observed']=True
        c['task_status']='eligible' if c['substrate_suitable'] else 'excluded'
        robot.sim.observations[c['id']]=dict(c,confidence=.95)
    racks=[]
    for c in robot.sim.corals:
        fragments=[f['id'] for f in robot.sim.fragments if f['donor_id']==c['id']]
        if fragments:
            racks.append(Rack(c['id'],c['genet_id'],'pocillopora',len(fragments),.95,
                tuple(c['position']),'living_reef',tuple(fragments)))
    station=BaseStation((0.,0.,0.),racks)
    output.mkdir(parents=True,exist_ok=True)
    cfg=FSMConfig(nav=NavConfig(max_speed=.65,carry_speed_scale=.7,timeout_s=160),
        survey_bounds=(-2.9,-2.9,-3.4,-3.4),hull_altitude=1.3,revisit_days=())
    model=ExplicitOfflineDemo()
    summary=run_mission(robot,model,base_station=station,genet_library=[],wait=robot.wait,
        fragment_held=robot.fragment_held,placement_verifier=robot.placement_verifier,
        registry=registry,config=cfg,out_dir=output/'mission',max_steps=100)
    robot.worker['state']='COMPLETE' if summary.final_state=='MISSION_COMPLETE' else 'ABORTED'
    robot.wait(2.)
    config['render']['quality_focus_ids']=[robot.source['id'],robot.recipient['id']]
    # The chosen attachment surface is fixed geometry for the entire take.
    # Share its final planning metadata with initial scene build; no moving or
    # invented recipient branch is authored halfway through the recording.
    for frame in robot.frames:
        for colony in frame['corals']:
            final=robot.sim._truth_by_id[colony['id']]
            if final.get('contact_fixture',{}):
                for key in ('contact_fixture','planting_point','contact_base','contact_point','contact_normal'):
                    colony[key]=copy.deepcopy(final[key])
    report={'summary' :dataclasses.asdict(summary),'audit':robot.audit,'push_tests':robot.push_tests,
        'sensor_mode':'explicit offline demo with pre-mapped colonies and analytical UV gate',
        'model_calls':0,'demo_interface_calls':model.calls,'drop_injected':robot.drop_done,
        'snapshot_count':len(robot.frames),'sim_duration_s':robot.sim.time}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    with gzip.open(output/'trace.json.gz','wt',compresslevel=3) as stream:
        json.dump({'config':config,'frames':robot.frames,'report':report},stream,separators=(',',':'))
    print(json.dumps(report,indent=2))
    if summary.final_state!='MISSION_COMPLETE' or not robot.push_tests or not all(p['stable'] and p['contact'] for p in robot.push_tests):
        raise RuntimeError('Team mission did not complete and verify a placement')
    return robot,report

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--config',type=Path)
    args=parser.parse_args(); plan(args.output,args.config)
