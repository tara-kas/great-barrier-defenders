#!/usr/bin/env python3
"""Fast, explicitly labelled offline edit of an existing verified recording.

Keeps source actions and sensor views. Removes brief intermediate camera shots,
cross-dissolves camera panes, slows the carrying/orientation shot and inserts a
short optical-flow transition at the old push-approach handoff. This is an edit,
not a fresh Isaac capture; original trace and verification remain unchanged.
"""
from pathlib import Path
import argparse,json,subprocess,hashlib
import cv2
import numpy as np

PANES=((24,116,1185,770),(1204,155,1577,378),(1204,449,1577,672))
class Reader:
    def __init__(self,path): self.cap=cv2.VideoCapture(str(path)); self.index=-1;self.frame=None
    def get(self,index):
        if index==self.index: return self.frame.copy()
        if index!=self.index+1:self.cap.set(cv2.CAP_PROP_POS_FRAMES,index)
        ok,frame=self.cap.read()
        if not ok:raise RuntimeError(f'Cannot decode source frame {index}')
        self.index=index;self.frame=frame
        return frame.copy()

def panes_blend(a,b,t):
    out=b.copy()
    for x0,y0,x1,y1 in PANES:
        out[y0:y1,x0:x1]=cv2.addWeighted(a[y0:y1,x0:x1],1-t,b[y0:y1,x0:x1],t,0)
    return out

def flow_pair(a,b):
    pairs=[]
    for x0,y0,x1,y1 in PANES:
        aa=a[y0:y1,x0:x1];bb=b[y0:y1,x0:x1];h,w=aa.shape[:2]
        size=(min(480,w),round(h*min(480,w)/w))
        ga=cv2.cvtColor(cv2.resize(aa,size),cv2.COLOR_BGR2GRAY)
        gb=cv2.cvtColor(cv2.resize(bb,size),cv2.COLOR_BGR2GRAY)
        dis=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        fa=dis.calc(ga,gb,None);fb=dis.calc(gb,ga,None)
        def expand(f):
            f=cv2.resize(f,(w,h));f[:,:,0]*=w/size[0];f[:,:,1]*=h/size[1];return f
        xx,yy=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32))
        pairs.append((aa,bb,expand(fa),expand(fb),xx,yy))
    return pairs

def flow_frame(a,b,t,pairs):
    out=b.copy()
    for pane,(aa,bb,fa,fb,xx,yy) in zip(PANES,pairs):
        x0,y0,x1,y1=pane
        wa=cv2.remap(aa,xx-t*fa[:,:,0],yy-t*fa[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        wb=cv2.remap(bb,xx-(1-t)*fb[:,:,0],yy-(1-t)*fb[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        out[y0:y1,x0:x1]=cv2.addWeighted(wa,1-t,wb,t,0)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    cv2.setNumThreads(4);args.output.mkdir(parents=True,exist_ok=True)
    # This edit decision list belongs to one capture, not arbitrary recordings.
    expected='37710b948c0ca191f59398aebe8d65a2cdbe34ef0d7a1f9901c88303c87f3b29'
    if hashlib.sha256(args.source.read_bytes()).hexdigest()!=expected:
        raise ValueError('Source does not match the verified team-video capture; rebuild the edit decision list first')
    reader=Reader(args.source)
    # Retain both UV inspections and every manipulation/failure/recovery action.
    segments=[(32,133,1.,'recipient_uv'),(190,291,1.,'donor_uv'),
        (316,493,1.,'natural_harvest'),(503,812,1.,'drop_and_recovery'),
        (812,916,1.5,'carry_and_orientation'),(916,1336,1.,'contact_release_push'),
        (1336,1385,1.,'verified_hold')]
    a,b=reader.get(1182),reader.get(1192);pair=flow_pair(a,b)
    final_view=reader.get(1335)
    movie=args.output/'pelagic-smooth-transitions.mp4'
    encoder=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','bgr24','-video_size','1600x900','-framerate','24','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)],stdin=subprocess.PIPE)
    count=0;pending=[];cuts=[];transition=16
    def write(frame):
        nonlocal count
        frame[872:900,20:1580]=(20,18,5)
        cv2.putText(frame,'SMOOTHED OFFLINE EDIT  |  ORIGINAL VERIFIED ISAAC CAPTURE  |  DEMO PERCEPTION - NO MODEL CALL',(24,890),cv2.FONT_HERSHEY_SIMPLEX,.43,(153,143,112),1,cv2.LINE_AA)
        encoder.stdin.write(frame.tobytes());count+=1
    for start,end,scale,label in segments:
        frames=[]
        for source in np.linspace(start,end-1,round((end-start)*scale)):
            low=int(source);frac=source-low
            frame=reader.get(low)
            if frac>1e-6:frame=panes_blend(frame,reader.get(min(end-1,low+1)),frac)
            if 1182<=source<=1192:
                t=(source-1182)/10;t=t*t*(3-2*t)
                frame=flow_frame(a,b,t,pair)
            if label=='verified_hold':
                for x0,y0,x1,y1 in PANES:frame[y0:y1,x0:x1]=final_view[y0:y1,x0:x1]
            frames.append(frame)
        if pending:
            n=min(transition,len(pending),len(frames))
            cuts.append({'output_frame':count,'next_shot':label,'dissolve_frames':n})
            for i in range(n):
                t=(i+1)/(n+1);t=t*t*(3-2*t)
                write(panes_blend(pending[-n+i],frames[i],t))
            frames=frames[n:]
        for frame in frames[:-transition]:write(frame)
        pending=frames[-transition:]
        print(json.dumps({'shot':label,'written_frames':count}),flush=True)
    for frame in pending:write(frame)
    encoder.stdin.close()
    if encoder.wait():raise RuntimeError('Encoder failed')
    report={'source':str(args.source.resolve()),'output':str(movie.resolve()),'frames':count,'fps':24,'duration_s':count/24,'camera_dissolves':cuts,'physical_source_unchanged':True,'new_isaac_render':False,'push_transition':'10-frame optical-flow interpolation of source handoff','final_view':'held final verification camera to avoid chase-camera snap','sha256':hashlib.sha256(movie.read_bytes()).hexdigest()}
    (args.output/'edit-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':main()
