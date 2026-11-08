import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

// Execute the production browser functions, replacing only UI, transport and clock.
const source=readFileSync(new URL('../web/lab/app.mjs',import.meta.url),'utf8');
const functions=['cancelAssistance','resetAssistanceEpisode','syncAssistanceEpisode','scheduleAssistanceRetry','maybeRequestAssistance','assistanceObservation','requestAssistance','requestBasePipeline','assistanceTarget','stageAssistanceContext','takeAssistanceContext','assistanceContextText','renderAssistance'];
function functionSource(name){
 const start=source.search(new RegExp(`(?:async )?function ${name}\\(`));
 assert.ok(start>=0,`${name} must exist`);
 const lineEnd=source.indexOf('\n',start),first=source.slice(start,lineEnd);
 return first.endsWith('}')?first:source.slice(start,source.indexOf('\n}',lineEnd)+2);
}
const issue={kind:'perception_uncertainty',key:'capture-1',reason:'Target appearance is unclear.'};
const unavailable=()=>({ok:false,status:502,json:async()=>({error:'Provider unavailable'})});
const advice=(body,action='rescan')=>({ok:true,status:200,json:async()=>({source:'argon_assist',requestId:body.id,episodeId:body.episodeId,advisoryOnly:true,controlAuthority:false,action,reason:'Inspect the target again.',model:'fixture-argon'})});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(responder=unavailable){
 const state={time:10,phase:'inspect_donor',running:true,controller:'base_station',pilot:{mode:'autonomous'},targetId:'recipient-1',donorId:'donor-1',fragmentId:'fragment-2',robot:{position:[0,0,1],velocity:[0,0,0],holding:null},water:{current:0,currentVector:[0,0,0],visibility:8},metrics:{drops:0},fragments:[{id:'fragment-1',donorId:'donor-1',state:'available',position:[1,0,0]},{id:'fragment-2',donorId:'donor-1',state:'available',position:[2,0,0],detachedAtStart:true}],intelligence:{onboard:{observations:[]}},assistanceHold:null};
 const calls=[],actions=[],logs=[],timers=new Map(),captures=[],perceptions=[],elements=new Map();let serial=0;
 const noop=()=>{};
 const lab={scene:{},snapshot:()=>structuredClone(state),get phase(){return state.phase;},get assistanceHold(){return state.assistanceHold;},_externalHealth:()=>({ready:true}),_fragmentEvidenceReady:()=>true,command(data){actions.push(structuredClone(data));if(data.action==='set_assistance_hold'){if(data.active)state.assistanceHold??={since:state.time};else state.assistanceHold=null;}if(data.action==='abort'){state.phase='aborted';state.running=false;state.assistanceHold=null;}}};
 const context=vm.createContext({lab,AbortController,TextEncoder,TypeError,console,crypto:{randomUUID:()=>`episode-${++serial}`},performance:{now:()=>state.time*1000},setTimeout:(callback,delay)=>{const id=++serial;timers.set(id,{callback,delay});return id;},clearTimeout:id=>timers.delete(id),fetch:async(path,options)=>{const body=JSON.parse(options.body);calls.push({path,body,signal:options.signal});return responder(body,options);},renderUI:noop,renderPilot:noop,renderArchitecture:noop,rememberObservations:noop,toast:noop,$:id=>{if(!elements.has(id))elements.set(id,{set innerHTML(value){throw Error('HTML rendering is forbidden');}});return elements.get(id);},clock:String,label:String,logActivity:(...args)=>logs.push(args),scene:{ready:true,captureObservation(options){captures.push(options);return{mimeType:'image/jpeg',data:'fixture',camera:'tool',time:state.time,imageFocus:{source:'tracked_camera_projection',target:[.5,.5]}};}},baseRequest:async(path,payload)=>{perceptions.push(payload);return{source:'gemma',requestId:payload.id,targetKind:payload.observation.targetKind,fragmentVisible:true,gripperState:'empty',model:'fixture-gemma',observations:[],frameTime:state.time};}});
 vm.runInContext(`let snapshot=lab.snapshot(),generation=0,assistEpisodeId='episode-initial',assistScene=lab.scene,assistLastTime=0,assistCount=0,assistIssues=new Set(),assistInflight=null,assistHolding=false,assistIssue=null,lastAssist=null,assistLastDrop=0,assistCurrentActive=false,assistCurrentSince=null,assistCurrentHandled=false,assistRetry=null,assistContext=null,baseInflight=null,baseAttempted=new Set(),evidenceHold=false,modelUnavailable=false,baseError='',lastPerception=null,packetCount=0,transportState='',lastPlanning=null;function command(data){lab.command(data);snapshot=lab.snapshot();return true;}\n${functions.map(functionSource).join('\n')}`,context);
 return{state,calls,actions,logs,timers,captures,perceptions,elements,eval:code=>vm.runInContext(code,context),request:()=>vm.runInContext(`requestAssistance(${JSON.stringify(issue)})`,context),tick:async time=>{state.time=time;vm.runInContext('snapshot=lab.snapshot();syncAssistanceEpisode(snapshot);maybeRequestAssistance()',context);await settle();}};
}

