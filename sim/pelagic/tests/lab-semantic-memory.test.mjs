import test from 'node:test';
import assert from 'node:assert/strict';
import {SemanticMemory,sceneFingerprint} from '../web/lab/semantic-memory.mjs';
import {ReefLab} from '../web/lab/simulation.mjs';
const storage=()=>{const data=new Map();return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
const observed=(sim,id='recipient-1',requestId='camera-1')=>{const s=sim.snapshot();s.intelligence.onboard.observations=[{id,health:'bleached_alive',confidence:.87,source:'gemma',provider:'fixture',model:'gemma-test-not-live',requestId,frameTime:10,receivedTime:12,genet:'must-not-store',rawImage:'must-not-store',apiKey:'must-not-store'}];return s;};
test('scene-scoped semantic memory persists explicit provenance without authorizing a mission',()=>{
 const db=storage(),sim=new ReefLab(),memory=new SemanticMemory({storage:db,clock:()=>1000});memory.bindScene(sim.exportScene());memory.remember(observed(sim));assert.equal(memory.entries().length,1);assert.equal(memory.entries()[0].usableForControl,false);assert.equal(memory.entries()[0].model,'gemma-test-not-live');assert.ok(!memory.exportJSON().includes('must-not-store'));
 const restored=new SemanticMemory({storage:db,clock:()=>1100});assert.equal(restored.bindScene(sim.exportScene()).restoredCount,1);assert.equal(restored.planningContext(['recipient-1']).usableForControl,false);assert.equal(restored.planningContext(['donor-1']).records.length,0);assert.equal(sim.intelligence.onboard.observations.length,0);assert.equal(sim.metrics.placed,0);
});
test('wrong scene, changed geometry and fabricated observation IDs are invalidated',()=>{
 const sim=new ReefLab(),memory=new SemanticMemory({storage:storage(),clock:()=>1000});memory.bindScene(sim.exportScene());memory.remember(observed(sim));const exported=memory.exportJSON();const other=new ReefLab({seed:43});memory.bindScene(other.exportScene());assert.throws(()=>memory.importJSON(exported));assert.throws(()=>memory.remember(observed(sim)));memory.bindScene(sim.exportScene());assert.throws(()=>memory.remember(observed(sim,'unknown-colony')));const scene=sim.exportScene();scene.colonies[0].position[0]+=.1;assert.notEqual(sceneFingerprint(scene),sceneFingerprint(sim.exportScene()));
});
test('memory retention is bounded, deduplicated and expires without refreshing stale evidence',()=>{
 let now=1000;const sim=new ReefLab(),memory=new SemanticMemory({storage:storage(),maxRecords:2,maxAgeSeconds:10,clock:()=>now});memory.bindScene(sim.exportScene());memory.remember(observed(sim,'recipient-1','a'));memory.remember(observed(sim,'recipient-1','a'));assert.equal(memory.entries().length,1);memory.remember(observed(sim,'recipient-2','b'));memory.remember(observed(sim,'recipient-3','c'));assert.equal(memory.entries().length,2);assert.equal(memory.entries()[0].id,'recipient-2');now=12000;assert.deepEqual(memory.entries(),[]);assert.deepEqual(memory.planningContext().records,[]);
});
test('storage failures degrade to in-session context and explicit clear/export remain safe',()=>{
 const broken={getItem:()=>{throw Error('denied');},setItem:()=>{throw Error('full');},removeItem:()=>{throw Error('denied');}},sim=new ReefLab(),memory=new SemanticMemory({storage:broken,clock:()=>1000});memory.bindScene(sim.exportScene());assert.ok(memory.status.lastError);memory.remember(observed(sim));assert.equal(memory.entries().length,1);assert.ok(memory.status.lastError);memory.clear();assert.equal(memory.entries().length,0);assert.ok(memory.status.lastError);assert.throws(()=>new SemanticMemory({maxRecords:257}));assert.throws(()=>memory.importJSON('x'.repeat(1024*1024+1)));
});
test('appearance observations survive persistence and context without implying viability or control',()=>{
 const db=storage(),sim=new ReefLab(),memory=new SemanticMemory({storage:db,clock:()=>1000});memory.bindScene(sim.exportScene());
 const snapshot=observed(sim),visual={health:'unknown',visualContract:'appearance/v1',targetVisible:true,objectKind:'coral_colony',appearance:'pale_or_bleached',viabilityKnown:false};Object.assign(snapshot.intelligence.onboard.observations[0],visual);memory.remember(snapshot);
 const restored=new SemanticMemory({storage:db,clock:()=>1100});restored.bindScene(sim.exportScene());
 for(const record of [restored.entries()[0],restored.planningContext().records[0]])for(const [key,value] of Object.entries(visual))assert.equal(record[key],value);
 assert.equal(restored.entries()[0].usableForControl,false);assert.equal(restored.planningContext().usableForControl,false);assert.equal(sim.intelligence.onboard.observations.length,0);
});
test('memory rejects malformed or biologically relabelled visual records on write and import',()=>{
 const sim=new ReefLab(),memory=new SemanticMemory({storage:storage(),clock:()=>1000});memory.bindScene(sim.exportScene());
 const snapshot=observed(sim),visual={health:'unknown',visualContract:'appearance/v1',targetVisible:true,objectKind:'coral_colony',appearance:'pigmented',viabilityKnown:false};Object.assign(snapshot.intelligence.onboard.observations[0],visual);memory.remember(snapshot);const exported=JSON.parse(memory.exportJSON());
 for(const change of [{appearance:'healthy'},{objectKind:'living_coral'},{viabilityKnown:true},{health:'healthy'},{visualContract:'appearance/v2'},{targetVisible:'yes'}]){
  const candidate=observed(sim,'recipient-1','new');Object.assign(candidate.intelligence.onboard.observations[0],visual,change);assert.throws(()=>memory.remember(candidate),/visual appearance/);
  const imported=structuredClone(exported);Object.assign(imported.records[0],change);assert.throws(()=>memory.importJSON(JSON.stringify(imported)),/visual appearance/);
 }
 assert.equal(memory.entries().length,1);assert.equal(memory.entries()[0].viabilityKnown,false);
});
