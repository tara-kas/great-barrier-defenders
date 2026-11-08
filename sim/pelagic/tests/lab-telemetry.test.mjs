import test from 'node:test';
import assert from 'node:assert/strict';
import {TelemetryRecorder} from '../web/lab/telemetry.mjs';

const snapshot = time => ({time, pilot: 'manual', robot: {position: [1,2,3], velocity: [.1,0,0], yaw: 1},
  water: {current: .2, vector: [.2,0,.01]}, forces: {thrust: [1,0,0]},
  sonar: {contacts: [{id: 'rock-1', distance: 1.5, position: [2,2,3]}], fusion: {hazards: ['rock-1']}},
  route: {mode: 'clearance', waypoints: [[3,2,4]]}, phase: 'transit', metrics: {collisions: 0},
  decision: {source: 'gemini', routeMode: 'clearance', reason: 'Sonar reports rock-1.', inputImageSha256: 'a'.repeat(64), secret: 'exclude'}});

test('samples at most 5Hz simulation time and exports independent frames', () => {
  const recorder = new TelemetryRecorder();
  const state = snapshot(0);
  assert.equal(recorder.sample(state), true);
  state.robot.position[0] = 99;
  assert.equal(recorder.sample(snapshot(.1)), false);
  assert.equal(recorder.sample(snapshot(.2)), true);
  assert.equal(recorder.sample(snapshot(.2)), false);
  const frames = recorder.exportJSONL().trim().split('\n').map(JSON.parse);
  assert.equal(frames.length, 2);
  assert.equal(frames[0].robot.position[0], 1);
  assert.deepEqual(frames[0].water.vector, [.2,0,.01]);
  assert.deepEqual(frames[0].sonar.fusion, {hazards: ['rock-1']});
  assert.equal(frames[0].decision.routeMode, 'clearance');
  assert.ok(!recorder.exportJSONL().includes('exclude'));
});

test('bounds retained frames and resets when simulation time decreases', () => {
  const recorder = new TelemetryRecorder({maxFrames: 2});
  for (const time of [0,.2,.4,.6]) recorder.sample(snapshot(time));
  assert.equal(recorder.summary().frames, 2);
  assert.equal(recorder.summary().droppedFrames, 2);
  recorder.sample(snapshot(0));
  assert.equal(recorder.summary().frames, 1);
  assert.equal(recorder.summary().resets, 1);
  assert.equal(recorder.summary().startTime, 0);
  recorder.clear();
  assert.equal(recorder.exportJSONL(), '');
});

test('does not invent missing measurements and bounds contact detail', () => {
  const recorder = new TelemetryRecorder();
  recorder.sample({time: 0, sonar: {contacts: Array.from({length: 100}, (_,id) => ({id: String(id), distance: id}))}});
  const frame = JSON.parse(recorder.exportJSONL());
  assert.equal(frame.forces, null);
  assert.equal(frame.water.vector, null);
  assert.equal(frame.sonar.valid, null);
  assert.equal(frame.sonar.contacts.length, 12);
  assert.equal(frame.sonar.omittedContacts, 88);
  assert.throws(() => recorder.sample({time: NaN}));
  assert.throws(() => new TelemetryRecorder({maxFrames: 3001}));
  assert.throws(() => new TelemetryRecorder({sampleHz: 6}));
});

