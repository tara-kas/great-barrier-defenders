/** Cross-language contract test: real Python adapters, explicitly mocked provider
 * transports and a 2×2 fixture JPEG. This does not run Gemma or native cuOpt. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {ReefLab} from '../web/lab/simulation.mjs';
const cwd=fileURLToPath(new URL('..',import.meta.url));
const bridge=String.raw`
import ast, io, json, math, pathlib, sys
from reefsim.lab_server import ArchitectureAdapters, GeminiPolicy
request=json.load(sys.stdin)
kind=request.pop('_kind')
def gemma_fixture(payload):
    props=payload['response_format']['json_schema']['schema']['properties']
    if 'fragmentVisible' in props:
        result={'summary':'Offline fragment fixture','uncertainty':'Mock transport; no visual model ran','observations':[],'fragmentVisible':True,'gripperState':'empty'}
    else:
        target=props['observations']['items']['properties']['id']['enum'][0]
        result={'summary':'Offline coral fixture','uncertainty':'Mock transport; no visual model ran','observations':[{'id':target,'health':'healthy' if target.startswith('donor-') else 'bleached_alive','confidence':.9}]}
    return {'choices':[{'message':{'content':json.dumps(result)}}]}
def cuopt_fixture(data):
    costs={r['id']:sum(math.dist(a,b) for a,b in zip(r['points'],r['points'][1:])) for r in data['alternatives']}
    selected=min(costs,key=costs.get)
    return {'id':data['id'],'requestId':data['id'],'source':'cuopt','configured':True,'status':'solved','solverStatus':'SUCCESS','model':'mock-cuopt-not-native','solverVersion':'offline-fixture','solveTimeMs':1,'routeMode':selected,'objectiveCost':costs[selected],'costs':costs}
def argon_fixture(http_request,**kwargs):
    payload=json.loads(http_request.data)
    observation=json.loads(payload['input'][0]['text'])['observation']
    result={'decision':request['allowedActions'][0],'reason':'Offline adapter contract fixture; no live reasoning model ran.','routeMode':observation['optimizer']['routeMode']}
    return io.BytesIO(json.dumps({'status':'completed','id':'offline-interaction','steps':[{'type':'model_output','content':[{'type':'text','text':json.dumps(result)}]}]}).encode())
adapters=ArchitectureAdapters(env={'GEMMA_MODEL':'mock-gemma-not-live'},gemma_infer=gemma_fixture,cuopt_solve=cuopt_fixture,argon=GeminiPolicy(api_key='offline-fixture-key',model='gemini-offline-fixture',transport=argon_fixture))
if kind=='perception':
    module=ast.parse(pathlib.Path('tests/test_lab_server.py').read_text())
    jpeg=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='JPEG_B64' for t in n.targets))
    request['image']={'mimeType':'image/jpeg','data':jpeg,'camera':'tool','time':request.pop('_frameTime')}
    response=adapters.perceive(request)
else:
    response=adapters.plan(request)
json.dump(response,sys.stdout)
`;
const callAdapter=body=>{const result=spawnSync('python3',['-c',bridge],{cwd,input:JSON.stringify(body),encoding:'utf8',maxBuffer:1024*1024});assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);};
test('real backend adapters and engine complete the full loop with mocked model/solver transports',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'inject_fault',kind:'drop'});sim.command({action:'run'});let captures=0,plans=0,lastPerception=null,largest=0;
 while(sim.running&&sim.time<600){sim.step(.2);const request=sim.perceptionRequest;
  if(request?.ready&&!sim.externalRequestIds.has(`perception:${request.id}`)){
   const body={_kind:'perception',id:request.id,observation:{time:sim.time,phase:sim.phase,donorId:sim.donorId,targetId:sim.targetId,perceptionRequest:request,cameraTargetId:request.targetId,captureRequestId:request.id},_frameTime:sim.time};
   lastPerception=callAdapter(body);sim.command({action:'ingest_perception',packet:lastPerception});captures++;
  }
  if(sim.pendingDecision){const pending=sim.pendingDecision;const body={_kind:'plan',id:pending.id,observation:pending.observation,allowedActions:pending.allowedActions,perception:lastPerception,requireFullStack:true};largest=Math.max(largest,Buffer.byteLength(JSON.stringify(body)));const packet=callAdapter(body);sim.command({action:'ingest_plan',packet});sim.command({action:'apply_decision',id:pending.id,decision:packet.decision,reason:packet.reason,routeMode:packet.routeMode,source:'base_station',evidence:{perception:lastPerception,planning:packet}});plans++;}
 }
 const state=sim.snapshot();assert.equal(state.completed,true);assert.equal(state.metrics.placed,4);assert.equal(state.metrics.drops,1);assert.equal(state.metrics.recoveries,1);assert.equal(captures,9);assert.equal(plans,5);assert.equal(state.decision.planning.optimizer.model,'mock-cuopt-not-native');assert.equal(state.decision.perception.model,'mock-gemma-not-live');assert.equal(state.decision.source,'base_station');assert.ok(largest<64*1024);
});
