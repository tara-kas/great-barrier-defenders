import base64, unittest
from reefsim.live_feed import LiveFeed
from reefsim.team_feed import FeedError
class RelayTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.feed=LiveFeed(lambda:self.now)
  self.data={'capturedAt':100.,'frame':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode(),'state':{'mode':'isaac','runtime':{'renderer':'isaac_rtx','camera_time':4.},'time':5.,'observations':[{'id':'c1','position':[1,2,3],'health':'bleached_alive','task_status':'verified'}],'events':[{'time':5,'type':'placement','message':'verified'}]}}
 def test_actual_source_provenance_and_frame(self):
  receipt=self.feed.ingest(self.data);status,p=self.feed.state();self.assertEqual(status,200);self.assertEqual(p['registry'][0]['health_status'],'TREATED');self.assertEqual(p['detections'],[]);self.assertFalse(p['provenance']['controlAuthority']);self.assertEqual(receipt['frameSha256'],p['frameSha256']);self.assertEqual(self.feed.frame()[1],'image/png')
 def test_age_does_not_refresh_without_source(self):
  self.feed.ingest(self.data);self.now+=6;self.assertTrue(self.feed.state()[1]['stale']);self.assertEqual(self.feed.state()[1]['sourceAgeSeconds'],6)
 def test_reject_stale_out_of_order_and_non_isaac(self):
  self.feed.ingest(self.data)
  with self.assertRaises(ValueError):self.feed.ingest(self.data)
  self.data['capturedAt']=0
  with self.assertRaises(ValueError):self.feed.ingest(self.data)
  self.data['capturedAt']=101;self.data['state']['mode']='browser'
  with self.assertRaises(ValueError):self.feed.ingest(self.data)
 def test_bad_frame_no_replacement(self):
  self.data['frame']='bad'
  with self.assertRaises(ValueError):self.feed.ingest(self.data)
  self.assertIsNone(self.feed.state())
  with self.assertRaises(FeedError):self.feed.frame()
 def test_nonfinite_positions_rejected(self):
  self.data['state']['observations'][0]['position'][0]=float('nan')
  with self.assertRaises(ValueError):self.feed.ingest(self.data)
 def test_frame_lag_labelled(self):
  self.data['state']['time']=15;self.feed.ingest(self.data);self.assertTrue(self.feed.state()[1]['stale']);self.assertEqual(self.feed.state()[1]['frameLagSeconds'],11)
if __name__=='__main__':unittest.main()