test('records actual engine route/navigation separation and sensors.fusion', () => {
  const recorder = new TelemetryRecorder();
  const state = snapshot(1);
  state.pilot = {mode: 'manual', command: [.2,0,0], lastInputTime: 1, watchdogSeconds: .5, expired: false};
  state.water = {current: .2, currentVector: [.1,.2,.03], currentSpeed: Math.hypot(.1,.2,.03)};
  state.forces = undefined;
  state.physics = {forces: {thrust: [1,2,3], drag: [-1,-1,0], buoyancy: [0,0,.15], net: [0,1,3.15]}};
  state.route = {mode: 'clearance', goal: [4,5,6], index: 1, waypoints: [[2,3,4],[4,5,6]], alternatives: [{id:'direct',points:[[0,0,0],[4,5,6]]}]};
  state.navigation = {velocity: [.1,0,0], speed: .1, bedClearance: .9, waypointIndex: 1};
  state.sensors = {fusion: {source:'synthetic',confidence:.65,contacts:[{id:'rock-a'}],controllerSource:'scripted'}};
  recorder.sample(state);
  const data = JSON.parse(recorder.exportJSONL());
  assert.equal(data.navigation.mode, 'clearance');
  assert.deepEqual(data.navigation.goal, [4,5,6]);
  assert.equal(data.navigation.waypoints.length, 2);
  assert.equal(data.navigation.bedClearance, .9);
  assert.equal(data.navigation.speed, .1);
  assert.deepEqual(data.sonar.fusion, state.sensors.fusion);
  assert.deepEqual(data.water.vector, state.water.currentVector);
  assert.deepEqual(data.forces, state.physics.forces);
  assert.equal(data.pilot.mode, 'manual');
});
test('architecture telemetry separates synthetic observations, model execution provenance, and registry truth',()=>{
 const recorder=new TelemetryRecorder();const state=snapshot(3);state.registryGroundTruth={genotypeSource:'explicit registry',pair:[{id:'d1',health:'healthy',species:'Pocillopora',genet:'G1'}]};state.perception={source:'synthetic_camera_uv',stage:'inspect',exposure:1,observations:[{id:'d1',source:'synthetic_camera_uv',uvMarker:'scenario-G1',rangeM:.5,exposureSeconds:1.2}]};state.intelligence={architecture:'Gemma → Argon → local safety',perceptionMaxAgeSeconds:120,planMaxAgeSeconds:45,onboard:{status:'received',observations:[{id:'d1',health:'unknown',confidence:.3,source:'gemma',model:'gemma-fixture',provider:'fixture',frameTime:2,requestId:'f1'}],lastPacket:{source:'gemma',model:'gemma-fixture',provider:'fixture',requestId:'f1',frameTime:2,rawImage:'do not record'}},baseStation:{status:'received',plan:{source:'argon',model:'argon-fixture',requestId:'p1',routeMode:'clearance',optimizer:{source:'not_configured'},credential:'do not record'},localValidation:{safe:true,guard:'local reflexes'}}};
 recorder.sample(state);const data=JSON.parse(recorder.exportJSONL());assert.equal(data.registryGroundTruth.pair[0].health,'healthy');assert.equal(data.intelligence.onboardPerception.observations[0].health,'unknown');assert.equal(data.intelligence.onboardPerception.provenance.model,'gemma-fixture');assert.equal(data.syntheticInspection.source,'synthetic_camera_uv');assert.equal(data.intelligence.hardwareValidated,false);assert.equal(data.intelligence.baseStation.optimizer.source,'not_configured');assert.equal(recorder.summary().containsExternalInference,true);assert.ok(!recorder.exportJSONL().includes('do not record'));
});
test('missing model outputs stay explicitly absent in telemetry',()=>{
 const recorder=new TelemetryRecorder();recorder.sample(snapshot(0));const data=JSON.parse(recorder.exportJSONL());assert.equal(data.intelligence.onboardPerception.externalInferenceReceived,false);assert.equal(data.intelligence.onboardPerception.provenance,null);assert.equal(data.intelligence.baseStation.externalPlanReceived,false);assert.equal(data.registryGroundTruth,null);assert.equal(recorder.summary().containsExternalInference,false);
});
test('five actual mission telemetry frames remain below 60 KiB at peak history and long routes',async()=>{
 const {ReefLab}=await import('../web/lab/simulation.mjs');const sim=new ReefLab({seed:42});sim.command({action:'set_route',mode:'clearance'});sim.command({action:'run'});const recorder=new TelemetryRecorder({maxFrames:5});let largest=0,checked=0;
 while(sim.running&&sim.time<600){sim.step(.2);recorder.sample(sim.snapshot());if(recorder.frames.length===5){largest=Math.max(largest,Buffer.byteLength(recorder.exportJSONL(),'utf8'));checked++;}}
 assert.equal(sim.completed,true);assert.ok(checked>100);assert.ok(largest<60*1024,`Five-frame payload peaked at ${largest} bytes`);for(const f of recorder.frames){assert.ok((f.sonar.fusion?.contacts?.length??0)<=12);if(f.sonar.fusion?.omittedContacts)assert.ok(f.sonar.fusion.totalContacts>12);}
});
