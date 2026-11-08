import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
bridge=load('bridge_isaac_stream');capture=load('capture_live_stream');finalizer=load('finalize_live_capture')
class LiveCaptureTests(unittest.TestCase):
 def test_observed_only_registry_has_no_model_scores_or_biological_recovery(self):
  state={'corals':[{'id':'seen','radius':.3,'task_status':'verified'},{'id':'unseen','radius':1}], 'observations':[{'id':'seen','health':'bleached_alive','position':[0,1,2],'height':.4,'species':'test','confidence':.99,'genet_id':'G1'}]}
  r=bridge.team_registry(state);self.assertEqual(len(r['entries']),1);self.assertEqual(r['entries'][0]['health_status'],'TREATED');self.assertIsNone(r['entries'][0]['health_score']);self.assertEqual(r['detections'],[])
 def test_capture_requires_exact_sixty_seconds(self):
  valid={'streams':[{'nb_read_frames':'600','r_frame_rate':'10/1','width':1280,'height':720,'codec_name':'h264'}],'format':{'duration':'60.000000'}}
  self.assertEqual(capture.validate_probe(valid)['durationSeconds'],60)
  for duration in ('59.9','60.1','120'):
   valid['format']['duration']=duration
   with self.assertRaises(ValueError):capture.validate_probe(valid)
 def test_nonverified_recipient_does_not_count_as_treated(self):
  state={'corals':[{'id':'seen','task_status':'attached'}], 'observations':[{'id':'seen','health':'bleached_alive','position':[0,0,0]}]}
  self.assertEqual(bridge.team_registry(state)['entries'][0]['health_status'],'BLEACHED')
 def test_finalizer_never_pads_short_or_discontinuous_takes(self):
  metadata={'schema':'reef-rescue-live-capture/v1','edited':False,'retimed':False,'assessment':{'continuous':True}}
  info={'format':{'duration':'60.25'},'streams':[{}]}
  self.assertEqual(finalizer.validate_source(metadata,info),60.25)
  info['format']['duration']='60.000000';self.assertEqual(finalizer.validate_source(metadata,info),60)
  for duration in ('59.99','61.1'):
   info['format']['duration']=duration
   with self.assertRaises(ValueError):finalizer.validate_source(metadata,info)
  info['format']['duration']='60.25';metadata['edited']=True
  with self.assertRaises(ValueError):finalizer.validate_source(metadata,info)
  metadata['edited']=False;metadata['assessment']['continuous']=False
  with self.assertRaises(ValueError):finalizer.validate_source(metadata,info)
 def test_missing_container_duration_uses_real_frame_timestamps_not_nominal_rate(self):
  frames=[{'pts_time':'0'},{'pts_time':'0.037'},{'pts_time':'60.167','duration_time':'0.001'}]
  timing=finalizer.frame_duration(frames);self.assertAlmostEqual(timing['durationSeconds'],60.168)
  info={'format':{'duration':str(timing['durationSeconds'])},'streams':[{}]}
  metadata={'schema':'reef-rescue-live-capture/v1','edited':False,'retimed':False,'assessment':{'continuous':True}}
  self.assertAlmostEqual(finalizer.validate_source(metadata,info),60.168)
  self.assertEqual(finalizer.frame_duration([{'pts_time':'10'},{'pts_time':'69.99'}])['durationSeconds'],59.989999999999995)
  for invalid in ([{'pts_time':'1'},{'pts_time':'0'}],[{'pts_time':'nan'},{'pts_time':'2'}],[{},{}]):
   with self.assertRaises(ValueError):finalizer.frame_duration(invalid)
if __name__=='__main__':unittest.main()
