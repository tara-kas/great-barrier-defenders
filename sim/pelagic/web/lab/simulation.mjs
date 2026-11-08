import {reefRegions,reefRegionAt} from './habitat-regions.mjs';
import {generateHabitat,generateHabitatRocks} from './habitat.mjs';
import {terrainHeight,coralHeight,coralContactPoint} from './terrain.mjs';
/** PELAGIC browser experiment. Z-up metres, seconds, newtons.
 * Reduced translation/drag model; not a replacement for Isaac contact dynamics.
 * No tissue recovery, cutting-force, glue chemistry or genotype inference model.
 */
const clone = value => JSON.parse(JSON.stringify(value));
const norm = a => Math.hypot(...a);
const sub = (a,b) => a.map((v,i)=>v-b[i]);
const add = (a,b) => a.map((v,i)=>v+b[i]);
const scale = (a,s) => a.map(v=>v*s);
const clamp = (v,a,b) => Math.max(a,Math.min(b,v));
const finite = (value,min,max,name) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw new Error(`${name} must be between ${min} and ${max}`);
  return value;
};
const vector = (value,name) => {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`${name} must be a three-dimensional position`);
  return value.map((v,i)=>finite(v,i===2?0:-12,i===2?5:12,name));
};
const rng = seed => {let a=seed>>>0;return ()=>{a+=0x6d2b79f5;let t=Math.imul(a^a>>>15,1|a);t^=t+Math.imul(t^t>>>7,61|t);return ((t^t>>>14)>>>0)/4294967296;};};
const HEALTH = ['healthy','bleached_alive','dead'];
const FAULTS = ['drop','bad_cut','bad_placement','current_surge','sensor_dropout'];
const DURATIONS = {survey:3,inspect_recipient:1.6,inspect_donor:1.6,approach:0.5,grasp:1,cut:1.2,retract:1,transport:0.3,align:1.5,secure:2,release:0.7,verify:2,recover_drop:0.6,regrasp:1};
function colony(input,index=0) {
  if (!input || typeof input !== 'object') throw new Error('Invalid colony');
  const c = {...input};
  if (typeof c.id !== 'string' || !/^[a-zA-Z0-9_-]{1,60}$/.test(c.id)) throw new Error('Colony ID must contain 1–60 letters, digits, hyphens or underscores');
  c.position=vector(c.position,'Colony position');c.position[2]=Math.max(c.position[2],terrainHeight(...c.position));
  if(!HEALTH.includes(c.health)) throw new Error('Unknown coral health');
  c.genet = typeof c.genet==='string' && c.genet.length<=60 ? c.genet : '';
  c.species=typeof c.species==='string' && c.species.length<=80 ? c.species : 'Pocillopora damicornis';
  c.radius=finite(c.radius??0.42,0.1,1.2,'Colony radius');
  c.height=finite(c.height??0.65,0.15,1.8,'Colony height');
  c.morphology=['branching','plate','boulder','fan'].includes(c.morphology)?c.morphology:'branching';
  return {id:c.id,position:c.position,health:c.health,genet:c.genet,species:c.species,radius:c.radius,height:c.height,morphology:c.morphology};
}
function obstacle(input) {
  if (!input || typeof input.id!=='string' || !/^[a-zA-Z0-9_-]{1,60}$/.test(input.id)) throw new Error('Invalid obstacle ID');
  const position=vector(input.position,'Obstacle position');position[2]=Math.max(position[2],terrainHeight(...position));
  return {id:input.id,position,radius:finite(input.radius??0.5,0.1,2,'Obstacle radius')};
}
export function defaultScene(seed=42) {
  const rand=rng(seed),colonies=[],regions=reefRegions(seed),healthy=regions.filter(r=>r.kind==='healthy'),bleached=regions.filter(r=>r.kind==='bleached_alive');
  const sample=(region,inner=.45,minGap=1.05)=>{
    for(let attempt=0;attempt<500;attempt++){
      const extent=inner+(attempt>=80?.18:0)+(attempt>=180?.17:0);
      const angle=rand()*Math.PI*2,radius=region.radius*extent*Math.sqrt(rand()),p=[region.center[0]+Math.cos(angle)*radius,region.center[1]+Math.sin(angle)*radius,0];
      if(Math.abs(p[0])>10||Math.abs(p[1])>10)continue;
      if(inner<.5&&reefRegionAt(p[0],p[1],seed).kind!==region.kind)continue;
      if(colonies.every(c=>Math.hypot(c.position[0]-p[0],c.position[1]-p[1])>(c.genet?Math.max(minGap,1.45):minGap)))return p;
    }
    throw new Error('Unable to sample a non-overlapping reef layout for this seed');
  };
  for(let i=0;i<4;i++) {
    const donorRegion=healthy[i%healthy.length],targetRegion=bleached[(i+1)%bleached.length];
    colonies.push(colony({id:`donor-${i+1}`,position:sample(donorRegion),health:'healthy',genet:`G${i+1}`,radius:.43+rand()*.1,height:.68+rand()*.15}));
    colonies.push(colony({id:`recipient-${i+1}`,position:sample(targetRegion),health:'bleached_alive',genet:`G${i+1}`,radius:.43+rand()*.1,height:.65+rand()*.15}));
  }
  for(let i=0;i<76;i++) {
    const region=regions[Math.floor(rand()*regions.length)],p=sample(region,1.2,.52),mix=reefRegionAt(p[0],p[1],seed).healthMix,value=rand();
    const health=value<mix.healthy?'healthy':value<mix.healthy+mix.bleached_alive?'bleached_alive':'dead';
    colonies.push(colony({id:`reef-${i+1}`,position:p,health,genet:'',radius:.23+rand()*.25,height:.32+rand()*.55,morphology:i%4===0?'plate':i%5===0?'boulder':'branching'}));
  }
  const obstacles=[{id:'rock-1',position:[-1,.3,0],radius:.45},{id:'rock-2',position:[2.1,.7,0],radius:.55}];
  return {version:1,seed,water:{current:.08,visibility:8},missionGoal:4,colonies,obstacles};
}
function validateScene(input) {
  if (!input || typeof input!=='object' || Array.isArray(input)) throw new Error('Scene must be an object');
  const seed=finite(input.seed??42,0,4294967295,'Seed');
  if(!Number.isInteger(seed)) throw new Error('Seed must be an integer');
  if(input.version!==undefined && input.version!==1) throw new Error('Unsupported scene version');
  if(!Array.isArray(input.colonies) || input.colonies.length>100 || !Array.isArray(input.obstacles??[]) || (input.obstacles??[]).length>40) throw new Error('Scene supports up to 100 colonies and 40 obstacles');
  const colonies=input.colonies.map(colony),obstacles=(input.obstacles??[]).map(obstacle);
  const restorationMode=input.restorationMode??'donor_cut';if(!['donor_cut','loose_fragment'].includes(restorationMode))throw new Error('Unknown restoration mode');
  const routeMode=input.routeMode??'direct';if(!['direct','clearance'].includes(routeMode))throw new Error('Unknown route mode');
  if(new Set([...colonies,...obstacles].map(c=>c.id)).size!==colonies.length+obstacles.length) throw new Error('Scene IDs must be unique');
  const missionGoal=finite(input.missionGoal??4,1,20,'Mission goal');
  if(!Number.isInteger(missionGoal)) throw new Error('Mission goal must be an integer');
  return {version:1,seed,missionGoal,routeMode,restorationMode,water:{current:finite(input.water?.current??.08,0,.8,'Current'),visibility:finite(input.water?.visibility??8,.2,20,'Visibility')},colonies,obstacles};
}
export class ReefLab {
  constructor(config={}) {
    this.scene=validateScene(config.colonies?config:{...defaultScene(config.seed??42),...config,water:{...defaultScene().water,...config.water}});
    this.controller=['gemini','base_station'].includes(config.controller)?config.controller:'scripted';this.requireFullStack=config.requireFullStack!==false;
    this.reset();
  }
  reset() {
    this.random=rng(this.scene.seed);this.time=0;this.accumulator=0;this.running=false;this.completed=false;this.phase='idle';this.phaseTime=0;this.phaseElapsed=0;this.status='Ready to begin';this.nominalStatus=this.status;this.lastCollision=-10;this.holdTarget=null;this.environmentHoldPosition=null;this.water=clone(this.scene.water);this.colonies=clone(this.scene.colonies);this.obstacles=clone(this.scene.obstacles);this.events=[];this.pendingDecision=null;this.decision=null;this.decisionCounter=this.decisionCounter??0;this.faults=[];this.surgeUntil=0;this.surgeStarted=null;this.dropoutUntil=0;this.environmentHold=0;this.assistanceHold=null;this.restoreCurrent=null;this.donorId=null;this.targetId=null;this.fragmentId=null;this.assisted=new Set();this.retries=0;
    this.metrics={placed:0,attempts:0,drops:0,recoveries:0,rejectedCuts:0,placementRetries:0,distance:0,energy:0,damage:0,collisions:0,decisionCount:0,wildlifeAvoidances:0,habitatAvoidances:0};
    this.perceptionReviewRetries=0;this.fragmentCaptureId=null;this.uncertainInspectionPhase=null;this.perceptionRequest=null;this.perceptionRequestCounter=this.perceptionRequestCounter??0;this.rescanContext=null;this.resumeAfterPerception=null;this.regions=reefRegions(this.scene.seed);this.intelligence={architecture:'Gemma perception → inspectable local policy / cuOpt route proposal → local safety controller; Argon provides bounded uncertainty assistance and between-mission review',hardwareValidated:false,requireFullStack:this.requireFullStack,perceptionMaxAgeSeconds:120,planMaxAgeSeconds:45,onboard:{status:'not_received',reason:'No external Gemma inference has been received.',observations:[],lastPacket:null},baseStation:{status:'not_received',reason:'No external base-station plan has been received.',plan:null,localValidation:null}};this.externalRequestIds=new Set();this.uvObservations=[];this.perceptionReason='Awaiting range-gated UV inspection; lineage is registry data.';this.grip={source:'Reduced hydrodynamic load proxy',loadN:0,dragN:0,inertialN:0,thresholdN:5,areaM2:.002,fragmentMassKg:.018,lastLoss:null};this.sonarCache=null;this.sonarCacheKey=null;this.pilot={mode:'autonomous',command:{forward:0,right:0,vertical:0,yaw:0},lastInputTime:null,watchdogSeconds:2,expired:false};this.forces={thrust:[0,0,0],drag:[0,0,0],buoyancy:[0,0,.15],net:[0,0,0]};
    this.robot={position:[-4,-4,Math.max(2,terrainHeight(-4,-4)+.9)],velocity:[0,0,0],target:[-4,-4,2],gripper:[-4,-4,1.35],yaw:0,holding:null,gripperOpen:1};
    this.habitat=[...generateHabitat(this.colonies,this.scene.seed),...generateHabitatRocks(this.colonies,this.scene.seed)];this.habitatIndex=new Map();for(const c of this.habitat){const key=`${Math.floor(c.position[0]/4)},${Math.floor(c.position[1]/4)}`;if(!this.habitatIndex.has(key))this.habitatIndex.set(key,[]);this.habitatIndex.get(key).push(c);}
    this.route={mode:this.scene.routeMode,goal:clone(this.robot.target),waypoints:[clone(this.robot.target)],index:0,alternatives:[]};this.wildlifeYield=false;this.wildlife=[];this._updateWildlife(0);this.robot.target=clone(this.robot.position);this.robot.gripper=add(this.robot.position,[0,0,-.65]);this.fragments=[];
    for(const c of this.colonies.filter(c=>c.health==='healthy'&&c.genet)) for(let i=0;i<2;i++){
      const loose=this.scene.restorationMode==='loose_fragment',position=loose?this._looseStockPosition(c,i):add(this._top(c),[.05*(i?1:-1),0,0]);
      if(!position){this._event('warning',`No collision-clear pickup for ${c.id}-fragment-${i+1}; this stock fragment was excluded.`);continue;}
      this.fragments.push({id:`${c.id}-fragment-${i+1}`,donorId:c.id,position,velocity:[0,0,0],state:loose?'available':'attached',quality:1,targetId:null,...(loose?{source:'scenario_permitted_loose_stock',sourcePosition:clone(position),detachedAtStart:true}: {})});
    }
    this._event('info','Scene ready. Known lineage gates donor–recipient compatibility.');
    return this.snapshot();
  }
  _event(type,message) {this.events.push({time:this.time,type,message});if(this.events.length>180)this.events.shift();}
  _setPhase(phase,status) {
    this.phase=phase;this.phaseTime=0;this.phaseElapsed=0;this.status=status??phase.replaceAll('_',' ');this.nominalStatus=this.status;
    const targetId=phase==='inspect_recipient'?this.targetId:phase==='inspect_donor'?this.donorId:phase==='inspect_fragment'?this.fragmentId:null;
    if(targetId){const fragment=phase==='inspect_fragment',c=this.colonies.find(c=>c.id===targetId);this.perceptionRequest={id:`capture-${++this.perceptionRequestCounter}`,targetId,targetKind:fragment?'fragment':'colony',targetPosition:clone(fragment?this._fragment().position:this._top(c)),frameTimeMin:this.time,ready:false,readyAt:null,exposureSeconds:0,expectedHealth:fragment?null:c.health,reason:this.status};if(fragment)this.fragmentCaptureId=this.perceptionRequest.id;const previous=this.uvObservations.find(o=>o.id===targetId);if(previous)previous.exposureSeconds=0;}
    else this.perceptionRequest=null;
  }
  _requestRescan(reason='Perception evidence expired; acquiring a new camera frame.',kind=null) {
    if(this.pilot.mode==='manual')throw new Error('Return to autonomous pilot before requesting a rescan');
    if(!this.targetId||!this.donorId||!this.fragmentId)throw new Error('There is no active mission pair to rescan');
    const initialStockView=this.scene.restorationMode==='loose_fragment'&&this.phase==='inspect_fragment'&&this._fragment()?.state==='available';
    const requestedKind=kind??this.pendingDecision?.kind??this.rescanContext?.kind??(['inspect_recipient','inspect_donor','approval'].includes(this.phase)||initialStockView?'inspect':'resume');const gateKind=requestedKind==='uncertain'?'inspect':requestedKind;
    if(gateKind==='resume'&&!this.resumeAfterPerception)this.resumeAfterPerception={phase:this.phase,phaseTime:this.phaseTime,phaseElapsed:this.phaseElapsed,goal:clone(this.route.goal)};else if(gateKind!=='resume')this.resumeAfterPerception=null;
    this.pendingDecision=null;this.intelligence.baseStation={status:'waiting_for_rescan',reason,plan:null,localValidation:null};
    this.rescanContext={kind:gateKind,message:reason,queue:gateKind==='inspect'?(this.scene.restorationMode==='loose_fragment'?['inspect_recipient','inspect_fragment']:['inspect_recipient','inspect_donor']):['inspect_fragment']};
    this._event('perception',reason);this._advanceRescan();
  }
  _advanceRescan() {
    const context=this.rescanContext;if(!context)return;
    const phase=context.queue.shift();if(phase){const point=phase==='inspect_fragment'?this._fragment().position:this._top(phase==='inspect_recipient'?this._recipient():this._donor());if(phase==='inspect_fragment'&&this.robot.holding)this._planRoute(this.robot.position);else this._setGripTarget(point,1);this._setPhase(phase,'Acquiring fresh '+(phase==='inspect_fragment'?'fragment view':phase==='inspect_recipient'?'recipient view':'donor view'));return;}
    this.rescanContext=null;this._setPhase('approval','Fresh perception received; awaiting a new base-station plan');this._gate(context.kind,context.message,true);
  }
  _fragmentEvidenceReady() {
    const p=this.intelligence.onboard.lastPacket;
    const appearance=this.scene.restorationMode!=='loose_fragment'||(p?.visualContract==='appearance/v1'&&p.targetVisible===true&&p.objectKind==='coral_fragment'&&p.appearance==='pigmented'&&p.viabilityKnown===false&&p.confidence>=.7);
    return appearance&&!!p&&!!this.fragmentCaptureId&&p.captureRequestId===this.fragmentCaptureId&&p.targetKind==='fragment'&&p.targetId===this.fragmentId&&p.fragmentVisible===true&&p.gripperState===(this.robot.holding?'holding':'empty')&&this.time-p.frameTime<=this.intelligence.perceptionMaxAgeSeconds;
  }
  // Detached stock does not manipulate its source colony; source eligibility
  // remains a registry gate, while recipient and fragment need actual images.
  _inspectionColonyIds(){return this.scene.restorationMode==='loose_fragment'?[this.targetId]:[this.donorId,this.targetId];}
  _inspectionEvidenceReady(){return this._inspectionColonyIds().every(id=>this._externalHealth(id,id===this.targetId?'bleached_alive':'healthy').ready);}
  _abort(reason) {this.assistanceHold=null;this.running=false;this.pendingDecision=null;this._setPhase('aborted',reason);this._event('error',reason);}
  _stockAvailable(f){return f.state===(this.scene.restorationMode==='loose_fragment'?'available':'attached');}
  _looseStockPosition(source,index){
    // Stable, already detached scenario stock. Reject crowded pickup sites instead
    // of teleporting a fragment or cutting the source colony to manufacture stock.
    for(let ring=0;ring<14;ring++)for(let step=0;step<32;step++){
      const angle=step*Math.PI/16+index*.27,range=source.radius+.32+ring*.09;
      const p=[source.position[0]+Math.cos(angle)*range,source.position[1]+Math.sin(angle)*range,0];
      if(Math.max(Math.abs(p[0]),Math.abs(p[1]))>11.5)continue;p[2]=terrainHeight(...p)+.07;
      if(this.fragments.some(f=>norm(sub(f.position,p))<.28))continue;
      const body=add(p,[0,0,.65]);
      const clear=this.obstacles.every(o=>norm(sub(body,add(o.position,[0,0,o.radius*.5])))>o.radius+.96)&&
        this.colonies.every(c=>{const h=coralHeight(c);if(body[2]-.3>c.position[2]+h+.15)return true;return norm(sub(body,add(c.position,[0,0,h*.45])))>Math.max(c.radius*.72,h*.45)+.3+(c.id===source.id?.04:.68);})&&
        this.habitat.every(c=>{if(Math.abs(c.position[0]-p[0])>3||Math.abs(c.position[1]-p[1])>3||body[2]-.3>c.position[2]+c.height+.15)return true;return norm(sub(body,add(c.position,[0,0,c.height*.45])))>Math.max(c.radius*.72,c.height*.45)+.49;});
      if(clear)return p;
    }
    return null;
  }
  _top(c) {return coralContactPoint(c);}
  _setGripTarget(p,offset=.65) {
    const goal=add(p,[0,0,offset]);
    if(this.route&&norm(sub(goal,this.route.goal))<.08){this.route.goal=goal;this.route.waypoints[this.route.waypoints.length-1]=goal;return;}
    this._planRoute(goal);
  }
  _planRoute(goal) {
    const start=clone(this.robot.position),horizontal=Math.hypot(goal[0]-start[0],goal[1]-start[1]);
    const direct=[start,goal];
    const cruise=Math.max(start[2],goal[2],...[...this.colonies,...this.habitat].filter(c=>Math.abs(c.position[0]-goal[0])<2).map(c=>c.position[2]+(c.species==='habitat'?c.height:coralHeight(c))+.85));
    if(horizontal>1.5)direct.splice(1,0,[start[0],start[1],cruise],[goal[0],goal[1],cruise]);
    const side=goal[0]<0?-7:7;
    const clear=horizontal>1.5?[start,[start[0],start[1],cruise+.35],[side,start[1],cruise+.35],[side,goal[1],cruise+.35],[goal[0],goal[1],cruise+.35],goal]:[start,goal];
    const mode=this.route?.mode??this.scene.routeMode;
    this.route={mode,goal:clone(goal),waypoints:clone((mode==='clearance'?clear:direct).slice(1)),index:0,alternatives:[{id:'direct',label:'Direct over-reef transit',points:direct},{id:'clearance',label:'Wide corridor · elevated clearance',points:clear}]};
    this.robot.target=clone(this.route.waypoints[0]);
  }
  _advanceRoute() {
    if(this.route.index<this.route.waypoints.length-1&&norm(sub(this.robot.position,this.robot.target))<.28){this.route.index++;this.robot.target=clone(this.route.waypoints[this.route.index]);}
    else if(this.route.index===this.route.waypoints.length-1)this.robot.target=clone(this.route.goal);
  }
  _currentAt(position) {
    const [x,y,z]=position,phase=(this.scene.seed%97)*.071;
    const speed=this.water.current*(.94+.12*Math.sin(this.time*.23+x*.31+y*.17+phase)+.05*Math.sin(z*.8+this.time*.41));
    const angle=.18*Math.sin(this.time*.045+phase)+.08*Math.sin(y*.3+this.time*.12);
    const age=this.surgeStarted===null?-1:this.time-this.surgeStarted;
    // Operator-injected four-second cross-current wave, peak3.2m/s; engineering stress proxy.
    const wave=age>=0&&age<=4?3.2*Math.exp(-(((age-1.2)/.4)**2)):0;
    return [speed*Math.cos(angle),speed*Math.sin(angle)-wave,this.water.current*.035*Math.sin(x*.4+y*.3+this.time*.16)];
  }
  _currentSamples() {
    const samples=[];for(let x=-8;x<=8;x+=4)for(let y=-8;y<=8;y+=4){const position=[x,y,terrainHeight(x,y)+1.2];samples.push({position,vector:this._currentAt(position)});}return samples;
  }
  _externalHealth(id,expectedHealth) {
    const result=this.intelligence.onboard.observations.find(o=>o.id===id);
    if(!result)return {ready:false,reason:`Awaiting external Gemma observation for ${id}.`};
    if(this.time-result.frameTime>this.intelligence.perceptionMaxAgeSeconds)return {ready:false,reason:`Gemma observation for ${id} is stale; a fresh frame is required.`};
    if(result.visualContract==='appearance/v1'){
      const colony=this.colonies.find(c=>c.id===id),expected={healthy:'pigmented',bleached_alive:'pale_or_bleached'}[expectedHealth];
      const ready=colony?.health===expectedHealth&&!!expected&&result.targetVisible===true&&result.objectKind==='coral_colony'&&result.appearance===expected&&result.confidence>=.7&&result.viabilityKnown===false;
      return {ready,reason:ready?'Fresh visual appearance matches the independent scenario registry; RGB does not establish viability or lineage.':`Gemma ${id}: visual evidence does not meet the target/appearance/0.70 gate; registry alone cannot approve handling.`};
    }
    if(this.scene.restorationMode==='loose_fragment')return {ready:false,reason:'Loose-stock handling requires the explicit appearance contract; legacy health labels cannot replace current visual evidence.'};
    if(result.health!==expectedHealth||result.confidence<.7)return {ready:false,reason:`Gemma ${id}: ${result.health}, confidence ${result.confidence.toFixed(2)}; conservative inspection gate requires ${expectedHealth} at ≥0.70.`};
    return {ready:true,reason:'Fresh external health estimate passed the engineering gate; registry lineage remains independent.'};
  }
  _ingestPerception(packet) {
    if(!packet||typeof packet!=='object'||packet.source!=='gemma')throw new Error('Perception packet must identify source gemma');
    const requestId=packet.requestId??packet.id;if(typeof requestId!=='string'||!requestId||requestId.length>160)throw new Error('Perception needs a bounded requestId');
    if(this.externalRequestIds.has(`perception:${requestId}`))throw new Error('Perception request was already ingested');
    const frameTime=finite(packet.frameTime,0,this.time+.1,'Perception frame time');
    if(this.time-frameTime>this.intelligence.perceptionMaxAgeSeconds)throw new Error('Perception frame is stale');
    for(const field of ['model','provider'])if(typeof packet[field]!=='string'||!packet[field]||packet[field].length>160)throw new Error(`Perception ${field} provenance is required`);
    const capture=this.perceptionRequest;if(!capture||packet.captureRequestId!==capture.id||packet.targetId!==capture.targetId||packet.targetKind!==capture.targetKind)throw new Error('Perception result does not match the current camera capture target');
    if(!capture.ready||capture.readyAt===null||frameTime<capture.readyAt-1e-6)throw new Error('Perception frame predates a valid in-range camera capture');
    const isFragment=capture.targetKind==='fragment';if(isFragment&&(typeof packet.fragmentVisible!=='boolean'||!['empty','holding','unknown'].includes(packet.gripperState)))throw new Error('Fragment perception needs explicit visibility and gripper state');
    if(!Array.isArray(packet.observations)||packet.observations.length>8||(!isFragment&&!packet.observations.length))throw new Error('Colony perception needs one to eight observations; fragment views may omit health estimates');
    const seen=new Set();const observations=packet.observations.map(o=>{
      if(!o||!this.colonies.some(c=>c.id===o.id)||o.id!==capture.targetId)throw new Error('Perception ID must refer to the active registered pair');
      if(seen.has(o.id))throw new Error('Duplicate perception observation');seen.add(o.id);
      if(!['healthy','bleached_alive','dead','unknown'].includes(o.health))throw new Error('Unknown external health estimate');
      const confidence=finite(o.confidence,0,1,'Perception confidence');
      const previous=this.intelligence.onboard.observations.find(old=>old.id===o.id);if(previous&&frameTime<previous.frameTime)throw new Error('Out-of-order perception frame');
      const visual={};
      if(packet.visualContract==='appearance/v1'){
        if(typeof o.targetVisible!=='boolean'||!['coral_colony','coral_fragment','other','unknown'].includes(o.objectKind)||!['pigmented','pale_or_bleached','bare_skeleton_or_algae','unknown'].includes(o.appearance)||o.viabilityKnown!==false)throw new Error('Invalid visual appearance observation');
        Object.assign(visual,{visualContract:packet.visualContract,targetVisible:o.targetVisible,objectKind:o.objectKind,appearance:o.appearance,viabilityKnown:false});
      }
      return {...visual,id:o.id,health:o.health,confidence,frameTime,receivedTime:this.time,requestId,source:'gemma',model:packet.model,provider:packet.provider,genotypeInferred:false,confidenceCalibration:'Uncalibrated provider score; 0.70 is an engineering demo gate'};
    });
    const visualPacket={};
    if(packet.visualContract==='appearance/v1'){
      if(typeof packet.targetVisible!=='boolean'||!['coral_colony','coral_fragment','other','unknown'].includes(packet.objectKind)||!['pigmented','pale_or_bleached','bare_skeleton_or_algae','unknown'].includes(packet.appearance)||packet.viabilityKnown!==false)throw new Error('Invalid visual packet');
      Object.assign(visualPacket,{visualContract:'appearance/v1',targetVisible:packet.targetVisible,objectKind:packet.objectKind,appearance:packet.appearance,confidence:finite(packet.confidence,0,1,'Visual confidence'),viabilityKnown:false,uncertainty:typeof packet.uncertainty==='string'?packet.uncertainty.slice(0,600):''});
    }
    this.externalRequestIds.add(`perception:${requestId}`);
    const old=this.intelligence.onboard.observations.filter(o=>!seen.has(o.id));
    this.intelligence.onboard={status:'received',reason:'External model estimates stored separately from scenario registry ground truth.',observations:[...old,...observations].slice(-24),lastPacket:{...visualPacket,requestId,captureRequestId:capture.id,targetId:capture.targetId,targetKind:capture.targetKind,fragmentVisible:isFragment?packet.fragmentVisible:null,gripperState:isFragment?packet.gripperState:null,frameTime,receivedTime:this.time,source:'gemma',provider:packet.provider,model:packet.model,deployment:typeof packet.deployment==='string'?packet.deployment.slice(0,160):'unspecified',summary:typeof packet.summary==='string'?packet.summary.slice(0,600):'',inputImageFocus:packet.inputImageFocus?.source==='tracked_camera_projection'?{source:'tracked_camera_projection',...Object.fromEntries(['target','gripper'].filter(k=>Array.isArray(packet.inputImageFocus[k])&&packet.inputImageFocus[k].length===2&&packet.inputImageFocus[k].every(v=>Number.isFinite(v)&&v>=0&&v<=1)).map(k=>[k,[...packet.inputImageFocus[k]]]))}:null,inputImageSha256:typeof packet.inputImageSha256==='string'?packet.inputImageSha256.slice(0,128):null,latencyMs:typeof packet.latencyMs==='number'&&Number.isFinite(packet.latencyMs)?packet.latencyMs:null}};
    this._event('perception',`Received external Gemma ${isFragment?'fragment/gripper view of '+capture.targetId:'health estimates for '+observations.map(o=>o.id).join(', ')}; no registry fields changed.`);
  }
  _routeClearance(mode) {
    const option=this.route.alternatives.find(r=>r.id===mode);if(!option)return {safe:false,reason:'Route is not a declared local alternative'};
    let minBedClearance=Infinity,needsLocalReplan=false;
    for(let i=1;i<option.points.length;i++){
      const a=option.points[i-1],b=option.points[i],steps=Math.max(1,Math.ceil(norm(sub(b,a))/.3));
      for(let j=0;j<=steps;j++){const p=a.map((v,k)=>v+(b[k]-v)*j/steps);if(Math.abs(p[0])>12||Math.abs(p[1])>12||p[2]>8)return {safe:false,reason:'Route leaves the local workspace'};const gap=p[2]-terrainHeight(...p);minBedClearance=Math.min(minBedClearance,gap);if(gap<.7-.001)needsLocalReplan=true;}
    }
    return {safe:true,needsLocalReplan,minBedClearance,reason:'Bounded route accepted; local terrain, habitat and wildlife reflexes remain authoritative.',guard:'Local closed-loop thrust and nonpenetration controller; external coordinates are never executed'};
  }
  _ingestPlan(packet) {
    if(!packet||typeof packet!=='object'||!['argon','local_planner'].includes(packet.source))throw new Error('Plan packet must identify source local_planner or legacy argon');
    if(packet.waypoints!==undefined||packet.path!==undefined)throw new Error('Only declared local route alternatives may be proposed; external coordinates are not executable');
    const requestId=packet.requestId??packet.id;
    if(!this.pendingDecision||requestId!==this.pendingDecision.id)throw new Error('Plan does not match the pending local decision');
    if(this.externalRequestIds.has(`plan:${requestId}`))throw new Error('Plan request was already ingested');
    const frameTime=finite(packet.frameTime,0,this.time+.1,'Plan frame time');if(this.time-frameTime>this.intelligence.planMaxAgeSeconds)throw new Error('Base-station plan is stale');
    if(!this.pendingDecision.allowedActions.includes(packet.decision))throw new Error('Base-station decision is not locally allowed');
    const routeMode=packet.routeMode??null;if(routeMode!==null&&!['direct','clearance'].includes(routeMode))throw new Error('Unknown base-station route');
    for(const field of ['model','provider'])if(typeof packet[field]!=='string'||!packet[field]||packet[field].length>160)throw new Error(`Plan ${field} provenance is required`);
    const localValidation=routeMode?this._routeClearance(routeMode):{safe:true,needsLocalReplan:false,reason:'No external route override; local route retained.'};
    if(!localValidation.safe)throw new Error(localValidation.reason);
    if(typeof packet.reason!=='string'||packet.reason.length>1600)throw new Error('Plan reason must be bounded text');
    const rawOptimizer=packet.optimizer;
    const optimizerRequired=this.requireFullStack||rawOptimizer?.configured===true||rawOptimizer?.source==='cuopt';
    let optimizer={source:'not_configured',configured:false};
    if(optimizerRequired){
      if(!rawOptimizer||rawOptimizer.source!=='cuopt'||rawOptimizer.configured!==true||rawOptimizer.status!=='solved'||rawOptimizer.solverStatus!=='SUCCESS')throw new Error('Full-stack planning requires a successful configured cuOpt solve');
      if((rawOptimizer.requestId??rawOptimizer.id)!==requestId)throw new Error('cuOpt solve belongs to another planning request');
      if(rawOptimizer.routeMode!==routeMode||!['direct','clearance'].includes(rawOptimizer.routeMode))throw new Error('Planner route must match the actual cuOpt-selected route');
      const objectiveCost=finite(rawOptimizer.objectiveCost,0,1e9,'cuOpt objective cost'),costs={};
      for(const id of ['direct','clearance'])if(rawOptimizer.costs?.[id]!==undefined)costs[id]=finite(rawOptimizer.costs[id],0,1e9,'cuOpt candidate cost');
      if(costs[routeMode]===undefined)throw new Error('cuOpt must report the selected candidate cost');
      optimizer={source:'cuopt',configured:true,status:'solved',solverStatus:'SUCCESS',requestId,routeMode,objectiveCost,costs,model:typeof rawOptimizer.model==='string'?rawOptimizer.model.slice(0,160):'nvidia-cuopt',solverVersion:typeof rawOptimizer.solverVersion==='string'?rawOptimizer.solverVersion.slice(0,80):null,solveTimeMs:typeof rawOptimizer.solveTimeMs==='number'&&Number.isFinite(rawOptimizer.solveTimeMs)?rawOptimizer.solveTimeMs:null};
    }
    this.intelligence.baseStation={status:'received',reason:'External plan passed local bounds; registry and perception gates still apply.',localValidation,plan:{requestId,frameTime,receivedTime:this.time,source:packet.source,provider:packet.provider,model:packet.model,decision:packet.decision,reason:packet.reason,routeMode,optimizer}};
    this.externalRequestIds.add(`plan:${requestId}`);this._event('plan','Planner proposal received; the planner cannot bypass local eligibility or reflexes.');
  }
  _registryTruth() {
    return {source:'scenario_registry_ground_truth',notModelOutput:true,genotypeSource:'Explicit scenario registry; never inferred from fluorescence or image colour',pair:[this._donor(),this._recipient()].filter(Boolean).map(c=>({id:c.id,health:c.health,species:c.species,genet:c.genet}))};
  }
  _recordInspection(dt) {
    const id=this.phase==='inspect_recipient'?this.targetId:this.phase==='inspect_donor'?this.donorId:this.phase==='inspect_fragment'?this.fragmentId:null;
    if(!id)return true;const isFragment=this.phase==='inspect_fragment',c=this.colonies.find(c=>c.id===id),point=isFragment?this._fragment().position:this._top(c),origin=isFragment?this.robot.position:this.robot.gripper,v=sub(point,origin),distance=norm(v);
    const occluded=this.obstacles.some(o=>{const centre=add(o.position,[0,0,o.radius*.5]),w=sub(centre,origin),u=v.reduce((a,x,i)=>a+x*w[i],0)/Math.max(.0001,distance**2);return u>.05&&u<.95&&norm(sub(add(origin,scale(v,u)),centre))<o.radius*.75;});
    const settled=!isFragment||(norm(sub(this.robot.target,this.robot.position))<=.18&&norm(this.robot.velocity)<=.12);
    const valid=settled&&distance<=1.6&&distance<=this.water.visibility&&this.water.visibility>=1.5&&this.time>=this.dropoutUntil&&!occluded&&!this.wildlifeYield;
    if(isFragment){const capture=this.perceptionRequest;capture.targetPosition=clone(point);if(valid)capture.exposureSeconds=Math.min(1.2,capture.exposureSeconds+dt);else capture.exposureSeconds=0;capture.ready=valid&&capture.exposureSeconds>=.96;if(capture.ready&&capture.readyAt===null)capture.readyAt=this.time;this.perceptionReason='Recovery camera acquisition; fragment identity comes from tracked scene association.';const ready=valid&&capture.exposureSeconds>=1.2&&(this.controller!=='base_station'||this._fragmentEvidenceReady());if(!ready)this.status='Waiting for a fresh Gemma view of the fragment and gripper state';return ready;}
    let observation=this.uvObservations.find(o=>o.id===id);
    if(!observation){observation={id,health:c.health,species:c.species,registryGenet:c.genet||null,uvMarker:null,score:0,exposureSeconds:0,source:'synthetic_camera_uv',rangeM:distance};this.uvObservations.push(observation);}
    observation.rangeM=distance;
    if(valid){observation.exposureSeconds=Math.min(1.2,observation.exposureSeconds+dt);observation.score=clamp((1-distance/Math.max(this.water.visibility,1.5))*.95,0,.95);if(observation.exposureSeconds>=1.2)observation.uvMarker=c.health==='dead'?'no_living_marker':`scenario-marker-${c.genet||'unregistered'}`;}
    if(this.perceptionRequest){this.perceptionRequest.targetPosition=clone(point);this.perceptionRequest.exposureSeconds=observation.exposureSeconds;this.perceptionRequest.ready=valid&&observation.exposureSeconds>=.96;if(this.perceptionRequest.ready&&this.perceptionRequest.readyAt===null)this.perceptionRequest.readyAt=this.time;}
    this.perceptionReason=valid?'Accumulating synthetic UV exposure at measured range; genotype remains known registry data.':occluded?'Inspection held: rock occludes the synthetic UV view.':'Inspection held: outside sensing range, low visibility or wildlife exclusion.';
    if(this.controller==='base_station'&&valid&&observation.exposureSeconds>=1.2){const gate=this._externalHealth(id,this.phase==='inspect_donor'?'healthy':'bleached_alive');this.intelligence.onboard.status=gate.ready?'approved':'waiting';this.intelligence.onboard.reason=gate.reason;if(!gate.ready){this.status=gate.reason;return false;}this.status=this.nominalStatus;}
    return valid&&observation.exposureSeconds>=1.2;
  }
  _perception() {
    const targetId=this.perceptionRequest?.targetId??null;
    const active=this.uvObservations.find(o=>o.id===targetId),target=this._recipient();
    return {source:'synthetic_camera_uv',stage:this.phase,targetId,targetKind:this.perceptionRequest?.targetKind??null,targetPosition:this.perceptionRequest?.targetPosition??null,exposure:this.phase==='inspect_fragment'?clamp((this.perceptionRequest?.exposureSeconds??0)/1.2,0,1):active?clamp(active.exposureSeconds/1.2,0,1):0,requiredExposureSeconds:1.2,observations:this.uvObservations.map(o=>({...o,exposure:clamp(o.exposureSeconds/1.2,0,1)})),candidateComparison:target?this.colonies.filter(c=>c.health==='healthy').slice(0,12).map(c=>({donorId:c.id,targetId:target.id,eligible:!!this._compatible(c,target)&&this.fragments.some(f=>f.donorId===c.id&&this._stockAvailable(f)),reason:!c.genet?'Unknown registered lineage':!this._compatible(c,target)?'Registered species or lineage mismatch':!this.fragments.some(f=>f.donorId===c.id&&this._stockAvailable(f))?'No eligible source stock':'Known matching species and lineage; available donor stock'})):[],reason:this.perceptionReason};
  }
  _checkGrip() {
    const f=this._fragment();if(!f||f.state!=='carried'||this.robot.holding!==f.id){this.grip.loadN=0;this.grip.dragN=0;this.grip.inertialN=0;return;}
    const relative=sub(this._currentAt(this.robot.gripper),this.robot.velocity);
    this.grip.dragN=.5*1025*1.15*this.grip.areaM2*norm(relative)**2;
    this.grip.inertialN=this.grip.fragmentMassKg*norm(this.forces.net)/18;
    this.grip.loadN=this.grip.dragN+this.grip.inertialN;
    if(this.grip.loadN>this.grip.thresholdN){this.grip.lastLoss={time:this.time,fragmentId:f.id,loadN:this.grip.loadN,thresholdN:this.grip.thresholdN};this._event('fault',`Hydrodynamic grip load ${this.grip.loadN.toFixed(2)}N exceeded ${this.grip.thresholdN.toFixed(1)}N proxy capacity.`);this._drop();}
  }
  _fusion() {
    const sonar=this._sonar(),opticalAvailable=this.time>=this.dropoutUntil&&this.water.visibility>=1.5;
    const contacts=sonar.contacts.slice(0,32).map(c=>{const registry=this.colonies.find(x=>x.id===c.id);const optical=opticalAvailable&&registry&&c.distance<this.water.visibility;
      return {id:c.id,type:c.type,position:c.position,distance:c.distance,confidence:optical?clamp(.96-c.distance/this.water.visibility*.22,.5,.96):.68,sources:optical?['synthetic_geometric_sonar','synthetic_optical_registry']:['synthetic_geometric_sonar'],classification:optical?{health:registry.health,species:registry.species,knownGenet:registry.genet||null}:null};});
    return {source:'Synthetic geometric sensor fusion; no learned perception or acoustic calibration',time:sonar.time,opticalAvailable,confidence:contacts.length?contacts.reduce((n,c)=>n+c.confidence,0)/contacts.length:0,contacts,controllerSource:this.decision?.source??'none',controllerDecisionId:this.decision?.id??null};
  }
  _updateWildlife(dt) {
    const t=this.time,previous=new Map(this.wildlife.map(a=>[a.id,a.position]));
    const animals=[],seedPhase=(this.scene.seed%47)*.19;
    for(let i=0;i<8;i++){
      const group=Math.floor(i/3),phase=seedPhase+group*2.2,school=i<6;
      const x=(school?3.1:4.2)*Math.sin(t*(school?.12:.087)+phase)+(school?.22*(i%3):.35*Math.sin(t*.21+phase));
      const y=2.45*Math.cos(t*(school?.095:.113)+phase*.7)+.22*Math.sin(t*.31+i);
      const z=terrainHeight(x,y)+1.15+.16*Math.sin(t*.22+phase+i*.3);
      animals.push({id:`fish-${i+1}`,type:'fish',schoolId:school?`school-${group+1}`:null,behavior:school?'coherent seeded school trajectory':'individual seeded wander',position:[x,y,z],radius:.1});
    }
    for(let i=0;i<3;i++) {const p=seedPhase+i*1.8,x=-2.5+i*2+.6*Math.sin(t*.053+p)+.18*Math.sin(t*.137+p),y=.2+.65*Math.cos(t*.041+p)+.2*Math.sin(t*.113+p);animals.push({id:`crab-${i+1}`,type:'crab',behavior:'seeded seabed wander',position:[x,y,terrainHeight(x,y)+.07],radius:.16});}
    const x=4*Math.sin(t*.055-.9+seedPhase*.2),y=.65*Math.sin(t*.071+seedPhase);animals.push({id:'turtle-1',type:'turtle',behavior:'seeded broad transit',position:[x,y,terrainHeight(x,y)+1.65],radius:.42});
    this.wildlife=animals.map(a=>({...a,velocity:dt&&previous.has(a.id)?scale(sub(a.position,previous.get(a.id)),1/dt):[0,0,0]}));
  }
  _nearHabitat(radius) {
    const [x,y]=this.robot.position,result=[];
    for(let gx=Math.floor((x-radius)/4);gx<=Math.floor((x+radius)/4);gx++)for(let gy=Math.floor((y-radius)/4);gy<=Math.floor((y+radius)/4);gy++)for(const c of this.habitatIndex.get(`${gx},${gy}`)??[])if(Math.hypot(c.position[0]-x,c.position[1]-y)<=radius)result.push(c);
    return result;
  }
  _sonar() {
    const range=6,origin=this.robot.position,key=Math.floor(this.time*5+1e-6);
    if(this.sonarCache&&this.sonarCacheKey===key&&(this.time!==this.sonarCache.time||norm(sub(origin,this.sonarCacheOrigin))<1e-8))return clone(this.sonarCache);
    const sources=[...this.obstacles.map(o=>({...o,type:'rock',position:add(o.position,[0,0,o.radius*.5])})),...this.colonies.map(c=>({...c,type:'coral',position:add(c.position,[0,0,coralHeight(c)*.5])})),...this._nearHabitat(range).map(c=>({...c,type:'habitat',position:add(c.position,[0,0,c.height*.5])})),...this.wildlife];
    const contacts=sources.map(o=>{const delta=sub(o.position,origin),distance=norm(delta);return {...o,distance,bearing:Math.atan2(Math.sin(Math.atan2(delta[1],delta[0])-this.robot.yaw),Math.cos(Math.atan2(delta[1],delta[0])-this.robot.yaw))};}).filter(o=>o.distance<=range).filter(o=>!this.obstacles.some(rock=>{
      if(rock.id===o.id)return false;const centre=add(rock.position,[0,0,rock.radius*.5]),v=sub(o.position,origin),w=sub(centre,origin),u=v.reduce((a,x,i)=>a+x*w[i],0)/Math.max(.0001,o.distance**2);return u>.03&&u<.95&&norm(sub(add(origin,scale(v,u)),centre))<rock.radius*.75;
    })).sort((a,b)=>a.distance-b.distance).map(({id,type,distance,bearing,position})=>({id,type,distance,bearing,position}));
    this.sonarCacheKey=key;this.sonarCacheOrigin=clone(origin);this.sonarCache={time:this.time,sampleRateHz:5,range,contacts:contacts.slice(0,64),totalContacts:contacts.length,omittedContacts:Math.max(0,contacts.length-64),closestRange:contacts[0]?.distance??null,model:'Synthetic analytic line-of-sight ranges; rock occlusion only, not acoustic propagation',visibilityLimited:false,maxContacts:64};return clone(this.sonarCache);
  }
  _fragment(){return this.fragments.find(f=>f.id===this.fragmentId);}
  _donor(){return this.colonies.find(c=>c.id===this.donorId);}
  _recipient(){return this.colonies.find(c=>c.id===this.targetId);}
  _compatible(d,t){return d?.health==='healthy'&&t?.health==='bleached_alive'&&d.genet&&d.genet===t.genet&&d.species===t.species;}
  _choosePair() {
    for(const t of this.colonies) {
      if(t.health!=='bleached_alive'||!t.genet||this.assisted.has(t.id))continue;
      for(const d of this.colonies) {
        const f=this.fragments.find(f=>f.donorId===d.id&&this._stockAvailable(f));
        if(!this._compatible(d,t)||!f)continue;
        this.targetId=t.id;this.donorId=d.id;this.fragmentId=f.id;this.retries=0;this.metrics.attempts++;
        this._setGripTarget(this._top(t),1);this._setPhase('inspect_recipient','Inspecting living recipient');this._event('plan',`Pair ${d.id} → ${t.id}; same registered genet ${d.genet}.`);return;
      }
    }
    this._abort(`No eligible pair remains (${this.metrics.placed}/${this.scene.missionGoal} verified). Unknown lineage and dead coral are excluded.`);
  }
  _gate(kind,message,perceptionReady=false) {
    if(this.controller==='base_station'&&kind!=='inspect'&&!perceptionReady){this._requestRescan(message,kind);return;}
    if(kind==='cut')this._planRoute(add(this._top(this._donor()),[0,0,.65]));else if(kind==='resume'&&this.resumeAfterPerception)this._planRoute(this.resumeAfterPerception.goal);else this._planRoute(add(this._top(this._recipient()),[0,0,1.3]));
    const allowedActions=kind==='inspect'?['proceed','abort']:kind==='uncertain'&&this.perceptionReviewRetries>=3?['abort']:['retry','abort'];
    const request={id:`decision-${++this.decisionCounter}`,kind,allowedActions,observation:{time:this.time,phase:this.phase,decisionKind:kind,robot:{holding:this.robot.holding},restorationMode:this.scene.restorationMode,requireFullStack:this.requireFullStack,perceptionRequest:clone(this.perceptionRequest),registryGroundTruth:this._registryTruth(),onboardPerception:{status:this.intelligence.onboard.status,lastPacket:clone(this.intelligence.onboard.lastPacket),observations:clone(this.intelligence.onboard.observations.filter(o=>[this.donorId,this.targetId].includes(o.id)))},reason:message,donorId:this.donorId,targetId:this.targetId,compatible:!!this._compatible(this._donor(),this._recipient()),water:clone(this.water),metrics:clone(this.metrics),fragment:clone(this._fragment()??null),sonar:this._sonar(),fusion:this._fusion(),perception:this._perception(),grip:clone(this.grip),currentVector:this._currentAt(this.robot.position),wildlife:clone(this.wildlife),route:clone(this.route),retryBudget:kind==='uncertain'?3-this.perceptionReviewRetries:3-this.retries}};
    if(this.controller!=='scripted') {this.robot.target=clone(this.robot.position);this.pendingDecision=request;this.status=this.controller==='base_station'?'Waiting for validated local policy and route plan':'Waiting for Gemini decision';this.nominalStatus=this.status;this._event('decision',message+(this.controller==='base_station'?' Awaiting live base-station plan.':' Awaiting live Gemini.'));}
    else {this.pendingDecision=request;this._applyDecision(request.id,allowedActions[0],message,'scripted');}
  }
  _applyDecision(id,action,reason,source,routeMode=null,evidence=null) {
    const pending=this.pendingDecision;
    if(!pending||pending.id!==id)throw new Error('Decision is stale or does not exist');
    if(!pending.allowedActions.includes(action))throw new Error('Decision action is not allowed');
    if(this.controller==='gemini' && source!=='gemini')throw new Error('Gemini mode requires an explicit Gemini result');
    if(this.controller==='base_station'&&source!=='base_station')throw new Error('Base-station mode requires an explicit base-station result');
    if(typeof reason!=='string'||reason.length>1600)throw new Error('Decision reason must be text of at most 1600 characters');
    if(routeMode!==null&&(!['direct','clearance'].includes(routeMode)||!pending.observation.route.alternatives.some(r=>r.id===routeMode)))throw new Error('Decision route must be a declared alternative');
    if(this.controller==='base_station'){const plan=this.intelligence.baseStation.plan;const planId=evidence?.planning?.requestId??evidence?.planning?.id;if(!plan||plan.requestId!==id||planId!==id)throw new Error('Ingest the matching base-station plan before applying it');if(this.time-plan.frameTime>this.intelligence.planMaxAgeSeconds)throw new Error('Base-station plan expired before execution');if(action!==plan.decision||routeMode!==plan.routeMode)throw new Error('Applied action must match the validated base-station plan');if(action==='retry'&&pending.kind!=='uncertain'&&!this._fragmentEvidenceReady())throw new Error('Recovery requires fresh fragment visibility and matching gripper-state evidence');if(action==='proceed'&&this.scene.restorationMode==='loose_fragment'&&!this._fragmentEvidenceReady())throw new Error('Loose stock requires fresh fragment visibility before pickup');if(action==='proceed'&&!this._inspectionEvidenceReady())throw new Error('Fresh Gemma evidence must pass for every colony handled by this mission');}
    if(routeMode!==null){this.route.mode=routeMode;this.scene.routeMode=routeMode;}
    const provenance={};if((source==='gemini'||source==='base_station')&&evidence&&typeof evidence==='object'&&!Array.isArray(evidence)){for(const key of ['model','inputMode','inputImageSha256','inputCamera','interactionId'])if(typeof evidence[key]==='string'&&evidence[key].length<=256)provenance[key]=evidence[key];for(const key of ['latencyMs','inputImageTime','inputImageWidth','inputImageHeight'])if(typeof evidence[key]==='number'&&Number.isFinite(evidence[key])&&evidence[key]>=0)provenance[key]=evidence[key];}
    this.pendingDecision=null;this.decision={id,action,reason,source,routeMode,time:this.time,...provenance};if(source==='base_station'){this.decision.perception=clone(this.intelligence.onboard.lastPacket);this.decision.planning=clone(this.intelligence.baseStation.plan);this.intelligence.baseStation.status='applied';}this.metrics.decisionCount++;this._event('decision',`${source}: ${action} — ${reason}`);
    if(action==='abort'){this._abort('Controller requested a safe abort.');return;}
    if(pending.kind==='uncertain'){
      this.perceptionReviewRetries++;const phase=this.uncertainInspectionPhase;if(!['inspect_recipient','inspect_donor'].includes(phase)){this._abort('Uncertainty review lost its inspection context.');return;}
      this._setGripTarget(this._top(phase==='inspect_recipient'?this._recipient():this._donor()),1);this._setPhase(phase,'Base requested a fresh visual inspection; harvesting remains blocked.');
    } else if(pending.kind==='inspect') {
      if(this.scene.restorationMode==='loose_fragment'&&(this._fragment()?.state!=='available'||this._fragment()?.detachedAtStart!==true||this._fragment()?.source!=='scenario_permitted_loose_stock'||this._fragment()?.donorId!==this.donorId)){this._abort('Loose restoration requires pre-existing detached stock; attached coral cannot be collected.');return;}
      if(!this._inspectionColonyIds().every(id=>this.uvObservations.some(o=>o.id===id&&o.exposureSeconds>=1.2))){this._abort('Required colony inspection exposure must pass before handling.');return;}
      if(!this._compatible(this._donor(),this._recipient())){this._abort('Compatibility gate failed.');return;}
      this._setGripTarget(this._fragment().position);this._setPhase('approach',this.scene.restorationMode==='loose_fragment'?'Approaching approved detached fragment':'Approaching approved donor cutting');
    } else if(pending.kind==='drop') {
      this._setPhase('recover_drop','Locating dropped cutting');
    } else if(pending.kind==='cut') {
      const f=this.fragments.find(f=>f.donorId===this.donorId&&this._stockAvailable(f));
      if(!f){this._abort('Donor stock exhausted after rejected cuts.');return;}
      this.fragmentId=f.id;this._setGripTarget(f.position);this._setPhase('approach','Retrying with a fresh donor cutting');
    } else if(pending.kind==='placement') {this._setPhase('recover_placement','Regrasping unstable placement');}
    else if(pending.kind==='resume'){const saved=this.resumeAfterPerception;if(!saved){this._abort('Missing mission context after rescan.');return;}this.resumeAfterPerception=null;this._planRoute(saved.goal);this._setPhase(saved.phase,'Resuming mission after fresh perception');this.phaseTime=saved.phaseTime;this.phaseElapsed=saved.phaseElapsed;}
  }
  command(data) {
    if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('Command must be an object');
    const action=data.action;
    switch(action) {
      case 'run': if((this.completed||this.phase==='aborted')&&this.pilot.mode!=='manual')throw new Error('Reset before starting another autonomous run');this.running=true;if(this.phase==='idle')this._setPhase('survey','Surveying the editable reef');break;
      case 'pause':this.running=false;break;
      case 'abort':if(this.completed||this.phase==='aborted')throw new Error('Mission is already terminal');this.assistanceHold=null;this._abort(typeof data.reason==='string'?data.reason.slice(0,400):'Operator requested a safe abort.');break;
      case 'set_assistance_hold':{
        if(typeof data.active!=='boolean')throw new Error('Assistance hold requires an active boolean');
        if(data.active){if(this.completed||this.phase==='aborted'||this.pilot.mode==='manual')throw new Error('Assistance hold requires a nonterminal autonomous mission');if(!this.assistanceHold){this.assistanceHold={since:this.time,position:clone(this.robot.position),resumeTarget:clone(this.robot.target),reason:typeof data.reason==='string'?data.reason.slice(0,400):'Waiting for bounded uncertainty assistance'};this._event('hold',this.assistanceHold.reason);}this.robot.target=clone(this.assistanceHold.position);}
        else if(this.assistanceHold){this.robot.target=clone(this.assistanceHold.resumeTarget);this.assistanceHold=null;this.status=this.nominalStatus;}
        break;
      }
      case 'reset':return this.reset();
      case 'set_water': {
        const next={current:data.current===undefined?this.water.current:finite(data.current,0,.8,'Current'),visibility:data.visibility===undefined?this.water.visibility:finite(data.visibility,.2,20,'Visibility')};
        this.water=next;this.scene.water=clone(next);this.restoreCurrent=null;this.surgeUntil=0;this._event('environment','Water conditions updated.');break;
      }
      case 'request_rescan':this._requestRescan(typeof data.reason==='string'?data.reason.slice(0,300):undefined);break;
      case 'review_uncertainty': {
        const capture=this.perceptionRequest,packet=this.intelligence.onboard.lastPacket;
        if(this.controller!=='base_station'||this.pilot.mode!=='autonomous'||!capture||capture.targetKind!=='colony'||!packet||packet.captureRequestId!==capture.id)throw new Error('Uncertainty review requires a matching actual colony observation');
        if(this.time-packet.frameTime>this.intelligence.perceptionMaxAgeSeconds)throw new Error('Uncertain observation expired; acquire a fresh frame');
        if(this._externalHealth(capture.targetId,capture.expectedHealth).ready)throw new Error('Accepted evidence does not need uncertainty review');
        this.uncertainInspectionPhase=this.phase;this._setPhase('approval','Visual evidence uncertain; asking the base to rescan or abort.');
        this._gate('uncertain','Gemma returned uncertain or incompatible visual evidence. Harvesting is forbidden. Review this observation and choose only a fresh inspection retry within budget or safe abort.',true);break;
      }
      case 'ingest_perception':this._ingestPerception(data.packet);break;
      case 'ingest_plan':this._ingestPlan(data.packet);break;
      case 'randomize':if(this.running)throw new Error('Pause before randomizing the scene');this.scene=validateScene({...defaultScene(finite(data.seed,0,4294967295,'Seed')),restorationMode:this.scene.restorationMode});return this.reset();
      case 'set_pilot': {
        if(!['manual','autonomous'].includes(data.mode))throw new Error('Unknown pilot mode');
        this.pilot.mode=data.mode;this.pilot.command={forward:0,right:0,vertical:0,yaw:0};this.pilot.lastInputTime=null;this.pilot.expired=false;
        if(data.mode==='manual'){this.assistanceHold=null;this.robot.target=clone(this.robot.position);this.running=true;this.status='Manual pilot · thruster control';}
        else {this._planRoute(this.route.goal);this.status=this.nominalStatus;if(this.completed||this.phase==='aborted')this.running=false;if(this.phase==='idle')this._setPhase('survey','Surveying the editable reef');this._event('plan','Autonomous route replanned from the pilot’s current pose.');}
        break;
      }
      case 'manual_input': {
        if(this.pilot.mode!=='manual')throw new Error('Enable manual pilot first');
        const command={};for(const key of ['forward','right','vertical','yaw'])command[key]=finite(data[key]??0,-1,1,key);
        this.pilot.command=command;this.pilot.lastInputTime=this.time;this.pilot.expired=false;break;
      }
      case 'manual_gripper': {
        if(this.pilot.mode!=='manual'||typeof data.open!=='boolean')throw new Error('Manual gripper requires manual mode and an open boolean');
        const f=this._fragment();
        if(data.open&&this.robot.holding){if(f?.state==='carried')this._drop();else if(f?.state==='grasped'){f.state='attached';f.position=this._top(this._donor());this.robot.holding=null;this._setPhase('approach','Reapproaching donor after manual release');this._setGripTarget(f.position);}}
        this.robot.gripperOpen=data.open?1:0;break;
      }
      case 'set_route':if(!['direct','clearance'].includes(data.mode))throw new Error('Unknown route mode');this.scene.routeMode=data.mode;this.route.mode=data.mode;this._planRoute(this.route.goal);this._event('plan',`Selected ${data.mode} route; replanning from current position.`);break;
      case 'set_controller':
        if(!['scripted','gemini','base_station'].includes(data.mode))throw new Error('Unknown controller');
        this.controller=data.mode;if(data.mode==='base_station'){this.requireFullStack=data.requireFullStack!==false;this.intelligence.requireFullStack=this.requireFullStack;}
        if(this.pendingDecision&&data.mode==='scripted')this._applyDecision(this.pendingDecision.id,this.pendingDecision.allowedActions[0],'Operator selected deterministic controller.','scripted');
        break;
      case 'inject_fault':if(this.scene.restorationMode==='loose_fragment'&&data.kind==='bad_cut')throw new Error('Loose-fragment restoration does not cut healthy colonies');
        if(!FAULTS.includes(data.kind))throw new Error('Unknown fault');
        if(this.phase==='aborted'||this.completed)throw new Error('Reset before injecting faults');
        if(data.kind==='current_surge'){this.restoreCurrent??=this.water.current;this.water.current=Math.min(.8,this.water.current+.38);this.surgeUntil=this.time+12;this.surgeStarted=this.time;this._event('fault','Current surge: four-second cross-current wave (3.2m/s localized peak) followed by elevated drift; grip load monitored during safe hold.');}
        else if(data.kind==='sensor_dropout'){this.dropoutUntil=this.time+8;this._event('fault','Camera dropout: perception unavailable for 8 seconds.');}
        else if(data.kind==='drop'&&this._fragment()?.state==='carried')this._drop();
        else {if(this.faults.length>=10)throw new Error('At most ten queued faults');this.faults.push(data.kind);this._event('fault',`${data.kind.replaceAll('_',' ')} armed for its next applicable phase.`);}break;
      case 'apply_decision':this._applyDecision(data.id,data.decision??data.choice,data.reason,data.source,data.routeMode??null,data.evidence??null);break;
      case 'edit_colony':case 'add_colony':case 'remove_colony':case 'add_obstacle':case 'remove_obstacle': {
        if(this.running)throw new Error('Pause before editing the environment');
        const next=this.exportScene();
        if(action==='edit_colony'){const i=next.colonies.findIndex(c=>c.id===data.id);if(i<0)throw new Error('Unknown colony');if(data.patch?.id&&data.patch.id!==data.id)throw new Error('Colony IDs cannot be edited');next.colonies[i]={...next.colonies[i],...data.patch,id:data.id};}
        if(action==='add_colony')next.colonies.push(data.colony);
        if(action==='remove_colony'){if(!next.colonies.some(c=>c.id===data.id))throw new Error('Unknown colony');next.colonies=next.colonies.filter(c=>c.id!==data.id);}
        if(action==='add_obstacle')next.obstacles.push(data.obstacle);
        if(action==='remove_obstacle'){if(!next.obstacles.some(c=>c.id===data.id))throw new Error('Unknown obstacle');next.obstacles=next.obstacles.filter(c=>c.id!==data.id);}
        this.scene=validateScene(next);this.reset();this._event('edit','Environment changed; mission state reset to preserve repeatability.');break;
      }
      default:throw new Error('Unknown command');
    }
    return {ok:true};
  }
  exportScene(){return clone(this.scene);}
  loadScene(input){if(this.running)throw new Error('Pause before importing a scene');const parsed=typeof input==='string'?JSON.parse(input):input;this.scene=validateScene(parsed);return this.reset();}
  _consume(kind){const i=this.faults.indexOf(kind);if(i<0)return false;this.faults.splice(i,1);return true;}
  _retry(kind,message){this.retries++;if(this.retries>3){this._abort('Recovery budget exhausted: '+message);return;}this._gate(kind,message);}
  _drop() {
    const f=this._fragment();if(!f||this.robot.holding!==f.id)return;
    this.fragmentCaptureId=null;f.state='dropped';f.position=clone(this.robot.gripper);f.velocity=add(this.robot.velocity,[.12,0,-.08]);this.robot.holding=null;this.robot.gripperOpen=1;this.metrics.drops++;this._event('fault','Grip lost: the same cutting is falling under submerged weight and drag.');this._setPhase('recovery','Assessing dropped cutting');this._retry('drop','Locate, recover and regrasp the existing cutting.');
  }
  step(dt) {
    finite(dt,0,60,'Time step');if(!this.running)return this.snapshot();
    this.accumulator+=dt;
    while(this.accumulator>=1/60-1e-10&&this.running){this.accumulator-=1/60;this._tick(1/60);}
    return this.snapshot();
  }
  _physics(dt,hold=false) {
    const r=this.robot;const old=clone(r.position);const err=sub(r.target,r.position);let desiredVelocity=scale(err,.9);const speedLimit=r.holding?.95:1.3;if(norm(desiredVelocity)>speedLimit)desiredVelocity=scale(desiredVelocity,speedLimit/norm(desiredVelocity));let force=scale(sub(desiredVelocity,r.velocity),24);
    if(this.pilot.mode==='manual'&&!hold){
      const stale=this.pilot.lastInputTime===null||this.time-this.pilot.lastInputTime>this.pilot.watchdogSeconds;
      this.pilot.expired=stale;const input=stale?{forward:0,right:0,vertical:0,yaw:0}:this.pilot.command;
      if(stale)this.pilot.command={forward:0,right:0,vertical:0,yaw:0};
      r.yaw+=input.yaw*.85*dt;r.yaw=Math.atan2(Math.sin(r.yaw),Math.cos(r.yaw));
      force=[32*(input.forward*Math.cos(r.yaw)+input.right*Math.sin(r.yaw)),32*(input.forward*Math.sin(r.yaw)-input.right*Math.cos(r.yaw)),28*input.vertical];
    }
    // Approximate habitat envelopes protect robot body; active tool targets are exempt.
    const habitat=[...this.obstacles.map(o=>({...o,position:add(o.position,[0,0,o.radius*.5])})),...this.colonies.filter(c=>this.pilot.mode==='manual'||(c.id!==this.donorId&&c.id!==this.targetId)).map(c=>({id:c.id,position:add(c.position,[0,0,coralHeight(c)*.45]),radius:Math.max(c.radius*.72,coralHeight(c)*.45),top:c.position[2]+coralHeight(c)})),...this._nearHabitat(2.6).map(c=>({id:c.id,position:add(c.position,[0,0,c.height*.45]),radius:Math.max(c.radius*.72,c.height*.45),top:c.position[2]+c.height,influence:.15}))];
    const nearby=this.wildlife.filter(a=>norm(sub(r.position,a.position))<a.radius+(this.wildlifeYield?.7:a.type==='crab'?.58:.45));
    const yielding=nearby.length>0;
    if(yielding&&!this.wildlifeYield){this.metrics.wildlifeAvoidances++;this._event('hold',`Yielding to ${nearby[0].type}; pausing progress and reducing thrust.`);}
    if(!yielding&&this.wildlifeYield)this._event('recovery','Wildlife clear; resuming selected route.');
    this.wildlifeYield=yielding;
    if(yielding){force=scale(r.velocity,-22);for(const a of nearby){const d=sub(r.position,a.position),n=norm(d);if(n>.001)force=add(force,scale(d,12*(a.radius+.85-n)/n));}}
    for(const o of habitat){if(o.top!==undefined&&r.position[2]-.3>o.top+.15)continue;const d=sub(r.position,o.position),n=norm(d),safe=o.radius+.3,influence=o.influence??.65;if(n<safe+influence&&n>1e-6){const gain=24*(safe+influence-n);force=add(force,scale(d,gain/n));}}
    const magnitude=norm(force);if(magnitude>42)force=scale(force,42/magnitude);
    const flow=this._currentAt(r.position);this.water.currentVector=clone(flow);this.water.currentSpeed=norm(flow);this.forces={thrust:clone(force),drag:[0,0,0],buoyancy:[0,0,.15],net:[0,0,0]};
    for(let i=0;i<3;i++){const relative=r.velocity[i]-flow[i];const drag=-7*relative*Math.abs(relative)-2*relative;this.forces.drag[i]=drag;this.forces.net[i]=force[i]+drag+(i===2?.15:0);const acceleration=this.forces.net[i]/18;r.velocity[i]+=acceleration*dt;r.position[i]+=r.velocity[i]*dt;}
    r.position[2]=Math.max(terrainHeight(...r.position)+.7,r.position[2]);
    for(const o of habitat){if(o.top!==undefined&&r.position[2]-.3>o.top+.15)continue;const d=sub(r.position,o.position),n=norm(d),safe=o.radius+.3;if(n<safe){const unit=n>1e-6?scale(d,1/n):[0,0,1];r.position=add(o.position,scale(unit,safe));r.velocity=[0,0,0];if(this.time-(this.lastCollision??-10)>1){this.metrics.collisions++;this.metrics.habitatAvoidances++;this.lastCollision=this.time;this._event('warning','Obstacle contact detected; controller replanning locally.');}}}
    for(let i=0;i<2;i++){const bounded=clamp(r.position[i],-12,12);if(bounded!==r.position[i])r.velocity[i]=0;r.position[i]=bounded;}r.position[2]=clamp(r.position[2],terrainHeight(...r.position)+.7,8);
    const movement=norm(sub(r.position,old));this.metrics.distance+=movement;this.metrics.energy+=norm(force)*norm(r.velocity)*dt;
    if(this.pilot.mode!=='manual'&&norm(r.velocity)>.05){const desired=Math.atan2(r.velocity[1],r.velocity[0]),delta=Math.atan2(Math.sin(desired-r.yaw),Math.cos(desired-r.yaw));r.yaw+=clamp(delta,-dt*1.2,dt*1.2);}r.gripper=add(r.position,[0,0,-.65]);this._checkGrip();
    for(const f of this.fragments){
      if(f.state==='carried'||f.state==='grasped'){f.position=clone(r.gripper);f.velocity=clone(r.velocity);}
      else if(f.state==='dropped'||f.state==='rejected'){
        // Effective submerged gravity: coral density 2,500 kg/m³ in seawater 1,025 kg/m³.
        const fragmentFlow=this._currentAt(f.position);f.velocity[0]+=(fragmentFlow[0]-f.velocity[0])*1.5*dt;f.velocity[1]+=(fragmentFlow[1]-f.velocity[1])*1.5*dt;f.velocity[2]+=(-5.79-4*f.velocity[2]*Math.abs(f.velocity[2]))*dt;
        f.position=add(f.position,scale(f.velocity,dt));const bed=terrainHeight(...f.position)+.07;if(f.position[2]<bed){f.position[2]=bed;f.velocity=[0,0,0];}
      }
    }
  }
  _tick(dt) {
    this.time+=dt;this._updateWildlife(dt);
    if(this.time>=this.surgeUntil&&this.restoreCurrent!==null){this.water.current=this.restoreCurrent;this.restoreCurrent=null;this._event('environment','Current surge passed.');}
    const environmentUnsafe=this.water.visibility<1.5||this.water.current>.42||this.time<this.dropoutUntil;
    if(environmentUnsafe){
      if(!this.environmentHold){this.holdTarget=clone(this.robot.target);this.environmentHoldPosition=clone(this.robot.position);this.robot.target=clone(this.environmentHoldPosition);this._event('hold','Safe hold: current, visibility or camera quality exceeds operating limits.');}
      this.robot.target=clone(this.environmentHoldPosition);this.environmentHold+=dt;this.status='Safe hold · waiting for usable sensing and current';this._physics(dt,true);
      if(this.environmentHold>30){if(this.pilot.mode==='manual'){this.running=false;this.status='Manual pilot paused: environmental limits exceeded.';}else this._abort('Environmental limits exceeded for 30 seconds. No unsafe manipulation attempted.');}return;
    }
    if(this.environmentHold){this.robot.target=clone(this.route.waypoints[this.route.index]??this.holdTarget);this.environmentHold=0;this.status=this.nominalStatus;this._event('recovery','Conditions recovered; resuming from the same mission state.');}
    if(this.pilot.mode==='manual'){this._physics(dt);return;}
    if(this.assistanceHold){this.robot.target=clone(this.assistanceHold.position);this.status='Assistance hold · local physics and safety active';this._physics(dt,true);if(this.time-this.assistanceHold.since>90)this._abort('Uncertainty assistance hold exceeded 90 seconds; mission aborted.');return;}
    if(this.pendingDecision){if(this.controller==='base_station'){const q=this.pendingDecision;const perceptionFresh=q.kind==='uncertain'?!!this.intelligence.onboard.lastPacket&&this.time-this.intelligence.onboard.lastPacket.frameTime<=this.intelligence.perceptionMaxAgeSeconds:q.kind==='inspect'?this._inspectionEvidenceReady()&&(this.scene.restorationMode!=='loose_fragment'||this._fragmentEvidenceReady()):this._fragmentEvidenceReady();if(!perceptionFresh){this._requestRescan('Evidence expired while awaiting the planner; reacquiring an actual camera view.',q.kind==='uncertain'?'inspect':q.kind);}else if(this.time-q.observation.time>this.intelligence.planMaxAgeSeconds){this.pendingDecision=null;this.intelligence.baseStation.plan=null;this._gate(q.kind,'Planning request expired; requesting a current plan.',true);}}this._physics(dt,true);return;}
    this.phaseElapsed+=dt;
    const waitingOnPerception=this.controller==='base_station'&&['inspect_recipient','inspect_donor','inspect_fragment'].includes(this.phase);if(this.phaseElapsed>(waitingOnPerception?180:90)){this._abort(waitingOnPerception?'Onboard perception wait exceeded 180 simulation seconds.':'Motion timeout: target cannot be reached safely.');return;}
    const f=this._fragment(),donor=this._donor(),target=this._recipient();
    if(this.phase==='inspect_fragment'&&f&&!this.robot.holding)this._setGripTarget(f.position,1);
    if(this.phase==='recover_drop'&&f)this._setGripTarget(f.position);
    if(this.phase==='recover_placement'&&f)this._setGripTarget(f.position);
    this._advanceRoute();this._physics(dt);
    const routeFinished=this.route.index===this.route.waypoints.length-1;
    const inspectionApproved=this._recordInspection(dt);
    const arrived=inspectionApproved&&routeFinished&&!this.wildlifeYield&&norm(sub(this.robot.position,this.robot.target))<.16&&norm(this.robot.velocity)<.22;
    if(arrived||this.phase==='survey')this.phaseTime+=dt;
    const done=this.phaseTime>=(DURATIONS[this.phase]??1);
    if(!done)return;
    switch(this.phase){
      case 'survey':this._choosePair();break;
      case 'inspect_fragment':if(this.rescanContext)this._advanceRescan();else{this._setPhase('approval','Awaiting loose-fragment transfer approval');this._gate('inspect','Recipient and registered detached stock inspected; existing loose fragment visible.');}break;
      case 'inspect_recipient':if(this.rescanContext){this._advanceRescan();break;}if(this.scene.restorationMode==='loose_fragment'){this._setGripTarget(f.position,1);this._setPhase('inspect_fragment','Inspecting the registered detached fragment before pickup');break;}this._setGripTarget(this._top(donor),1);this._setPhase('inspect_donor','Inspecting compatible healthy donor');break;
      case 'inspect_donor':if(this.rescanContext){this._advanceRescan();break;}if(this.scene.restorationMode==='loose_fragment'){this._setGripTarget(f.position,1);this._setPhase('inspect_fragment','Inspecting the existing loose fragment before pickup');break;}this._setPhase('approval','Awaiting harvest approval');this._gate('inspect','Both living colonies inspected; known lineage and species match.');break;
      case 'approach':this.robot.gripperOpen=.15;this._setPhase('grasp',this.scene.restorationMode==='loose_fragment'?'Closing jaws around the existing loose fragment':'Closing jaws around the attached cutting');break;
      case 'grasp':this.robot.gripperOpen=0;this.robot.holding=f.id;if(this.scene.restorationMode==='loose_fragment'){f.state='carried';this._setGripTarget(f.sourcePosition,1.2);this._setPhase('retract','Lifting the same pre-existing fragment; no coral cut');this._event('collection',`${f.id} collected from registered loose stock; healthy colonies unchanged.`);}else{f.state='grasped';this._setPhase('cut','Executing bounded donor cut');}break;
      case 'cut':
        f.quality=this._consume('bad_cut') ? .35 : clamp(.93+this.random()*.06-this.water.current*.08,0,1);
        if(f.quality<.75){f.state='rejected';f.velocity=[0,0,-.2];this.robot.holding=null;this.robot.gripperOpen=1;this.metrics.rejectedCuts++;this.metrics.damage++;this._event('fault','Cut quality failed inspection; fragment rejected, donor stock reduced.');this._setPhase('recovery','Rejecting poor cut');this._retry('cut','Reject damaged cutting and retry within available donor stock.');}
        else {f.state='carried';this._setGripTarget(this._top(donor),1.2);this._setPhase('retract','Retracting the same detached cutting');}break;
      case 'retract':this._setGripTarget(this._top(target),1.3);this._setPhase('transport','Transporting cutting to its compatible recipient');if(this._consume('drop'))this._drop();break;
      case 'transport':this._setGripTarget(this._top(target));this._setPhase('align','Aligning tissue contact and attachment');break;
      case 'align':this._setPhase('secure','Securing the fragment base');break;
      case 'secure':f.state='secured';f.position=this._top(target);f.targetId=target.id;f.unstable=this._consume('bad_placement');this.robot.holding=null;this.robot.gripperOpen=1;this._setPhase('release','Releasing and checking for movement');break;
      case 'release':this._setGripTarget(this._top(target),1.2);this._setPhase('verify','Verifying mechanical placement');break;
      case 'verify':
        if(f.unstable){f.state='unsecured';f.position=add(this._top(target),[.2,0,-.12]);this.metrics.placementRetries++;this._event('fault','Placement shifted during verification; success withheld.');this._setPhase('recovery','Placement requires correction');this._retry('placement','Regrasp, realign and repeat the securing and verification sequence.');}
        else {f.state='placed';this.assisted.add(target.id);this.metrics.placed++;this._event('success',`${f.id} mechanically verified on ${target.id}. Biological recovery is not simulated.`);if(this.metrics.placed>=this.scene.missionGoal){this.completed=true;this.running=false;this._setPhase('complete','Mission complete · all placements verified');}else this._choosePair();}break;
      case 'recover_drop':if(f.position[2]>terrainHeight(...f.position)+.09){this.phaseTime=0;break;}this.robot.holding=f.id;this.robot.gripperOpen=0;f.state='carried';this._setPhase('regrasp','Closing jaws on recovered cutting');break;
      case 'recover_placement':this.robot.holding=f.id;this.robot.gripperOpen=0;f.state='carried';f.unstable=false;this._setPhase('regrasp','Regrasping the same cutting');break;
      case 'regrasp':this.metrics.recoveries++;this._event('recovery','Cutting recovered; identity and stock conserved.');this._setGripTarget(this._top(target),1.3);this._setPhase('transport','Resuming transfer after recovery');break;
    }
  }
  snapshot() {
    return clone({time:this.time,running:this.running,seed:this.scene.seed,restorationMode:this.scene.restorationMode,phase:this.phase,phaseProgress:clamp(this.phaseTime/(DURATIONS[this.phase]??1),0,1),controller:this.controller,status:this.status,water:{...this.water,currentSamples:this._currentSamples(),fieldSource:'Exact samples of the reduced flow field used by vehicle and loose-fragment drag'},regions:this.regions,colonies:this.colonies,obstacles:this.obstacles,terrain:{model:'Shared sloping limestone relief',units:'metres'},habitatCount:this.habitat.length,wildlife:this.wildlife,intelligence:this.intelligence,perceptionRequest:this.perceptionRequest,rescan:this.rescanContext,registryGroundTruth:this._registryTruth(),perception:this._perception(),grip:this.grip,pilot:this.pilot,sensors:{fusion:this._fusion()},navigation:{velocity:this.robot.velocity,speed:norm(this.robot.velocity),bedClearance:this.robot.position[2]-terrainHeight(...this.robot.position),waypointIndex:this.route.index},sonar:this._sonar(),route:this.route,robot:this.robot,fragments:this.fragments,fragmentId:this.fragmentId,targetId:this.targetId,donorId:this.donorId,metrics:this.metrics,events:this.events,decision:this.decision,pendingDecision:this.pendingDecision,completed:this.completed,missionGoal:this.scene.missionGoal,queuedFaults:this.faults,environmentHold:this.environmentHold,assistanceHold:this.assistanceHold,physics:{parameterProvenance:'Engineering demonstration constants; not calibrated to a vehicle or validated onboard hardware',uvProxy:{minimumExposureSeconds:1.2,rangeM:1.6,genotypeInference:false},gripProxy:{capacityN:5,areaM2:.002,fragmentMassKg:.018,waterDensityKgM3:1025,dragCoefficient:1.15},waveProxy:{localizedPeakMS:3.2,envelopeSeconds:4},model:'Reduced buoyancy, thrust and quadratic drag; bounded kinematic grip/contact',massKg:18,maxThrustN:42,stepSeconds:1/60,forces:this.forces,currentModel:'Seeded continuous spatial, depth and temporal current field',assetResponses:{stonyCoral:'Rigid terrain-anchored skeleton collision proxies; not swaying plants',rocks:'Rigid terrain-anchored collision proxies',flexibleTissue:'Bounded visual bending driven by local flow; not a structural mechanics simulation',looseFragments:'Submerged weight and local-flow drag',vehicles:'Thrust, buoyancy residual and relative-current drag'}},limits:{biology:'Mechanical verification only; no tissue fusion or biological recovery',perception:'Synthetic known scene labels; no image-based genotype inference',contacts:'Approximate obstacle collision and fragment contact; no fracture or glue chemistry'}});
  }
  evaluate({seeds=[42,43,44],scenario='baseline'}={}) {
    if(!Array.isArray(seeds)||!seeds.length||seeds.length>30)throw new Error('Evaluation accepts 1–30 seeds');
    if(!['baseline',...FAULTS].includes(scenario))throw new Error('Unknown evaluation scenario');
    const runs=seeds.map(seed=>{const scene=this.exportScene();scene.seed=seed;const sim=new ReefLab(scene);if(scenario!=='baseline')sim.command({action:'inject_fault',kind:scenario});sim.command({action:'run'});for(let i=0;i<600&&sim.running;i++)sim.step(1);const timedOut=sim.running;if(timedOut)sim._abort('Evaluation exceeded its 600-second simulation budget.');const s=sim.snapshot();return {seed,success:s.completed,timedOut,time:s.time,phase:s.phase,metrics:s.metrics,reason:s.status,unconsumedFaults:s.queuedFaults};});
    return {scenario,controller:'scripted',timeLimitSeconds:600,seedVariation:'Fixed exported scene geometry; seeds vary procedural cut-quality samples, wildlife and current phases. New randomize scenes also vary mission and habitat layout. Fault timing is deterministic.',model:'Browser reduced physics; synthetic fault injection',runs,successRate:runs.filter(r=>r.success).length/runs.length};
  }
}
