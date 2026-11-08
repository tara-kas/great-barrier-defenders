import ast
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
from reefsim.team_feed import TeamFeed, MAX_TEXT, MAX_FRAME, MAX_STATE, canonical_readers
from reefsim.lab_server import make_server, ArchitectureAdapters, GeminiPolicy

class TeamFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.registry=self.root/'registry.json'
        self.registry.write_text(json.dumps({'entries':[{'cluster_id':'C-1','health_status':'DEAD'}], 'detections':[{'cluster_id':'C-1','box':[.1,.2,.3,.4]}]}))
        (self.root/'decisions.jsonl').write_text(json.dumps({'state':'SURVEY_SEABED','action':'Surveyed','outcome':'Mapped'})+'\n')
        (self.root/'frame.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.feed=TeamFeed(self.root)

    def test_real_files_use_canonical_readers_and_refresh(self):
        status,first=self.feed.state()
        self.assertEqual(status,200)
        self.assertEqual(first['registry'][0]['health_status'],'DEAD')
        self.assertEqual(first['detections'][0]['box'],[.1,.2,.3,.4])
        self.assertEqual(first['provenance']['parser'],'canonical_dashboard')
        self.assertIsNone(first['frame_synthetic'])
        replacement=self.root/'registry.tmp'
        replacement.write_text(json.dumps([{'cluster_id':'C-1','health_status':'TREATED'}]))
        os.replace(replacement,self.registry)
        with (self.root/'decisions.jsonl').open('a') as stream:
            stream.write(json.dumps({'state':'VERIFY','outcome':'Passed'})+'\n')
        _,second=self.feed.state()
        self.assertEqual(second['registry'][0]['health_status'],'TREATED')
        self.assertEqual(len(second['decisions']),2)
        self.assertEqual(self.feed.frame()[1],'image/png')

    def test_malformed_or_oversize_keeps_last_good_without_raw_paths(self):
        self.feed.state()
        for raw in ('not json','x'*(MAX_TEXT+1),'[{"confidence":NaN}]'):
            self.registry.write_text(raw)
            status,result=self.feed.state()
            self.assertEqual(status,503)
            self.assertTrue(result['stale'])
            self.assertEqual(result['registry'][0]['health_status'],'DEAD')
            self.assertNotIn(str(self.root),result['error'])

    def test_frame_symlink_and_record_shape_rejected(self):
        target=self.root/'frame.png'
        target.unlink()
        target.symlink_to('/etc/hosts')
        status,state=self.feed.state()
        self.assertEqual(status,200)
        self.assertIsNone(state["frameUrl"])
        self.assertTrue(state["frameWarning"])
        with self.assertRaises(ValueError):self.feed.frame()
        target.unlink();target.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.registry.write_text('["invalid record"]')
        self.assertEqual(self.feed.state()[0],503)

    def test_provenance_explicit_and_stale_sources_labelled(self):
        (self.root/'source.json').write_text('{"frameSynthetic":true}')
        os.utime(self.root/'frame.png',(1,1))
        _,result=self.feed.state()
        self.assertTrue(result['frame_synthetic'])
        self.assertEqual(result['mode'],'synthetic file source')
        self.assertEqual(result['status'],'stale')
        self.assertFalse(result['provenance']['controlAuthority'])
        (self.root/'source.json').write_text('{"frameSynthetic":false}')
        _,result=self.feed.state()
        self.assertEqual(result['provenance']['frameOrigin'],'camera')
        self.assertFalse(result['provenance']['frameOriginVerified'])

    def test_record_limits_and_no_default_demo(self):
        (self.root/'decisions.jsonl').write_text('\n'.join(json.dumps({'sequence':i}) for i in range(205)))
        _,result=self.feed.state()
        self.assertEqual(len(result['decisions']),200)
        self.assertEqual(result['decisions'][0]['sequence'],5)
        self.assertEqual(result['totalRecords']['decisions'],205)
        status,result=TeamFeed('').state()
        self.assertEqual(status,200)
        self.assertFalse(result['configured'])
        self.assertEqual(result['registry'],[])
        self.assertIsNone(result['frameUrl'])

    def test_response_and_frame_byte_bounds(self):
        self.registry.write_text(json.dumps([{'description':'x'*MAX_STATE}]))
        status,result=self.feed.state()
        self.assertEqual(status,503)
        self.assertEqual(result['status'],'error')
        (self.root/'frame.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*MAX_FRAME)
        with self.assertRaises(ValueError):self.feed.frame()

    def test_missing_frame_keeps_registry_and_decisions(self):
        (self.root/'frame.png').unlink()
        status,result=self.feed.state()
        self.assertEqual(status,200)
        self.assertEqual(result['registry'][0]['cluster_id'],'C-1')
        self.assertIsNone(result['frameUrl'])
        self.assertIsNone(result['frame_updated'])
        self.assertTrue(result['frameWarning'])

    def test_canonical_packaged_layout_parser_resolution(self):
        canonical=self.root/'team'
        dashboard=canonical/'dashboard';dashboard.mkdir(parents=True)
        source=Path(canonical_readers()[0].__code__.co_filename)
        (dashboard/'server.py').write_text(source.read_text())
        with patch('reefsim.team_feed.ROOT', canonical/'sim/pelagic'):
            status,result=TeamFeed(self.root).state()
        self.assertEqual(status,200)
        self.assertEqual(result['provenance']['parser'],'canonical_dashboard')

    def test_shallow_container_root_parser_resolution_is_safe(self):
        for root in (Path('/'),Path('/root')):
            with self.subTest(root=root),patch('reefsim.team_feed.ROOT',root),patch.object(Path,'is_file',return_value=False):
                self.assertIsNone(canonical_readers())

    def test_modal_module_path_resolver_under_actual_remote_file_layout(self):
        source=Path(__file__).resolve().parents[1]/'scripts/modal_lab_backend.py'
        parsed=ast.parse(source.read_text())
        names={'ROOT','TEAM_DASHBOARD_CANDIDATES','TEAM_DASHBOARD_SOURCE'}
        statements=[node for node in parsed.body if isinstance(node,ast.Assign)
                    and any(isinstance(target,ast.Name) and target.id in names for target in node.targets)]
        self.assertEqual(len(statements),3)
        program=compile(ast.Module(body=statements,type_ignores=[]),str(source),'exec')
        for filename,expected in (('/root/modal_lab_backend.py',Path('/')),
                                  ('/workspace/team/sim/pelagic/scripts/modal_lab_backend.py',Path('/workspace/team/sim/pelagic'))):
            namespace={'Path':Path,'__file__':filename}
            with self.subTest(filename=filename),patch.object(Path,'is_file',return_value=False):
                exec(program,namespace)
            self.assertEqual(namespace['ROOT'],expected)
            self.assertEqual(namespace['TEAM_DASHBOARD_SOURCE'],Path('/root/dashboard/server.py'))

    def test_missing_optional_canonical_parser_is_explicit(self):
        with patch('reefsim.team_feed.canonical_readers', return_value=None):
            status,result=TeamFeed(self.root).state()
        self.assertEqual(status,503)
        self.assertEqual(result['status'],'unconfigured')
        self.assertEqual(result['registry'],[])

    def test_http_fixed_paths_and_frame(self):
        server=make_server(port=0,team_feed=self.feed,policy=GeminiPolicy(api_key=''),architecture=ArchitectureAdapters(env={}))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urlopen(base+'/api/lab/team-state') as response:state=json.load(response)
            with urlopen(base+state['frameUrl']) as response:self.assertEqual(response.headers['Content-Type'],'image/png')
            for endpoint in ('team-state?path=/etc/hosts','team-frame?path=/etc/hosts'):
                with self.assertRaises(HTTPError) as error:urlopen(base+'/api/lab/'+endpoint)
                self.assertEqual(error.exception.code,400)
        finally:
            server.shutdown();server.server_close();thread.join()
