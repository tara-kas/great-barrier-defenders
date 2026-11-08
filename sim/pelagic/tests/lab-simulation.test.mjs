import test from 'node:test';
import assert from 'node:assert/strict';
import {terrainHeight,coralContactPoint} from '../web/lab/terrain.mjs';
import {ReefLab,defaultScene} from '../web/lab/simulation.mjs';
const finish=sim=>{sim.command({action:'run'});for(let i=0;i<1200&&sim.running;i++)sim.step(1);return sim.snapshot();};
const until=(sim,predicate,max=400)=>{for(let i=0;i<max&&!predicate(sim.snapshot())&&sim.running;i++)sim.step(.5);return sim.snapshot();};

test('baseline completes four verified compatible placements and conserves eight fragments',()=>{
 const s=finish(new ReefLab());assert.equal(s.completed,true);assert.equal(s.metrics.placed,4);assert.equal(s.fragments.length,8);
 assert.equal(s.fragments.filter(f=>f.state==='placed').length,4);assert.equal(s.fragments.filter(f=>f.state==='attached').length,4);
 for(const f of s.fragments.filter(f=>f.state==='placed')){const d=s.colonies.find(c=>c.id===f.donorId),t=s.colonies.find(c=>c.id===f.targetId);assert.equal(d.genet,t.genet);assert.equal(t.health,'bleached_alive');assert.equal(d.health,'healthy');}
 assert.ok(s.metrics.distance>40);assert.ok(s.metrics.energy>0);assert.equal(s.metrics.collisions,0);
});
test('seed replay is deterministic including metrics and events',()=>{assert.deepEqual(finish(new ReefLab({seed:71})),finish(new ReefLab({seed:71})));});
test('fixed substeps are insensitive to caller frame rate',()=>{
 const a=new ReefLab(),b=new ReefLab();a.command({action:'run'});b.command({action:'run'});
 for(let i=0;i<1200;i++)a.step(1/60);for(let i=0;i<200;i++)b.step(.1);assert.deepEqual(a.snapshot(),b.snapshot());
});
for(const [fault,metric] of [['drop','drops'],['bad_cut','rejectedCuts'],['bad_placement','placementRetries']])test(`${fault} is detected and recovered without false success`,()=>{
 const sim=new ReefLab();sim.command({action:'inject_fault',kind:fault});const s=finish(sim);assert.equal(s.completed,true);assert.equal(s.metrics[metric],1);assert.equal(s.fragments.length,8);assert.equal(s.metrics.placed,4);assert.deepEqual(s.queuedFaults,[]);
 if(fault==='bad_cut'){assert.equal(s.metrics.damage,1);assert.equal(s.fragments.filter(f=>f.state==='rejected').length,1);}
 else assert.equal(s.metrics.recoveries,1);
});
test('drop exhibits settling dynamics and retains a single fragment identity',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='transport');const id=sim.snapshot().robot.holding;sim.command({action:'inject_fault',kind:'drop'});const before=sim.snapshot().fragments.find(f=>f.id===id);sim.step(.4);const after=sim.snapshot().fragments.find(f=>f.id===id);assert.equal(before.state,'dropped');assert.ok(after.position[2]<before.position[2]);assert.equal(sim.snapshot().metrics.placed,0);const result=finish(sim);assert.equal(result.fragments.find(f=>f.id===id).state,'placed');
});
test('a drop armed before cutting never detaches an uncut donor',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='cut');sim.command({action:'inject_fault',kind:'drop'});assert.equal(sim.snapshot().metrics.drops,0);assert.equal(sim.snapshot().fragments.find(f=>f.id===sim.fragmentId).state,'grasped');assert.equal(finish(sim).metrics.drops,1);
});
test('bad placement must be mechanically reverified before success',()=>{
 const sim=new ReefLab();sim.command({action:'inject_fault',kind:'bad_placement'});sim.command({action:'run'});const s=until(sim,s=>s.metrics.placementRetries===1);assert.equal(s.metrics.placed,0);assert.equal(s.completed,false);assert.equal(s.fragments.find(f=>f.id===sim.fragmentId).state,'unsecured');assert.equal(finish(sim).metrics.placed,4);
});
for(const fault of ['current_surge','sensor_dropout'])test(`${fault} holds and resumes automatically`,()=>{
 const sim=new ReefLab();sim.command({action:'inject_fault',kind:fault});sim.command({action:'run'});sim.step(2);assert.ok(sim.snapshot().environmentHold>0);assert.equal(sim.snapshot().metrics.placed,0);assert.equal(finish(sim).completed,true);
});
test('persistent unsafe conditions abort rather than reporting success',()=>{const sim=new ReefLab({water:{visibility:.5}});const s=finish(sim);assert.equal(s.phase,'aborted');assert.equal(s.completed,false);assert.equal(s.metrics.placed,0);assert.ok(s.time>=30);});
test('exhausted donor stock fails with no invented replacement fragments',()=>{
 const sim=new ReefLab();sim.command({action:'inject_fault',kind:'bad_cut'});sim.command({action:'inject_fault',kind:'bad_cut'});const s=finish(sim);assert.equal(s.phase,'aborted');assert.equal(s.metrics.rejectedCuts,2);assert.equal(s.fragments.length,8);assert.equal(s.metrics.placed,0);
});
test('unknown/mismatched lineage and dead colonies never form a pair',()=>{
 for(const health of ['dead','bleached_alive']){const scene=defaultScene();scene.colonies=scene.colonies.map(c=>c.id.startsWith('recipient')?{...c,health,genet:'UNKNOWN'}:c);const s=finish(new ReefLab(scene));assert.equal(s.completed,false);assert.equal(s.metrics.attempts,0);assert.equal(s.fragments.filter(f=>f.state==='attached').length,8);}
});
test('Gemini mode waits for a real explicit decision and rejects stale actions',()=>{
 const sim=new ReefLab({controller:'gemini'});sim.command({action:'run'});let s=until(sim,s=>!!s.pendingDecision);assert.ok(s.pendingDecision);assert.equal(s.metrics.placed,0);const id=s.pendingDecision.id;sim.step(10);assert.equal(sim.snapshot().pendingDecision.id,id);assert.equal(sim.snapshot().metrics.decisionCount,0);
 assert.throws(()=>sim.command({action:'apply_decision',id,decision:'retry',reason:'x',source:'gemini'}));
 assert.throws(()=>sim.command({action:'apply_decision',id,decision:'proceed',reason:'x',source:'scripted'}));
 sim.command({action:'apply_decision',id,decision:'proceed',reason:'Conditions acceptable',source:'gemini'});assert.equal(sim.snapshot().decision.source,'gemini');
 assert.throws(()=>sim.command({action:'apply_decision',id,decision:'proceed',reason:'stale',source:'gemini'}));
 s=until(sim,s=>s.metrics.placed===1);assert.equal(s.metrics.placed,1);
});
test('controller abort never marks a mission complete',()=>{const sim=new ReefLab({controller:'gemini'});sim.command({action:'run'});const s=until(sim,s=>!!s.pendingDecision);sim.command({action:'apply_decision',id:s.pendingDecision.id,decision:'abort',reason:'Uncertain observation',source:'gemini'});assert.equal(sim.snapshot().phase,'aborted');assert.equal(sim.snapshot().completed,false);});
test('paused edits validate atomically and restart repeatable mission state',()=>{
 const sim=new ReefLab();sim.command({action:'run'});assert.throws(()=>sim.command({action:'remove_colony',id:'donor-1'}));sim.command({action:'pause'});sim.command({action:'edit_colony',id:'donor-1',patch:{position:[-2,-2,0]}});assert.deepEqual(sim.snapshot().colonies.find(c=>c.id==='donor-1').position,[-2,-2,terrainHeight(-2,-2)]);assert.equal(sim.snapshot().time,0);
 const scene=sim.exportScene();assert.throws(()=>sim.command({action:'edit_colony',id:'donor-1',patch:{position:[Infinity,0,0]}}));assert.deepEqual(sim.exportScene(),scene);
 assert.throws(()=>sim.command({action:'add_colony',colony:scene.colonies[0]}));assert.deepEqual(sim.exportScene(),scene);
});
test('export/import persists scene geometry and conditions, not mission outcomes',()=>{
 const a=new ReefLab();a.command({action:'set_water',current:.2,visibility:5});a.command({action:'add_obstacle',obstacle:{id:'extra',position:[4,4,0],radius:.7}});const b=new ReefLab();b.loadScene(JSON.stringify(a.exportScene()));assert.deepEqual(a.exportScene(),b.exportScene());assert.equal(b.snapshot().metrics.placed,0);
});
test('snapshots and scene exports cannot mutate the simulation',()=>{const a=new ReefLab();const s=a.snapshot();s.robot.position[0]=100;s.colonies[0].health='dead';a.exportScene().water.current=.8;assert.equal(a.snapshot().robot.position[0],-4);assert.equal(a.snapshot().colonies[0].health,'healthy');assert.equal(a.exportScene().water.current,.08);});
test('malformed commands, scene data and nonfinite time are rejected',()=>{
 const a=new ReefLab();for(const command of [null,[],{action:'unknown'},{action:'set_water',current:NaN},{action:'set_controller',mode:'fake'},{action:'inject_fault',kind:'fake'}])assert.throws(()=>a.command(command));
 for(const dt of [-1,Infinity,NaN,61])assert.throws(()=>a.step(dt));assert.throws(()=>a.loadScene('{"colonies":"invalid"}'));assert.throws(()=>a.loadScene({...defaultScene(),seed:.5}));
});
test('benchmark reports per-seed outcomes without altering live mission',()=>{const sim=new ReefLab();const before=sim.snapshot();const result=sim.evaluate({seeds:[42,43],scenario:'drop'});assert.equal(result.runs.length,2);assert.equal(result.successRate,1);assert.deepEqual(sim.snapshot(),before);});
test('reset clears collision debounce state for deterministic replay',()=>{
 const scene=defaultScene();scene.obstacles.push({id:'initial-contact',position:[-4,-4,2],radius:.5});
 const sim=new ReefLab(scene);sim.command({action:'run'});sim.step(1);const first=sim.snapshot();assert.ok(first.metrics.collisions>0);
 sim.reset();sim.command({action:'run'});sim.step(1);assert.deepEqual(sim.snapshot(),first);
});
test('environment recovery restores the current phase status immediately',()=>{
 const sim=new ReefLab();sim.command({action:'run'});const status=sim.snapshot().status;
 sim.command({action:'inject_fault',kind:'sensor_dropout'});sim.step(2);assert.match(sim.snapshot().status,/Safe hold/);
 sim.step(6.1);const s=sim.snapshot();assert.equal(s.environmentHold,0);assert.equal(s.phase,'survey');assert.equal(s.status,status);
});
test('compound faults recover with conserved identities and bounded retries',()=>{
 const sim=new ReefLab();for(const kind of ['bad_cut','drop','bad_placement','current_surge','sensor_dropout'])sim.command({action:'inject_fault',kind});
 const s=finish(sim);assert.equal(s.completed,true);assert.ok(s.time<360);assert.equal(s.metrics.placed,4);assert.equal(s.metrics.rejectedCuts,1);assert.equal(s.metrics.drops,1);assert.equal(s.metrics.placementRetries,1);assert.equal(s.metrics.recoveries,2);assert.equal(s.fragments.length,8);assert.equal(s.fragments.filter(f=>f.state==='rejected').length,1);assert.deepEqual(s.queuedFaults,[]);
});
test('18 seeded baseline and single-fault evaluations complete within 600 seconds',()=>{
 const sim=new ReefLab();for(const scenario of ['baseline','drop','bad_cut','bad_placement','current_surge','sensor_dropout']){
  const report=sim.evaluate({seeds:[42,43,44],scenario});assert.equal(report.timeLimitSeconds,600);assert.equal(report.successRate,1);assert.match(report.seedVariation,/Fixed exported scene geometry/);
  for(const run of report.runs){assert.equal(run.timedOut,false);assert.ok(run.time<600);assert.equal(run.metrics.placed,4);assert.deepEqual(run.unconsumedFaults,[]);}
 }
});
test('shared sloping bathymetry grounds all scene objects and dropped fragments',()=>{
 assert.ok(terrainHeight(8,0)>terrainHeight(-8,0)+.4);
 const sim=new ReefLab();for(const c of [...sim.snapshot().colonies,...sim.snapshot().obstacles])assert.ok(c.position[2]>=terrainHeight(...c.position));
 sim.command({action:'run'});until(sim,s=>s.phase==='transport');sim.command({action:'set_controller',mode:'gemini'});sim.command({action:'inject_fault',kind:'drop'});sim.step(4);
 const s=sim.snapshot(),f=s.fragments.find(f=>f.state==='dropped');assert.ok(f);assert.ok(Math.abs(f.position[2]-terrainHeight(...f.position)-.07)<1e-8);assert.ok(s.robot.position[2]>=terrainHeight(...s.robot.position)+.7);
});
test('mechanically placed bases use the shared actual scan triangle contact',()=>{
 const s=finish(new ReefLab());for(const f of s.fragments.filter(f=>f.state==='placed'))assert.deepEqual(f.position,coralContactPoint(s.colonies.find(c=>c.id===f.targetId)));
});
test('wildlife affects control and produces deterministic range observations',()=>{
 const sim=new ReefLab();const initial=sim.snapshot();assert.equal(initial.wildlife.length,12);assert.ok(initial.sonar.contacts.length);assert.ok(initial.sonar.contacts.every(c=>c.distance<=initial.sonar.range));
 const result=finish(sim);assert.ok(result.metrics.wildlifeAvoidances>0);assert.ok(result.events.some(e=>e.message.includes('Wildlife clear')));assert.notDeepEqual(result.wildlife[0].position,initial.wildlife[0].position);assert.equal(result.completed,true);
});
test('direct and clearance routes follow distinct waypoints without teleportation',()=>{
 const direct=finish(new ReefLab());const sim=new ReefLab();sim.command({action:'set_route',mode:'clearance'});sim.command({action:'run'});until(sim,s=>s.phase==='inspect_donor');
 const before=sim.snapshot();assert.equal(before.route.alternatives.length,2);assert.ok(before.route.waypoints.length>3);sim.step(1/60);const after=sim.snapshot();assert.ok(Math.hypot(...after.robot.position.map((v,i)=>v-before.robot.position[i]))<.1);
 const result=finish(sim);assert.equal(result.completed,true);assert.ok(result.metrics.distance>direct.metrics.distance+20);assert.equal(result.route.mode,'clearance');assert.throws(()=>sim.command({action:'set_route',mode:'unknown'}));
});
test('Gemini observations include sensor and navigation context',()=>{
 const sim=new ReefLab({controller:'gemini'});sim.command({action:'run'});const s=until(sim,s=>!!s.pendingDecision);assert.ok(s.pendingDecision.observation.sonar.contacts.length);assert.equal(s.pendingDecision.observation.wildlife.length,12);assert.equal(s.pendingDecision.observation.route.mode,'direct');
});
test('dense visible habitat has shared broadphase and sonar proxies',()=>{
 const sim=new ReefLab();assert.ok(sim.snapshot().habitatCount>500);
 const first=sim.habitat.find(c=>c.type==='coral');sim.robot.position=[first.position[0],first.position[1],first.position[2]+first.height+.4];
 assert.ok(sim._nearHabitat(2.6).some(c=>c.id===first.id));const sonar=sim._sonar();assert.ok(sonar.contacts.some(c=>c.id===first.id));assert.ok(sonar.contacts.length<=64);assert.equal(sonar.omittedContacts,sonar.totalContacts-sonar.contacts.length);assert.ok(sonar.contacts.every(c=>c.bearing>=-Math.PI&&c.bearing<=Math.PI));
 const d=sim.colonies.find(c=>c.id==='donor-1');assert.ok(sim.habitat.every(c=>Math.hypot(c.position[0]-d.position[0],c.position[1]-d.position[1])>1));
});
test('near-seabed crab encounter triggers actual vehicle yielding',()=>{
 const sim=new ReefLab(),crab=sim.wildlife.find(a=>a.type==='crab');sim.robot.position=[...crab.position];sim.robot.position[2]+=.65;sim.robot.target=[sim.robot.position[0]+1,...sim.robot.position.slice(1)];sim._physics(1/60);assert.equal(sim.wildlifeYield,true);assert.equal(sim.metrics.wildlifeAvoidances,1);
});
test('manual body-frame thrust moves smoothly and watchdog returns to neutral',()=>{
 const sim=new ReefLab();sim.robot.position=[0,0,5];sim.robot.gripper=[0,0,4.35];sim.command({action:'set_pilot',mode:'manual'});assert.equal(sim.running,true);sim.command({action:'manual_input',forward:1,right:0,vertical:0,yaw:0});sim.step(1);
 let s=sim.snapshot();assert.ok(s.robot.position[0]>.3);assert.ok(s.robot.velocity[0]>0);assert.ok(Math.hypot(...s.physics.forces.thrust)<=42.00001);
 sim.step(1.2);s=sim.snapshot();assert.equal(s.pilot.expired,true);assert.deepEqual(s.pilot.command,{forward:0,right:0,vertical:0,yaw:0});assert.deepEqual(s.physics.forces.thrust,[0,0,0]);assert.ok(s.robot.position[0]<3);
 sim.command({action:'pause'});const frozen=sim.snapshot();sim.step(1);assert.deepEqual(sim.snapshot(),frozen);
});
test('neutral manual vehicle responds to continuous current while forces remain measurable',()=>{
 const make=current=>{const sim=new ReefLab({water:{current}});sim.robot.position=[0,0,5];sim.command({action:'set_pilot',mode:'manual'});sim.step(2);return sim.snapshot();};
 const still=make(0),flowing=make(.3);assert.ok(flowing.robot.velocity[0]>still.robot.velocity[0]+.02);assert.ok(flowing.water.currentSpeed>0);assert.ok(flowing.physics.forces.drag.some(v=>v!==0));assert.equal(flowing.physics.forces.buoyancy[2],.15);
});
test('manual release conserves the held cutting and autonomous recovery resumes from current pose',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='transport');const id=sim.snapshot().robot.holding;assert.ok(id);sim.command({action:'set_pilot',mode:'manual'});sim.command({action:'manual_gripper',open:true});assert.equal(sim.snapshot().fragments.find(f=>f.id===id).state,'dropped');assert.equal(sim.snapshot().fragments.length,8);
 const pose=sim.snapshot().robot.position;sim.command({action:'set_pilot',mode:'autonomous'});assert.deepEqual(sim.snapshot().robot.position,pose);assert.equal(finish(sim).completed,true);
});
test('manual movement enforces world and seabed bounds and validates all input axes',()=>{
 const sim=new ReefLab();sim.robot.position=[11.99,0,5];sim.command({action:'set_pilot',mode:'manual'});sim.command({action:'manual_input',forward:1,vertical:-1});sim.step(1.5);const s=sim.snapshot();assert.ok(s.robot.position[0]<=12);assert.ok(s.robot.position[2]>=terrainHeight(...s.robot.position)+.7);
 for(const value of [NaN,Infinity,2,-2])assert.throws(()=>sim.command({action:'manual_input',forward:value}));assert.throws(()=>sim.command({action:'set_pilot',mode:'fake'}));
});
test('new seeds randomize actual mission positions and reproducibly varied schools',()=>{
 const a=new ReefLab({seed:42}),b=new ReefLab({seed:43});assert.notDeepEqual(a.snapshot().colonies.find(c=>c.id==='donor-1').position,b.snapshot().colonies.find(c=>c.id==='donor-1').position);assert.notDeepEqual(a.snapshot().wildlife,b.snapshot().wildlife);
 a.command({action:'randomize',seed:43});assert.deepEqual(a.exportScene(),b.exportScene());assert.deepEqual(a.snapshot().wildlife,b.snapshot().wildlife);assert.ok(a.snapshot().wildlife.filter(x=>x.schoolId).length>=6);
 a.command({action:'run'});a.step(10);assert.ok(a.snapshot().wildlife.every(x=>x.position.every(Number.isFinite)&&Math.hypot(...x.velocity)<3));assert.throws(()=>a.command({action:'randomize',seed:44}));
});
test('sensor fusion is bounded and honestly labeled and sonar samples at five hertz',()=>{
 const sim=new ReefLab();sim.command({action:'run'});sim.step(.21);const first=sim.snapshot();sim.step(.05);const next=sim.snapshot();assert.equal(first.sonar.time,next.sonar.time);assert.ok(next.sensors.fusion.contacts.length<=32);assert.match(next.sensors.fusion.source,/Synthetic/);assert.equal(next.sensors.fusion.controllerSource,'none');assert.ok(next.navigation.bedClearance>=.7);
});
test('Gemini can select only a declared high-level route',()=>{
 const sim=new ReefLab({controller:'gemini'});sim.command({action:'run'});const s=until(sim,s=>!!s.pendingDecision);const id=s.pendingDecision.id;assert.throws(()=>sim.command({action:'apply_decision',id,decision:'proceed',reason:'x',source:'gemini',routeMode:'teleport'}));sim.command({action:'apply_decision',id,decision:'proceed',reason:'Prefer clearance',source:'gemini',routeMode:'clearance'});assert.equal(sim.snapshot().route.mode,'clearance');assert.equal(sim.snapshot().decision.routeMode,'clearance');
});
test('Gemini provenance records only bounded explicit scalar evidence',()=>{
 const sim=new ReefLab({controller:'gemini'});sim.command({action:'run'});const s=until(sim,s=>!!s.pendingDecision);assert.ok(JSON.stringify(s.pendingDecision.observation).length<32768);
 sim.command({action:'apply_decision',id:s.pendingDecision.id,decision:'proceed',reason:'Image and telemetry reviewed',source:'gemini',evidence:{model:'gemini-test',latencyMs:250,inputMode:'image_and_telemetry',inputImageSha256:'abc',inputCamera:'wrist',inputImageTime:10,rawImage:'must not store',apiKey:'must not store',inputImageWidth:640}});
 const d=sim.snapshot().decision;assert.equal(d.model,'gemini-test');assert.equal(d.latencyMs,250);assert.equal(d.inputCamera,'wrist');assert.equal(d.rawImage,undefined);assert.equal(d.apiKey,undefined);
});
test('manual exploration after completion preserves verified mission metrics',()=>{
 const sim=new ReefLab();finish(sim);const metrics=sim.snapshot().metrics.placed;sim.command({action:'set_pilot',mode:'manual'});sim.command({action:'run'});sim.command({action:'manual_input',vertical:1});sim.step(.2);assert.equal(sim.snapshot().metrics.placed,metrics);assert.equal(sim.snapshot().completed,true);sim.command({action:'set_pilot',mode:'autonomous'});assert.equal(sim.snapshot().running,false);
});
test('UV inspection exposure requires actual safe range and both registered colonies before cut',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='inspect_recipient');const targetId=sim.targetId;sim.robot.gripper=[12,12,7];const before=sim.uvObservations.find(o=>o.id===targetId)?.exposureSeconds??0;assert.equal(sim._recordInspection(.5),false);assert.equal(sim.uvObservations.find(o=>o.id===targetId).exposureSeconds,before);
 const s=until(sim,s=>s.phase==='cut');assert.equal(s.phase,'cut');for(const id of [s.targetId,s.donorId]){const observation=s.perception.observations.find(o=>o.id===id);assert.ok(observation);assert.equal(observation.exposure,1);assert.equal(observation.source,'synthetic_camera_uv');assert.ok(observation.registryGenet);assert.ok(observation.uvMarker.startsWith('scenario-marker-'));}assert.ok(s.perception.candidateComparison.some(c=>!c.eligible));
});
test('injected current wave overloads the carried grip and recovers the same cutting',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='transport');const id=sim.snapshot().robot.holding;sim.command({action:'inject_fault',kind:'current_surge'});sim.step(4);
 const failure=sim.snapshot();assert.equal(failure.metrics.drops,1);assert.equal(failure.metrics.placed,0);assert.equal(failure.completed,false);assert.equal(failure.grip.lastLoss.fragmentId,id);assert.ok(failure.grip.lastLoss.loadN>failure.grip.lastLoss.thresholdN);assert.equal(failure.fragments.find(f=>f.id===id).state,'dropped');
 const result=finish(sim);assert.equal(result.completed,true);assert.equal(result.fragments.find(f=>f.id===id).state,'placed');assert.equal(result.metrics.recoveries,1);assert.equal(result.fragments.length,8);
});
test('a current wave cannot detach a cutting before its authorized cut',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='cut');const id=sim.fragmentId;sim.command({action:'inject_fault',kind:'current_surge'});sim.step(4);assert.equal(sim.snapshot().fragments.find(f=>f.id===id).state,'grasped');assert.equal(sim.snapshot().metrics.drops,0);assert.equal(sim.snapshot().grip.lastLoss,null);assert.equal(finish(sim).completed,true);
});
test('seeded dense habitat changes and remains shared with physical proxies',()=>{
 const a=new ReefLab({seed:42}),b=new ReefLab({seed:43});assert.notDeepEqual(a.habitat[0].position,b.habitat[0].position);assert.deepEqual(a.habitat,new ReefLab({seed:42}).habitat);
});
const externalPerception=(sim,id,health,overrides={})=>({requestId:sim.perceptionRequest.id,captureRequestId:sim.perceptionRequest.id,targetId:id,targetKind:sim.perceptionRequest.targetKind,frameTime:sim.time,source:'gemma',provider:'test_fixture_transport',model:'gemma-fixture-not-live',observations:sim.perceptionRequest.targetKind==='fragment'?[]:[{id,health,confidence:.92}],fragmentVisible:sim.perceptionRequest.targetKind==='fragment'?true:null,gripperState:sim.perceptionRequest.targetKind==='fragment'?(sim.robot.holding?'holding':'empty'):null,...overrides});
const externalPlan=(sim,overrides={})=>({requestId:sim.pendingDecision.id,frameTime:sim.pendingDecision.observation.time,source:'argon',provider:'test_fixture_transport',model:'argon-fixture-not-live',decision:sim.pendingDecision.allowedActions[0],reason:'Offline fixture chooses a bounded local alternative.',routeMode:'direct',optimizer:sim.requireFullStack?{source:'cuopt',configured:true,status:'solved',solverStatus:'SUCCESS',requestId:sim.pendingDecision.id,routeMode:'direct',objectiveCost:10,costs:{direct:10,clearance:15},model:'cuopt-fixture-not-live',solverVersion:'fixture',solveTimeMs:1}:{source:'not_configured'},...overrides});
function runBaseFixture(sim,onStep=null){sim.command({action:'run'});let maxBytes=0;while(sim.running&&sim.time<600){sim.step(.2);if(onStep)onStep(sim);const p=sim.snapshot().perception;if(sim.perceptionRequest?.ready&&!sim.externalRequestIds.has(`perception:${sim.perceptionRequest.id}`)){sim.command({action:'ingest_perception',packet:externalPerception(sim,p.targetId,p.stage==='inspect_donor'?'healthy':'bleached_alive')});}if(sim.pendingDecision){maxBytes=Math.max(maxBytes,JSON.stringify(sim.pendingDecision.observation).length);const packet=externalPlan(sim);sim.command({action:'ingest_plan',packet});sim.command({action:'apply_decision',id:packet.requestId,decision:packet.decision,reason:packet.reason,routeMode:packet.routeMode,source:'base_station',evidence:{planning:packet}});}}return {state:sim.snapshot(),maxBytes};}
test('base-station architecture waits for model perception and keeps physics/reflexes running',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});until(sim,s=>s.perception.exposure===1);const before=sim.snapshot();assert.equal(before.phase,'inspect_recipient');assert.equal(before.intelligence.onboard.status,'waiting');sim.step(3);const after=sim.snapshot();assert.equal(after.phase,'inspect_recipient');assert.ok(after.time>before.time);assert.equal(after.metrics.placed,0);assert.equal(after.intelligence.onboard.lastPacket,null);assert.equal(after.pendingDecision,null);assert.notDeepEqual(after.wildlife[0].position,before.wildlife[0].position);
});
test('external Gemma estimates cannot overwrite registry truth or bypass a conservative health gate',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});until(sim,s=>s.perception.exposure===1);const id=sim.targetId,registry=sim.snapshot().registryGroundTruth;const packet=externalPerception(sim,id,'dead');packet.observations[0].genet='invented';sim.command({action:'ingest_perception',packet});sim.step(2);assert.equal(sim.phase,'inspect_recipient');assert.deepEqual(sim.snapshot().registryGroundTruth,registry);assert.equal(sim.intelligence.onboard.observations[0].genotypeInferred,false);assert.equal(sim.intelligence.onboard.observations[0].genet,undefined);assert.equal(sim.metrics.attempts,1);assert.equal(sim.fragments.every(f=>f.state==='attached'),true);
});
test('perception packet freshness, ordering and replay validation rejects unsafe updates',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});until(sim,s=>s.perception.exposure===1);const id=sim.targetId,packet=externalPerception(sim,id,'bleached_alive');sim.command({action:'ingest_perception',packet});assert.throws(()=>sim.command({action:'ingest_perception',packet}));assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,requestId:'future',frameTime:sim.time+1}}));assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,requestId:'older',frameTime:sim.time-1}}));assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,requestId:'unknown',observations:[{id:'nonexistent',health:'healthy',confidence:.9}]}}));sim.time+=121;assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,requestId:'stale'}}));assert.equal(sim._externalHealth(id,'bleached_alive').ready,false);
});
test('offline architecture fixture exercises Gemma gating and Argon planning without claiming live models',()=>{
 const sim=new ReefLab({controller:'base_station',requireFullStack:false}),{state,maxBytes}=runBaseFixture(sim);assert.equal(state.completed,true);assert.equal(state.metrics.placed,4);assert.equal(state.intelligence.onboard.observations.length,8);assert.equal(state.decision.source,'base_station');assert.equal(state.decision.planning.model,'argon-fixture-not-live');assert.equal(state.decision.perception.model,'gemma-fixture-not-live');assert.equal(state.decision.planning.optimizer.source,'not_configured');assert.ok(maxBytes<32768);assert.equal(state.intelligence.hardwareValidated,false);
});
test('Argon route proposals require matching fresh plans and local bounded alternatives',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});while(!sim.pendingDecision&&sim.running){sim.step(.2);const p=sim.snapshot().perception;if(sim.perceptionRequest?.ready&&!sim.externalRequestIds.has(`perception:${sim.perceptionRequest.id}`))sim.command({action:'ingest_perception',packet:externalPerception(sim,p.targetId,p.stage==='inspect_donor'?'healthy':'bleached_alive')});}
 const packet=externalPlan(sim);assert.throws(()=>sim.command({action:'apply_decision',id:packet.requestId,decision:packet.decision,reason:packet.reason,source:'base_station',routeMode:'direct',evidence:{planning:packet}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,requestId:'stale-other'}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,routeMode:'teleport'}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,waypoints:[[999,0,0]]}}));sim.command({action:'ingest_plan',packet});assert.equal(sim.intelligence.baseStation.localValidation.safe,true);assert.throws(()=>sim.command({action:'ingest_plan',packet}));sim.time+=46;assert.throws(()=>sim.command({action:'apply_decision',id:packet.requestId,decision:packet.decision,reason:packet.reason,source:'base_station',routeMode:'direct',evidence:{planning:packet}}));assert.equal(sim.phase,'approval');assert.equal(sim.metrics.placed,0);
});
test('seeded mission colonies occupy multiple nonlinear healthy and bleached regions',()=>{
 const sim=new ReefLab({seed:42}),s=sim.snapshot(),donors=s.colonies.filter(c=>c.id.startsWith('donor-')),recipients=s.colonies.filter(c=>c.id.startsWith('recipient-'));
 assert.equal(s.regions.filter(r=>r.kind==='healthy').length,2);assert.equal(s.regions.filter(r=>r.kind==='bleached_alive').length,2);assert.ok(s.regions.some(r=>r.kind==='mixed'));
 for(const [colonies,kind] of [[donors,'healthy'],[recipients,'bleached_alive']]){const occupied=new Set();for(const c of colonies){const nearest=s.regions.filter(r=>r.kind===kind).sort((a,b)=>Math.hypot(c.position[0]-a.center[0],c.position[1]-a.center[1])-Math.hypot(c.position[0]-b.center[0],c.position[1]-b.center[1]))[0];assert.ok(Math.hypot(c.position[0]-nearest.center[0],c.position[1]-nearest.center[1])<nearest.radius*.5);occupied.add(nearest.id);}assert.equal(occupied.size,2);assert.equal(new Set(colonies.map(c=>c.position[1].toFixed(3))).size,4);}
 const [a,b,c]=donors.map(c=>c.position);assert.ok(Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))>.5);
 for(const c of s.colonies)assert.ok(c.position[2]>=terrainHeight(...c.position));
});
test('visible current samples are the exact local field used by dynamics and vanish at zero base current',()=>{
 const sim=new ReefLab();sim.command({action:'run'});sim.step(1);const samples=sim.snapshot().water.currentSamples;assert.equal(samples.length,25);for(const s of samples)assert.deepEqual(s.vector,sim._currentAt(s.position));assert.notDeepEqual(samples[0].vector,samples[12].vector);assert.match(sim.snapshot().physics.assetResponses.stonyCoral,/Rigid/);
 sim.command({action:'set_water',current:0});assert.ok(sim.snapshot().water.currentSamples.every(s=>s.vector.every(v=>v===0)));
});
test('one thousand seeded layouts generate without crowded-region sampling failures',()=>{
 for(let seed=0;seed<1000;seed++){const scene=defaultScene(seed);assert.equal(scene.colonies.length,84);assert.equal(new Set(scene.colonies.map(c=>c.id)).size,84);const mission=scene.colonies.filter(c=>c.genet);for(let i=0;i<mission.length;i++){assert.ok(mission[i].position.every(Number.isFinite));for(let j=i+1;j<mission.length;j++)assert.ok(Math.hypot(mission[i].position[0]-mission[j].position[0],mission[i].position[1]-mission[j].position[1])>1.45);}}
});
test('full-stack fixture consumes actual solver-selected route and recovers via a matched fragment capture',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'inject_fault',kind:'drop'});const {state,maxBytes}=runBaseFixture(sim);assert.equal(state.completed,true);assert.equal(state.metrics.drops,1);assert.equal(state.metrics.recoveries,1);assert.equal(state.decision.planning.optimizer.source,'cuopt');assert.equal(state.decision.planning.optimizer.solverStatus,'SUCCESS');assert.equal(state.decision.routeMode,state.decision.planning.optimizer.routeMode);assert.ok(state.events.some(e=>e.message.includes('fragment/gripper view')));assert.ok(maxBytes<32768);
});
test('expired approval evidence triggers physical rescans and invalidates the old planning request',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});while(!sim.pendingDecision&&sim.running){sim.step(.2);const request=sim.perceptionRequest;if(request?.ready&&!sim.externalRequestIds.has(`perception:${request.id}`))sim.command({action:'ingest_perception',packet:externalPerception(sim,request.targetId,request.expectedHealth)});}
 const old=externalPlan(sim),pose=sim.snapshot().robot.position;for(const o of sim.intelligence.onboard.observations)o.frameTime=sim.time-121;sim.step(1/60);assert.equal(sim.phase,'inspect_recipient');assert.equal(sim.pendingDecision,null);assert.ok(sim.perceptionRequest);assert.ok(Math.hypot(...sim.robot.position.map((v,i)=>v-pose[i]))<.1);assert.throws(()=>sim.command({action:'ingest_plan',packet:old}));
 const {state}=runBaseFixture(sim);assert.equal(state.completed,true);assert.notEqual(state.decision.id,old.requestId);
});
test('a rescan while carrying preserves the cutting and resumes transport without a second cut',()=>{
 const sim=new ReefLab();sim.command({action:'run'});until(sim,s=>s.phase==='transport');const id=sim.robot.holding;sim.command({action:'request_rescan'});assert.equal(sim.phase,'inspect_fragment');assert.equal(sim.robot.holding,id);const s=finish(sim);assert.equal(s.completed,true);assert.equal(s.metrics.drops,0);assert.equal(s.fragments.filter(f=>f.id===id).length,1);assert.equal(s.fragments.find(f=>f.id===id).state,'placed');
});
test('capture target binding rejects wrong-camera and early frames while allowing an explicit fresh retry',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});until(sim,s=>s.perceptionRequest?.ready);const request=sim.perceptionRequest,packet=externalPerception(sim,request.targetId,request.expectedHealth);assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,targetId:sim.donorId}}));assert.throws(()=>sim.command({action:'ingest_perception',packet:{...packet,frameTime:request.frameTimeMin}}));
 sim.command({action:'ingest_perception',packet:{...packet,observations:[{id:request.targetId,health:'unknown',confidence:.3}]}});sim.step(.2);sim.command({action:'ingest_perception',packet:{...externalPerception(sim,request.targetId,request.expectedHealth),requestId:request.id+'-retry'}});assert.equal(sim._externalHealth(request.targetId,request.expectedHealth).ready,true);
 const oldCapture=request.id;sim.command({action:'pause'});sim.reset();sim.command({action:'run'});until(sim,s=>s.perceptionRequest?.ready);assert.notEqual(sim.perceptionRequest.id,oldCapture);assert.throws(()=>sim.command({action:'ingest_perception',packet}));
});
test('configured cuOpt cannot be omitted, mismatched, or replaced with an unsolved heuristic',()=>{
 const sim=new ReefLab({controller:'base_station'});sim.command({action:'run'});while(!sim.pendingDecision&&sim.running){sim.step(.2);const request=sim.perceptionRequest;if(request?.ready&&!sim.externalRequestIds.has(`perception:${request.id}`))sim.command({action:'ingest_perception',packet:externalPerception(sim,request.targetId,request.expectedHealth)});}
 const packet=externalPlan(sim);assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,optimizer:{source:'not_configured'}}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,optimizer:{...packet.optimizer,solverStatus:'HEURISTIC'}}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,optimizer:{...packet.optimizer,routeMode:'clearance'}}}));assert.throws(()=>sim.command({action:'ingest_plan',packet:{...packet,optimizer:{...packet.optimizer,requestId:'another-job'}}}));sim.command({action:'ingest_plan',packet});assert.equal(sim.intelligence.baseStation.plan.optimizer.objectiveCost,10);
});
test('full-stack recovery handles hydrodynamic grip failure without moving into an unsafe current hold',()=>{
 const sim=new ReefLab({controller:'base_station'});let injected=false;const {state,maxBytes}=runBaseFixture(sim,s=>{if(!injected&&s.phase==='transport'){injected=true;s.command({action:'inject_fault',kind:'current_surge'});}});assert.equal(state.completed,true);assert.ok(state.grip.lastLoss);assert.equal(state.metrics.drops,1);assert.equal(state.metrics.recoveries,1);assert.equal(state.fragments.find(f=>f.id===state.grip.lastLoss.fragmentId).state,'placed');assert.equal(state.decision.planning.optimizer.solverStatus,'SUCCESS');assert.ok(maxBytes<32768);
});
