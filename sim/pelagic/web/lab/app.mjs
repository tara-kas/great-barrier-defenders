import { ReefLab, defaultScene } from './simulation.mjs';
import { ReefScene } from './scene.mjs';
import { TelemetryRecorder } from './telemetry.mjs';
const $ = id => document.getElementById(id);
const randomSeed=()=>crypto.getRandomValues(new Uint32Array(1))[0];
const lab = new ReefLab({seed:randomSeed()});
const telemetry=new TelemetryRecorder();
const pilotKeys=new Set();let lastPilot=0;
let scene, snapshot=lab.snapshot(), selectedId='donor-1', speed=1, report=null, suiteWorker=null;
let sceneSignature='', eventSignature='', lastUi=0, previous=performance.now(), frameCount=0, fpsStart=performance.now();
let geminiReady=false, inflight=null, attempted=null, generation=0, toastTimer;
const uplink={enabled:false,id:null,sequence:0,queue:[],accepted:0,skipped:0,lastSent:0,lastReceipt:null,error:'',controller:null};
let architecture=null,architectureError='',baseInflight=null,baseAttempted=new Set(),lastPerception=null,lastPlanning=null,baseError='',packetCount=0,transportState='Local recorder only';
const names={idle:'Ready to begin',survey:'Survey & pairing',inspect_recipient:'Inspect recipient',inspect_donor:'Inspect donor',approval:'Harvest approval',approach:'Approach donor',grasp:'Close gripper',cut:'Cut donor branch',retract:'Retract cutting',transport:'Transfer fragment',align:'Align contact',secure:'Secure fragment',release:'Release gripper',verify:'Verify placement',recover_drop:'Recover dropped fragment',recover_placement:'Correct placement',regrasp:'Regrasp fragment',recovery:'Assess setback',complete:'Mission complete',aborted:'Safe abort'};
const label = text => String(text??'').replaceAll('_',' ');
const clock = seconds => `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function cancelDecision(){generation++;inflight?.abort();baseInflight?.abort();inflight=null;baseInflight=null;attempted=null;baseAttempted.clear();baseError='';lastPerception=null;lastPlanning=null;transportState='Local recorder only';$('retry-gemini').hidden=true;$('decision-fallback').hidden=true;}
function command(data){try{lab.command(data);snapshot=lab.snapshot();renderUI(true);renderPilot(snapshot);return true;}catch(error){toast(error.message);return false;}}
function reset(){cancelDecision();pilotKeys.clear();telemetry.clear();lab.reset();if($('scenario').value==='compound')for(const kind of ['drop','bad_cut','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();renderUI(true);}
function switchTab(name){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-content').forEach(p=>p.hidden=p.id!==`tab-${name}`);}
for(const b of document.querySelectorAll('[data-tab]'))b.addEventListener('click',()=>switchTab(b.dataset.tab));
$('run').onclick=()=>command({action:snapshot.running?'pause':'run'});
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
$('scenario').onchange=()=>{cancelDecision();lab.command({action:'pause'});const chosen=$('scenario').value, config=defaultScene(snapshot.seed);if(chosen==='current')config.water.current=.32;if(chosen==='visibility')config.water.visibility=2;lab.loadScene(config);if(chosen==='compound')for(const kind of ['drop','bad_cut','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();$('scene-title').textContent={baseline:'Sheltered reef',current:'Cross-current',visibility:'Low visibility',compound:'Compound setbacks'}[chosen];renderUI(true);toast('Scenario loaded. Start a fresh mission.');};
$('scripted').onclick=()=>{cancelDecision();command({action:'set_controller',mode:'scripted'});};
$('gemini').onclick=()=>{if(!geminiReady){toast('Gemini needs a server-side API key. Scripted control is ready now.');return;}cancelDecision();command({action:'set_controller',mode:'gemini'});};
async function checkHealth(){try{const r=await fetch('/api/lab/health',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error();const h=await r.json();geminiReady=!!h.geminiConfigured;$('gemini-status').textContent=geminiReady?`${h.model} · live camera + sonar decisions; simulation frames sent to Google`:'Gemini offline · configure GEMINI_API_KEY on the server to enable live decisions.';}catch{$('gemini-status').textContent='Scripted control works offline. Gemini requires the lab decision server.';} $('gemini').setAttribute('aria-disabled',String(!geminiReady));}
async function requestDecision(force=false){if(snapshot.controller==='base_station')return requestBasePipeline(force);const p=snapshot.pendingDecision;if(!p||snapshot.controller!=='gemini'||inflight||!snapshot.running||(!force&&attempted===p.id))return;attempted=p.id;const token=generation,controller=new AbortController();inflight=controller;$('decision-text').textContent='Requesting a live Gemini decision from the observed mission state…';$('retry-gemini').hidden=true;const timer=setTimeout(()=>controller.abort(),35000);try{const r=await fetch('/api/lab/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:p.id,observation:p.observation,allowedActions:p.allowedActions,...(scene?.captureObservation?{image:scene.captureObservation()}: {})}),signal:controller.signal});const data=await r.json();if(!r.ok)throw new Error(data.error||'Decision service failed');if(token!==generation)return;if(data.source!=='gemini'||data.id!==p.id||!p.allowedActions.includes(data.decision)||typeof data.reason!=='string')throw new Error('Decision service returned an invalid response');command({action:'apply_decision',id:data.id,decision:data.decision,reason:data.reason,source:data.source,routeMode:data.routeMode??null,evidence:{model:data.model,latencyMs:data.latencyMs,inputMode:data.inputMode,inputImageSha256:data.inputImageSha256,inputCamera:data.inputCamera,inputImageTime:data.inputImageTime}});}catch(error){if(token===generation){$('decision-text').textContent=`Gemini held: ${error.name==='AbortError'?'request timed out':error.message}. Retry explicitly or select scripted control.`;$('retry-gemini').hidden=false;toast('Gemini decision unavailable; the mission is holding.');}}finally{clearTimeout(timer);if(inflight===controller)inflight=null;}}
$('retry-gemini').onclick=()=>requestDecision(true);
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
function loadScene(data){try{lab.loadScene(data);cancelDecision();snapshot=lab.snapshot();renderUI(true);toast('Scene loaded. Ready for a new episode.');}catch(e){toast(e.message);}}
$('load-scene').onclick=()=>{try{const s=localStorage.getItem('pelagic-lab-scene-v1');if(s)loadScene(s);else toast('No saved scene in this browser yet.');}catch{toast('Could not read local storage.');}};
$('export-scene').onclick=()=>download(`reef-rescue-scene-${snapshot.seed}.json`,lab.exportScene());
$('import-scene').onclick=()=>$('scene-file').click();
$('scene-file').onchange=async()=>{const f=$('scene-file').files[0];if(f){if(f.size>250000)toast('Scene file exceeds 250 KB.');else loadScene(await f.text());}$('scene-file').value='';};
$('capture-frame').onclick=()=>{try{const frame=scene.captureObservation();$('camera-evidence').src=`data:${frame.mimeType};base64,${frame.data}`;$('download-frame').href=$('camera-evidence').src;$('camera-evidence-meta').textContent=`Tool camera · T+ ${clock(frame.time)} · 768 × 576 · actual simulation render. No remote request made.`;$('frame-dialog').showModal();}catch(e){toast(e.message);}};
$('story').onclick=()=>$('story-dialog').showModal();$('close-story').onclick=()=>$('story-dialog').close();
$('close-frame').onclick=()=>$('frame-dialog').close();
$('export-run').onclick=()=>download(`reef-rescue-episode-${snapshot.seed}.json`,{version:1,scene:lab.exportScene(),episode:snapshot,exportedAt:new Date().toISOString()});
$('run-suite').onclick=()=>{if(suiteWorker){suiteWorker.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';$('suite-status').textContent='Evaluation stopped. No partial results reported.';return;}command({action:'pause'});report=null;$('export-report').disabled=true;$('suite-results').replaceChildren();$('run-suite').textContent='■ Stop suite';suiteWorker=new Worker(new URL('./evaluate.mjs',import.meta.url),{type:'module'});suiteWorker.onmessage=e=>{if(e.data.type==='progress')$('suite-status').textContent=`Running episode ${e.data.done} / ${e.data.total} · ${label(e.data.scenario)}`;if(e.data.type==='result'){report=e.data.report;renderReport();suiteWorker.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';$('export-report').disabled=false;}};suiteWorker.onerror=()=>{toast('Evaluation failed. Please reload and retry.');suiteWorker?.terminate();suiteWorker=null;$('run-suite').textContent='▶ Run stress suite';};suiteWorker.postMessage({scene:lab.exportScene(),count:Number($('run-count').value)});};
function renderReport(){const total=report.runs.length,passed=report.runs.filter(r=>r.success).length,summary=document.createElement('p');const strong=document.createElement('strong');strong.textContent=`${passed} / ${total}`;summary.append(strong,document.createTextNode(' completed'));const table=document.createElement('table'),head=table.createTHead().insertRow();for(const t of ['Condition','Pass','Mean time']){const th=document.createElement('th');th.textContent=t;head.append(th);}const body=table.createTBody();for(const condition of report.conditions){const rows=report.runs.filter(r=>r.condition===condition),row=body.insertRow();for(const text of [label(condition),`${rows.filter(r=>r.success).length}/${rows.length}`,`${(rows.reduce((v,r)=>v+r.time,0)/rows.length).toFixed(1)}s`])row.insertCell().textContent=text;}$('suite-results').replaceChildren(summary,table);$('suite-status').textContent='Suite complete. Export includes seeds, per-run outcomes, fault exposure, metrics and event logs.';}
$('export-report').onclick=()=>report&&download('reef-rescue-robustness-report.json',report);
for(const id of ['about','details'])$(id).onclick=()=>$('about-dialog').showModal();document.querySelector('.dialog-close').onclick=()=>$('about-dialog').close();
function renderUI(force=false){const s=snapshot;renderArchitecture(s);const p=s.perception;if(p){$('perception-evidence').textContent=p.reason||`${label(p.stage)} · ${p.targetId||'survey'} · simulated sensor evidence`;$('uv-exposure').style.width=`${Math.min(1,Math.max(0,p.exposure||0))*100}%`;} drawSonar(s);renderSensors(s);if(document.activeElement!==$('reef-seed'))$('reef-seed').value=s.seed;if(s.route){$('route-mode').value=s.route.mode;$('route-status').textContent=`${s.route.mode==='clearance'?'B / Wider clearance':'A / Direct transit'} · ${s.route.waypoints?.length||0} waypoints`;} $('elapsed').textContent=`${clock(s.time)}.${Math.floor(s.time%1*10)}`;$('phase').textContent=names[s.phase]||label(s.phase);$('phase-progress').style.width=`${s.phaseProgress*100}%`;$('run').textContent=s.running?'Ⅱ Pause mission':s.completed?'✓ Completed':s.phase==='aborted'?'■ Aborted':s.time?'▶ Resume mission':'▶ Start mission';$('run').disabled=s.completed||s.phase==='aborted';$('run-status').textContent=s.pendingDecision?'AWAITING DECISION':s.environmentHold?'SAFE HOLD':s.completed?'MISSION COMPLETE':s.running?'MISSION RUNNING':s.phase==='aborted'?'SAFE ABORT':'MISSION PAUSED';$('status-dot').style.background=s.environmentHold||s.phase==='aborted'?'#e9b978':'#a8e7cf';$('placed').textContent=`${s.metrics.placed}/${s.missionGoal}`;$('recoveries').textContent=s.metrics.recoveries;$('distance').replaceChildren(document.createTextNode(s.metrics.distance.toFixed(1)+' '),Object.assign(document.createElement('small'),{textContent:'m'}));$('energy').replaceChildren(document.createTextNode(Math.round(s.metrics.energy)+' '),Object.assign(document.createElement('small'),{textContent:'J'}));$('scene-seed').textContent=`SEED ${s.seed}`;for(const key of ['current','visibility']){$(`${key}-value`).textContent=`${s.water[key].toFixed(key==='current'?2:1)} ${key==='current'?'m/s':'m'}`;if(document.activeElement!==$(key))$(key).value=s.water[key];}$('scripted').classList.toggle('active',s.controller==='scripted');$('gemini').classList.toggle('active',s.controller==='gemini');$('base-station').classList.toggle('active',s.controller==='base_station');$('policy-badge').textContent=s.controller==='base_station'?'ROBOT + BASE':s.controller==='gemini'?'GEMINI':'DETERMINISTIC';$('decision-source').textContent=s.controller==='base_station'?'BASE STATION':s.controller.toUpperCase();if(s.controller==='base_station'&&baseError)$('decision-text').textContent=baseError;else if(s.controller==='base_station'&&baseInflight)$('decision-text').textContent=transportState;else if(!s.pendingDecision)$('decision-text').textContent=s.decision?.reason||s.status;
const stage=s.phase==='survey'||s.phase==='idle'?0:s.phase.startsWith('inspect')||s.phase==='approval'?1:['approach','grasp','cut','retract'].includes(s.phase)?2:['transport','recover_drop','regrasp','recovery'].includes(s.phase)?3:['align','secure','release','recover_placement'].includes(s.phase)?4:5;document.querySelectorAll('.mission-steps li').forEach((li,i)=>{li.classList.toggle('active',i===stage&&!s.completed);li.classList.toggle('done',i<stage||s.completed);});
const sig=JSON.stringify(s.colonies);if(sig!==sceneSignature){sceneSignature=sig;$('colony-select').replaceChildren(...s.colonies.map(c=>Object.assign(document.createElement('option'),{value:c.id,textContent:`${c.id} · ${label(c.health)}`})));if(!s.colonies.some(c=>c.id===selectedId))selectedId=s.colonies[0]?.id;selectColony(selectedId);}const es=JSON.stringify(s.events);if(es!==eventSignature){eventSignature=es;$('events').replaceChildren(...s.events.slice(-35).reverse().map(e=>{const div=document.createElement('div');div.className=`event ${e.type}`;const time=document.createElement('time'),p=document.createElement('p');time.textContent=clock(e.time);p.textContent=e.message;div.append(time,p);return div;}));}
}
async function boot(){renderUI(true);checkHealth();checkArchitecture();try{scene=new ReefScene($('reef'),{onSelect:id=>{selectColony(id);switchTab('editor');toast(`Selected ${id}. Pause the mission to edit.`);}});await scene.init();scene.setQuality($('quality').value);scene.update(snapshot,0);$('loading').hidden=true;}catch(e){$('loading').replaceChildren(Object.assign(document.createElement('strong'),{textContent:'3D view could not load'}),Object.assign(document.createElement('span'),{textContent:e.message}));console.error(e);}requestAnimationFrame(frame);}
function frame(now){const dt=Math.min(.1,(now-previous)/1000);previous=now;if(!document.hidden){if(snapshot.pilot?.mode==='manual'&&snapshot.running&&now-lastPilot>80){lab.command({action:'manual_input',...pilotInput()});lastPilot=now;}snapshot=lab.step(dt*speed);if(telemetry.sample(snapshot))queueTelemetry(telemetry.frames.at(-1));flushTelemetry(now);scene?.ready&&scene.update(snapshot,dt);if(now-lastUi>120){renderUI();renderPilot(snapshot);requestDecision();lastUi=now;}frameCount++;if(now-fpsStart>1000){$('fps').textContent=`${Math.round(frameCount*1000/(now-fpsStart))} FPS`;frameCount=0;fpsStart=now;}}requestAnimationFrame(frame);}
document.addEventListener('visibilitychange',()=>previous=performance.now());
window.addEventListener('pagehide',()=>{suiteWorker?.terminate();inflight?.abort();baseInflight?.abort();uplink.controller?.abort();scene?.dispose();});
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

function regenerate(seed){if(!Number.isInteger(seed)||seed<0||seed>4294967295){toast('Use an integer seed between 0 and 4294967295.');return;}cancelDecision();pilotKeys.clear();telemetry.clear();lab.command({action:'pause'});if(command({action:'randomize',seed})){selectedId=snapshot.colonies[0]?.id;$('scenario').value='baseline';$('scene-title').textContent='Sheltered reef';toast(`New reef generated · seed ${seed}`);}}
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
function stackReady(){return !!(componentStatus('gemma').configured&&componentStatus('argon').configured);}
const placementLabel=value=>({robot:'robot runtime',base_station:'base station',modal:'Modal hosted',cloud:'cloud service',unverified:'placement unverified'}[value]||value||'placement unverified');
async function checkArchitecture(){
 try{const response=await fetch('/api/lab/architecture',{signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error('Architecture service unavailable');architecture=await response.json();architectureError='';}
 catch(error){architecture=null;architectureError='Service status unavailable. Local scripted control is ready.';}
 renderArchitecture(snapshot);
}
function renderArchitecture(s){renderUplink();
 const gemma=componentStatus('gemma'),argon=componentStatus('argon'),cuopt=componentStatus('cuopt');
 for(const[name,result]of[['gemma',lastPerception],['argon',lastPlanning],['cuopt',lastPlanning?.optimizer?.source==='cuopt'?lastPlanning.optimizer:null]]){
  const component=componentStatus(name),badge=$(`${name}-runtime`);badge.textContent=result?'RESPONSE RECEIVED':component.configured?'CONFIGURED':'NOT CONNECTED';badge.dataset.state=result?'live':component.configured?'configured':'offline';
  $(`${name}-model`).textContent=component.configured?`${component.model||name} · ${placementLabel(component.deployment)} · ${result?'response verified':'awaiting first response'}`:name==='cuopt'?'Local waypoint routes; cuOpt not configured.':`${name==='gemma'?'Gemma perception':'Argon reasoning'} adapter not configured.`;
 }
 $('stack-status').textContent=architectureError||(stackReady()?'Gemma perception → Argon reasoning. Selecting Robot + base sends tool-camera frames and telemetry to configured services.':'Local scripted control ready. Robot + base needs configured Gemma and Argon services.');
 for(const id of['base-station','use-base'])$(id).setAttribute('aria-disabled',String(!stackReady()));
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
 $('pipeline-base').textContent=remote?(lastPlanning?'Base reasoning · Argon response received':'Base reasoning · awaiting Argon'):s.controller==='gemini'?'Legacy cloud policy · Google Gemini':'Base policy · local scripted control';
 $('pipeline-transport').textContent=uplink.enabled?`Base received ${uplink.accepted} sensor frames · ${uplink.queue.length} queued`:remote?`${transportState} · continuous uplink disconnected`:'5 Hz local recorder · uplink disconnected';
 $('sensor-evidence-source').textContent='CAMERA / UV EXPOSURE · SYNTHETIC';
}
function useBase(){if(!stackReady()){switchTab('architecture');toast('Configure Gemma perception and Argon reasoning adapters first. Scripted control remains available.');return;}cancelDecision();speed=1;$('speed').value='1';if(command({action:'set_controller',mode:'base_station'})){transportState='HTTP decision-gate packets';toast('Robot + base selected. Camera frames go to configured perception; telemetry goes to the base.');}}
$('base-station').onclick=useBase;$('use-base').onclick=useBase;
for(const id of['show-architecture','pipeline-details'])$(id).onclick=()=>switchTab('architecture');
$('refresh-architecture').onclick=checkArchitecture;
for(const id of['safe-scripted','decision-fallback'])$(id).onclick=()=>{cancelDecision();command({action:'set_controller',mode:'scripted'});toast('Local scripted control selected. Remote results cannot override local safety.');};
async function baseRequest(path,payload,controller){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Configured service failed');packetCount++;return data;}
async function requestBasePipeline(force=false){
 if(baseInflight||!snapshot.running||snapshot.pilot?.mode==='manual'||!scene?.ready)return;
 const inspecting=['inspect_recipient','inspect_donor'].includes(snapshot.phase),pending=snapshot.pendingDecision;
 const targetId=snapshot.phase==='inspect_recipient'?snapshot.targetId:snapshot.donorId;
 const operation=inspecting&&Number(snapshot.perception?.exposure||0)>=.8?'perception':pending?'planning':null;if(!operation)return;
 const key=operation==='perception'?`${generation}:${snapshot.phase}:${targetId}`:`${generation}:${pending.id}`;
 if(!force&&baseAttempted.has(key))return;baseAttempted.add(key);baseError='';
 const token=generation,controller=new AbortController();baseInflight=controller;$('retry-gemini').hidden=true;$('decision-fallback').hidden=true;
 transportState=operation==='perception'?'Sending robot camera to Gemma…':'Sending observations to Argon / route planning…';renderArchitecture(snapshot);
 const timer=setTimeout(()=>controller.abort(),45000);
 try{
  if(operation==='perception'){
   const image=scene.captureObservation(),id=`perception-${generation}-${targetId}-${Math.round(image.time*1000)}`;
   const observation={phase:snapshot.phase,frameTime:image.time,targetId:snapshot.targetId,donorId:snapshot.donorId,water:snapshot.water,robot:{position:snapshot.robot.position,gripper:snapshot.robot.gripper,yaw:snapshot.robot.yaw},sonar:{range:snapshot.sonar?.range,contacts:(snapshot.sonar?.contacts||[]).slice(0,24)}};
   const packet=await baseRequest('/api/lab/perception',{id,observation,image},controller);if(token!==generation)return;
   if(packet.source!=='gemma'||(packet.requestId??packet.id)!==id)throw new Error('Gemma packet source or identity mismatch');
   lab.command({action:'ingest_perception',packet});lastPerception=packet;snapshot=lab.snapshot();transportState='Gemma observation received via HTTP';
   const expected=snapshot.phase==='inspect_recipient'?'bleached_alive':'healthy',accepted=packet.observations?.some(o=>o.id===targetId&&o.health===expected&&o.confidence>=.7);
   if(!accepted){baseError='Gemma evidence is uncertain or incompatible. Inspection is held; retry a new frame or use local scripted control.';$('retry-gemini').hidden=false;$('decision-fallback').hidden=false;}
  }else{
   const observation={...pending.observation,frameTime:snapshot.time,route:snapshot.route};
   const packet=await baseRequest('/api/lab/plan',{id:pending.id,observation,allowedActions:pending.allowedActions,perception:lastPerception},controller);if(token!==generation)return;
   if(packet.source!=='argon'||(packet.requestId??packet.id)!==pending.id||!pending.allowedActions.includes(packet.decision))throw new Error('Argon packet source, identity or action mismatch');
   lab.command({action:'ingest_plan',packet});lab.command({action:'apply_decision',id:pending.id,decision:packet.decision,reason:packet.reason,source:'base_station',routeMode:packet.routeMode??null,evidence:{perception:lastPerception,planning:packet}});lastPlanning=packet;snapshot=lab.snapshot();transportState='Base plan received via HTTP';
  }
 }catch(error){if(token===generation){baseError=`${operation==='perception'?'Gemma perception':'Base planning'} held: ${error.name==='AbortError'?'request timed out':error.message}. Retry explicitly or select local scripted control.`;transportState='HTTP request failed · mission held';$('retry-gemini').hidden=false;$('decision-fallback').hidden=false;toast('Remote stage unavailable. Local safety remains active.');}}
 finally{clearTimeout(timer);if(baseInflight===controller)baseInflight=null;if(token===generation)renderUI(true);}
}

function resetUplink(){uplink.controller?.abort();uplink.controller=null;uplink.id=crypto.randomUUID();uplink.sequence=0;uplink.queue=[];uplink.accepted=0;uplink.skipped=0;uplink.lastSent=0;uplink.lastReceipt=null;uplink.lastFrameTime=null;uplink.error='';}
function queueTelemetry(frame){
 if(!uplink.enabled||!frame)return;
 if(uplink.lastFrameTime!==null&&frame.time<uplink.lastFrameTime-1e-9)resetUplink();
 if(uplink.lastFrameTime!==null&&frame.time<=uplink.lastFrameTime)return;
 uplink.lastFrameTime=frame.time;uplink.queue.push(frame);
 if(uplink.queue.length>5){uplink.skipped+=uplink.queue.length-5;uplink.queue.splice(0,uplink.queue.length-5);}
}
function renderUplink(){
 $('connect-telemetry').textContent=uplink.enabled?'Disconnect telemetry':'Connect telemetry to base';
 $('uplink-badge').textContent=uplink.error?'ERROR':uplink.enabled?(uplink.lastReceipt?'CONNECTED':'CONNECTING'):'DISCONNECTED';$('uplink-badge').dataset.state=uplink.error?'error':uplink.lastReceipt&&uplink.enabled?'live':'offline';
 $('uplink-received').textContent=`${uplink.accepted} frames acknowledged`;$('uplink-queue').textContent=`${uplink.queue.length} / ${uplink.skipped}`;
 $('uplink-status').textContent=uplink.error||(uplink.enabled?(uplink.lastReceipt?`Base gateway receipt at T+ ${clock(uplink.lastReceipt.lastFrameTime)}. Sensor batches only; model inference is separate.`:'Connecting with the next sensor frame. Up to 5 frames per batch; no images or model calls.'):'Uplink disconnected. Local recording continues; connect to send bounded sensor batches to the base gateway.');
}
$('connect-telemetry').onclick=()=>{
 if(uplink.enabled){uplink.enabled=false;uplink.controller?.abort();uplink.controller=null;uplink.queue=[];toast('Telemetry uplink disconnected. Local recording continues.');}
 else{resetUplink();uplink.enabled=true;queueTelemetry(telemetry.frames.at(-1));toast('Telemetry uplink enabled. Sensor batches go to the base gateway; images stay out of this stream.');}
 renderArchitecture(snapshot);
};
async function flushTelemetry(now){
 if(!uplink.enabled||uplink.controller||!uplink.queue.length||now-uplink.lastSent<1100)return;
 const id=uplink.id,sequence=uplink.sequence++,frames=uplink.queue.splice(0,5),controller=new AbortController();
 while(frames.length>1&&new TextEncoder().encode(JSON.stringify({streamId:id,sequence,frames})).length>60*1024)uplink.queue.unshift(frames.pop());
 uplink.controller=controller;uplink.lastSent=now;
 const timer=setTimeout(()=>controller.abort(),8000);
 try{
  const response=await fetch('/api/lab/telemetry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({streamId:id,sequence,frames}),signal:controller.signal});const receipt=await response.json();
  if(!response.ok)throw new Error(receipt.error||'Telemetry gateway rejected the batch');
  if(!uplink.enabled||uplink.id!==id)return;
  if(receipt.streamId!==id||receipt.sequence!==sequence||receipt.acceptedFrames!==frames.length||!Number.isInteger(receipt.totalFrames)||receipt.totalFrames<receipt.acceptedFrames||!Number.isFinite(receipt.lastFrameTime))throw new Error('Telemetry receipt did not match the transmitted batch');
  uplink.accepted+=receipt.acceptedFrames;uplink.lastReceipt=receipt;
 }catch(error){if(uplink.enabled&&uplink.id===id){uplink.error=`Telemetry disconnected: ${error.name==='AbortError'?'request timed out':error.message}. Reconnect explicitly; local physics and recording continue.`;uplink.enabled=false;uplink.skipped+=frames.length+uplink.queue.length;uplink.queue=[];}}
 finally{clearTimeout(timer);if(uplink.controller===controller)uplink.controller=null;renderUplink();}
}
