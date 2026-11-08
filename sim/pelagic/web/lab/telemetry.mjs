// Local, bounded simulation telemetry. No network, credentials or image bytes.
const number = value => typeof value === 'number' && Number.isFinite(value) ? Number(value.toFixed(6)) : null;
const vector = value => Array.isArray(value) && value.length >= 3 ? value.slice(0, 3).map(number) : null;
const text = value => typeof value === 'string' ? value.slice(0, 320) : null;
function bounded(value, depth = 0) {
  if (depth > 4 || value == null) return null;
  if (typeof value === 'number') return number(value);
  if (typeof value === 'string') return text(value);
  if (typeof value === 'boolean') return value;
  if (Array.isArray(value)) return value.slice(0, 32).map(item => bounded(item, depth + 1));
  if (typeof value === 'object') return Object.fromEntries(Object.entries(value).slice(0, 32)
    .filter(([key]) => !/key|token|credential|image|base64|secret/i.test(key))
    .map(([key, item]) => [key.slice(0, 80), bounded(item, depth + 1)]));
  return null;
}
function frame(snapshot) {
  const robot = snapshot.robot || {}, sonar = snapshot.sonar || {};
  const route = {...snapshot.navigation, ...snapshot.route};
  const decision = snapshot.decision || {};
  const intelligence=snapshot.intelligence||{},onboard=intelligence.onboard||{},base=intelligence.baseStation||{};
  const estimate=value=>({id:text(value.id),health:text(value.health),confidence:number(value.confidence),frameTime:number(value.frameTime),receivedTime:number(value.receivedTime),source:text(value.source),model:text(value.model),provider:text(value.provider),requestId:text(value.requestId),genotypeInferred:false,confidenceCalibration:text(value.confidenceCalibration)});
  const provenance=value=>value?{requestId:text(value.requestId),captureRequestId:text(value.captureRequestId),targetId:text(value.targetId),targetKind:text(value.targetKind),fragmentVisible:typeof value.fragmentVisible==='boolean'?value.fragmentVisible:null,gripperState:text(value.gripperState),source:text(value.source),provider:text(value.provider),model:text(value.model),deployment:text(value.deployment),frameTime:number(value.frameTime),receivedTime:number(value.receivedTime),latencyMs:number(value.latencyMs),inputImageSha256:text(value.inputImageSha256)}:null;
  const flow = snapshot.water?.vector ?? snapshot.water?.currentVector ?? snapshot.water?.current_vector;
  const contacts = Array.isArray(sonar.contacts) ? sonar.contacts : [];
  const rawFusion=snapshot.sensors?.fusion??snapshot.fusion??snapshot.sensorFusion??sonar.fusion??null;
  const fusion=rawFusion&&Array.isArray(rawFusion.contacts)&&rawFusion.contacts.length>12?{...rawFusion,contacts:rawFusion.contacts.slice(0,12),totalContacts:rawFusion.contacts.length,omittedContacts:Math.max(0,rawFusion.contacts.length-12)}:rawFusion;
  return {
    schema: 'reef-rescue-telemetry/v1', numericPrecisionDecimals:6, time: number(snapshot.time),
    pilot: bounded(snapshot.pilot ?? snapshot.controlMode ?? snapshot.controller),
    robot: {position: vector(robot.position), velocity: vector(robot.velocity), yaw: number(robot.yaw),
      target: vector(robot.target), gripper: vector(robot.gripper), holding: text(robot.holding)},
    water: {current: number(snapshot.water?.current), currentSpeed: number(snapshot.water?.currentSpeed), vector: vector(flow),currentSamples:(snapshot.water?.currentSamples||[]).filter((_,i)=>i%3===0).slice(0,9).map(s=>({position:vector(s.position),vector:vector(s.vector)})),fieldSource:text(snapshot.water?.fieldSource), visibility: number(snapshot.water?.visibility)},
    forces: bounded(snapshot.forces ?? snapshot.physics?.forces ?? robot.forces ?? null),
    sonar: {source: 'synthetic_sonar', model: text(sonar.model), valid: typeof sonar.valid === 'boolean' ? sonar.valid : null,
      range: number(sonar.range), closestRange: number(sonar.closestRange),
      totalContacts: number(sonar.totalContacts) ?? contacts.length,
      omittedContacts: Math.max(0, (number(sonar.totalContacts) ?? contacts.length) - Math.min(12, contacts.length)),
      contacts: contacts.slice(0, 12).map(contact => ({id: text(contact.id), type: text(contact.type),
        distance: number(contact.distance ?? contact.range), bearing: number(contact.bearing),
        position: vector(contact.position), velocity: vector(contact.velocity)})),
      fusion: bounded(fusion)},
    navigation: {mode: text(route.mode), goal: vector(route.goal), index: number(route.index),
      velocity: vector(route.velocity), speed: number(route.speed), bedClearance: number(route.bedClearance),
      waypointIndex: number(route.waypointIndex),
      waypoints: Array.isArray(route.waypoints) ? route.waypoints.slice(0, 24).map(vector) : [],
      alternatives: Array.isArray(route.alternatives) ? route.alternatives.slice(0, 2).map(item => ({
        id: text(item.id ?? item.mode), clearance: number(item.clearance), risk: number(item.risk),
        points: Array.isArray(item.points) ? item.points.slice(0, 24).map(vector) : [],
      })) : []},
    intelligence: {
      architecture:text(intelligence.architecture),hardwareValidated:false,requireFullStack:intelligence.requireFullStack===true,
      onboardPerception:{status:text(onboard.status),reason:text(onboard.reason),provenance:provenance(onboard.lastPacket),externalInferenceReceived:!!onboard.lastPacket,
        observations:Array.isArray(onboard.observations)?onboard.observations.slice(-24).map(estimate):[]},
      baseStation:{status:text(base.status),reason:text(base.reason),provenance:provenance(base.plan),externalPlanReceived:!!base.plan,
        decision:text(base.plan?.decision),routeMode:text(base.plan?.routeMode),optimizer:bounded(base.plan?.optimizer),localValidation:bounded(base.localValidation)},
      freshnessPolicy:{perceptionMaxAgeSeconds:number(intelligence.perceptionMaxAgeSeconds),planMaxAgeSeconds:number(intelligence.planMaxAgeSeconds)},
    },
    perceptionRequest:bounded(snapshot.perceptionRequest),rescan:bounded(snapshot.rescan),
    registryGroundTruth: snapshot.registryGroundTruth?{source:'scenario_registry_ground_truth',notModelOutput:true,genotypeSource:text(snapshot.registryGroundTruth.genotypeSource),
      pair:(snapshot.registryGroundTruth.pair||[]).slice(0,2).map(c=>({id:text(c.id),health:text(c.health),species:text(c.species),genet:text(c.genet)}))}:null,
    syntheticInspection:{source:text(snapshot.perception?.source),stage:text(snapshot.perception?.stage),targetId:text(snapshot.perception?.targetId),exposure:number(snapshot.perception?.exposure),
      observations:(snapshot.perception?.observations||[]).slice(-8).map(c=>({id:text(c.id),source:text(c.source),uvMarker:text(c.uvMarker),rangeM:number(c.rangeM),exposureSeconds:number(c.exposureSeconds),score:number(c.score)}))},
    regions:(snapshot.regions||[]).slice(0,8).map(r=>({id:text(r.id),kind:text(r.kind),center:Array.isArray(r.center)?r.center.slice(0,2).map(number):null,radius:number(r.radius)})),
    simulationParameters:bounded({provenance:snapshot.physics?.parameterProvenance,uv:snapshot.physics?.uvProxy,grip:snapshot.physics?.gripProxy,wave:snapshot.physics?.waveProxy}),
    phase: text(snapshot.phase), metrics: bounded(snapshot.metrics),
    decision: {id: text(decision.id), source: text(decision.source), decision: text(decision.decision ?? decision.action),
      reason: text(decision.reason), routeMode: text(decision.routeMode), model: text(decision.model),
      latencyMs: number(decision.latencyMs), inputMode: text(decision.inputMode),
      inputImageSha256: text(decision.inputImageSha256), inputCamera: text(decision.inputCamera),
      inputImageTime: number(decision.inputImageTime), inputImageWidth: number(decision.inputImageWidth),
      inputImageHeight: number(decision.inputImageHeight), interactionId: text(decision.interactionId),perception:provenance(decision.perception),planning:provenance(decision.planning),optimizer:bounded(decision.planning?.optimizer)},
  };
}