test('transient assistance errors retry automatically with fresh telemetry and stable three-attempt budget',async()=>{
 const h=harness();await h.request();assert.equal(h.calls.length,1);assert.equal(h.eval('assistRetry.dueAt'),12);
 await h.tick(11.9);assert.equal(h.calls.length,1);
 h.state.water.currentVector=[.1,.2,0];await h.tick(12);assert.equal(h.calls.length,2);assert.equal(h.calls[1].body.observation.time,12);assert.deepEqual(h.calls[1].body.observation.water.currentVector,[.1,.2,0]);
 await h.tick(16);assert.equal(h.calls.length,3);await h.tick(20);assert.equal(h.calls.length,3);assert.equal(h.eval('assistRetry'),null);
 assert.equal(new Set(h.calls.map(c=>c.body.episodeId)).size,1);assert.equal(new Set(h.calls.map(c=>c.body.id)).size,3);assert.deepEqual(h.calls.map(c=>c.body.observation.assistanceAttemptsRemaining),[2,1,0]);
 assert(h.state.assistanceHold);assert(!h.actions.some(a=>a.action==='request_rescan'||a.action==='apply_decision'));assert.equal(h.state.assistanceHold.since,10);
});
test('inflight assistance is not duplicated and successful retry clears scheduling without granting motion',async()=>{
 let finish,attempt=0;const h=harness(body=>++attempt===1?unavailable():new Promise(resolve=>{finish=()=>resolve(advice(body));}));
 await h.request();await h.tick(12);await h.tick(13);assert.equal(h.calls.length,2);assert.equal(h.eval('assistCount'),2);
 finish();await settle();assert.equal(h.eval('assistRetry'),null);assert.equal(h.eval('assistHolding'),false);assert.equal(h.state.assistanceHold,null);assert.equal(h.actions.filter(a=>a.action==='request_rescan').length,1);assert(!h.actions.some(a=>a.action==='apply_decision'));
 await h.tick(20);assert.equal(h.calls.length,2);
});
test('HOLD advice gets bounded rechecks while keeping the original physical hold',async()=>{
 const h=harness(body=>advice(body,'hold'));await h.request();await h.tick(12);await h.tick(16);await h.tick(30);
 assert.equal(h.calls.length,3);assert.equal(h.state.assistanceHold.since,10);assert(!h.actions.some(a=>a.action==='request_rescan'||a.action==='apply_decision'));
});
test('late failures cannot extend the hold deadline or start retries after it',async()=>{
 let finish;const h=harness(()=>new Promise(resolve=>{finish=()=>resolve(unavailable());}));h.state.assistanceHold={since:0};h.state.time=89;
 const pending=h.request();assert.equal([...h.timers.values()][0].delay,1000);finish();await pending;
 assert.equal(h.eval('assistRetry'),null);h.state.time=90;await h.request();assert.equal(h.calls.length,1);assert.equal(h.state.assistanceHold.since,0);
});
test('episode reset cancels inflight request and discards its later response',async()=>{
 let finish;const h=harness(body=>new Promise(resolve=>{finish=()=>resolve(advice(body));}));const pending=h.request();h.eval('resetAssistanceEpisode()');assert(h.calls[0].signal.aborted);finish();await pending;
 assert.equal(h.eval('assistCount'),0);assert.equal(h.eval('assistRetry'),null);assert(!h.actions.some(a=>a.action==='request_rescan'));await h.tick(20);assert.equal(h.calls.length,1);
});
test('explicit cancellation ignores a transport response that arrives after abort',async()=>{
 let finish;const h=harness(body=>new Promise(resolve=>{finish=()=>resolve(advice(body));}));const pending=h.request();h.eval('cancelAssistance()');finish();await pending;
 assert(h.calls[0].signal.aborted);assert.equal(h.eval('assistRetry'),null);assert(!h.actions.some(a=>a.action==='request_rescan'));assert.equal(h.eval('lastAssist'),null);
});
test('active request timeout retries, but cancellation AbortError cannot resurrect the retry',async()=>{
 const transport=(body,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('Aborted'),{name:'AbortError'}))));
 const active=harness(transport),pending=active.request();[...active.timers.values()][0].callback();await pending;
 assert.equal(active.eval('assistRetry.dueAt'),12);assert(active.state.assistanceHold);
 const canceled=harness(transport),canceledPending=canceled.request();canceled.eval('cancelAssistance()');await canceledPending;
 assert.equal(canceled.eval('assistRetry'),null);assert.equal(canceled.eval('assistHolding'),false);
});
test('pause defers retries and cancellation or terminal state discards scheduled work',async()=>{
 const h=harness();await h.request();h.state.running=false;await h.tick(12);assert.equal(h.calls.length,1);h.state.running=true;await h.tick(13);assert.equal(h.calls.length,2);
 h.eval('cancelAssistance()');await h.tick(20);assert.equal(h.calls.length,2);
 const terminal=harness();await terminal.request();terminal.state.phase='aborted';terminal.state.running=false;await terminal.tick(20);assert.equal(terminal.eval('assistRetry'),null);assert.equal(terminal.calls.length,1);
});
test('malformed or unauthorized advice never schedules an automatic retry or grants motion',async()=>{
 const h=harness(body=>advice(body,'proceed'));await h.request();await h.tick(30);assert.equal(h.calls.length,1);assert.equal(h.eval('assistRetry'),null);assert(h.state.assistanceHold);assert(!h.actions.some(a=>a.action==='apply_decision'||a.action==='request_rescan'));
});
test('explicit nonretryable gateway failure overrides HTTP 502 while retryable timeout may retry',async()=>{
 for(const retryable of [false,true]){
  const h=harness(()=>({ok:false,status:502,json:async()=>({error:'Assistance failed',retryable})}));await h.request();await h.tick(12);
  assert.equal(h.calls.length,retryable?2:1);assert(h.state.assistanceHold);assert.equal(h.state.assistanceHold.since,10);assert(!h.actions.some(a=>a.action==='request_rescan'||a.action==='apply_decision'));
  if(!retryable)assert.equal(h.eval('assistRetry'),null);
 }
});
test('assistance binds the selected fragment and never substitutes another donor fragment',async()=>{
 const h=harness();h.state.fragments[1].state='dropped';await h.request();assert.equal(h.calls[0].body.observation.fragment.id,'fragment-2');assert.equal(h.calls[0].body.observation.fragment.state,'dropped');
 h.state.fragmentId='missing';h.eval('snapshot=lab.snapshot()');assert.equal(h.eval('assistanceObservation().fragment'),null);
 h.state.fragmentId=null;h.state.perceptionRequest={targetKind:'fragment',targetId:'fragment-2'};h.eval('snapshot=lab.snapshot()');assert.equal(h.eval('assistanceObservation().fragment.id'),'fragment-2');
 h.state.perceptionRequest=null;h.state.pendingDecision={observation:{fragment:{id:'fragment-2'}}};h.eval('snapshot=lab.snapshot()');assert.equal(h.eval('assistanceObservation().fragment.id'),'fragment-2');
});
for(const kind of ['colony','fragment'])test(`${kind} capture sends projection of its explicit target with matching provenance`,async()=>{
 const h=harness();h.state.phase=kind==='fragment'?'inspect_fragment':'inspect_donor';h.state.perceptionRequest={id:'capture-actual',targetId:kind==='fragment'?'fragment-2':'donor-1',targetKind:kind,targetPosition:[2,3,1],ready:true};h.eval('snapshot=lab.snapshot()');await h.eval('requestBasePipeline()');
 assert.equal(h.captures.length,1);assert.equal(h.captures[0].includeProjection,true);assert.deepEqual([...h.captures[0].targetPosition],[2,3,1]);const payload=h.perceptions[0];assert.equal(payload.observation.cameraTargetId,h.state.perceptionRequest.targetId);assert.equal(payload.observation.captureRequestId,'capture-actual');assert.equal(payload.observation.imageFocus.source,'tracked_camera_projection');assert.equal(payload.observation.imageFocus.target[0],.5);assert.equal(payload.image.imageFocus,undefined);assert.equal(h.calls.length,0);
});

