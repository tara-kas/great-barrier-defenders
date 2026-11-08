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
 const direct=finish(new ReefLab());const sim=new ReefLab();sim.command({action:'set_route',mode:'clearance'});sim.command({action:'run'});until(sim,s=>s.phase==='inspect_recipient');
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
