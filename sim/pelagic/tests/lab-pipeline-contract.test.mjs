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
    assert payload['structured_outputs']['whitespace_pattern']==''
    target=request['observation']['perceptionRequest']
    fragment=target['targetKind']=='fragment'
    result={'targetVisible':True,'objectKind':'coral_fragment' if fragment else 'coral_colony',
        'appearance':'pale_or_bleached' if request['observation']['phase']=='inspect_recipient' else 'pigmented',
        'confidence':.9,'visualEvidence':'Explicit offline visual fixture; no Gemma inference ran.',
        'uncertainty':'Biological viability is not inferred from this fixture.',
        'fragmentVisible':fragment,'gripperState':'holding' if request['observation']['robot']['holding'] else 'empty'}
    return {'choices':[{'message':{'content':json.dumps(result)},'finish_reason':'stop'}]}
def cuopt_fixture(data):
    costs={r['id']:sum(math.dist(a,b) for a,b in zip(r['points'],r['points'][1:])) for r in data['alternatives']}
    selected=min(costs,key=costs.get)
    return {'id':data['id'],'requestId':data['id'],'source':'cuopt','configured':True,'status':'solved','solverStatus':'SUCCESS','model':'mock-cuopt-not-native','solverVersion':'offline-fixture','solveTimeMs':1,'routeMode':selected,'objectiveCost':costs[selected],'costs':costs}
def argon_fixture(*args,**kwargs):
    raise AssertionError('Mission-time planning must never call Argon')
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
 const sim=new ReefLab({controller:'base_station',restorationMode:'loose_fragment'});sim.command({action:'inject_fault',kind:'drop'});sim.command({action:'run'});let captures=0,plans=0,lastPerception=null,largest=0;
 while(sim.running&&sim.time<600){sim.step(.2);const request=sim.perceptionRequest;
  if(request?.ready&&!sim.externalRequestIds.has(`perception:${request.id}`)){
   assert.notEqual(sim.phase,'inspect_donor','Loose stock must be inspected directly, not through a source-colony proxy');
   const body={_kind:'perception',id:request.id,observation:{time:sim.time,phase:sim.phase,donorId:sim.donorId,targetId:sim.targetId,perceptionRequest:request,cameraTargetId:request.targetId,captureRequestId:request.id,robot:{holding:sim.robot.holding}},_frameTime:sim.time};
   lastPerception=callAdapter(body);sim.command({action:'ingest_perception',packet:lastPerception});captures++;
  }
  if(sim.pendingDecision){const pending=sim.pendingDecision;const body={_kind:'plan',id:pending.id,observation:pending.observation,allowedActions:pending.allowedActions,perception:lastPerception,requireFullStack:true};largest=Math.max(largest,Buffer.byteLength(JSON.stringify(body)));const packet=callAdapter(body);assert.equal(packet.cloudReasoningUsed,false);sim.command({action:'ingest_plan',packet});sim.command({action:'apply_decision',id:pending.id,decision:packet.decision,reason:packet.reason,routeMode:packet.routeMode,source:'base_station',evidence:{perception:lastPerception,planning:packet}});plans++;}
 }
 const state=sim.snapshot();assert.equal(state.completed,true);assert.equal(state.metrics.placed,4);assert.equal(state.metrics.drops,1);assert.equal(state.metrics.recoveries,1);assert.ok(captures>=9);assert.ok(plans>=5);assert.equal(state.restorationMode,'loose_fragment');assert.equal(state.decision.planning.source,'local_planner');assert.equal(state.decision.planning.optimizer.model,'mock-cuopt-not-native');assert.equal(state.decision.perception.model,'mock-gemma-not-live');assert.equal(state.decision.source,'base_station');assert.ok(largest<64*1024);
});