const contextAdvice=(body,patch={},action='rescan')=>({ok:true,status:200,json:async()=>({source:'argon_assist',requestId:body.id,episodeId:body.episodeId,advisoryOnly:true,controlAuthority:false,action,reason:'Reinspect the visible fragment.',model:'fixture-argon',advisoryContext:{source:'argon_assist',requestId:body.id,episodeId:body.episodeId,targetId:body.observation.cameraTargetId,targetKind:body.observation.targetKind,previousCaptureRequestId:body.observation.captureRequestId,issuedAt:body.observation.time,expiresAt:body.observation.time+60,guidance:'Compare the detached shape with the new frame; do not assume it is healthy.',observations:['The earlier model was uncertain.'],checks:['Check visible shape and gripper occupancy.'],advisoryOnly:true,controlAuthority:false,...patch}})});
function setCapture(h,id='capture-before',targetId='fragment-2',targetKind='fragment'){
 h.state.phase='inspect_fragment';h.state.perceptionRequest={id,targetId,targetKind,targetPosition:[2,3,1],ready:true};h.eval('snapshot=lab.snapshot()');
}
test('Argon context accompanies exactly one new actual camera request and never becomes handling evidence',async()=>{
 const h=harness(body=>contextAdvice(body));setCapture(h);await h.request();assert(h.eval('assistContext'));assert.equal(h.calls[0].body.observation.cameraTargetId,'fragment-2');assert.equal(h.calls[0].body.observation.captureRequestId,'capture-before');
 h.state.time=11;setCapture(h,'capture-after');await h.eval('requestBasePipeline()');
 assert.equal(h.captures.length,1);const sent=h.perceptions[0];assert.equal(sent.image.time,11);assert.equal(sent.episodeId,h.calls[0].body.episodeId);assert.equal(sent.advisoryContext.targetId,'fragment-2');assert.equal(sent.advisoryContext.previousCaptureRequestId,'capture-before');assert.equal(sent.advisoryContext.controlAuthority,false);assert.equal(sent.observation.advisoryContext,undefined);assert.equal(h.eval('assistContext'),null);assert(!h.actions.some(a=>a.action==='apply_decision'));
 h.state.time=12;setCapture(h,'capture-later');await h.eval('requestBasePipeline()');assert.equal(h.perceptions[1].advisoryContext,undefined);assert.equal(h.perceptions[1].episodeId,undefined);
});
test('context is omitted for a different target, kind, episode, replayed capture or nonfresh frame',async()=>{
 for(const change of ['target','kind','episode','capture','frame']){
  const h=harness(body=>contextAdvice(body));setCapture(h);await h.request();h.state.time=11;setCapture(h,'capture-after');
  if(change==='target')h.state.perceptionRequest.targetId='fragment-1';if(change==='kind')h.state.perceptionRequest.targetKind='colony';if(change==='episode')h.eval("assistEpisodeId='different-episode'");if(change==='capture')h.state.perceptionRequest.id='capture-before';if(change==='frame')h.state.time=10;h.eval('snapshot=lab.snapshot()');await h.eval('requestBasePipeline()');
  assert.equal(h.perceptions.length,1,change);assert.equal(h.perceptions[0].advisoryContext,undefined,change);if(change==='episode')assert.equal(h.eval('assistContext'),null,change);else assert(h.eval('assistContext'),change);
 }
});
test('advice expires by simulation or wall clock and clears on cancellation, reset or terminal phase',async()=>{
 for(const change of ['simulation','wall','cancel','reset','abort','complete','recipient','donor','fragment']){
  const h=harness(body=>contextAdvice(body));setCapture(h);await h.request();assert(h.eval('assistContext'));
  if(change==='simulation')h.state.time=71;if(change==='wall')h.eval('performance.now=()=>70000');if(change==='cancel')h.eval('cancelAssistance()');if(change==='reset')h.eval('resetAssistanceEpisode()');if(change==='abort')h.state.phase='aborted';if(change==='complete')h.state.phase='complete';if(change==='recipient')h.state.targetId='recipient-2';if(change==='donor')h.state.donorId='donor-2';if(change==='fragment')h.state.fragmentId='fragment-1';
  h.eval('snapshot=lab.snapshot();syncAssistanceEpisode(snapshot)');assert.equal(h.eval('assistContext'),null,change);
 }
});
test('malformed, mismatched or authority-bearing advice remains held without rescan',async()=>{
 for(const patch of [{episodeId:'other'},{targetId:'other'},{targetKind:'colony'},{previousCaptureRequestId:'other'},{requestId:'other'},{controlAuthority:true},{advisoryOnly:false},{expiresAt:1000},{issuedAt:0},{checks:[]},{checks:['x'.repeat(201)]},{observations:['x'.repeat(241)]},{guidance:'x'.repeat(1201)},{grantPermission:true}]){
  const h=harness(body=>contextAdvice(body,patch));setCapture(h);await h.request();assert.equal(h.eval('assistContext'),null);assert(h.state.assistanceHold);assert(!h.actions.some(a=>a.action==='request_rescan'||a.action==='apply_decision'));
 }
});
test('advisory display uses plain text and preserves uncertainty without granting permission',async()=>{
 const text='<img src=x onerror=alert(1)> inspect the new image';const h=harness(body=>contextAdvice(body,{guidance:text}));setCapture(h);await h.request();h.eval('renderAssistance(snapshot)');assert(h.elements.get('argon-assistance').textContent.includes(text));assert(h.elements.get('argon-assistance').textContent.includes('Untrusted advice only'));assert(!h.actions.some(a=>a.action==='apply_decision'));
});
test('valid context on hold or abort is displayable but never staged for a new perception request',async()=>{
 for(const action of ['hold','abort']){
  const h=harness(body=>contextAdvice(body,{},action));setCapture(h);await h.request();assert.equal(h.eval('assistContext'),null);assert(h.eval('lastAssist'));assert(!h.actions.some(a=>a.action==='request_rescan'));if(action==='abort')assert.equal(h.state.phase,'aborted');else assert(h.state.assistanceHold);
 }
});

test('fragment rescan advice survives the intermediate recipient inspection and reaches only its fresh fragment frame',async()=>{
 const h=harness(body=>contextAdvice(body));setCapture(h);await h.request();
 h.state.time=11;setCapture(h,'recipient-rescan','recipient-1','colony');h.eval('syncAssistanceEpisode(snapshot)');await h.eval('requestBasePipeline()');assert.equal(h.perceptions[0].advisoryContext,undefined);assert(h.eval('assistContext'));
 h.state.time=12;setCapture(h,'fragment-rescan');h.eval('syncAssistanceEpisode(snapshot)');await h.eval('requestBasePipeline()');assert.equal(h.perceptions[1].advisoryContext.targetId,'fragment-2');assert.equal(h.perceptions[1].image.time,12);assert.equal(h.eval('assistContext'),null);assert(!h.actions.some(a=>a.action==='apply_decision'));
});
