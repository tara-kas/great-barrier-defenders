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
  const rand=rng(seed), colonies=[];
  for(let i=0;i<4;i++) {
    colonies.push(colony({id:`donor-${i+1}`,position:[-3.2+i*1.85,-2.2,0],health:'healthy',genet:`G${i+1}`,radius:0.48,height:0.75}));
    colonies.push(colony({id:`recipient-${i+1}`,position:[-3+i*1.85,2,0],health:'bleached_alive',genet:`G${i+1}`,radius:0.48,height:0.72}));
  }
  for(let i=0;i<64;i++) {
    const a=rand()*Math.PI*2,r=4.7+rand()*4.3;
    colonies.push(colony({id:`reef-${i+1}`,position:[Math.cos(a)*r,Math.sin(a)*r,0],health:i%5===0?'dead':i%4===0?'bleached_alive':'healthy',genet:'',radius:.3+rand()*.45,height:.35+rand()*.65,morphology:i%3===0?'plate':i%4===0?'boulder':'branching'}));
  }
  for(let i=0;i<12;i++) {
    const x=-3+(i%4)*2,y=[-.7,.35,1.05][Math.floor(i/4)];
    colonies.push(colony({id:`habitat-${i+1}`,position:[x,y,0],health:i%5===0?'dead':'healthy',genet:'',radius:.23+rand()*.12,height:.3+rand()*.18,morphology:i%3===0?'plate':'branching'}));
  }
  return {version:1,seed,water:{current:.08,visibility:8},missionGoal:4,colonies,obstacles:[{id:'rock-1',position:[-1,0,0],radius:.45},{id:'rock-2',position:[3.8,.4,0],radius:.55}]};
}
function validateScene(input) {
  if (!input || typeof input!=='object' || Array.isArray(input)) throw new Error('Scene must be an object');
  const seed=finite(input.seed??42,0,4294967295,'Seed');
  if(!Number.isInteger(seed)) throw new Error('Seed must be an integer');
  if(input.version!==undefined && input.version!==1) throw new Error('Unsupported scene version');
  if(!Array.isArray(input.colonies) || input.colonies.length>100 || !Array.isArray(input.obstacles??[]) || (input.obstacles??[]).length>40) throw new Error('Scene supports up to 100 colonies and 40 obstacles');
  const colonies=input.colonies.map(colony),obstacles=(input.obstacles??[]).map(obstacle);
  const routeMode=input.routeMode??'direct';if(!['direct','clearance'].includes(routeMode))throw new Error('Unknown route mode');
  if(new Set([...colonies,...obstacles].map(c=>c.id)).size!==colonies.length+obstacles.length) throw new Error('Scene IDs must be unique');
  const missionGoal=finite(input.missionGoal??4,1,20,'Mission goal');
  if(!Number.isInteger(missionGoal)) throw new Error('Mission goal must be an integer');
  return {version:1,seed,missionGoal,routeMode,water:{current:finite(input.water?.current??.08,0,.8,'Current'),visibility:finite(input.water?.visibility??8,.2,20,'Visibility')},colonies,obstacles};
}
export class ReefLab {
  constructor(config={}) {
    this.scene=validateScene(config.colonies?config:{...defaultScene(config.seed??42),...config,water:{...defaultScene().water,...config.water}});
    this.controller=config.controller==='gemini'?'gemini':'scripted';
    this.reset();
  }
  reset() {
    this.random=rng(this.scene.seed);this.time=0;this.accumulator=0;this.running=false;this.completed=false;this.phase='idle';this.phaseTime=0;this.phaseElapsed=0;this.status='Ready to begin';this.nominalStatus=this.status;this.lastCollision=-10;this.holdTarget=null;this.water=clone(this.scene.water);this.colonies=clone(this.scene.colonies);this.obstacles=clone(this.scene.obstacles);this.events=[];this.pendingDecision=null;this.decision=null;this.decisionCounter=0;this.faults=[];this.surgeUntil=0;this.dropoutUntil=0;this.environmentHold=0;this.restoreCurrent=null;this.donorId=null;this.targetId=null;this.fragmentId=null;this.assisted=new Set();this.retries=0;
    this.metrics={placed:0,attempts:0,drops:0,recoveries:0,rejectedCuts:0,placementRetries:0,distance:0,energy:0,damage:0,collisions:0,decisionCount:0,wildlifeAvoidances:0,habitatAvoidances:0};
    this.robot={position:[-4,-4,2],velocity:[0,0,0],target:[-4,-4,2],gripper:[-4,-4,1.35],yaw:0,holding:null,gripperOpen:1};
    this.habitat=[...generateHabitat(this.colonies),...generateHabitatRocks(this.colonies)];this.habitatIndex=new Map();for(const c of this.habitat){const key=`${Math.floor(c.position[0]/4)},${Math.floor(c.position[1]/4)}`;if(!this.habitatIndex.has(key))this.habitatIndex.set(key,[]);this.habitatIndex.get(key).push(c);}
    this.route={mode:this.scene.routeMode,goal:clone(this.robot.target),waypoints:[clone(this.robot.target)],index:0,alternatives:[]};this.wildlifeYield=false;this.wildlife=[];this._updateWildlife(0);this.fragments=[];
    for(const c of this.colonies.filter(c=>c.health==='healthy'&&c.genet)) for(let i=0;i<2;i++) this.fragments.push({id:`${c.id}-fragment-${i+1}`,donorId:c.id,position:add(this._top(c),[.05*(i?1:-1),0,0]),velocity:[0,0,0],state:'attached',quality:1,targetId:null});
    this._event('info','Scene ready. Known lineage gates donor–recipient compatibility.');
    return this.snapshot();
  }
  _event(type,message) {this.events.push({time:this.time,type,message});if(this.events.length>180)this.events.shift();}
  _setPhase(phase,status) {this.phase=phase;this.phaseTime=0;this.phaseElapsed=0;this.status=status??phase.replaceAll('_',' ');this.nominalStatus=this.status;}
  _abort(reason) {this.running=false;this.pendingDecision=null;this._setPhase('aborted',reason);this._event('error',reason);}
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
    const side=goal[0]<0?-4.2:4.2;
    const clear=horizontal>1.5?[start,[start[0],start[1],cruise+.35],[side,start[1],cruise+.35],[side,goal[1],cruise+.35],[goal[0],goal[1],cruise+.35],goal]:[start,goal];
    const mode=this.route?.mode??this.scene.routeMode;
    this.route={mode,goal:clone(goal),waypoints:clone((mode==='clearance'?clear:direct).slice(1)),index:0,alternatives:[{id:'direct',label:'Direct over-reef transit',points:direct},{id:'clearance',label:'Wide corridor · elevated clearance',points:clear}]};
    this.robot.target=clone(this.route.waypoints[0]);
  }
  _advanceRoute() {
    if(this.route.index<this.route.waypoints.length-1&&norm(sub(this.robot.position,this.robot.target))<.28){this.route.index++;this.robot.target=clone(this.route.waypoints[this.route.index]);}
    else if(this.route.index===this.route.waypoints.length-1)this.robot.target=clone(this.route.goal);
  }
  _updateWildlife(dt) {
    const t=this.time,previous=new Map(this.wildlife.map(a=>[a.id,a.position]));
    const animals=[];
    for(let i=0;i<8;i++){
      const phase=t*.13+i*.65,x=3.7*Math.sin(phase)+.18*(i%3),y=2.7*Math.cos(phase*.79)+.12*(i%2),z=terrainHeight(x,y)+1.05+.15*Math.sin(phase*1.7);
      animals.push({id:`fish-${i+1}`,type:'fish',position:[x,y,z],radius:.1});
    }
    for(let i=0;i<3;i++) {const x=-2.5+i*2+.45*Math.sin(t*.06+i),y=.2+.7*Math.cos(t*.045+i);animals.push({id:`crab-${i+1}`,type:'crab',position:[x,y,terrainHeight(x,y)+.07],radius:.16});}
    const x=4*Math.sin(t*.055-.9),y=.45*Math.sin(t*.07);animals.push({id:'turtle-1',type:'turtle',position:[x,y,terrainHeight(x,y)+1.65],radius:.42});
    this.wildlife=animals.map(a=>({...a,velocity:dt&&previous.has(a.id)?scale(sub(a.position,previous.get(a.id)),1/dt):[0,0,0]}));
  }
  _nearHabitat(radius) {
    const [x,y]=this.robot.position,result=[];
    for(let gx=Math.floor((x-radius)/4);gx<=Math.floor((x+radius)/4);gx++)for(let gy=Math.floor((y-radius)/4);gy<=Math.floor((y+radius)/4);gy++)for(const c of this.habitatIndex.get(`${gx},${gy}`)??[])if(Math.hypot(c.position[0]-x,c.position[1]-y)<=radius)result.push(c);
    return result;
  }
  _sonar() {
    const range=6,origin=this.robot.position;
    const sources=[...this.obstacles.map(o=>({...o,type:'rock',position:add(o.position,[0,0,o.radius*.5])})),...this.colonies.map(c=>({...c,type:'coral',position:add(c.position,[0,0,coralHeight(c)*.5])})),...this._nearHabitat(range).map(c=>({...c,type:'habitat',position:add(c.position,[0,0,c.height*.5])})),...this.wildlife];
    const contacts=sources.map(o=>{const delta=sub(o.position,origin),distance=norm(delta);return {...o,distance,bearing:Math.atan2(Math.sin(Math.atan2(delta[1],delta[0])-this.robot.yaw),Math.cos(Math.atan2(delta[1],delta[0])-this.robot.yaw))};}).filter(o=>o.distance<=range).filter(o=>!this.obstacles.some(rock=>{
      if(rock.id===o.id)return false;const centre=add(rock.position,[0,0,rock.radius*.5]),v=sub(o.position,origin),w=sub(centre,origin),u=v.reduce((a,x,i)=>a+x*w[i],0)/Math.max(.0001,o.distance**2);return u>.03&&u<.95&&norm(sub(add(origin,scale(v,u)),centre))<rock.radius*.75;
    })).sort((a,b)=>a.distance-b.distance).map(({id,type,distance,bearing,position})=>({id,type,distance,bearing,position}));
    return {range,contacts:contacts.slice(0,64),totalContacts:contacts.length,omittedContacts:Math.max(0,contacts.length-64),closestRange:contacts[0]?.distance??null,model:'Synthetic analytic line-of-sight ranges; rock occlusion only, not acoustic propagation',visibilityLimited:false,maxContacts:64};
  }
  _fragment(){return this.fragments.find(f=>f.id===this.fragmentId);}
  _donor(){return this.colonies.find(c=>c.id===this.donorId);}
  _recipient(){return this.colonies.find(c=>c.id===this.targetId);}
  _compatible(d,t){return d?.health==='healthy'&&t?.health==='bleached_alive'&&d.genet&&d.genet===t.genet&&d.species===t.species;}
  _choosePair() {
    for(const t of this.colonies) {
      if(t.health!=='bleached_alive'||!t.genet||this.assisted.has(t.id))continue;
      for(const d of this.colonies) {
        const f=this.fragments.find(f=>f.donorId===d.id&&f.state==='attached');
        if(!this._compatible(d,t)||!f)continue;
        this.targetId=t.id;this.donorId=d.id;this.fragmentId=f.id;this.retries=0;this.metrics.attempts++;
        this._setGripTarget(this._top(t),1);this._setPhase('inspect_recipient','Inspecting living recipient');this._event('plan',`Pair ${d.id} → ${t.id}; same registered genet ${d.genet}.`);return;
      }
    }
    this._abort(`No eligible pair remains (${this.metrics.placed}/${this.scene.missionGoal} verified). Unknown lineage and dead coral are excluded.`);
  }
  _gate(kind,message) {
    const allowedActions=kind==='inspect'?['proceed','abort']:['retry','abort'];
    const request={id:`decision-${++this.decisionCounter}`,kind,allowedActions,observation:{phase:this.phase,reason:message,donorId:this.donorId,targetId:this.targetId,compatible:!!this._compatible(this._donor(),this._recipient()),water:clone(this.water),metrics:clone(this.metrics),fragment:clone(this._fragment()??null),sonar:this._sonar(),wildlife:clone(this.wildlife),route:clone(this.route),retryBudget:3-this.retries}};
    if(this.controller==='gemini') {this.robot.target=clone(this.robot.position);this.pendingDecision=request;this.status='Waiting for Gemini decision';this.nominalStatus=this.status;this._event('decision',message+' Awaiting live Gemini.');}
    else {this.pendingDecision=request;this._applyDecision(request.id,allowedActions[0],message,'scripted');}
  }
  _applyDecision(id,action,reason,source) {
    const pending=this.pendingDecision;
    if(!pending||pending.id!==id)throw new Error('Decision is stale or does not exist');
    if(!pending.allowedActions.includes(action))throw new Error('Decision action is not allowed');
    if(this.controller==='gemini' && source!=='gemini')throw new Error('Gemini mode requires an explicit Gemini result');
    if(typeof reason!=='string'||reason.length>1600)throw new Error('Decision reason must be text of at most 1600 characters');
    this.pendingDecision=null;this.decision={id,action,reason,source,time:this.time};this.metrics.decisionCount++;this._event('decision',`${source}: ${action} — ${reason}`);
    if(action==='abort'){this._abort('Controller requested a safe abort.');return;}
    if(pending.kind==='inspect') {
      if(!this._compatible(this._donor(),this._recipient())){this._abort('Compatibility gate failed.');return;}
      this._setGripTarget(this._fragment().position);this._setPhase('approach','Approaching approved donor cutting');
    } else if(pending.kind==='drop') {
      this._setPhase('recover_drop','Locating dropped cutting');
    } else if(pending.kind==='cut') {
      const f=this.fragments.find(f=>f.donorId===this.donorId&&f.state==='attached');
      if(!f){this._abort('Donor stock exhausted after rejected cuts.');return;}
      this.fragmentId=f.id;this._setGripTarget(f.position);this._setPhase('approach','Retrying with a fresh donor cutting');
    } else if(pending.kind==='placement') {this._setPhase('recover_placement','Regrasping unstable placement');}
  }
  command(data) {
    if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('Command must be an object');
    const action=data.action;
    switch(action) {
      case 'run': if(this.completed||this.phase==='aborted')throw new Error('Reset before starting another run');this.running=true;if(this.phase==='idle')this._setPhase('survey','Surveying the editable reef');break;
      case 'pause':this.running=false;break;
      case 'reset':return this.reset();
      case 'set_water': {
        const next={current:data.current===undefined?this.water.current:finite(data.current,0,.8,'Current'),visibility:data.visibility===undefined?this.water.visibility:finite(data.visibility,.2,20,'Visibility')};
        this.water=next;this.scene.water=clone(next);this.restoreCurrent=null;this.surgeUntil=0;this._event('environment','Water conditions updated.');break;
      }
      case 'set_route':if(!['direct','clearance'].includes(data.mode))throw new Error('Unknown route mode');this.scene.routeMode=data.mode;this.route.mode=data.mode;this._planRoute(this.route.goal);this._event('plan',`Selected ${data.mode} route; replanning from current position.`);break;
      case 'set_controller':
        if(!['scripted','gemini'].includes(data.mode))throw new Error('Unknown controller');
        this.controller=data.mode;
        if(this.pendingDecision&&data.mode==='scripted')this._applyDecision(this.pendingDecision.id,this.pendingDecision.allowedActions[0],'Operator selected deterministic controller.','scripted');
        break;
      case 'inject_fault':
        if(!FAULTS.includes(data.kind))throw new Error('Unknown fault');
        if(this.phase==='aborted'||this.completed)throw new Error('Reset before injecting faults');
        if(data.kind==='current_surge'){this.restoreCurrent??=this.water.current;this.water.current=Math.min(.8,this.water.current+.38);this.surgeUntil=this.time+12;this._event('fault','Current surge: elevated drift and safe-hold control for 12 seconds.');}
        else if(data.kind==='sensor_dropout'){this.dropoutUntil=this.time+8;this._event('fault','Camera dropout: perception unavailable for 8 seconds.');}
        else if(data.kind==='drop'&&this._fragment()?.state==='carried')this._drop();
        else {if(this.faults.length>=10)throw new Error('At most ten queued faults');this.faults.push(data.kind);this._event('fault',`${data.kind.replaceAll('_',' ')} armed for its next applicable phase.`);}break;
      case 'apply_decision':this._applyDecision(data.id,data.decision??data.choice,data.reason,data.source);break;
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
    f.state='dropped';f.position=clone(this.robot.gripper);f.velocity=add(this.robot.velocity,[.12,0,-.08]);this.robot.holding=null;this.robot.gripperOpen=1;this.metrics.drops++;this._event('fault','Grip lost: the same cutting is falling under submerged weight and drag.');this._setPhase('recovery','Assessing dropped cutting');this._retry('drop','Locate, recover and regrasp the existing cutting.');
  }
  step(dt) {
    finite(dt,0,60,'Time step');if(!this.running)return this.snapshot();
    this.accumulator+=dt;
    while(this.accumulator>=1/60-1e-10&&this.running){this.accumulator-=1/60;this._tick(1/60);}
    return this.snapshot();
  }
  _physics(dt,hold=false) {
    const r=this.robot;const old=clone(r.position);const err=sub(r.target,r.position);let force=err.map((v,i)=>18*v-14*r.velocity[i]);
    // Approximate habitat envelopes protect robot body; active tool targets are exempt.
    const habitat=[...this.obstacles.map(o=>({...o,position:add(o.position,[0,0,o.radius*.5])})),...this.colonies.filter(c=>c.id!==this.donorId&&c.id!==this.targetId).map(c=>({id:c.id,position:add(c.position,[0,0,coralHeight(c)*.45]),radius:Math.max(c.radius*.72,coralHeight(c)*.45),top:c.position[2]+coralHeight(c)})),...this._nearHabitat(2.6).map(c=>({id:c.id,position:add(c.position,[0,0,c.height*.45]),radius:Math.max(c.radius*.72,c.height*.45),top:c.position[2]+c.height,influence:.15}))];
    const nearby=this.wildlife.filter(a=>norm(sub(r.position,a.position))<a.radius+(this.wildlifeYield?.7:a.type==='crab'?.58:.45));
    const yielding=nearby.length>0;
    if(yielding&&!this.wildlifeYield){this.metrics.wildlifeAvoidances++;this._event('hold',`Yielding to ${nearby[0].type}; pausing progress and reducing thrust.`);}
    if(!yielding&&this.wildlifeYield)this._event('recovery','Wildlife clear; resuming selected route.');
    this.wildlifeYield=yielding;
    if(yielding){force=scale(r.velocity,-22);for(const a of nearby){const d=sub(r.position,a.position),n=norm(d);if(n>.001)force=add(force,scale(d,12*(a.radius+.85-n)/n));}}
    for(const o of habitat){if(o.top!==undefined&&r.position[2]-.3>o.top+.15)continue;const d=sub(r.position,o.position),n=norm(d),safe=o.radius+.3,influence=o.influence??.65;if(n<safe+influence&&n>1e-6){const gain=24*(safe+influence-n);force=add(force,scale(d,gain/n));}}
    const magnitude=norm(force);if(magnitude>42)force=scale(force,42/magnitude);
    const flow=[this.water.current,0,0];
    for(let i=0;i<3;i++){const relative=r.velocity[i]-flow[i];const drag=-7*relative*Math.abs(relative)-2*relative;const acceleration=(force[i]+drag+(i===2?.15:0))/18;r.velocity[i]+=acceleration*dt;r.position[i]+=r.velocity[i]*dt;}
    r.position[2]=Math.max(terrainHeight(...r.position)+.7,r.position[2]);
    for(const o of habitat){if(o.top!==undefined&&r.position[2]-.3>o.top+.15)continue;const d=sub(r.position,o.position),n=norm(d),safe=o.radius+.3;if(n<safe){const unit=n>1e-6?scale(d,1/n):[0,0,1];r.position=add(o.position,scale(unit,safe));r.velocity=[0,0,0];if(this.time-(this.lastCollision??-10)>1){this.metrics.collisions++;this.metrics.habitatAvoidances++;this.lastCollision=this.time;this._event('warning','Obstacle contact detected; controller replanning locally.');}}}
    const movement=norm(sub(r.position,old));this.metrics.distance+=movement;this.metrics.energy+=norm(force)*norm(r.velocity)*dt;
    if(norm(r.velocity)>.05)r.yaw=Math.atan2(r.velocity[1],r.velocity[0]);r.gripper=add(r.position,[0,0,-.65]);
    for(const f of this.fragments){
      if(f.state==='carried'||f.state==='grasped'){f.position=clone(r.gripper);f.velocity=clone(r.velocity);}
      else if(f.state==='dropped'||f.state==='rejected'){
        // Effective submerged gravity: coral density 2,500 kg/m³ in seawater 1,025 kg/m³.
        f.velocity[0]+=(this.water.current-f.velocity[0])*1.5*dt;f.velocity[1]-=f.velocity[1]*1.5*dt;f.velocity[2]+=(-5.79-4*f.velocity[2]*Math.abs(f.velocity[2]))*dt;
        f.position=add(f.position,scale(f.velocity,dt));const bed=terrainHeight(...f.position)+.07;if(f.position[2]<bed){f.position[2]=bed;f.velocity=[0,0,0];}
      }
    }
  }
  _tick(dt) {
    this.time+=dt;this._updateWildlife(dt);
    if(this.time>=this.surgeUntil&&this.restoreCurrent!==null){this.water.current=this.restoreCurrent;this.restoreCurrent=null;this._event('environment','Current surge passed.');}
    const environmentUnsafe=this.water.visibility<1.5||this.water.current>.42||this.time<this.dropoutUntil;
    if(environmentUnsafe){
      if(!this.environmentHold){this.holdTarget=clone(this.robot.target);this.robot.target=clone(this.robot.position);this._event('hold','Safe hold: current, visibility or camera quality exceeds operating limits.');}
      this.environmentHold+=dt;this.status='Safe hold · waiting for usable sensing and current';this._physics(dt,true);
      if(this.environmentHold>30)this._abort('Environmental limits exceeded for 30 seconds. No unsafe manipulation attempted.');return;
    }
    if(this.environmentHold){this.robot.target=this.holdTarget;this.environmentHold=0;this.status=this.nominalStatus;this._event('recovery','Conditions recovered; resuming from the same mission state.');}
    if(this.pendingDecision){this._physics(dt,true);return;}
    this.phaseElapsed+=dt;
    if(this.phaseElapsed>90){this._abort('Motion timeout: target cannot be reached safely.');return;}
    const f=this._fragment(),donor=this._donor(),target=this._recipient();
    if(this.phase==='recover_drop'&&f)this._setGripTarget(f.position);
    if(this.phase==='recover_placement'&&f)this._setGripTarget(f.position);
    this._advanceRoute();this._physics(dt);
    const routeFinished=this.route.index===this.route.waypoints.length-1;
    const arrived=routeFinished&&!this.wildlifeYield&&norm(sub(this.robot.position,this.robot.target))<.16&&norm(this.robot.velocity)<.22;
    if(arrived||this.phase==='survey')this.phaseTime+=dt;
    const done=this.phaseTime>=(DURATIONS[this.phase]??1);
    if(!done)return;
    switch(this.phase){
      case 'survey':this._choosePair();break;
      case 'inspect_recipient':this._setGripTarget(this._top(donor),1);this._setPhase('inspect_donor','Inspecting compatible healthy donor');break;
      case 'inspect_donor':this._setPhase('approval','Awaiting harvest approval');this._gate('inspect','Both living colonies inspected; known lineage and species match.');break;
      case 'approach':this.robot.gripperOpen=.15;this._setPhase('grasp','Closing jaws around the attached cutting');break;
      case 'grasp':this.robot.gripperOpen=0;this.robot.holding=f.id;f.state='grasped';this._setPhase('cut','Executing bounded donor cut');break;
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
    return clone({time:this.time,running:this.running,seed:this.scene.seed,phase:this.phase,phaseProgress:clamp(this.phaseTime/(DURATIONS[this.phase]??1),0,1),controller:this.controller,status:this.status,water:this.water,colonies:this.colonies,obstacles:this.obstacles,terrain:{model:'Shared sloping limestone relief',units:'metres'},habitatCount:this.habitat.length,wildlife:this.wildlife,sonar:this._sonar(),route:this.route,robot:this.robot,fragments:this.fragments,targetId:this.targetId,donorId:this.donorId,metrics:this.metrics,events:this.events,decision:this.decision,pendingDecision:this.pendingDecision,completed:this.completed,missionGoal:this.scene.missionGoal,queuedFaults:this.faults,environmentHold:this.environmentHold,physics:{model:'Reduced buoyancy, thrust and quadratic drag; bounded kinematic grip/contact',massKg:18,maxThrustN:42,stepSeconds:1/60},limits:{biology:'Mechanical verification only; no tissue fusion or biological recovery',perception:'Synthetic known scene labels; no image-based genotype inference',contacts:'Approximate obstacle collision and fragment contact; no fracture or glue chemistry'}});
  }
  evaluate({seeds=[42,43,44],scenario='baseline'}={}) {
    if(!Array.isArray(seeds)||!seeds.length||seeds.length>30)throw new Error('Evaluation accepts 1–30 seeds');
    if(!['baseline',...FAULTS].includes(scenario))throw new Error('Unknown evaluation scenario');
    const runs=seeds.map(seed=>{const scene=this.exportScene();scene.seed=seed;const sim=new ReefLab(scene);if(scenario!=='baseline')sim.command({action:'inject_fault',kind:scenario});sim.command({action:'run'});for(let i=0;i<600&&sim.running;i++)sim.step(1);const timedOut=sim.running;if(timedOut)sim._abort('Evaluation exceeded its 600-second simulation budget.');const s=sim.snapshot();return {seed,success:s.completed,timedOut,time:s.time,phase:s.phase,metrics:s.metrics,reason:s.status,unconsumedFaults:s.queuedFaults};});
    return {scenario,controller:'scripted',timeLimitSeconds:600,seedVariation:'Fixed exported scene geometry; seeds vary procedural cut-quality samples only. Fault timing is deterministic.',model:'Browser reduced physics; synthetic fault injection',runs,successRate:runs.filter(r=>r.success).length/runs.length};
  }
}
