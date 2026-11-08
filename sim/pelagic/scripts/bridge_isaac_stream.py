#!/usr/bin/env python3
"""Observe an actual live Isaac HTTP feed; publish team files and an honest MJPEG view.

No mission commands, recorded footage, model calls, fabricated boxes or classifications.
Camera refresh age is visible. File-source observations remain explicitly synthetic.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, STREAM_FPS = 1280, 720, 10

def bounded_get(url, maximum=8*1024*1024):
    with urlopen(url, timeout=4) as response:
        value=response.read(maximum+1)
    if len(value)>maximum: raise ValueError('Source response exceeds bound')
    return value

def atomic(path, data):
    temporary=path.with_name(path.name+'.tmp');temporary.write_bytes(data);temporary.replace(path)

def team_registry(state):
    truths={c['id']:c for c in state.get('corals',[])}
    entries=[]
    for observation in state.get('observations',[]):
        identifier=observation['id'];truth=truths.get(identifier,{})
        status={'healthy':'LIVE','bleached_alive':'BLEACHED','dead':'DEAD'}.get(observation.get('health'))
        if status is None: continue
        if status=='BLEACHED' and truth.get('task_status')=='verified':status='TREATED'
        entries.append({'cluster_id':identifier,'species_class':observation.get('species','unknown'),
            'health_status':status,'health_score':None,'position_world':observation['position'],
            'bounding_box_extent':[2*truth.get('radius',.2)]*2+[observation.get('height',.3)],
            'optimal_graft_pose_world':None,'sampled_or_restored':status=='TREATED',
            'genet_id':observation.get('genet_id'),'uv_signature':None})
    return {'entries':entries,'detections':[]}

class Bridge:
    def __init__(self, source, output):
        self.source=source.rstrip('/');self.output=output;output.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock();self.state=None;self.overview=None;self.robot=None;self.received=0.;self.error='Waiting for actual Isaac camera';self.sequence=0;self.events={};self.stop=threading.Event()
    def sample(self):
        raw=bounded_get(self.source+'/api/state',2*1024*1024);state=json.loads(raw)
        if state.get('runtime',{}).get('renderer')!='isaac_rtx':raise ValueError('Source is not an actual Isaac RTX runtime')
        overview=bounded_get(self.source+'/api/overview.png');robot=bounded_get(self.source+'/api/frame.png')
        # Endpoints are independent: retain each declared source timestamp, not false synchrony.
        overview_image=Image.open(io.BytesIO(overview)).convert('RGB');robot_image=Image.open(io.BytesIO(robot)).convert('RGB')
        captured=datetime.now(timezone.utc).isoformat();runtime=state.get('runtime',{})
        for event in state.get('events',[]):
            key=json.dumps(event,sort_keys=True)
            if key not in self.events:
                self.events[key]={'timestamp':captured,'state':event.get('type','event'),'action':event.get('message',''),
                    'evidence':{'source':'live_isaac_analytical_mission','event_sim_time':event.get('time'),'observed_at_sim_time':state.get('time'),
                        **{k:v for k,v in event.items() if k not in ('time','type','message')}},'outcome':'Actual source event; wall timestamp is first receipt, not event execution'}
        self.events=dict(list(self.events.items())[-500:]);self.sequence+=1
        manifest={'sequence':self.sequence,'simTime':state.get('time'),'capturedAt':captured,
            'frameSha256':hashlib.sha256(robot).hexdigest(),'overviewSha256':hashlib.sha256(overview).hexdigest(),
            'cameraTime':runtime.get('camera_time'),'overviewTime':runtime.get('overview_time'),
            'sourceMode':'live_isaac_rtx','perception':'visibility_limited_synthetic_observation',
            'modelProvenance':None,'liveModelsVerified':False,'snapshotEndpointsAtomic':False,'metrics':state.get('metrics',{})}
        atomic(self.output/'registry.json',json.dumps(team_registry(state)).encode())
        atomic(self.output/'decisions.jsonl',('\n'.join(json.dumps(e) for e in self.events.values())+'\n').encode())
        atomic(self.output/'frame.png',robot)
        atomic(self.output/'source.json',json.dumps({'frameSynthetic':True,'source':'live_isaac_rtx','perception':'Analytical simulation; no live model inference','capturedAt':captured}).encode())
        atomic(self.output/'stream-source.json',json.dumps(manifest,indent=2).encode())
        with self.lock:self.state=state;self.overview=overview_image;self.robot=robot_image;self.received=time.monotonic();self.error=''
    def run(self):
        while not self.stop.is_set():
            start=time.monotonic()
            try:self.sample()
            except Exception as exc:
                with self.lock:self.error=f'{type(exc).__name__}: {exc}'[:180]
            self.stop.wait(max(.01,.5-(time.monotonic()-start)))
    def image(self):
        with self.lock:state=self.state;overview=self.overview;robot=self.robot;age=time.monotonic()-self.received if self.received else None;error=self.error
        image=Image.new('RGB',(WIDTH,HEIGHT),(5,23,29));draw=ImageDraw.Draw(image)
        try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
        except OSError:
            try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',18)
            except OSError:font=ImageFont.load_default()
        def line(x,y,value,color=(213,235,229)):draw.text((x,y),str(value),font=font,fill=color)
        line(20,15,'REEF RESCUE / LIVE ISAAC RTX CAMERA STREAM');line(20,43,datetime.now(timezone.utc).isoformat(timespec='milliseconds'))
        def paste(source,box):
            if source is None:return
            copy=source.copy();copy.thumbnail((box[2],box[3]));image.paste(copy,(box[0],box[1]))
        paste(overview,(20,88,850,532));paste(robot,(900,88,360,225))
        line(900,325,'ACTUAL ROBOT RENDER');line(900,350,f'Source refresh age: {age:.2f}s' if age is not None else 'Awaiting pixels')
        if state:
            worker=next((r for r in state.get('robots',[]) if r.get('role')=='restoration'),{})
            line(900,380,f'Sim time: {state.get("time",0):.2f}s'+(' PAUSED' if state.get('paused') else ''));line(900,405,worker.get('state','unknown')[:30]);line(900,430,'Held: '+str(worker.get('fragment_id') or 'none'))
            line(900,455,'Verified: '+str(state.get('metrics',{}).get('verified',0)))
            line(20,625,'PERCEPTION: analytical/synthetic observations; no live Gemma/Argon in this source',(238,191,114))
            event=state.get('events',[{}])[-1];line(20,655,str(event.get('message','No source event'))[:115])
        if error:line(20,685,'STALE / '+error,(255,130,130))
        buffer=io.BytesIO();image.save(buffer,'JPEG',quality=85);return buffer.getvalue()

def handler(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/frame.jpg':
                data=bridge.image();self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if self.path=='/api/source':
                try:data=(bridge.output/'stream-source.json').read_bytes();self.send_response(200)
                except OSError:data=b'{"ready":false}';self.send_response(503)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            if self.path!='/stream.mjpg':
                data=b'<!doctype html><title>Live Isaac stream</title><body style="background:#05171d;margin:0"><img src="/stream.mjpg" style="width:100%"><p style="color:white">Live camera frames. Analytical policy; no live model claim. Source refresh age is shown.</p>'
                self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame');self.send_header('Cache-Control','no-store');self.end_headers()
            try:
                while not bridge.stop.is_set():
                    start=time.monotonic();data=bridge.image();self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n');self.wfile.flush();bridge.stop.wait(max(.001,1/STREAM_FPS-(time.monotonic()-start)))
            except (BrokenPipeError,ConnectionResetError):pass
    return Handler

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',default='http://127.0.0.1:8765');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--port',type=int,default=8780);args=parser.parse_args()
    bridge=Bridge(args.source,args.output);threading.Thread(target=bridge.run,daemon=True).start();server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(bridge));server.daemon_threads=True
    print(f'LIVE_ISAAC_VIEW http://127.0.0.1:{args.port}/  TEAM_RUN_DIR={args.output.resolve()}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:bridge.stop.set();server.server_close()
if __name__=='__main__':main()
