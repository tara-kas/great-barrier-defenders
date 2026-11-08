#!/usr/bin/env python3
"""Relay an SSH-tunnelled Isaac stream into the existing authenticated demo gateway."""
import argparse, base64, getpass, json, os, sys, time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='http://127.0.0.1:8765');parser.add_argument('--gateway',required=True);parser.add_argument('--duration',type=float,default=3600);args=parser.parse_args()
    source=urlsplit(args.source);gateway=urlsplit(args.gateway)
    if source.scheme!='http' or source.hostname not in ('127.0.0.1','localhost'):parser.error('Source must be a loopback SSH tunnel')
    if gateway.scheme!='https' or gateway.username or gateway.password or gateway.query or gateway.fragment:parser.error('Gateway must be HTTPS')
    token=os.environ.get('LAB_GATEWAY_TOKEN') or getpass.getpass('Gateway token: ')
    def read(path):
        with urlopen(args.source.rstrip('/')+path,timeout=10) as response:
            data=response.read(2200001)
            if len(data)>2200000:raise ValueError('Source exceeds bound')
            return data
    until=time.monotonic()+args.duration;last=None;count=0
    while time.monotonic()<until:
        try:
            state=json.loads(read('/api/state')); frame=read('/api/frame.png'); fresh=json.loads(read('/api/state'))
            if state['runtime']['camera_time']!=fresh['runtime']['camera_time']:continue
            identity=(state['time'],state['runtime']['camera_time'])
            if identity!=last:
                body=json.dumps({'state':state,'frame':base64.b64encode(frame).decode(),'capturedAt':time.time()},allow_nan=False).encode()
                request=Request(args.gateway.rstrip('/')+'/api/lab/team-snapshot',body,{'Content-Type':'application/json','Authorization':'Bearer '+token})
                with urlopen(request,timeout=15) as response:result=json.load(response)
                count+=1;last=identity
                if count==1 or count%20==0:print(json.dumps({'snapshots':count,'simulationTime':result.get('simulationTime'),'frameSha256':result.get('frameSha256')}),flush=True)
        except Exception as error:print(json.dumps({'status':'retry','errorType':type(error).__name__}),flush=True)
        time.sleep(1)
if __name__=='__main__':main()
