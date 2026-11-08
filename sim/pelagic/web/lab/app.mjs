import { ReefLab, defaultScene } from './simulation.mjs';
import { ReefScene } from './scene.mjs';
import { TelemetryRecorder } from './telemetry.mjs';
import { SemanticMemory } from './semantic-memory.mjs';
const $ = id => document.getElementById(id);
const randomSeed=()=>crypto.getRandomValues(new Uint32Array(1))[0];
const lab = new ReefLab({seed:randomSeed()});
const telemetry=new TelemetryRecorder();
const semanticMemory=new SemanticMemory({maxRecords:128});let memorySceneSignature='',memoryUiSignature='',memoryError='';
const pilotKeys=new Set();let lastPilot=0;
let pipCamera='tool',evidenceCamera='tool',lastPip=0,lastEvidence=0;const activityLog=[];
let scene, snapshot=lab.snapshot(), selectedId='donor-1', speed=1, report=null, suiteWorker=null;
let sceneSignature='', eventSignature='', lastUi=0, previous=performance.now(), frameCount=0, fpsStart=performance.now();
let geminiReady=false, inflight=null, attempted=null, generation=0, toastTimer;
const uplink={enabled:false,id:null,sequence:0,queue:[],accepted:0,skipped:0,lastSent:0,lastReceipt:null,error:'',controller:null};
let activationRequested=false,activationWasRunning=false,activationStarted=0,readinessTimer=null,warmupInflight=null;
let readinessTrace='',fallbackActive=false,modelUnavailable=false,evidenceHold=false;
let architecture=null,architectureError='',baseInflight=null,baseAttempted=new Set(),lastPerception=null,lastPlanning=null,baseError='',packetCount=0,transportState='Local recorder only';
const names={inspect_fragment:'Inspect fragment recovery',idle:'Ready to begin',survey:'Survey & pairing',inspect_recipient:'Inspect recipient',inspect_donor:'Inspect donor',approval:'Harvest approval',approach:'Approach donor',grasp:'Close gripper',cut:'Cut donor branch',retract:'Retract cutting',transport:'Transfer fragment',align:'Align contact',secure:'Secure fragment',release:'Release gripper',verify:'Verify placement',recover_drop:'Recover dropped fragment',recover_placement:'Correct placement',regrasp:'Regrasp fragment',recovery:'Assess setback',complete:'Mission complete',aborted:'Safe abort'};
const label = text => String(text??'').replaceAll('_',' ');
const publicText=text=>String(text??'').replace(/scripted/gi,'local fallback');
const autonomyReady=()=>fallbackActive||snapshot.controller==='base_station'&&!activationRequested&&stackReady();
const clock = seconds => `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function cancelDecision(){stopActivation();generation++;inflight?.abort();baseInflight?.abort();inflight=null;baseInflight=null;attempted=null;baseAttempted.clear();baseError='';lastPerception=null;lastPlanning=null;transportState='Local recorder only';$('retry-gemini').hidden=true;$('decision-fallback').hidden=true;}
function command(data){try{lab.command(data);snapshot=lab.snapshot();renderUI(true);renderPilot(snapshot);return true;}catch(error){toast(error.message);return false;}}
function reset(){cancelDecision();activityLog.length=0;pilotKeys.clear();telemetry.clear();lab.reset();if($('scenario').value==='compound')for(const kind of ['drop','bad_cut','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();renderUI(true);}
function switchTab(name){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-content').forEach(p=>p.hidden=p.id!==`tab-${name}`);}
for(const b of document.querySelectorAll('[data-tab]'))b.addEventListener('click',()=>switchTab(b.dataset.tab));
$('run').onclick=()=>{if(!snapshot.running&&snapshot.pilot?.mode!=='manual'&&!autonomyReady()){toast('Model services are not ready. The mission remains paused.');return;}command({action:snapshot.running?'pause':'run'});};
$('reset').onclick=reset;
$('new-reef').onclick=()=>regenerate(randomSeed());
$('apply-seed').onclick=()=>regenerate(Number($('reef-seed').value));
$('route-mode').onchange=()=>command({action:'set_route',mode:$('route-mode').value});
for(const id of ['show-routes','show-sonar','show-currents','show-regions'])$(id).onchange=()=>scene?.setOverlays?.({routes:$('show-routes').checked,sonar:$('show-sonar').checked,currents:$('show-currents').checked,regions:$('show-regions').checked});
$('speed').onchange=()=>{if(snapshot.controller==='base_station'){speed=1;$('speed').value='1';toast('Robot + base control runs at1× so camera observations stay current.');}else speed=Number($('speed').value);};
$('quality').onchange=()=>scene?.setQuality($('quality').value);
for(const b of document.querySelectorAll('[data-camera]'))b.onclick=()=>{scene?.setCamera(b.dataset.camera);document.querySelectorAll('[data-camera]').forEach(x=>x.classList.toggle('active',x===b));};
for(const key of ['current','visibility'])$(''+key).addEventListener('input',()=>command({action:'set_water',[key]:Number($(key).value)}));
for(const b of document.querySelectorAll('[data-fault]'))b.onclick=()=>{if(command({action:'inject_fault',kind:b.dataset.fault})){toast(`${label(b.dataset.fault)} introduced`);$('fault-status').textContent=`Last injected: ${label(b.dataset.fault)} · see event log.`;}};
$('scenario').onchange=()=>{activityLog.length=0;cancelDecision();lab.command({action:'pause'});const chosen=$('scenario').value, config=defaultScene(snapshot.seed);if(chosen==='current')config.water.current=.32;if(chosen==='visibility')config.water.visibility=2;lab.loadScene(config);if(chosen==='compound')for(const kind of ['drop','bad_cut','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();$('scene-title').textContent={baseline:'Sheltered reef',current:'Cross-current',visibility:'Low visibility',compound:'Compound setbacks'}[chosen];renderUI(true);toast('Scenario loaded. Start a fresh mission.');};
$('scripted').onclick=()=>{};
$('gemini').onclick=()=>{if(!geminiReady){toast('Gemini needs a server-side API key. Local fallback requires an unavailable model service.');return;}cancelDecision();command({action:'set_controller',mode:'gemini'});};
async function checkHealth(){try{const r=await fetch('/api/lab/health',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();const h=await r.json();geminiReady=!!h.geminiConfigured;$('gemini-status').textContent=geminiReady?`${h.model} · live camera + sonar decisions; simulation frames sent to Google`:'Gemini offline · configure GEMINI_API_KEY on the server to enable live decisions.';}catch{$('gemini-status').textContent='The local fallback works offline. Gemini requires the lab decision server.';} $('gemini').setAttribute('aria-disabled',String(!geminiReady));}
async function requestDecision(force=false){if(snapshot.controller==='base_station')return requestBasePipeline(force);const p=snapshot.pendingDecision;if(!p||snapshot.controller!=='gemini'||inflight||!snapshot.running||(!force&&attempted===p.id))return;attempted=p.id;const token=generation,controller=new AbortController();inflight=controller;$('decision-text').textContent='Requesting a live Gemini decision from the observed mission state…';$('retry-gemini').hidden=true;const timer=setTimeout(()=>controller.abort(),35000);try{const r=await fetch('/api/lab/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:p.id,observation:p.observation,allowedActions:p.allowedActions,...(scene?.captureObservation?{image:scene.captureObservation()}: {})}),signal:controller.signal});const data=await r.json();if(!r.ok)throw new Error(data.error||'Decision service failed');if(token!==generation)return;if(data.source!=='gemini'||data.id!==p.id||!p.allowedActions.includes(data.decision)||typeof data.reason!=='string')throw new Error('Decision service returned an invalid response');command({action:'apply_decision',id:data.id,decision:data.decision,reason:data.reason,source:data.source,routeMode:data.routeMode??null,evidence:{model:data.model,latencyMs:data.latencyMs,inputMode:data.inputMode,inputImageSha256:data.inputImageSha256,inputCamera:data.inputCamera,inputImageTime:data.inputImageTime}});}catch(error){if(token===generation){$('decision-text').textContent=`Gemini held: ${error.name==='AbortError'?'request timed out':error.message}. Retry explicitly or retry the model service.`;$('retry-gemini').hidden=false;toast('Gemini decision unavailable; the mission is holding.');}}finally{clearTimeout(timer);if(inflight===controller)inflight=null;}}
$('retry-gemini').onclick=()=>requestDecision(true);
$('rescan-evidence').onclick=()=>{cancelDecision();if(command({action:'request_rescan',reason:'Operator requested fresh camera evidence'}))toast('Repositioning for fresh visual evidence; fragment ownership is preserved.');};
function selectColony(id){selectedId=id;scene?.setSelected(id);$('colony-select').value=id;fillColony();}
function fillColony(){const c=snapshot.colonies.find(c=>c.id===selectedId);if(!c)return;$('colony-x').value=c.position[0].toFixed(2);$('colony-y').value=c.position[1].toFixed(2);$('colony-health').value=c.health;$('colony-genet').value=c.genet;$('colony-radius').value=c.radius;$('colony-height').value=c.height;}
$('colony-select').onchange=()=>selectColony($('colony-select').value);
$('colony-form').onsubmit=e=>{e.preventDefault();const c=snapshot.colonies.find(c=>c.id===selectedId);if(!c)return;if(command({action:'edit_colony',id:selectedId,patch:{position:[Number($('colony-x').value),Number($('colony-y').value),0],health:$('colony-health').value,genet:$('colony-genet').value.trim(),radius:Number($('colony-radius').value),height:Number($('colony-height').value)}})){cancelDecision();toast('Colony updated. Episode reset with the edited scene.');}};
$('add-colony').onclick=()=>{const id=`colony-${Date.now().toString(36)}`,c={id,position:[0,3,0],health:'bleached_alive',genet:'G1',species:'Pocillopora damicornis',radius:.45,height:.7};if(command({action:'add_colony',colony:c})){cancelDecision();selectColony(id);toast('Colony added. Adjust its position in the editor.');}};
$('remove-colony').onclick=()=>{if(command({action:'remove_colony',id:selectedId})){cancelDecision();toast('Colony removed. Episode reset.');}};
$('add-rock').onclick=()=>{if(command({action:'add_obstacle',obstacle:{id:`rock-${Date.now().toString(36)}`,position:[(snapshot.obstacles.length%4)*1.4-2,0,0],radius:.55}})){cancelDecision();toast('Rock added to the vehicle clearance model.');}};
$('remove-rock').onclick=()=>{const rock=snapshot.obstacles.at(-1);if(rock&&command({action:'remove_obstacle',id:rock.id}))cancelDecision();};
function download(name,data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('save-scene').onclick=()=>{try{localStorage.setItem('pelagic-lab-scene-v1',JSON.stringify(lab.exportScene()));toast('Scene saved in this browser.');}catch{toast('Local storage unavailable. Export a scene file instead.');}};
function loadScene(data){try{lab.loadScene(data);activityLog.length=0;cancelDecision();snapshot=lab.snapshot();renderUI(true);toast('Scene loaded. Ready for a new episode.');}catch(e){toast(e.message);}}
$('load-scene').onclick=()=>{try{const s=localStorage.getItem('pelagic-lab-scene-v1');if(s)loadScene(s);else toast('No saved scene in this browser yet.');}catch{toast('Could not read local storage.');}};
$('export-scene').onclick=()=>download(`reef-rescue-scene-${snapshot.seed}.json`,lab.exportScene());
$('import-scene').onclick=()=>$('scene-file').click();
$('scene-file').onchange=async()=>{const f=$('scene-file').files[0];if(f){if(f.size>250000)toast('Scene file exceeds 250 KB.');else loadScene(await f.text());}$('scene-file').value='';};
function illuminationLabel(){return{uv_exposure:'UV exposure · simulated marker',white_inspection:'White RGB inspection',white_navigation:'White navigation torch'}[scene?.lampMode]||'Camera illumination initializing';}
function inspectCamera(camera='tool'){try{evidenceCamera=camera;const frame=scene.captureObservation({camera,targetPosition:snapshot.perceptionRequest?.targetPosition});$('camera-evidence').src=`data:${frame.mimeType};base64,${frame.data}`;$('download-frame').href=$('camera-evidence').src;$('download-frame').download=`reef-rescue-${camera}-camera.jpg`;$('camera-evidence-meta').textContent=`${camera==='forward'?'Forward hull':'Tool'} optic · T+ ${clock(frame.time)} · 768 × 576 · ${illuminationLabel()} · live independent simulation render (2 Hz). No remote request made by this inspector.`;$('evidence-tool').classList.toggle('active',camera==='tool');$('evidence-forward').classList.toggle('active',camera==='forward');if(!$('frame-dialog').open)$('frame-dialog').showModal();}catch(e){toast(e.message);}}
$('capture-frame').onclick=()=>inspectCamera('tool');$('evidence-tool').onclick=()=>inspectCamera('tool');$('evidence-forward').onclick=()=>inspectCamera('forward');
$('pip-tool').onclick=()=>setPipOptic('tool');$('pip-forward').onclick=()=>setPipOptic('forward');$('pip-enlarge').onclick=()=>inspectCamera(pipCamera);
$('story').onclick=()=>$('story-dialog').showModal();$('close-story').onclick=()=>$('story-dialog').close();
$('close-frame').onclick=()=>$('frame-dialog').close();
$('export-run').onclick=()=>download(`reef-rescue-episode-${snapshot.seed}.json`,{version:1,scene:lab.exportScene(),episode:snapshot,transportActivity:activityLog,exportedAt:new Date().toISOString()});
$('run-suite').onclick=()=>{if(suiteWorker){suiteWorker.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';$('suite-status').textContent='Evaluation stopped. No partial results reported.';return;}command({action:'pause'});report=null;$('export-report').disabled=true;$('suite-results').replaceChildren();$('run-suite').textContent='■ Stop suite';suiteWorker=new Worker(new URL('./evaluate.mjs',import.meta.url),{type:'module'});suiteWorker.onmessage=e=>{if(e.data.type==='progress')$('suite-status').textContent=`Running episode ${e.data.done} / ${e.data.total} · ${label(e.data.scenario)}`;if(e.data.type==='result'){report=e.data.report;renderReport();suiteWorker.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';$('export-report').disabled=false;}};suiteWorker.onerror=()=>{toast('Evaluation failed. Please reload and retry.');suiteWorker?.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';};suiteWorker.postMessage({scene:lab.exportScene(),count:Number($('run-count').value)});};
function renderReport(){const total=report.runs.length,passed=report.runs.filter(r=>r.success).length,summary=document.createElement('p');const strong=document.createElement('strong');strong.textContent=`${passed} / ${total}`;summary.append(strong,document.createTextNode(' completed'));const table=document.createElement('table'),head=table.createTHead().insertRow();for(const t of ['Condition','Pass','Mean time']){const th=document.createElement('th');th.textContent=t;head.append(th);}const body=table.createTBody();for(const condition of report.conditions){const rows=report.runs.filter(r=>r.condition===condition),row=body.insertRow();for(const text of [label(condition),`${rows.filter(r=>r.success).length}/${rows.length}`,`${(rows.reduce((v,r)=>v+r.time,0)/rows.length).toFixed(1)}s`])row.insertCell().textContent=text;}$('suite-results').replaceChildren(summary,table);$('suite-status').textContent='Suite complete. Export includes seeds, per-run outcomes, fault exposure, metrics and event logs.';}
$('export-report').onclick=()=>report&&download('reef-rescue-robustness-report.json',report);
for(const id of ['about','details'])$(id).onclick=()=>$('about-dialog').showModal();document.querySelector('.dialog-close').onclick=()=>$('about-dialog').close();
function renderUI(force=false){const s=snapshot;if(force)bindMemoryScene();renderArchitecture(s);const p=s.perception;if(p){$('perception-evidence').textContent=p.reason||`${label(p.stage)} · ${p.targetId||'survey'} · simulated sensor evidence`;$('uv-exposure').style.width=`${Math.min(1,Math.max(0,p.exposure||0))*100}%`;} drawSonar(s);renderSensors(s);if(document.activeElement!==$('reef-seed'))$('reef-seed').value=s.seed;if(s.route){$('route-mode').value=s.route.mode;$('route-status').textContent=`${s.route.mode==='clearance'?'B / Wider clearance':'A / Direct transit'} · ${s.route.waypoints?.length||0} waypoints`;} $('elapsed').textContent=`${clock(s.time)}.${Math.floor(s.time%1*10)}`;$('phase').textContent=names[s.phase]||label(s.phase);$('phase-progress').style.width=`${s.phaseProgress*100}%`;$('run').textContent=s.running?'Ⅱ Pause mission':s.completed?'✓ Completed':s.phase==='aborted'?'■ Aborted':s.time?'▶ Resume mission':'▶ Start mission';$('run').disabled=s.completed||s.phase==='aborted'||!s.running&&!autonomyReady();$('run-status').textContent=s.pendingDecision?'AWAITING DECISION':s.environmentHold?'SAFE HOLD':s.completed?'MISSION COMPLETE':s.running?'MISSION RUNNING':s.phase==='aborted'?'SAFE ABORT':'MISSION PAUSED';$('status-dot').style.background=s.environmentHold||s.phase==='aborted'?'#e9b978':'#a8e7cf';$('placed').textContent=`${s.metrics.placed}/${s.missionGoal}`;$('recoveries').textContent=s.metrics.recoveries;$('distance').replaceChildren(document.createTextNode(s.metrics.distance.toFixed(1)+' '),Object.assign(document.createElement('small'),{textContent:'m'}));$('energy').replaceChildren(document.createTextNode(Math.round(s.metrics.energy)+' '),Object.assign(document.createElement('small'),{textContent:'J'}));$('scene-seed').textContent=`SEED ${s.seed}`;for(const key of ['current','visibility']){$(`${key}-value`).textContent=`${s.water[key].toFixed(key==='current'?2:1)} ${key==='current'?'m/s':'m'}`;if(document.activeElement!==$(key))$(key).value=s.water[key];}$('scripted').classList.toggle('active',s.controller==='scripted');$('gemini').classList.toggle('active',s.controller==='gemini');$('base-station').classList.toggle('active',s.controller==='base_station');$('policy-badge').textContent=fallbackActive?'LOCAL FALLBACK':activationRequested?'CONNECTING':'MODEL-GUIDED';$('decision-source').textContent=fallbackActive?'LOCAL FALLBACK':s.controller==='base_station'?'ROBOT + BASE':'AWAITING MODELS';if(s.controller==='base_station'&&s.rescan)$('decision-text').textContent=s.status;else if(s.controller==='base_station'&&baseError)$('decision-text').textContent=baseError;else if(s.controller==='base_station'&&baseInflight)$('decision-text').textContent=transportState;else if(!s.pendingDecision)$('decision-text').textContent=publicText(s.decision?.reason||s.status);
const stage=s.phase==='survey'||s.phase==='idle'?0:s.phase.startsWith('inspect')||s.phase==='approval'?1:['approach','grasp','cut','retract'].includes(s.phase)?2:['transport','recover_drop','regrasp','recovery'].includes(s.phase)?3:['align','secure','release','recover_placement'].includes(s.phase)?4:5;document.querySelectorAll('.mission-steps li').forEach((li,i)=>{li.classList.toggle('active',i===stage&&!s.completed);li.classList.toggle('done',i<stage||s.completed);});
const sig=JSON.stringify(s.colonies);if(sig!==sceneSignature){sceneSignature=sig;$('colony-select').replaceChildren(...s.colonies.map(c=>Object.assign(document.createElement('option'),{value:c.id,textContent:`${c.id} · ${label(c.health)}`})));if(!s.colonies.some(c=>c.id===selectedId))selectedId=s.colonies[0]?.id;selectColony(selectedId);}const visibleEvents=[...s.events,...activityLog].sort((a,b)=>a.time-b.time).slice(-55);const es=JSON.stringify(visibleEvents);if(es!==eventSignature){eventSignature=es;$('events').replaceChildren(...visibleEvents.reverse().map(e=>{const div=document.createElement('div');div.className=`event ${e.type}`;const time=document.createElement('time'),p=document.createElement('p');time.textContent=clock(e.time);p.textContent=publicText(e.message);div.append(time,p);return div;}));}
}
async function boot(){renderUI(true);useBase({automatic:true});try{scene=new ReefScene($('reef'),{onSelect:id=>{selectColony(id);switchTab('editor');toast(`Selected ${id}. Pause the mission to edit.`);}});await scene.init();scene.setQuality($('quality').value);scene.update(snapshot,0);$('loading').hidden=true;}catch(e){$('loading').replaceChildren(Object.assign(document.createElement('strong'),{textContent:'3D view could not load'}),Object.assign(document.createElement('span'),{textContent:e.message}));console.error(e);}requestAnimationFrame(frame);}
function frame(now){const dt=Math.min(.1,(now-previous)/1000);previous=now;if(!document.hidden){if(snapshot.pilot?.mode==='manual'&&snapshot.running&&now-lastPilot>80){lab.command({action:'manual_input',...pilotInput()});lastPilot=now;}snapshot=lab.step(dt*speed);if(telemetry.sample(snapshot))queueTelemetry(telemetry.frames.at(-1));flushTelemetry(now);scene?.ready&&scene.update(snapshot,dt);renderCameraPreview(now);if(now-lastUi>120){renderUI();renderPilot(snapshot);requestDecision();lastUi=now;}frameCount++;if(now-fpsStart>1000){$('fps').textContent=`${Math.round(frameCount*1000/(now-fpsStart))} FPS`;frameCount=0;fpsStart=now;}}requestAnimationFrame(frame);}
document.addEventListener('visibilitychange',()=>previous=performance.now());
window.addEventListener('pagehide',()=>{suiteWorker?.terminate();inflight?.abort();baseInflight?.abort();warmupInflight?.abort();clearTimeout(readinessTimer);uplink.controller?.abort();scene?.dispose();});
boot();

function drawSonar(s){
 const canvas=$('sonar-map'),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,cx=w/2,cy=h-20,range=s.sonar?.range||6,radius=h-40;
 ctx.clearRect(0,0,w,h);ctx.fillStyle='#0a2025';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#28483d';ctx.lineWidth=1;
 for(let i=1;i<=3;i++){ctx.beginPath();ctx.arc(cx,cy,radius*i/3,Math.PI,Math.PI*2);ctx.stroke();}
 for(const angle of [-Math.PI/2,-Math.PI/4,0,Math.PI/4,Math.PI/2]){ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.sin(angle)*radius,cy-Math.cos(angle)*radius);ctx.stroke();}
 ctx.fillStyle='#84bba4';ctx.font='14px monospace';ctx.fillText(`${range} m`,w-60,23);
 const contacts=s.sonar?.contacts||[];
 for(const c of contacts){const distance=Number(c.distance)||0;if(distance>range)continue;let angle=Number(c.bearing)||0;if(Math.abs(angle)>Math.PI/2)continue;const x=cx+Math.sin(angle)*distance/range*radius,y=cy-Math.cos(angle)*distance/range*radius;ctx.fillStyle=['fish','crab','turtle','wildlife'].includes(c.type)?'#ebbd80':'#8bc4aa';ctx.beginPath();ctx.arc(x,y,c.type==='crab'?4:3,0,Math.PI*2);ctx.fill();}
 ctx.fillStyle='#d9efdc';ctx.beginPath();ctx.moveTo(cx,cy-8);ctx.lineTo(cx-5,cy+3);ctx.lineTo(cx+5,cy+3);ctx.closePath();ctx.fill();
 $('sonar-status').textContent=`${contacts.length} range returns · geometric model`;
 $('wildlife-status').textContent=`${s.metrics.wildlifeAvoidances||0} wildlife yields`;
}

function regenerate(seed){activityLog.length=0;if(!Number.isInteger(seed)||seed<0||seed>4294967295){toast('Use an integer seed between 0 and 4294967295.');return;}cancelDecision();pilotKeys.clear();telemetry.clear();lab.command({action:'pause'});if(command({action:'randomize',seed})){selectedId=snapshot.colonies[0]?.id;$('scenario').value='baseline';$('scene-title').textContent='Sheltered reef';toast(`New reef generated · seed ${seed}`);}}
function pilotInput(){return {forward:Number(pilotKeys.has('KeyW'))-Number(pilotKeys.has('KeyS')),right:Number(pilotKeys.has('KeyD'))-Number(pilotKeys.has('KeyA')),vertical:Number(pilotKeys.has('KeyQ'))-Number(pilotKeys.has('KeyE')),yaw:Number(pilotKeys.has('ArrowLeft'))-Number(pilotKeys.has('ArrowRight'))};}
function stopPilot(pause=false){pilotKeys.clear();if(snapshot.pilot?.mode==='manual'){lab.command({action:'manual_input',forward:0,right:0,vertical:0,yaw:0});if(pause)command({action:'pause'});}}
$('manual-toggle').onclick=()=>{cancelDecision();pilotKeys.clear();const mode=snapshot.pilot?.mode==='manual'?'autonomous':'manual';if(command({action:'set_pilot',mode})){if(mode==='manual'){speed=1;$('speed').value='1';switchTab('mission');scene?.setCamera('pilot');toast('Manual pilot active. WASD · Q/E · arrows.');}else toast('Autonomous control resumed from the current pose.');}};
$('pilot-brake').onclick=()=>stopPilot();
$('grip-open').onclick=()=>command({action:'manual_gripper',open:true});$('grip-close').onclick=()=>command({action:'manual_gripper',open:false});
const pilotCodes=['KeyW','KeyS','KeyA','KeyD','KeyQ','KeyE','ArrowLeft','ArrowRight'];
window.addEventListener('keydown',e=>{if(snapshot.pilot?.mode!=='manual'||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if(e.code==='Escape'){stopPilot(true);return;}if(pilotCodes.includes(e.code)){e.preventDefault();pilotKeys.add(e.code);}});
window.addEventListener('keyup',e=>pilotKeys.delete(e.code));window.addEventListener('blur',()=>stopPilot(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPilot(true);});
for(const b of document.querySelectorAll('[data-pilot]')){b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);pilotKeys.add(b.dataset.pilot);});for(const event of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(event,()=>pilotKeys.delete(b.dataset.pilot));}
function renderPilot(s){const manual=s.pilot?.mode==='manual';$('manual-controls').hidden=!manual;$('manual-toggle').textContent=manual?'↗ Autonomy':'⌨ Pilot';$('manual-toggle').classList.toggle('active',manual);$('speed').disabled=manual||s.controller==='base_station';document.querySelectorAll('[data-pilot]').forEach(b=>b.classList.toggle('held',pilotKeys.has(b.dataset.pilot)));if(manual){$('run').disabled=false;$('run').textContent=s.running?'Ⅱ Pause pilot':'▶ Resume pilot';$('run-status').textContent=s.running?'MANUAL PILOT':'PILOT PAUSED';}}
function renderSensors(s){const v=s.water.currentVector||[s.water.current,0,0];$('current-overlay-legend').textContent=`Current arrows ×5 (capped) · ${Math.hypot(...v).toFixed(2)} m/s at robot`; $('current-vector').textContent=v.map(n=>Number(n).toFixed(2)).join(' / ')+' m/s';const velocity=s.robot.velocity||[0,0,0];const clearance=s.navigation?.bedClearance??s.navigation?.clearance??s.navigation?.terrainClearance;$('nav-state').textContent=`${Math.hypot(...velocity).toFixed(2)} m/s · ${Number.isFinite(clearance)?clearance.toFixed(2):'—'} m`;$('fusion-state').textContent=s.sensors?.fusion?.opticalAvailable?'Sonar + optical registry':'Sonar · optical unavailable';const summary=telemetry.summary();$('stream-count').textContent=summary.frames??summary.count??summary.samples??0;}
$('export-telemetry').onclick=()=>{const url=URL.createObjectURL(new Blob([telemetry.exportJSONL()],{type:'application/x-ndjson'})),a=document.createElement('a');a.href=url;a.download=`reef-rescue-telemetry-${snapshot.seed}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};


