#!/usr/bin/env python3
"""Validate a raw browser take and trim only its excess tail to exactly 60 seconds.

No concatenation, speed change, frame synthesis, inserted images or audio edits.
Constant-frame-rate output may repeat actual captured frames if the source stalls;
source continuity is assessed separately from the recorder's evidence metadata.
"""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess
from pathlib import Path

def frame_duration(frames):
 times=[];ends=[]
 for frame in frames:
  raw=frame.get('best_effort_timestamp_time',frame.get('pts_time'))
  if raw is None:raise ValueError('Decoded frame has no presentation timestamp')
  pts=float(raw);duration=float(frame.get('duration_time',frame.get('pkt_duration_time',0)))
  if not math.isfinite(pts) or not math.isfinite(duration) or duration<0:raise ValueError('Invalid decoded frame timestamp')
  if times and pts<times[-1]:raise ValueError('Decoded presentation timestamps moved backwards')
  times.append(pts);ends.append(pts+duration)
 if len(times)<2:raise ValueError('At least two timestamped frames are required')
 # Missing final-frame duration is zero: conservative observed coverage, never
 # extrapolated from nominal FPS or padded to manufacture a full minute.
 return {'durationSeconds':max(ends)-times[0],'firstTimestamp':times[0],'lastTimestamp':times[-1],'observedEndTimestamp':max(ends),'timestampedFrames':len(times)}

def probe(path):
 result=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=width,height,nb_read_frames,r_frame_rate,codec_name,duration','-show_entries','format=duration','-of','json',str(path)]))
 if not result.get('format',{}).get('duration') and not result['streams'][0].get('duration'):
  decoded=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=pts_time,best_effort_timestamp_time,pkt_duration_time,duration_time','-of','json',str(path)]))
  timing=frame_duration(decoded['frames']);result.setdefault('format',{})['duration']=str(timing['durationSeconds']);result['durationEvidence']={'method':'decoded_frame_timestamps','lastFrameDurationExtrapolated':False,**timing}
 else:result['durationEvidence']={'method':'container_or_stream_duration'}
 return result

def validate_source(metadata,info):
 if metadata.get('schema')!='reef-rescue-live-capture/v1' or metadata.get('edited') is not False or metadata.get('retimed') is not False:raise ValueError('Expected original unedited live browser capture evidence')
 if not metadata.get('assessment',{}).get('continuous'):raise ValueError('Source capture continuity did not pass; do not hide the failure with encoding')
 duration=float(info['format'].get('duration',info['streams'][0].get('duration',0)))
 if not 60<=duration<=61:raise ValueError(f'Raw source must contain at least 60 and at most 61 seconds, got {duration}; no padding or retiming is permitted')
 return duration

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('Choose a new output file; existing captures are not overwritten')
 metadata=json.loads(a.evidence.read_text());original=probe(a.source);duration=validate_source(metadata,original);a.output.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','warning','-i',str(a.source),'-t','60','-an','-vf','fps=30','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)],check=True)
 final=probe(a.output);stream=final['streams'][0]
 if abs(float(final['format']['duration'])-60)>.001 or int(stream['nb_read_frames'])!=1800 or stream['r_frame_rate']!='30/1':raise RuntimeError('Final file is not exactly 60 seconds / 1800 frames at 30 fps')
 retained=[sample for sample in metadata.get('samples',[]) if isinstance(sample.get('wallSeconds'),(int,float)) and sample['wallSeconds']<=60]
 record={'lastEvidenceAtOrBefore60Seconds':retained[-1] if retained else None,'rawTailOutcomeMayBeExcluded':True,'schema':'reef-rescue-final-live-video/v1','inputSha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'evidenceSha256':hashlib.sha256(a.evidence.read_bytes()).hexdigest(),'outputSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'rawDurationSeconds':duration,'rawDurationEvidence':original.get('durationEvidence'),'durationSeconds':60,'frames':1800,'fps':30,'operation':'Only excess final source time removed; no internal cuts or speed changes','tailRemovedSeconds':duration-60,'sourceAssessment':metadata['assessment'],'probe':final,'taskOutcomeVerified':False,'note':'Review decoded video, model receipts, fault timing and same-fragment conservation separately before claiming task success.'}
 a.output.with_suffix('.validation.json').write_text(json.dumps(record,indent=2));print(json.dumps({'video':str(a.output),'duration':60,'frames':1800,'taskOutcomeVerified':False}))
if __name__=='__main__':main()
