#!/usr/bin/env python3
"""Capture exactly 60 seconds from the live MJPEG display without cuts or retiming.

The MJPEG source repeats its current rendered view at 10 Hz with visible refresh
age. The capture retains source receipt timestamps; it never substitutes replay.
Successful encoding alone does not establish model inference or restoration.
"""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess, threading, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

DURATION=60
FPS=10

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,nb_read_frames,r_frame_rate,codec_name','-show_entries','format=duration','-of','json',str(path)]))

def validate_probe(value):
    stream=value['streams'][0];duration=float(value['format']['duration']);frames=int(stream['nb_read_frames']);rate=stream['r_frame_rate']
    if abs(duration-DURATION)>.001 or frames!=DURATION*FPS or rate!='10/1':raise ValueError(f'Capture is not exactly 60 seconds / 600 frames at 10 fps: {duration}, {frames}, {rate}')
    return {'durationSeconds':duration,'frames':frames,'fps':FPS,'width':stream['width'],'height':stream['height'],'codec':stream['codec_name']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',default='http://127.0.0.1:8780');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Choose a new output path; captures are never overwritten')
    a.output.parent.mkdir(parents=True,exist_ok=True);source=a.source.rstrip('/');receipts=[];stop=threading.Event()
    def observe():
        while not stop.is_set():
            received=datetime.now(timezone.utc).isoformat()
            try:
                with urlopen(source+'/api/source',timeout=2) as r:data=json.load(r)
                receipts.append({'receivedAt':received,'monotonic':time.monotonic(),'source':data})
            except Exception as e:receipts.append({'receivedAt':received,'error':str(e)[:180]})
            stop.wait(.5)
    # No credential-bearing URL or unrelated network source is accepted.
    from urllib.parse import urlsplit
    u=urlsplit(source)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password:p.error('Use a loopback live-stream URL (SSH tunnel if remote)')
    with urlopen(source+'/api/source',timeout=5) as r:initial=json.load(r)
    if initial.get('sourceMode')!='live_isaac_rtx':p.error('Live Isaac source manifest is required')
    started=time.monotonic();start_wall=datetime.now(timezone.utc).isoformat();threading.Thread(target=observe,daemon=True).start()
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','warning','-r',str(FPS),'-f','mpjpeg','-i',source+'/stream.mjpg','-an','-frames:v',str(DURATION*FPS),'-r',str(FPS),'-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)]
    try:subprocess.run(command,check=True,timeout=100)
    finally:stop.set()
    elapsed=time.monotonic()-started;validation=validate_probe(probe(a.output));valid_source=[r['source'] for r in receipts if 'source'in r];sequences={s.get('sequence') for s in valid_source};times=[s['simTime'] for s in valid_source if isinstance(s.get('simTime'),(int,float))]
    # Constant stream cadence must be close to wall time; a delayed source cannot
    # silently compress a long interval into a minute and still pass validation.
    continuous=58<=elapsed<=65 and len(sequences)>1 and all(b>=a for a,b in zip(times,times[1:]))
    record={'capturedAt':start_wall,'source':source,'durationSeconds':DURATION,'wallElapsedSeconds':elapsed,'video':validation,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'sourceReceipts':receipts,'continuousWallClockCheck':continuous,'sourceSamples':len(receipts),'distinctSourceSequences':len(sequences),'edited':False,'retimed':False,'sourceFrameAgeVisible':True,'taskOutcomeVerified':False,'limits':['This checks stream capture continuity, not model inference, current-driven fragment loss or completed restoration.','Repeated current camera frames remain visible with their refresh age; no interpolation creates new imagery.']}
    a.output.with_suffix('.evidence.json').write_text(json.dumps(record,indent=2))
    if not continuous:raise SystemExit('Exact-duration file encoded, but source continuity/wall-time check failed; do not present as validated live take')
    print(json.dumps({'video':str(a.output),'validation':validation,'wallElapsedSeconds':elapsed,'taskOutcomeVerified':False}),flush=True)
if __name__=='__main__':main()