function componentStatus(name){return architecture?.components?.[name]||{};}
function requiredComponents(){return $('allow-partial-stack').checked?['gemma','argon']:['gemma','argon','cuopt'];}
function stackConfigured(){return requiredComponents().every(name=>componentStatus(name).configured);}
function componentReady(name){const c=componentStatus(name);if(typeof c.ready==='boolean')return c.ready;if(c.readiness)return c.readiness==='ready';return c.status==='verified_response';}
function stackReady(){return requiredComponents().every(componentReady);}
const placementLabel=value=>({robot:'robot runtime',base_station:'base station',modal:'Modal hosted',cloud:'cloud service',unverified:'placement unverified'}[value]||value||'placement unverified');
async function checkArchitecture(){
 try{const response=await fetch('/api/lab/architecture',{signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error('Architecture service unavailable');architecture=await response.json();architectureError='';if(activationRequested){const trace=JSON.stringify(Object.entries(architecture.components||{}).map(([name,c])=>[name,c.readiness||c.status]));if(trace!==readinessTrace){readinessTrace=trace;logActivity('transport',`Service readiness: ${Object.entries(architecture.components||{}).map(([name,c])=>`${name} ${c.readiness||c.status||'unknown'}`).join(' · ')}.`);}}}
 catch(error){architecture=null;architectureError='Model service status unavailable. The mission is paused until reconnection or explicit local fallback.';}
 renderArchitecture(snapshot);return architecture;
}
function renderArchitecture(s){renderUplink();renderMemory();
 const gemma=componentStatus('gemma'),argon=componentStatus('argon'),cuopt=componentStatus('cuopt');
 for(const[name,result]of[['gemma',lastPerception],['argon',lastPlanning],['cuopt',lastPlanning?.optimizer?.source==='cuopt'?lastPlanning.optimizer:null]]){
  const component=componentStatus(name),badge=$(`${name}-runtime`),readiness=component.readiness||component.status||'unconfigured',warming=['warming','loading','starting'].includes(readiness),error=readiness==='error',ready=componentReady(name);
  badge.textContent=warming?'WARMING':error?'SERVICE ERROR':ready?(result?'RESPONSE RECEIVED':'SERVICE READY'):component.configured?'NOT STARTED':'NOT CONFIGURED';badge.dataset.state=warming?'warming':error?'error':ready?'live':component.configured?'configured':'offline';
  $(`${name}-model`).textContent=component.configured?`${component.model||name} · ${placementLabel(component.deployment)} · ${warming?'model startup in progress':error?'readiness failed':ready?(result?'actual response received':'ready for requests'):component.message||'awaiting service startup'}`:name==='cuopt'?'cuOpt is required in full-stack mode.':'Adapter is not configured.';
 }
 const missing=requiredComponents().filter(name=>!componentStatus(name).configured),waiting=requiredComponents().filter(name=>!componentReady(name));
 $('stack-readiness-label').textContent=`${$('allow-partial-stack').checked?'PARTIAL STACK':'FULL STACK'} · ${activationRequested?'CONNECTING':stackReady()?'READY':missing.length?'UNCONFIGURED':'NOT READY'}`;
 $('stack-readiness-detail').textContent=architectureError||(missing.length?`Missing: ${missing.join(', ')}. No substitute model or solver is implied.`:waiting.length?`Waiting for ${waiting.join(', ')}. Startup and inference are separate stages.`:`${requiredComponents().join(' + ')} services are ready. Model evidence appears only after actual requests.`);
 $('stack-status').textContent=fallbackActive?'Local fallback · model unavailable. Decisions use the local controller.':architectureError||(activationRequested?'Model-guided autonomy · warming services. The mission stays paused.':stackReady()?'Model-guided autonomy · Gemma → Argon → '+($('allow-partial-stack').checked&&!componentReady('cuopt')?'local routes (explicit partial mode)':'cuOpt')+'. Ready when you start the mission.':'Model-guided autonomy · awaiting model services.');
 const fallbackOffered=!fallbackActive&&!evidenceHold&&(modelUnavailable||activationRequested&&!stackReady());
 $('safe-scripted').hidden=!fallbackOffered;$('decision-fallback').hidden=!fallbackOffered||!baseError;
 $('base-station').textContent=fallbackActive?'Reconnect model-guided autonomy':activationRequested?'Model services warming…':'Model-guided autonomy';
 for(const id of['base-station','use-base'])$(id).setAttribute('aria-disabled',String(activationRequested));
 $('use-base').textContent=activationRequested?'Connecting model services…':$('allow-partial-stack').checked?'Connect partial robot + base':'Connect full robot + base stack';$('cancel-stack-connect').hidden=!activationRequested;
 $('rescan-evidence').hidden=s.controller!=='base_station'||!s.pendingDecision&&!/stale|expired|rescan/i.test(s.status||'');
 $('placement-robot').textContent=gemma.configured?`Simulated robot · Gemma ${placementLabel(gemma.deployment)}`:'Browser simulation · synthetic sensors';
 $('placement-base').textContent=argon.configured?`Argon ${placementLabel(argon.deployment)}`:'No reasoning service connected';
 const modal=Object.entries(architecture?.components||{}).filter(([,c])=>c.configured&&c.deployment==='modal').map(([name])=>name);
 $('placement-modal').textContent=modal.length?`${modal.join(' + ')} configured · ${[lastPerception,lastPlanning].some(p=>p?.deployment==='modal')?'response received':'unverified'}`:'Optional · not configured';
 $('perception-runtime').textContent=lastPerception?`Last Gemma frame T+ ${clock(lastPerception.frameTime??lastPerception.inputImageTime??0)} · ${lastPerception.provider||'configured adapter'}`:'Current evidence: synthetic browser sensors';
 $('model-perception-evidence').textContent=lastPerception?`${lastPerception.summary||'Structured observations received.'} Source: ${lastPerception.source} · ${lastPerception.model} · frame ${clock(lastPerception.frameTime??lastPerception.inputImageTime??0)}.`:'No Gemma response received. Camera/UV observations in the browser remain synthetic.';
 $('model-reasoning-evidence').textContent=lastPlanning?`${lastPlanning.reason} Action: ${lastPlanning.decision}. Source: ${lastPlanning.source} · ${lastPlanning.model}.`:'No Argon response received.';
 const optimizer=lastPlanning?.optimizer;$('model-planning-evidence').textContent=optimizer?.source==='cuopt'?`cuOpt response received. ${optimizer.summary||optimizer.reason||''} Selected route: ${lastPlanning.routeMode||'unchanged'}.`:'Local terrain-aware waypoint alternatives. No cuOpt response received.';
 $('transport-runtime').textContent=uplink.enabled?`${uplink.accepted} STREAM FRAMES`:baseInflight?'HTTP IN FLIGHT':packetCount?`${packetCount} GATE PACKETS`:'LOCAL ONLY';
 const remote=s.controller==='base_station';$('pipeline-robot').textContent=remote?(lastPerception?'Robot observation · Gemma response received':'Robot observation · awaiting Gemma'):'Robot observation · synthetic perception';
 $('pipeline-base').textContent=remote?(lastPlanning?'Base reasoning · Argon response received':'Base reasoning · awaiting Argon'):s.controller==='gemini'?'Legacy cloud policy · Google Gemini':fallbackActive?'Local fallback · model unavailable':'Base reasoning · awaiting model connection';
 $('pipeline-transport').textContent=uplink.enabled?`Base received ${uplink.accepted} sensor frames · ${uplink.queue.length} queued`:remote?`${transportState} · continuous uplink disconnected`:'5 Hz local recorder · uplink disconnected';
 $('sensor-evidence-source').textContent='CAMERA / UV EXPOSURE · SYNTHETIC';
}
function stopActivation(){activationRequested=false;clearTimeout(readinessTimer);readinessTimer=null;warmupInflight?.abort();warmupInflight=null;if($('cancel-stack-connect'))$('cancel-stack-connect').hidden=true;}
function connectUplink(){if(uplink.enabled)return;resetUplink();uplink.enabled=true;queueTelemetry(telemetry.frames.at(-1));}
function activateBase(){
 const resume=activationWasRunning;stopActivation();fallbackActive=false;modelUnavailable=false;evidenceHold=false;speed=1;$('speed').value='1';
 if(command({action:'set_controller',mode:'base_station',requireFullStack:!$('allow-partial-stack').checked})){if(snapshot.pilot?.mode==='manual')command({action:'set_pilot',mode:'autonomous'});connectUplink();transportState='Live telemetry + model gate packets';if(resume)command({action:'run'});toast('Robot + base connected. Telemetry streams continuously; model gates use fresh camera evidence.');}
}
async function pollStackReadiness(){
 if(!activationRequested)return;await checkArchitecture();if(!activationRequested)return;
 if(stackReady()){activateBase();return;}
 // Readiness leases can expire while another cold model is still compiling.
 if(!warmupInflight&&requiredComponents().some(name=>componentStatus(name).configured&&componentStatus(name).readiness==='not_started')){
  const controller=new AbortController();warmupInflight=controller;const timer=setTimeout(()=>controller.abort(),20000);
  try{const response=await fetch('/api/lab/warmup',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Readiness refresh failed');if(activationRequested&&data.components)architecture=data;}
  catch(error){if(activationRequested)logActivity('transport',`Readiness refresh pending: ${error.name==='AbortError'?'request timed out':error.message}. Retrying status polling.`);}
  finally{clearTimeout(timer);if(warmupInflight===controller)warmupInflight=null;}
  if(!activationRequested)return;
 }
 if(Date.now()-activationStarted>15*60*1000||requiredComponents().some(name=>componentStatus(name).readiness==='error')){stopActivation();modelUnavailable=true;baseError='Model services are not ready. Review their status and reconnect explicitly.';renderUI(true);return;}
 readinessTimer=setTimeout(pollStackReadiness,3000);
}
async function useBase(options={}){
 if(activationRequested)return;const wasRunning=snapshot.running;cancelDecision();const token=generation;activationWasRunning=wasRunning;activationRequested=true;fallbackActive=false;modelUnavailable=false;evidenceHold=false;activationStarted=Date.now();command({action:'pause'});connectUplink();if(!options.automatic)switchTab('architecture');await checkArchitecture();if(!activationRequested||token!==generation)return;
 if(!stackConfigured()){stopActivation();modelUnavailable=true;renderUI(true);toast(`Configure ${requiredComponents().filter(name=>!componentStatus(name).configured).join(', ')} before connecting this stack.`);return;}
 activationRequested=true;activationStarted=Date.now();connectUplink();if(stackReady()){activateBase();return;}
 const controller=new AbortController();warmupInflight=controller;renderArchitecture(snapshot);const timer=setTimeout(()=>controller.abort(),20000);
 try{logActivity('request','Starting Gemma / cuOpt service warmup; waiting for verified readiness before live control.');const response=await fetch('/api/lab/warmup',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Service warmup failed');if(!activationRequested)return;if(data.components)architecture=data;await pollStackReadiness();}
 catch(error){if(activationRequested){stopActivation();modelUnavailable=true;architectureError=`Service startup failed: ${error.name==='AbortError'?'request timed out':error.message}. Reconnect explicitly.`;renderArchitecture(snapshot);toast('Model startup did not complete. An explicit local fallback is available.');}}
 finally{clearTimeout(timer);if(warmupInflight===controller)warmupInflight=null;}
}
$('cancel-stack-connect').onclick=()=>{stopActivation();modelUnavailable=true;renderUI(true);toast('Model connection canceled. The mission remains paused.');};
$('allow-partial-stack').onchange=()=>{stopActivation();renderArchitecture(snapshot);if(snapshot.controller==='base_station')useBase();};
$('base-station').onclick=useBase;$('use-base').onclick=useBase;
for(const id of['show-architecture','pipeline-details'])$(id).onclick=()=>switchTab('architecture');
$('refresh-architecture').onclick=checkArchitecture;
for(const id of['safe-scripted','decision-fallback'])$(id).onclick=()=>{if(evidenceHold||!(modelUnavailable||activationRequested&&!stackReady()))return;cancelDecision();fallbackActive=true;modelUnavailable=true;command({action:'set_controller',mode:'scripted'});logActivity('control','Local fallback · model unavailable. Local controller selected explicitly; no model result is claimed.');toast('Local fallback · model unavailable. Start the mission when ready.');};
async function baseRequest(path,payload,controller){const started=performance.now(),perception=path.endsWith('/perception');logActivity('request',perception?`Sending tool frame T+ ${clock(payload.image.time)} (768×576; ${illuminationLabel()}) to Gemma · target ${payload.observation.cameraTargetId} · capture ${payload.observation.captureRequestId}. Awaiting visual observations.`:`Sending accepted observations to Argon · actions ${payload.allowedActions.join('/')} · routes ${(payload.observation.route?.alternatives||[]).map(r=>r.id).join('/')} · ${payload.requireFullStack?'cuOpt solve required':'explicit partial planning'}. Awaiting action and route.`);const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});const data=await response.json();if(!response.ok){const error=new Error(data.error||'Configured service failed');error.serviceUnavailable=response.status===429||response.status>=500;throw error;}packetCount++;data.clientLatencyMs=Math.round(performance.now()-started);return data;}
async function requestBasePipeline(force=false){
 if(baseInflight||!snapshot.running||snapshot.pilot?.mode==='manual'||!scene?.ready)return;
 const request=snapshot.perceptionRequest,pending=snapshot.pendingDecision,inspecting=['inspect_recipient','inspect_donor','inspect_fragment'].includes(snapshot.phase);
 const targetId=request?.targetId||(snapshot.phase==='inspect_recipient'?snapshot.targetId:snapshot.donorId);
 const perceptionReady=request?request.ready:inspecting&&Number(snapshot.perception?.exposure||0)>=.8;
 const operation=perceptionReady?'perception':pending?'planning':null;if(!operation)return;
 const key=operation==='perception'?`${generation}:${request?.id||snapshot.phase}:${targetId}`:`${generation}:${pending.id}`;
 if(!force&&baseAttempted.has(key))return;baseAttempted.add(key);baseError='';modelUnavailable=false;evidenceHold=false;
 const token=generation,controller=new AbortController();baseInflight=controller;$('retry-gemini').hidden=true;$('decision-fallback').hidden=true;
 transportState=operation==='perception'?'Sending robot camera to Gemma…':'Sending observations to Argon / route planning…';renderArchitecture(snapshot);
 const timer=setTimeout(()=>controller.abort(),45000);
 try{
  if(operation==='perception'){
   const image=scene.captureObservation({targetPosition:request?.targetPosition}),id=request?`${request.id}-${generation}-${Math.round(image.time*1000)}`:`perception-${generation}-${targetId}-${Math.round(image.time*1000)}`;
   const observation={phase:snapshot.phase,frameTime:image.time,perceptionRequest:request,captureRequestId:request?.id||id,cameraTargetId:targetId,targetKind:request?.targetKind||'colony',targetPosition:request?.targetPosition,targetId:snapshot.targetId,donorId:snapshot.donorId,water:{current:snapshot.water.current,currentVector:snapshot.water.currentVector,visibility:snapshot.water.visibility},robot:{position:snapshot.robot.position,gripper:snapshot.robot.gripper,yaw:snapshot.robot.yaw},sonar:{range:snapshot.sonar?.range,contacts:(snapshot.sonar?.contacts||[]).slice(0,24)}};
   const packet=await baseRequest('/api/lab/perception',{id,observation,image},controller);if(token!==generation||request&&lab.snapshot().perceptionRequest?.id!==request.id)return;
   if(packet.source!=='gemma'||(packet.requestId??packet.id)!==id)throw new Error('Gemma packet source or identity mismatch');
   lab.command({action:'ingest_perception',packet});lastPerception=packet;snapshot=lab.snapshot();rememberObservations();transportState='Gemma observation received via HTTP';logActivity('response',`Gemma ${packet.model} responded in ${packet.clientLatencyMs}ms: ${packet.summary||'Structured visual observations received.'} ${packet.targetKind==='fragment'?`Fragment visible: ${packet.fragmentVisible}; gripper: ${packet.gripperState}.`:(packet.observations||[]).map(o=>`${o.id}: ${label(o.health)} (${Math.round(o.confidence*100)}% provider score)`).join('; ')} Frame T+ ${clock(packet.frameTime)}.`);
   const expected=request?.expectedHealth||(snapshot.phase==='inspect_recipient'?'bleached_alive':'healthy'),accepted=request?.targetKind==='fragment'?(packet.fragmentVisible===true&&packet.gripperState===(snapshot.robot.holding?'holding':'empty')):packet.observations?.some(o=>o.id===targetId&&o.health===expected&&o.confidence>=.7);
   if(!accepted){evidenceHold=true;baseError='Gemma evidence is uncertain or incompatible. Inspection is held; retry a fresh camera frame. Local fallback cannot bypass this observation.';$('retry-gemini').hidden=false;$('decision-fallback').hidden=true;}
  }else{
   const observation=planningObservation(pending);
   const packet=await baseRequest('/api/lab/plan',{id:pending.id,observation,allowedActions:pending.allowedActions,perception:lastPerception,requireFullStack:snapshot.intelligence?.requireFullStack!==false},controller);if(token!==generation||lab.snapshot().pendingDecision?.id!==pending.id)return;
   if(snapshot.intelligence?.requireFullStack!==false&&packet.optimizer?.source!=='cuopt')throw new Error('Full stack requires an actual cuOpt result');
   if(packet.source!=='argon'||(packet.requestId??packet.id)!==pending.id||!pending.allowedActions.includes(packet.decision))throw new Error('Argon packet source, identity or action mismatch');
   lab.command({action:'ingest_plan',packet});lab.command({action:'apply_decision',id:pending.id,decision:packet.decision,reason:packet.reason,source:'base_station',routeMode:packet.routeMode??null,evidence:{perception:lastPerception,planning:packet}});lastPlanning=packet;snapshot=lab.snapshot();transportState='Base plan received via HTTP';logActivity('response',`Argon ${packet.model} responded in ${packet.clientLatencyMs}ms: ${packet.decision.toUpperCase()} — ${packet.reason} ${packet.optimizer?.source==='cuopt'?`cuOpt selected ${packet.routeMode}; objective ${packet.optimizer.objectiveCost??'reported by solver'}.`:'Explicit partial mode; local route retained.'}`);
  }
 }catch(error){if(token===generation){modelUnavailable=!!error.serviceUnavailable||error.name==='AbortError'||error instanceof TypeError;evidenceHold=!modelUnavailable;baseError=`${operation==='perception'?'Gemma perception':'Base planning'} held: ${error.name==='AbortError'?'request timed out':error.message}. ${modelUnavailable?'Retry the service or explicitly use local fallback.':'Retry fresh evidence; local fallback cannot bypass a rejected observation.'}`;transportState='HTTP request failed · mission held';logActivity('error',baseError);$('retry-gemini').hidden=false;$('decision-fallback').hidden=!modelUnavailable;toast('Remote stage unavailable. Local safety remains active.');}}
 finally{clearTimeout(timer);if(baseInflight===controller)baseInflight=null;if(token===generation)renderUI(true);}
}

function resetUplink(){uplink.controller?.abort();uplink.controller=null;uplink.id=crypto.randomUUID();uplink.sequence=0;uplink.queue=[];uplink.accepted=0;uplink.skipped=0;uplink.lastSent=0;uplink.lastReceipt=null;uplink.lastFrameTime=null;uplink.error='';uplink.retryCount=0;uplink.retryAt=0;}
function queueTelemetry(frame){
 if(!uplink.enabled||!frame)return;
 if(uplink.lastFrameTime!==null&&frame.time<uplink.lastFrameTime-1e-9)resetUplink();
 if(uplink.lastFrameTime!==null&&frame.time<=uplink.lastFrameTime)return;
 uplink.lastFrameTime=frame.time;uplink.queue.push(frame);
 if(uplink.queue.length>5){uplink.skipped+=uplink.queue.length-5;uplink.queue.splice(0,uplink.queue.length-5);}
}
function renderUplink(){
 $('connect-telemetry').textContent=uplink.enabled?'Disconnect telemetry':'Connect telemetry to base';
 $('uplink-badge').textContent=uplink.error?'ERROR':uplink.retryCount&&uplink.enabled?'RETRYING':uplink.enabled?(uplink.lastReceipt?'CONNECTED':'CONNECTING'):'DISCONNECTED';$('uplink-badge').dataset.state=uplink.error?'error':uplink.lastReceipt&&uplink.enabled?'live':'offline';
 $('uplink-received').textContent=`${uplink.accepted} frames acknowledged`;$('uplink-queue').textContent=`${uplink.queue.length} / ${uplink.skipped}`;
 $('uplink-status').textContent=uplink.error||(uplink.retryCount&&uplink.enabled?'Gateway rate limit; retrying the bounded unacknowledged sensor queue. No new receipt is claimed.':null)||(uplink.enabled?(uplink.lastReceipt?`Base gateway receipt at T+ ${clock(uplink.lastReceipt.lastFrameTime)}. Sensor batches only; model inference is separate.`:'Connecting with the next sensor frame. Up to 5 frames per batch; no images or model calls.'):'Uplink disconnected. Local recording continues; connect to send bounded sensor batches to the base gateway.');
}
$('connect-telemetry').onclick=()=>{
 if(uplink.enabled){uplink.enabled=false;uplink.controller?.abort();uplink.controller=null;uplink.queue=[];toast('Telemetry uplink disconnected. Local recording continues.');}
 else{resetUplink();uplink.enabled=true;queueTelemetry(telemetry.frames.at(-1));toast('Telemetry uplink enabled. Sensor batches go to the base gateway; images stay out of this stream.');}
 renderArchitecture(snapshot);
};
async function flushTelemetry(now){
 if(!uplink.enabled||uplink.controller||!uplink.queue.length||now-uplink.lastSent<1200||now<(uplink.retryAt||0))return;
 const id=uplink.id,sequence=uplink.sequence++,frames=uplink.queue.splice(0,5),controller=new AbortController();
 while(frames.length>1&&new TextEncoder().encode(JSON.stringify({streamId:id,sequence,frames})).length>60*1024)uplink.queue.unshift(frames.pop());
 uplink.controller=controller;uplink.lastSent=now;
 const timer=setTimeout(()=>controller.abort(),8000);
 try{
  const response=await fetch('/api/lab/telemetry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({streamId:id,sequence,frames}),signal:controller.signal});const receipt=await response.json();
  if(response.status===429&&uplink.enabled&&uplink.id===id&&(uplink.retryCount||0)<5){
   const unsent=[...frames,...uplink.queue].filter(frame=>frame.time>(uplink.lastReceipt?.lastFrameTime??-Infinity));
   const unique=[...new Map(unsent.map(frame=>[frame.time,frame])).values()].sort((a,b)=>a.time-b.time);
   uplink.skipped+=Math.max(0,unique.length-5);uplink.queue=unique.slice(-5);uplink.retryCount=(uplink.retryCount||0)+1;
   const retrySeconds=Number(response.headers.get('Retry-After'));uplink.retryAt=performance.now()+Math.max(1200,Math.min(10000,Number.isFinite(retrySeconds)?retrySeconds*1000:1200));
   if(uplink.retryCount===1)logActivity('transport','Telemetry gateway rate limited one batch; retrying up to 5 retained sensor frames. Acknowledged count is unchanged.');return;
  }
  if(!response.ok)throw new Error(receipt.error||'Telemetry gateway rejected the batch');
  if(!uplink.enabled||uplink.id!==id)return;
  if(receipt.streamId!==id||receipt.sequence!==sequence||receipt.acceptedFrames!==frames.length||!Number.isInteger(receipt.totalFrames)||receipt.totalFrames<receipt.acceptedFrames||!Number.isFinite(receipt.lastFrameTime))throw new Error('Telemetry receipt did not match the transmitted batch');
  if(!uplink.lastReceipt)logActivity('transport',`Base gateway acknowledged ${receipt.acceptedFrames} actual sensor frames. Continuous telemetry connected; images are sent only at model gates.`);uplink.accepted+=receipt.acceptedFrames;uplink.lastReceipt=receipt;uplink.retryCount=0;uplink.retryAt=0;
 }catch(error){if(uplink.enabled&&uplink.id===id){uplink.error=`Telemetry disconnected: ${error.name==='AbortError'?'request timed out':error.message}. Reconnect explicitly; local physics and recording continue.`;uplink.enabled=false;logActivity('error',uplink.error);uplink.skipped+=frames.length+uplink.queue.length;uplink.queue=[];}}
 finally{clearTimeout(timer);if(uplink.controller===controller)uplink.controller=null;renderUplink();}
}


function bindMemoryScene(){
 const exported=lab.exportScene(),signature=JSON.stringify({seed:exported.seed,colonies:exported.colonies,obstacles:exported.obstacles});if(signature===memorySceneSignature)return;
 try{semanticMemory.bindScene(exported);memorySceneSignature=signature;memoryUiSignature='';memoryError='';}catch(error){memoryError=error.message;}
}
function rememberObservations(){try{bindMemoryScene();semanticMemory.remember(snapshot);memoryError='';memoryUiSignature='';}catch(error){memoryError=error.message;}renderMemory();}
function renderMemory(){
 const status=semanticMemory.status,records=semanticMemory.entries();$('memory-count').textContent=`${records.length} RECORDS`;
 $('memory-status').textContent=memoryError||status.lastError||`${status.persistence==='local_storage'?'Saved in this browser':'Session-only memory'} · ${status.restoredCount||0} restored · 7-day expiry. Historical model estimates never satisfy fresh visual approval.`;
 const signature=JSON.stringify(records.slice(-5));if(signature===memoryUiSignature)return;memoryUiSignature=signature;
 $('memory-records').replaceChildren(...(records.length?records.slice(-5).reverse().map(record=>{const paragraph=document.createElement('p');paragraph.textContent=`${record.id} · ${label(record.health)} · ${(record.confidence*100).toFixed(0)}% provider score. ${record.model} / T+ ${clock(record.frameTime)}. Historical, not a control approval.`;return paragraph;}):[Object.assign(document.createElement('p'),{textContent:'No accepted Gemma observations saved for this scene.'})]));
}
$('export-memory').onclick=()=>{try{download(`reef-rescue-memory-${snapshot.seed}.json`,JSON.parse(semanticMemory.exportJSON()));}catch(error){toast(error.message);}};
$('import-memory').onclick=()=>$('memory-file').click();
$('memory-file').onchange=async()=>{const file=$('memory-file').files[0];if(file){try{if(file.size>1024*1024)throw new Error('Memory file exceeds1MiB');bindMemoryScene();const result=semanticMemory.importJSON(await file.text());memoryUiSignature='';renderMemory();toast(`${result.imported} historical records restored for this exact scene. Fresh camera approval is still required.`);}catch(error){toast(error.message);}}$('memory-file').value='';};
$('clear-memory').onclick=()=>{semanticMemory.clear();memoryUiSignature='';renderMemory();toast('Observation memory cleared for this scene.');};

function planningObservation(pending){
 const observation={...pending.observation,frameTime:snapshot.time,route:snapshot.route,semanticMemory:semanticMemory.planningContext?.([snapshot.donorId,snapshot.targetId])};
 for(const[key,limit]of[['sonar',24],['fusion',16]]){const stream=observation[key];if(stream?.contacts?.length>limit)observation[key]={...stream,contacts:stream.contacts.slice(0,limit),omittedContacts:(stream.omittedContacts||0)+stream.contacts.length-limit};}
 return observation;
}

function logActivity(type,message){activityLog.push({time:snapshot.time,type,message:String(message).slice(0,1500),receivedAt:new Date().toISOString()});if(activityLog.length>80)activityLog.splice(0,activityLog.length-80);}
function setPipOptic(camera){pipCamera=camera;lastPip=0;$('pip-tool').classList.toggle('active',camera==='tool');$('pip-forward').classList.toggle('active',camera==='forward');}
function renderCameraPreview(now){
 if(!scene?.ready)return;
 if($('frame-dialog').open){if(now-lastEvidence>=500){lastEvidence=now;inspectCamera(evidenceCamera);}return;}
 if(now-lastPip<200)return;lastPip=now;
 try{const frame=scene.renderPreview($('robot-camera-pip'),{camera:pipCamera,targetPosition:snapshot.perceptionRequest?.targetPosition});$('pip-time').textContent=`T+ ${clock(frame.time)}`;$('pip-light').textContent=`${illuminationLabel()} · actual camera render`;}catch(error){$('pip-light').textContent=`Camera unavailable: ${error.message}`;}
}
