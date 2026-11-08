#!/usr/bin/env python3
"""Validate a completed offline team recording and extract actual MP4 review frames."""
from pathlib import Path
import argparse, hashlib, json, math, shutil, subprocess


def validate(output):
    movie=output/'pelagic-team-pip.mp4'
    state=json.loads((output/'state.json').read_text())
    schedule=json.loads((output/'schedule.json').read_text())
    geometry=json.loads((output/'geometry-validation.json').read_text())
    if not movie.is_file() or not geometry.get('passed'):
        raise RuntimeError('Completed MP4 and passing native geometry report are required')
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise RuntimeError('ffmpeg and ffprobe are required')
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,avg_frame_rate,nb_frames,duration','-of','json',str(movie)]))['streams'][0]
    assert (probe['width'],probe['height'])==(1600,900)
    assert int(probe['nb_frames'])==schedule['frame_count']
    assert abs(float(probe['duration'])-schedule['duration_seconds'])<1/schedule['fps']
    subprocess.run([ffmpeg,'-v','error','-i',str(movie),'-f','null','-'],check=True)
    recording=state['recording']; report=recording['trace_summary']
    assert recording['server_started'] is False
    assert report['summary']['final_state']=='MISSION_COMPLETE'
    assert report['model_calls']==0
    events=report['audit']
    harvest=next(e for e in events if e['event']=='harvest')
    loss=next(e for e in events if e['event']=='fragment_lost')
    recovery=next(e for e in events if e['event']=='recovered')
    placement=next(e for e in events if e['event']=='placed')
    push=next(e for e in events if e['event']=='push_test')
    assert len([e for e in events if e['event']=='harvest'])==1
    assert len({e['fragment_id'] for e in (harvest,loss,recovery,placement,push)})==1
    assert harvest['time']<loss['time']<recovery['time']<placement['time']<push['time']
    approvals=[e for e in events if e['event'] in ('uv_recipient','uv_donor')]
    assert len(approvals)==2 and all(e['accepted'] and e['timestamp']<harvest['time'] for e in approvals)
    assert push['stable'] and push['contact'] and push['max_contact_gap_m']<=.0015
    required={'SCAN_RECIPIENT','SCAN_DONOR','CLOSE_GRIPPER','FRAGMENT_LOST','RECOVERY_GRASP','LOWER_FRAGMENT','OPEN_GRIPPER','PUSH_TEST','VERIFY_ATTACHMENT'}
    assert required.issubset(set(geometry['phases_checked']))
    review=output/'video-review';review.mkdir(exist_ok=True)
    extracted=[]
    for run in schedule['phase_runs']:
        if run['state'] not in required: continue
        index=min(range(len(schedule['ticks'])),key=lambda i:abs(schedule['ticks'][i]-run['midpoint_tick']))
        path=review/(run['name']+'.png')
        subprocess.run([ffmpeg,'-v','error','-y','-ss',str(index/schedule['fps']),'-i',str(movie),'-frames:v','1',str(path)],check=True)
        extracted.append({'phase':run['state'],'frame':index,'path':str(path.resolve())})
    result={'passed':True,'movie':str(movie.resolve()),'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),
        'bytes':movie.stat().st_size,'probe':probe,'native_geometry_checks':geometry['checks'],
        'max_contact_gap_m':push['max_contact_gap_m'],'same_recovered_fragment':harvest['fragment_id'],
        'perception':'explicit offline pre-mapped demo; zero model calls','review_frames':extracted}
    (output/'video-validation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    validate(parser.parse_args().output)