export class TelemetryRecorder {
  constructor({maxFrames = 3000, sampleHz = 5} = {}) {
    if (!Number.isInteger(maxFrames) || maxFrames < 1 || maxFrames > 3000) throw new Error('maxFrames must be 1–3000');
    if (!Number.isFinite(sampleHz) || sampleHz <= 0 || sampleHz > 5) throw new Error('sampleHz must be >0 and ≤5');
    this.maxFrames = maxFrames;
    this.sampleHz = sampleHz;
    this.resets = 0;
    this.clear();
  }
  clear() {
    this.frames = [];
    this.lastObservedTime = null;
    this.lastSampleTime = null;
    this.droppedFrames = 0;
  }
  sample(snapshot) {
    if (!snapshot || number(snapshot.time) === null || snapshot.time < 0) throw new Error('Snapshot needs finite nonnegative simulation time');
    if (this.lastObservedTime !== null && snapshot.time < this.lastObservedTime - 1e-9) { this.clear(); this.resets++; }
    this.lastObservedTime = snapshot.time;
    if (this.lastSampleTime !== null && snapshot.time - this.lastSampleTime < 1 / this.sampleHz - 1e-9) return false;
    this.frames.push(frame(snapshot));
    this.lastSampleTime = snapshot.time;
    if (this.frames.length > this.maxFrames) { this.frames.shift(); this.droppedFrames++; }
    return true;
  }
  exportJSONL() { return this.frames.map(item => JSON.stringify(item)).join('\n') + (this.frames.length ? '\n' : ''); }
  summary() {
    return {schema: 'reef-rescue-telemetry/v1', frames: this.frames.length, maxFrames: this.maxFrames,
      sampleHz: this.sampleHz, startTime: this.frames[0]?.time ?? null, endTime: this.frames.at(-1)?.time ?? null,
      durationSeconds: this.frames.length ? this.frames.at(-1).time - this.frames[0].time : 0,
      droppedFrames: this.droppedFrames, resets: this.resets, source: 'browser_simulation', network: false,transport:'Local bounded recorder; configured model API round trips are separate',containsExternalInference:this.frames.some(f=>f.intelligence.onboardPerception.externalInferenceReceived),hardwareValidated:false};
  }
}
