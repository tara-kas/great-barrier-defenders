"""Volatile authenticated Isaac snapshot relay; read-only, no robot commands."""
import base64
import copy
import hashlib
import json
import math
import threading
import time
from reefsim.team_feed import FeedError

class LiveFeed:
    def __init__(self, clock=time.time):
        self.clock=clock; self.lock=threading.Lock(); self.latest=None; self.image=None; self.received=None
    def ingest(self, data):
        if not isinstance(data,dict) or set(data)!={'state','frame','capturedAt'}:
            raise ValueError('Expected state, frame and capturedAt')
        state=data['state']; stamp=data['capturedAt']; frame=data['frame']
        if not isinstance(state,dict) or state.get('mode')!='isaac' or state.get('runtime',{}).get('renderer')!='isaac_rtx':
            raise ValueError('Expected actual Isaac runtime snapshot')
        if not isinstance(stamp,(int,float)) or isinstance(stamp,bool) or not math.isfinite(stamp) or abs(self.clock()-stamp)>30:
            raise ValueError('Snapshot capture is stale or invalid')
        if not isinstance(frame,str) or len(frame)>2800000: raise ValueError('Frame exceeds bound')
        image=base64.b64decode(frame,validate=True)
        if len(image)>2*1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Expected bounded PNG')
        if len(json.dumps(state,allow_nan=False).encode())>512*1024: raise ValueError('State exceeds bound')
        def vec(v):
            return isinstance(v,list) and len(v)==3 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in v)
        rows=state.get('observations',[])
        if not isinstance(rows,list) or len(rows)>1000: raise ValueError('Invalid observations')
        registry=[]
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not vec(row.get('position')): raise ValueError('Invalid observation')
            health={'healthy':'LIVE','bleached_alive':'BLEACHED','dead':'DEAD'}.get(row.get('health'))
            if health is None: continue
            registry.append({'cluster_id':row['id'][:128],'species_class':str(row.get('species','unknown'))[:128], 'health_status':'TREATED' if row.get('task_status')=='verified' else health,'health_score':None,'position_world':row['position'],'sampled_or_restored':row.get('task_status')=='verified'})
        events=state.get('events',[])
        if not isinstance(events,list): raise ValueError('Invalid events')
        decisions=[]
        for event in events[-200:]:
            if not isinstance(event,dict): raise ValueError('Invalid event')
            decisions.append({'state':str(event.get('type','event'))[:100],'action':str(event.get('message',''))[:1500],'evidence':event,'outcome':'Isaac analytical controller event; not a model decision','source':'isaac_analytical_controller','simulationTime':event.get('time')})
        camera_time=state.get('runtime',{}).get('camera_time')
        sim_time=state.get('time')
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in [camera_time,sim_time]): raise ValueError('Missing frame time')
        lag=max(0,sim_time-camera_time)
        payload={'ok':True,'configured':True,'status':'ready','mode':'Live Isaac RTX / analytical controller; synthetic scene observations', 'registry':registry,'detections':[],'decisions':decisions,'registry_updated':stamp,'decisions_updated':stamp,'frame_updated':stamp,'frame_synthetic':True,'frameUrl':f'/api/lab/team-frame?v={int(stamp*1000)}','stale':lag>5,'sourceAgeSeconds':0,'simulationTime':sim_time,'cameraSimulationTime':camera_time,'frameLagSeconds':lag,'frameSha256':hashlib.sha256(image).hexdigest(),'metrics':state.get('metrics',{}),'provenance':{'source':'live_isaac_rtx','registry':'Analytical simulated observations, not Gemma detections','controlAuthority':False,'biologicalRecoveryVerified':False}}
        with self.lock:
            if self.latest and stamp<=self.latest['registry_updated']: raise ValueError('Out-of-order snapshot')
            self.latest=payload;self.image=image;self.received=self.clock()
        return {'ok':True,'receivedAt':self.received,'simulationTime':sim_time,'frameSha256':payload['frameSha256']}
    def state(self):
        with self.lock:
            if self.latest is None:return None
            payload=copy.deepcopy(self.latest);age=max(0,self.clock()-payload['registry_updated']);payload['sourceAgeSeconds']=round(age,3);payload['stale']=payload['stale'] or age>5;payload['status']='stale' if payload['stale'] else 'ready'
            return 200,payload
    def frame(self):
        with self.lock:
            if self.image is None:raise FeedError('No live frame received')
            return self.image,'image/png'
