import { ReefLab, defaultScene } from './simulation.mjs';
import { ReefScene } from './scene.mjs';
import { TelemetryRecorder } from './telemetry.mjs';
import { SemanticMemory } from './semantic-memory.mjs';
import { MissionPanel } from './mission-panel.mjs';
import { LiveDemoRecorder } from './recorder.mjs';
const $ = id => document.getElementById(id);
const randomSeed=()=>crypto.getRandomValues(new Uint32Array(1))[0];
const lab = new ReefLab({...defaultScene(randomSeed()),restorationMode:'loose_fragment',missionGoal:1,controller:'base_station'});
const telemetry=new TelemetryRecorder();
const semanticMemory=new SemanticMemory({maxRecords:128});let memorySceneSignature='',memoryUiSignature='',memoryError='';
const pilotKeys=new Set(),roamKeys=new Set();let lastPilot=0;
let pipCamera='tool',evidenceCamera='tool',lastPip=0,lastEvidence=0;const activityLog=[];
let missionPanel, reviewAbort=null;
let scene, snapshot=lab.snapshot(), selectedId='donor-1', speed=1, report=null, suiteWorker=null;
let sceneSignature='', eventSignature='', lastUi=0, previous=performance.now(), frameCount=0, fpsStart=performance.now();
let generation=0, toastTimer;
const uplink={enabled:false,id:null,sequence:0,queue:[],accepted:0,skipped:0,lastSent:0,lastReceipt:null,error:'',controller:null};
let activationRequested=false,activationWasRunning=false,activationStarted=0,readinessTimer=null,warmupInflight=null;
let readinessTrace='',modelUnavailable=false,evidenceHold=false,architectureCheckedAt=0,startCheckInflight=false;
let architecture=null,architectureError='',baseInflight=null,baseAttempted=new Set(),lastPerception=null,lastPlanning=null,lastReview=null,reviewInflight=false,baseError='',packetCount=0,transportState='Local recorder only';
let assistEpisodeId=crypto.randomUUID(),assistScene=lab.scene,assistLastTime=0,assistCount=0,assistIssues=new Set(),assistInflight=null,assistHolding=false,assistIssue=null,lastAssist=null,assistLastDrop=0,assistCurrentActive=false,assistCurrentSince=null,assistCurrentHandled=false;
let assistRetry=null,assistContext=null;
const names={inspect_fragment:'Inspect fragment',idle:'Ready to begin',survey:'Survey & pairing',inspect_recipient:'Inspect recipient',inspect_donor:'Inspect donor',approval:'Harvest approval',approach:'Approach donor',grasp:'Close gripper',cut:'Cut donor branch',retract:'Retract cutting',transport:'Transfer fragment',align:'Align contact',secure:'Secure fragment',release:'Release gripper',verify:'Verify placement',recover_drop:'Recover dropped fragment',recover_placement:'Correct placement',regrasp:'Regrasp fragment',recovery:'Assess setback',complete:'Mission complete',aborted:'Safe abort'};
const label = text => String(text??'').replaceAll('_',' ');
const publicText=text=>String(text??'');
const autonomyReady=()=>!startCheckInflight&&(snapshot.controller==='base_station'&&!activationRequested&&stackReady());
const clock = seconds => `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function cancelDecision(){reviewAbort?.abort();reviewAbort=null;cancelAssistance();stopActivation();generation++;baseInflight?.abort();baseInflight=null;baseAttempted.clear();baseError='';lastPerception=null;lastPlanning=null;transportState='Local recorder only';$('retry-gemini').hidden=true;}
function command(data){try{lab.command(data);snapshot=lab.snapshot();renderUI(true);renderPilot(snapshot);return true;}catch(error){toast(error.message);return false;}}
function reset(){cancelDecision();resetAssistanceEpisode();activityLog.length=0;pilotKeys.clear();telemetry.clear();lab.reset();if($('scenario').value==='compound')for(const kind of ['drop','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();renderUI(true);}
function switchTab(name){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-content').forEach(p=>p.hidden=p.id!==`tab-${name}`);missionPanel?.setActive(name==='evidence');}
for(const b of document.querySelectorAll('[data-tab]'))b.addEventListener('click',()=>switchTab(b.dataset.tab));
$('run').onclick=async()=>{
 if(startCheckInflight)return;
 if(!snapshot.running&&snapshot.pilot?.mode!=='manual'&&snapshot.controller==='base_station'&&!activationRequested&&Date.now()-architectureCheckedAt>180000){
  const token=generation;startCheckInflight=true;renderUI();
  try{await checkArchitecture();if(token!==generation)return;if(!stackReady()){toast('Refreshing model services before the mission starts. Start again when ready.');await useBase({automatic:true});return;}}
  finally{startCheckInflight=false;renderUI();}
 }
 if(!snapshot.running&&snapshot.pilot?.mode!=='manual'&&!autonomyReady()){toast('Model services are not ready. The mission remains paused.');return;}
 command({action:snapshot.running?'pause':'run'});
};
$('reset').onclick=reset;
$('new-reef').onclick=()=>regenerate(randomSeed());
$('apply-seed').onclick=()=>regenerate(Number($('reef-seed').value));
$('route-mode').onchange=()=>command({action:'set_route',mode:$('route-mode').value});
for(const id of ['show-routes','show-sonar','show-currents','show-regions'])$(id).onchange=()=>scene?.setOverlays?.({routes:$('show-routes').checked,sonar:$('show-sonar').checked,currents:$('show-currents').checked,regions:$('show-regions').checked});
$('speed').onchange=()=>{if(snapshot.controller==='base_station'){speed=1;$('speed').value='1';toast('Robot + base control runs at1× so camera observations stay current.');}else speed=Number($('speed').value);};
$('quality').onchange=()=>scene?.setQuality($('quality').value);
for(const b of document.querySelectorAll('[data-camera]'))b.onclick=()=>{roamKeys.clear();scene?.setCamera(b.dataset.camera);document.querySelectorAll('[data-camera]').forEach(x=>x.classList.toggle('active',x===b));};
for(const key of ['current','visibility'])$(''+key).addEventListener('input',()=>command({action:'set_water',[key]:Number($(key).value)}));
for(const b of document.querySelectorAll('[data-fault]'))b.onclick=()=>{if(command({action:'inject_fault',kind:b.dataset.fault})){toast(`${label(b.dataset.fault)} introduced`);$('fault-status').textContent=`Last injected: ${label(b.dataset.fault)} · see event log.`;}};
$('scenario').onchange=()=>{activityLog.length=0;cancelDecision();lab.command({action:'pause'});const chosen=$('scenario').value, config={...defaultScene(snapshot.seed),restorationMode:'loose_fragment',missionGoal:lab.scene.missionGoal};if(chosen==='current')config.water.current=.32;if(chosen==='visibility')config.water.visibility=2;lab.loadScene(config);if(chosen==='compound')for(const kind of ['drop','bad_placement'])lab.command({action:'inject_fault',kind});snapshot=lab.snapshot();$('scene-title').textContent={baseline:'Sheltered reef',current:'Cross-current',visibility:'Low visibility',compound:'Compound setbacks'}[chosen];renderUI(true);toast('Scenario loaded. Start a fresh mission.');};
async function requestDecision(force=false){if(snapshot.controller!=='base_station')return;if(maybeRequestAssistance())return;return requestBasePipeline(force);}
$('retry-gemini').onclick=()=>requestDecision(true);
$('rescan-evidence').onclick=()=>{cancelDecision();if(command({action:'request_rescan',reason:'Operator requested fresh camera evidence'}))toast('Repositioning for fresh visual evidence; fragment ownership is preserved.');};
function selectColony(id){selectedId=id;missionPanel?.selectColony(id);scene?.setSelected(id);$('colony-select').value=id;fillColony();}
function fillColony(){const c=snapshot.colonies.find(c=>c.id===selectedId);if(!c)return;$('colony-x').value=c.position[0].toFixed(2);$('colony-y').value=c.position[1].toFixed(2);$('colony-health').value=c.health;$('colony-genet').value=c.genet;$('colony-radius').value=c.radius;$('colony-height').value=c.height;}
$('colony-select').onchange=()=>selectColony($('colony-select').value);
$('colony-form').onsubmit=e=>{e.preventDefault();const c=snapshot.colonies.find(c=>c.id===selectedId);if(!c)return;if(command({action:'edit_colony',id:selectedId,patch:{position:[Number($('colony-x').value),Number($('colony-y').value),0],health:$('colony-health').value,genet:$('colony-genet').value.trim(),radius:Number($('colony-radius').value),height:Number($('colony-height').value)}})){cancelDecision();toast('Colony updated. Episode reset with the edited scene.');}};
$('add-colony').onclick=()=>{const id=`colony-${Date.now().toString(36)}`,c={id,position:[0,3,0],health:'bleached_alive',genet:'G1',species:'Pocillopora damicornis',radius:.45,height:.7};if(command({action:'add_colony',colony:c})){cancelDecision();selectColony(id);toast('Colony added. Adjust its position in the editor.');}};
$('remove-colony').onclick=()=>{if(command({action:'remove_colony',id:selectedId})){cancelDecision();toast('Colony removed. Episode reset.');}};
$('add-rock').onclick=()=>{if(command({action:'add_obstacle',obstacle:{id:`rock-${Date.now().toString(36)}`,position:[(snapshot.obstacles.length%4)*1.4-2,0,0],radius:.55}})){cancelDecision();toast('Rock added to the vehicle clearance model.');}};
$('remove-rock').onclick=()=>{const rock=snapshot.obstacles.at(-1);if(rock&&command({action:'remove_obstacle',id:rock.id}))cancelDecision();};
function download(name,data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('save-scene').onclick=()=>{try{localStorage.setItem('pelagic-lab-scene-v1',JSON.stringify(lab.exportScene()));toast('Scene saved in this browser.');}catch{toast('Local storage unavailable. Export a scene file instead.');}};
function loadScene(data){try{const parsed=typeof data==='string'?JSON.parse(data):data;lab.loadScene({...parsed,restorationMode:'loose_fragment'});activityLog.length=0;cancelDecision();snapshot=lab.snapshot();renderUI(true);toast('Scene loaded in loose-fragment rescue mode. Ready for a new episode.');}catch(e){toast(e.message);}}
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
function renderUI(force=false){const s=snapshot;syncAssistanceEpisode(s);missionPanel?.update(s,activityLog);if(force)bindMemoryScene();renderArchitecture(s);const p=s.perception;if(p){$('perception-evidence').textContent=p.reason||`${label(p.stage)} · ${p.targetId||'survey'} · simulated sensor evidence`;$('uv-exposure').style.width=`${Math.min(1,Math.max(0,p.exposure||0))*100}%`;} drawSonar(s);renderSensors(s);if(document.activeElement!==$('reef-seed'))$('reef-seed').value=s.seed;if(s.route){$('route-mode').value=s.route.mode;$('route-status').textContent=`${s.route.mode==='clearance'?'B / Wider clearance':'A / Direct transit'} · ${s.route.waypoints?.length||0} waypoints`;} $('elapsed').textContent=`${clock(s.time)}.${Math.floor(s.time%1*10)}`;$('phase').textContent=names[s.phase]||label(s.phase);$('phase-progress').style.width=`${s.phaseProgress*100}%`;$('run').textContent=s.running?'Ⅱ Pause mission':s.completed?'✓ Completed':s.phase==='aborted'?'■ Aborted':s.time?'▶ Resume mission':'▶ Start mission';$('run').disabled=s.completed||s.phase==='aborted'||!s.running&&!autonomyReady();$('run-status').textContent=s.assistanceHold?'ASSISTANCE HOLD':s.pendingDecision?'AWAITING DECISION':s.environmentHold?'SAFE HOLD':s.completed?'MISSION COMPLETE':s.running?'MISSION RUNNING':s.phase==='aborted'?'SAFE ABORT':'MISSION PAUSED';$('status-dot').style.background=s.environmentHold||s.phase==='aborted'?'#e9b978':'#a8e7cf';$('placed').textContent=`${s.metrics.placed}/${s.missionGoal}`;$('recoveries').textContent=s.metrics.recoveries;$('distance').replaceChildren(document.createTextNode(s.metrics.distance.toFixed(1)+' '),Object.assign(document.createElement('small'),{textContent:'m'}));$('energy').replaceChildren(document.createTextNode(Math.round(s.metrics.energy)+' '),Object.assign(document.createElement('small'),{textContent:'J'}));$('scene-seed').textContent=`SEED ${s.seed}`;for(const key of ['current','visibility']){$(`${key}-value`).textContent=`${s.water[key].toFixed(key==='current'?2:1)} ${key==='current'?'m/s':'m'}`;if(document.activeElement!==$(key))$(key).value=s.water[key];}$('base-station').classList.toggle('active',s.controller==='base_station');$('policy-badge').textContent=activationRequested?'CONNECTING':'MODEL-GUIDED';$('decision-source').textContent=s.controller==='base_station'?'ROBOT + BASE':'AWAITING MODELS';if(assistHolding)$('decision-text').textContent=baseError||'Robot held for bounded Argon assistance; fresh Gemma evidence remains required.';else if(s.controller==='base_station'&&s.rescan)$('decision-text').textContent=s.status;else if(s.controller==='base_station'&&baseError)$('decision-text').textContent=baseError;else if(s.controller==='base_station'&&baseInflight)$('decision-text').textContent=transportState;else if(!s.pendingDecision)$('decision-text').textContent=publicText(s.decision?.reason||s.status);
const stage=s.phase==='survey'||s.phase==='idle'?0:s.phase.startsWith('inspect')||s.phase==='approval'?1:['approach','grasp','cut','retract'].includes(s.phase)?2:['transport','recover_drop','regrasp','recovery'].includes(s.phase)?3:['align','secure','release','recover_placement'].includes(s.phase)?4:5;document.querySelectorAll('.mission-steps li').forEach((li,i)=>{li.classList.toggle('active',i===stage&&!s.completed);li.classList.toggle('done',i<stage||s.completed);});
const sig=JSON.stringify(s.colonies);if(sig!==sceneSignature){sceneSignature=sig;$('colony-select').replaceChildren(...s.colonies.map(c=>Object.assign(document.createElement('option'),{value:c.id,textContent:`${c.id} · ${label(c.health)}`})));if(!s.colonies.some(c=>c.id===selectedId))selectedId=s.colonies[0]?.id;selectColony(selectedId);}const visibleEvents=[...s.events,...activityLog].sort((a,b)=>a.time-b.time).slice(-55);const es=JSON.stringify(visibleEvents);if(es!==eventSignature){eventSignature=es;$('events').replaceChildren(...visibleEvents.reverse().map(e=>{const div=document.createElement('div');div.className=`event ${e.type}`;const time=document.createElement('time'),p=document.createElement('p');time.textContent=clock(e.time);p.textContent=publicText(e.message);div.append(time,p);return div;}));}
}
async function boot(){renderUI(true);useBase({automatic:true});try{scene=new ReefScene($('reef'),{onSelect:id=>{selectColony(id);if(!missionPanel?.active||missionPanel.source!=='lab'){switchTab('editor');toast(`Selected ${id}. Pause the mission to edit.`);}}});await scene.init();scene.setQuality($('quality').value);scene.update(snapshot,0);$('loading').hidden=true;}catch(e){$('loading').replaceChildren(Object.assign(document.createElement('strong'),{textContent:'3D view could not load'}),Object.assign(document.createElement('span'),{textContent:e.message}));console.error(e);}requestAnimationFrame(frame);}
function frame(now){const dt=Math.max(0,Math.min(.1,(now-previous)/1000));previous=now;if(!document.hidden){if(snapshot.pilot?.mode==='manual'&&snapshot.running&&now-lastPilot>80){lab.command({action:'manual_input',...pilotInput()});lastPilot=now;}snapshot=lab.step(dt*speed);if(telemetry.sample(snapshot))queueTelemetry(telemetry.frames.at(-1));flushTelemetry(now);if(scene?.ready){moveFieldCamera(dt);scene.update(snapshot,dt);}renderCameraPreview(now);if(now-lastUi>120){renderUI();renderPilot(snapshot);requestDecision();lastUi=now;}frameCount++;if(now-fpsStart>1000){$('fps').textContent=`${Math.round(frameCount*1000/(now-fpsStart))} FPS`;frameCount=0;fpsStart=now;}}requestAnimationFrame(frame);}
document.addEventListener('visibilitychange',()=>previous=performance.now());
window.addEventListener('pagehide',()=>{suiteWorker?.terminate();baseInflight?.abort();assistInflight?.abort();warmupInflight?.abort();clearTimeout(readinessTimer);uplink.controller?.abort();scene?.dispose();});
missionPanel=new MissionPanel({onSelect:id=>selectColony(id)});
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
$('manual-toggle').onclick=()=>{cancelDecision();pilotKeys.clear();roamKeys.clear();const mode=snapshot.pilot?.mode==='manual'?'autonomous':'manual';if(command({action:'set_pilot',mode})){if(mode==='manual'){speed=1;$('speed').value='1';switchTab('mission');scene?.setCamera('pilot');toast('Robot Pilot selected. Resume pilot to move: WASD · Q rise / E dive · arrows yaw.');}else toast('Autonomous control resumed from the current pose.');}};
$('pilot-brake').onclick=()=>stopPilot();
$('grip-open').onclick=()=>command({action:'manual_gripper',open:true});$('grip-close').onclick=()=>command({action:'manual_gripper',open:false});
const pilotCodes=['KeyW','KeyS','KeyA','KeyD','KeyQ','KeyE','ArrowLeft','ArrowRight'];
const roamCodes=['KeyW','KeyS','KeyA','KeyD','KeyQ','KeyE'];
function keyboardBlocked(target=document.activeElement){return !!document.querySelector('dialog[open]')||!!target?.closest?.('input,select,textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');}
function roamActive(){return document.activeElement===$('reef')&&snapshot.pilot?.mode!=='manual'&&!keyboardBlocked();}
function updateCameraHint(){const manual=snapshot.pilot?.mode==='manual',focused=document.activeElement===$('reef');$('view-hint').textContent=manual?'ROBOT PILOT · WASD MOVE · Q RISE / E DIVE · ← → YAW · ESC PAUSE':focused?'CAMERA ONLY · WASD ROAM · Q UP / E DOWN · DRAG ORBIT · ESC RELEASE':'CLICK REEF TO ROAM · WASD · Q UP / E DOWN · DRAG ORBIT · SCROLL ZOOM';$('reef').classList.toggle('keyboard-active',focused&&!manual);}
function moveFieldCamera(dt){if(!roamActive()){roamKeys.clear();return;}if(!roamKeys.size)return;scene.moveSpectator?.({forward:Number(roamKeys.has('KeyW'))-Number(roamKeys.has('KeyS')),right:Number(roamKeys.has('KeyD'))-Number(roamKeys.has('KeyA')),up:Number(roamKeys.has('KeyQ'))-Number(roamKeys.has('KeyE'))},dt);document.querySelectorAll('[data-camera]').forEach(b=>b.classList.toggle('active',b.dataset.camera==='orbit'));}
$('reef').addEventListener('pointerdown',()=>{if(!document.querySelector('dialog[open]'))$('reef').focus({preventScroll:true});});
$('reef').addEventListener('focus',updateCameraHint);
$('reef').addEventListener('blur',()=>{roamKeys.clear();updateCameraHint();});
window.addEventListener('keydown',e=>{
 if(keyboardBlocked(e.target)||e.ctrlKey||e.metaKey||e.altKey)return;
 if(snapshot.pilot?.mode==='manual'){
  if(e.code==='Escape'){e.preventDefault();stopPilot(true);return;}
  if(pilotCodes.includes(e.code)){e.preventDefault();pilotKeys.add(e.code);}return;
 }
 if(!roamActive())return;
 if(e.code==='Escape'){e.preventDefault();roamKeys.clear();$('reef').blur();return;}
 if(roamCodes.includes(e.code)){e.preventDefault();roamKeys.add(e.code);}
});
window.addEventListener('keyup',e=>{pilotKeys.delete(e.code);roamKeys.delete(e.code);});
window.addEventListener('blur',()=>{roamKeys.clear();stopPilot(true);});
document.addEventListener('focusin',e=>{roamKeys.clear();if(keyboardBlocked(e.target))stopPilot();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){roamKeys.clear();stopPilot(true);}});
for(const b of document.querySelectorAll('[data-pilot]')){b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);pilotKeys.add(b.dataset.pilot);});for(const event of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(event,()=>pilotKeys.delete(b.dataset.pilot));}
function renderPilot(s){updateCameraHint();const manual=s.pilot?.mode==='manual';$('manual-controls').hidden=!manual;$('manual-toggle').textContent=manual?'↗ Autonomy':'⌨ Pilot';$('manual-toggle').classList.toggle('active',manual);$('speed').disabled=manual||s.controller==='base_station';document.querySelectorAll('[data-pilot]').forEach(b=>b.classList.toggle('held',pilotKeys.has(b.dataset.pilot)));if(manual){$('run').disabled=false;$('run').textContent=s.running?'Ⅱ Pause pilot':'▶ Resume pilot';$('run-status').textContent=s.running?'MANUAL PILOT':'PILOT PAUSED';}}
function renderSensors(s){const v=s.water.currentVector||[s.water.current,0,0];$('current-overlay-legend').textContent=`Current arrows ×5 (capped) · ${Math.hypot(...v).toFixed(2)} m/s at robot`; $('current-vector').textContent=v.map(n=>Number(n).toFixed(2)).join(' / ')+' m/s';const velocity=s.robot.velocity||[0,0,0];const clearance=s.navigation?.bedClearance??s.navigation?.clearance??s.navigation?.terrainClearance;$('nav-state').textContent=`${Math.hypot(...velocity).toFixed(2)} m/s · ${Number.isFinite(clearance)?clearance.toFixed(2):'—'} m`;$('fusion-state').textContent=s.sensors?.fusion?.opticalAvailable?'Sonar + optical registry':'Sonar · optical unavailable';const summary=telemetry.summary();$('stream-count').textContent=summary.frames??summary.count??summary.samples??0;}
$('export-telemetry').onclick=()=>{const url=URL.createObjectURL(new Blob([telemetry.exportJSONL()],{type:'application/x-ndjson'})),a=document.createElement('a');a.href=url;a.download=`reef-rescue-telemetry-${snapshot.seed}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};


function componentStatus(name){return architecture?.components?.[name]||{};}
function requiredComponents(){return ['gemma','cuopt'];}
function stackConfigured(){return requiredComponents().every(name=>componentStatus(name).configured);}
function componentReady(name){const c=componentStatus(name);if(typeof c.ready==='boolean')return c.ready;if(c.readiness)return c.readiness==='ready';return c.status==='verified_response';}
function stackReady(){return requiredComponents().every(componentReady);}
const placementLabel=value=>({robot:'robot runtime',base_station:'base station',modal:'Modal hosted',cloud:'cloud service',unverified:'placement unverified'}[value]||value||'placement unverified');
async function checkArchitecture(){
 try{const response=await fetch('/api/lab/architecture',{signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error('Architecture service unavailable');architecture=await response.json();architectureCheckedAt=Date.now();architectureError='';if(activationRequested){const trace=JSON.stringify(Object.entries(architecture.components||{}).map(([name,c])=>[name,c.readiness||c.status]));if(trace!==readinessTrace){readinessTrace=trace;logActivity('transport',`Service readiness: ${Object.entries(architecture.components||{}).map(([name,c])=>`${name} ${c.readiness||c.status||'unknown'}`).join(' · ')}.`);}}}
 catch(error){architecture=null;architectureError='Model service status unavailable. Autonomous operation remains held until model services reconnect.';}
 renderArchitecture(snapshot);return architecture;
}
function renderArchitecture(s){renderUplink();renderMemory();renderAssistance(s);
 $('review-mission').disabled=reviewInflight||!['complete','aborted'].includes(s.phase);
 $('postmission-review').textContent=lastReview?`${lastReview.summary} ${(lastReview.recommendations||[]).join(' ')} Review only; no policy change applied.`:reviewInflight?'Argon is reviewing the completed mission…':'Argon also reviews completed missions. Recommendations require human review and regression checks.';
 const gemma=componentStatus('gemma'),argon=componentStatus('argon'),cuopt=componentStatus('cuopt');
 for(const[name,result]of[['gemma',lastPerception],['argon',lastAssist||lastReview],['cuopt',lastPlanning?.optimizer?.source==='cuopt'?lastPlanning.optimizer:null]]){
  const component=componentStatus(name),badge=$(`${name}-runtime`),readiness=component.readiness||component.status||'unconfigured',warming=['warming','loading','starting'].includes(readiness),error=readiness==='error',ready=componentReady(name);
  badge.textContent=result?'RESPONSE RECEIVED':warming?'WARMING':error?'SERVICE ERROR':ready?(result?'RESPONSE RECEIVED':'SERVICE READY'):component.configured?'NOT STARTED':'NOT CONFIGURED';badge.dataset.state=result?'live':warming?'warming':error?'error':ready?'live':component.configured?'configured':'offline';
  $(`${name}-model`).textContent=component.configured?`${component.model||name} · ${placementLabel(component.deployment)} · ${warming?'model startup in progress':error?'readiness failed':ready?(result?'actual response received':'ready for requests'):component.message||'awaiting service startup'}`:name==='cuopt'?'cuOpt is required in full-stack mode.':'Adapter is not configured.';
 }
 const missing=requiredComponents().filter(name=>!componentStatus(name).configured),waiting=requiredComponents().filter(name=>!componentReady(name));
 $('stack-readiness-label').textContent=`FULL STACK · ${activationRequested?'CONNECTING':stackReady()?'READY':missing.length?'UNCONFIGURED':'NOT READY'}`;
 $('stack-readiness-detail').textContent=architectureError||(missing.length?`Missing: ${missing.join(', ')}. No substitute model or solver is implied.`:waiting.length?`Waiting for ${waiting.join(', ')}. Startup and inference are separate stages.`:`${requiredComponents().join(' + ')} services are ready. Model evidence appears only after actual requests.`);
 $('stack-status').textContent=architectureError||(activationRequested?'Model-guided autonomy · warming services. The mission stays paused.':stackReady()?'Model-guided autonomy · Gemma → inspectable policy → '+'cuOpt'+'. Ready when you start the mission.':'Model-guided autonomy · awaiting model services.');
 $('base-station').textContent=activationRequested?'Model services warming…':'Model-guided autonomy';
 for(const id of['base-station','use-base'])$(id).setAttribute('aria-disabled',String(activationRequested));
 $('use-base').textContent=activationRequested?'Connecting model services…':'Connect full robot + base stack';$('cancel-stack-connect').hidden=!activationRequested;
 $('rescan-evidence').hidden=s.controller!=='base_station'||(!assistHolding&&!s.pendingDecision&&!/stale|expired|rescan/i.test(s.status||''));
 $('placement-robot').textContent=gemma.configured?`Simulated robot · Gemma ${placementLabel(gemma.deployment)}`:'Browser simulation · synthetic sensors';
 $('placement-base').textContent='Local policy + cuOpt; Argon assists held issues and reviews completed missions';
 const modal=Object.entries(architecture?.components||{}).filter(([,c])=>c.configured&&c.deployment==='modal').map(([name])=>name);
 $('placement-modal').textContent=modal.length?`${modal.join(' + ')} configured · ${[lastPerception,lastPlanning].some(p=>p?.deployment==='modal')?'response received':'unverified'}`:'Optional · not configured';
 $('perception-runtime').textContent=lastPerception?`Last Gemma frame T+ ${clock(lastPerception.frameTime??lastPerception.inputImageTime??0)} · ${lastPerception.provider||'configured adapter'}`:'Current evidence: synthetic browser sensors';
 $('model-perception-evidence').textContent=lastPerception?`${lastPerception.summary||'Structured observations received.'}${lastPerception.uncertainty?' Uncertainty: '+String(lastPerception.uncertainty).slice(0,700):''} Source: ${lastPerception.source} · ${lastPerception.model} · frame ${clock(lastPerception.frameTime??lastPerception.inputImageTime??0)}.`:'No Gemma response received. Camera/UV observations in the browser remain synthetic.';
 $('model-reasoning-evidence').textContent=lastPlanning?`${lastPlanning.reason} Action: ${lastPlanning.decision}. Source: ${lastPlanning.source} · ${lastPlanning.model}.`:'No local policy decision received.';
 const optimizer=lastPlanning?.optimizer;$('model-planning-evidence').textContent=optimizer?.source==='cuopt'?`cuOpt response received. ${optimizer.summary||optimizer.reason||''} Selected route: ${lastPlanning.routeMode||'unchanged'}.`:'Local terrain-aware waypoint alternatives. No cuOpt response received.';
 $('transport-runtime').textContent=uplink.enabled?`${uplink.accepted} STREAM FRAMES`:baseInflight?'HTTP IN FLIGHT':packetCount?`${packetCount} GATE PACKETS`:'LOCAL ONLY';
 const remote=s.controller==='base_station';$('pipeline-robot').textContent=remote?(lastPerception?'Robot observation · Gemma response received':'Robot observation · awaiting Gemma'):'Robot observation · synthetic perception';
 $('pipeline-base').textContent=remote?(lastPlanning?'Planning · inspectable policy applied':'Planning · awaiting solver'):'Base reasoning · awaiting model connection';
 $('pipeline-transport').textContent=uplink.enabled?`Base received ${uplink.accepted} sensor frames · ${uplink.queue.length} queued`:remote?`${transportState} · continuous uplink disconnected`:'5 Hz local recorder · uplink disconnected';
 $('sensor-evidence-source').textContent='CAMERA / UV EXPOSURE · SYNTHETIC';
}
function stopActivation(){activationRequested=false;clearTimeout(readinessTimer);readinessTimer=null;warmupInflight?.abort();warmupInflight=null;if($('cancel-stack-connect'))$('cancel-stack-connect').hidden=true;}
function connectUplink(){if(uplink.enabled)return;resetUplink();uplink.enabled=true;queueTelemetry(telemetry.frames.at(-1));}
function activateBase(){
 const resume=activationWasRunning;stopActivation();modelUnavailable=false;evidenceHold=false;speed=1;$('speed').value='1';
 if(command({action:'set_controller',mode:'base_station',requireFullStack:true})){if(snapshot.pilot?.mode==='manual')command({action:'set_pilot',mode:'autonomous'});connectUplink();transportState='Live telemetry + model gate packets';if(resume)command({action:'run'});toast('Robot + base connected. Telemetry streams continuously; model gates use fresh camera evidence.');}
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
 if(activationRequested)return;const wasRunning=snapshot.running;cancelDecision();const token=generation;activationWasRunning=wasRunning;activationRequested=true;modelUnavailable=false;evidenceHold=false;activationStarted=Date.now();command({action:'pause'});connectUplink();if(!options.automatic)switchTab('architecture');await checkArchitecture();if(!activationRequested||token!==generation)return;
 if(!stackConfigured()){stopActivation();modelUnavailable=true;renderUI(true);toast(`Configure ${requiredComponents().filter(name=>!componentStatus(name).configured).join(', ')} before connecting this stack.`);return;}
 activationRequested=true;activationStarted=Date.now();connectUplink();if(stackReady()){activateBase();return;}
 const controller=new AbortController();warmupInflight=controller;renderArchitecture(snapshot);const timer=setTimeout(()=>controller.abort(),20000);
 try{logActivity('request','Starting Gemma / cuOpt service warmup; waiting for verified readiness before live control.');const response=await fetch('/api/lab/warmup',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});const data=await response.json();if(!response.ok)throw new Error(data.error||'Service warmup failed');if(!activationRequested)return;if(data.components)architecture=data;await pollStackReadiness();}
 catch(error){if(activationRequested){stopActivation();modelUnavailable=true;architectureError=`Service startup failed: ${error.name==='AbortError'?'request timed out':error.message}. Reconnect explicitly.`;renderArchitecture(snapshot);toast('Model startup did not complete. The mission remains paused; reconnect explicitly.');}}
 finally{clearTimeout(timer);if(warmupInflight===controller)warmupInflight=null;}
}
$('cancel-stack-connect').onclick=()=>{stopActivation();modelUnavailable=true;renderUI(true);toast('Model connection canceled. The mission remains paused.');};
$('base-station').onclick=useBase;$('use-base').onclick=useBase;
for(const id of['show-architecture','pipeline-details'])$(id).onclick=()=>switchTab('architecture');
$('refresh-architecture').onclick=checkArchitecture;
async function baseRequest(path,payload,controller){const started=performance.now(),perception=path.endsWith('/perception');logActivity('request',perception?`Sending tool frame T+ ${clock(payload.image.time)} (768×576; ${illuminationLabel()}) to Gemma · target ${payload.observation.cameraTargetId} · capture ${payload.observation.captureRequestId}. Awaiting visual observations.`:`Sending observations to inspectable policy · actions ${payload.allowedActions.join('/')} · routes ${(payload.observation.route?.alternatives||[]).map(r=>r.id).join('/')} · ${payload.requireFullStack?'cuOpt solve required':'explicit partial planning'}. Awaiting action and route.`);const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});const data=await response.json();if(!response.ok){const error=new Error(data.error||'Configured service failed');error.serviceUnavailable=response.status===429||response.status>=500;throw error;}packetCount++;data.clientLatencyMs=Math.round(performance.now()-started);return data;}
async function requestBasePipeline(force=false){
 if(assistInflight||assistHolding||baseInflight||!snapshot.running||snapshot.pilot?.mode==='manual'||!scene?.ready)return;
 const request=snapshot.perceptionRequest,pending=snapshot.pendingDecision,inspecting=['inspect_recipient','inspect_donor','inspect_fragment'].includes(snapshot.phase);
 const targetId=request?.targetId||(snapshot.phase==='inspect_recipient'?snapshot.targetId:snapshot.donorId);
 const perceptionReady=request?request.ready:inspecting&&Number(snapshot.perception?.exposure||0)>=.8;
 const operation=perceptionReady?'perception':pending?'planning':null;if(!operation)return;
 const key=operation==='perception'?`${generation}:${request?.id||snapshot.phase}:${targetId}`:`${generation}:${pending.id}`;
 if(!force&&baseAttempted.has(key))return;baseAttempted.add(key);baseError='';modelUnavailable=false;evidenceHold=false;
 const token=generation,controller=new AbortController();baseInflight=controller;$('retry-gemini').hidden=true;
 transportState=operation==='perception'?'Sending robot camera to Gemma…':'Solving declared routes / checking local policy…';renderArchitecture(snapshot);
 const timer=setTimeout(()=>controller.abort(),45000);
 try{
  if(operation==='perception'){
   const {imageFocus,...image}=scene.captureObservation({targetPosition:request?.targetPosition,includeProjection:!!request?.targetPosition}),id=request?`${request.id}-${generation}-${Math.round(image.time*1000)}`:`perception-${generation}-${targetId}-${Math.round(image.time*1000)}`;
   const observation={...(imageFocus?{imageFocus}:{}),phase:snapshot.phase,frameTime:image.time,perceptionRequest:request,captureRequestId:request?.id||id,cameraTargetId:targetId,targetKind:request?.targetKind||'colony',targetPosition:request?.targetPosition,targetId:snapshot.targetId,donorId:snapshot.donorId,water:{current:snapshot.water.current,currentVector:snapshot.water.currentVector,visibility:snapshot.water.visibility},robot:{position:snapshot.robot.position,gripper:snapshot.robot.gripper,yaw:snapshot.robot.yaw},sonar:{range:snapshot.sonar?.range,contacts:(snapshot.sonar?.contacts||[]).slice(0,24)}};
   const advisoryContext=takeAssistanceContext(targetId,observation.targetKind,image.time,observation.captureRequestId);
   const packet=await baseRequest('/api/lab/perception',{id,observation,image,...(advisoryContext?{advisoryContext,episodeId:assistEpisodeId}:{})},controller);if(token!==generation||request&&lab.snapshot().perceptionRequest?.id!==request.id)return;
   if(packet.source!=='gemma'||(packet.requestId??packet.id)!==id)throw new Error('Gemma packet source or identity mismatch');
   lab.command({action:'ingest_perception',packet});lastPerception=packet;snapshot=lab.snapshot();rememberObservations();transportState='Gemma observation received via HTTP';logActivity('response',`Gemma ${packet.model} responded in ${packet.clientLatencyMs}ms: ${packet.summary||'Structured visual observations received.'}${packet.uncertainty?' Uncertainty: '+String(packet.uncertainty).slice(0,700):''} ${packet.targetKind==='fragment'?`Fragment visible: ${packet.fragmentVisible}; gripper: ${packet.gripperState}.`:(packet.observations||[]).map(o=>`${o.id}: ${label(o.appearance||o.health)} (${Math.round(o.confidence*100)}% provider score; viability from registry only)`).join('; ')} Frame T+ ${clock(packet.frameTime)}.`);
   const expected=request?.expectedHealth||(snapshot.phase==='inspect_recipient'?'bleached_alive':'healthy'),accepted=request?.targetKind==='fragment'?lab._fragmentEvidenceReady():lab._externalHealth(targetId,expected).ready;
   if(!accepted){evidenceHold=true;modelUnavailable=false;requestAssistance({kind:'perception_uncertainty',key:`capture-${request?.id||targetId}`,reason:`Fresh Gemma ${request?.targetKind||'colony'} observation is uncertain or incompatible: ${packet.uncertainty||packet.summary||'visual gate did not pass'}`});}

  }else{
   const observation=planningObservation(pending);
   const packet=await baseRequest('/api/lab/plan',{id:pending.id,observation,allowedActions:pending.allowedActions,perception:lastPerception,requireFullStack:snapshot.intelligence?.requireFullStack!==false},controller);if(token!==generation||lab.snapshot().pendingDecision?.id!==pending.id)return;
   if(snapshot.intelligence?.requireFullStack!==false&&packet.optimizer?.source!=='cuopt')throw new Error('Full stack requires an actual cuOpt result');
   if(packet.source!=='local_planner'||(packet.requestId??packet.id)!==pending.id||!pending.allowedActions.includes(packet.decision))throw new Error('Local planner packet source, identity or action mismatch');
   lab.command({action:'ingest_plan',packet});lab.command({action:'apply_decision',id:pending.id,decision:packet.decision,reason:packet.reason,source:'base_station',routeMode:packet.routeMode??null,evidence:{perception:lastPerception,planning:packet}});lastPlanning=packet;snapshot=lab.snapshot();transportState='Base plan received via HTTP';logActivity('response',`Local planner ${packet.model} responded in ${packet.clientLatencyMs}ms: ${packet.decision.toUpperCase()} — ${packet.reason} ${packet.optimizer?.source==='cuopt'?`cuOpt selected ${packet.routeMode}; objective ${packet.optimizer.objectiveCost??'reported by solver'}.`:'Explicit partial mode; local route retained.'}`);
  }
 }catch(error){if(token===generation){modelUnavailable=!!error.serviceUnavailable||error.name==='AbortError'||error instanceof TypeError;evidenceHold=!modelUnavailable;baseError=`${operation==='perception'?'Gemma perception':'Base planning'} held: ${error.name==='AbortError'?'request timed out':error.message}. Bounded Argon assistance will review the held issue; no rejected visual observation can be bypassed.`;transportState='HTTP request failed · mission held';logActivity('error',baseError);$('retry-gemini').hidden=false;toast('Remote stage unavailable. Local safety remains active.');requestAssistance({kind:'service_issue',key:`service-${key}`,reason:`${operation} service failed: ${error.message}`});}}
 finally{clearTimeout(timer);if(baseInflight===controller)baseInflight=null;if(token===generation)renderUI(true);}
}

function cancelAssistance(){assistContext=null;assistRetry=null;assistInflight?.abort();assistInflight=null;assistHolding=false;assistIssue=null;if(lab.assistanceHold)lab.command({action:'set_assistance_hold',active:false});}
function resetAssistanceEpisode(){cancelAssistance();assistEpisodeId=crypto.randomUUID();assistScene=lab.scene;assistLastTime=0;assistCount=0;assistIssues.clear();assistLastDrop=0;assistCurrentActive=false;assistCurrentSince=null;assistCurrentHandled=false;lastAssist=null;}
function syncAssistanceEpisode(s){
 if(assistScene!==lab.scene||s.time<assistLastTime-1e-9)resetAssistanceEpisode();assistLastTime=s.time;
 if(assistContext){const c=assistContext.packet,b=assistContext.mission;if(c.episodeId!==assistEpisodeId||s.time>c.expiresAt||performance.now()>=assistContext.wallExpiresAt||s.donorId!==b.donorId||s.targetId!==b.targetId||s.fragmentId!==b.fragmentId)assistContext=null;}
 if(['complete','aborted'].includes(s.phase)){assistContext=null;assistRetry=null;assistInflight?.abort();assistInflight=null;assistHolding=false;}
}
function assistanceTarget(s){
 const request=s.perceptionRequest;
 if(request?.targetId)return{cameraTargetId:request.targetId,targetKind:request.targetKind||'colony',captureRequestId:request.id};
 return{};
}
function stageAssistanceContext(result,payload,started){
 assistContext=null;
 const c=result.advisoryContext;if(c===undefined)return;
 const expected=['source','requestId','episodeId','targetId','targetKind','previousCaptureRequestId','issuedAt','expiresAt','guidance','observations','checks','advisoryOnly','controlAuthority'];
 const bounded=(value,max)=>typeof value==='string'&&value.trim().length>0&&value.length<=max;
 if(!c||typeof c!=='object'||Object.keys(c).length!==expected.length||expected.some(key=>!Object.hasOwn(c,key))||c.source!=='argon_assist'||c.requestId!==payload.id||c.episodeId!==payload.episodeId||c.targetId!==payload.observation.cameraTargetId||c.targetKind!==payload.observation.targetKind||!['colony','fragment'].includes(c.targetKind)||!bounded(c.targetId,160)||c.previousCaptureRequestId!==payload.observation.captureRequestId||!bounded(c.previousCaptureRequestId,160)||c.advisoryOnly!==true||c.controlAuthority!==false||!Number.isFinite(c.issuedAt)||c.issuedAt!==payload.observation.time||!Number.isFinite(c.expiresAt)||c.expiresAt<=c.issuedAt||c.expiresAt>c.issuedAt+60||!bounded(c.guidance,1200)||!Array.isArray(c.observations)||c.observations.length>3||c.observations.some(value=>!bounded(value,240))||!Array.isArray(c.checks)||c.checks.length<1||c.checks.length>4||c.checks.some(value=>!bounded(value,200)))throw Error('Invalid or mismatched Argon advisory context');
 if(result.action==='rescan')assistContext={packet:c,wallExpiresAt:started+60000,mission:{donorId:payload.observation.donorId,targetId:payload.observation.targetId,fragmentId:payload.observation.fragmentId}};
}
function takeAssistanceContext(targetId,targetKind,imageTime,captureRequestId){
 const staged=assistContext;if(!staged)return null;
 const c=staged.packet,b=staged.mission,s=lab.snapshot();
 if(c.episodeId!==assistEpisodeId||performance.now()>=staged.wallExpiresAt||imageTime>c.expiresAt||['complete','aborted'].includes(lab.phase)||s.donorId!==b.donorId||s.targetId!==b.targetId||s.fragmentId!==b.fragmentId){assistContext=null;return null;}
 if(c.targetId!==targetId||c.targetKind!==targetKind||!Number.isFinite(imageTime)||imageTime<=c.issuedAt||captureRequestId===c.previousCaptureRequestId)return null;
 assistContext=null;return c;
}
function assistanceContextText(result){
 const c=result?.advisoryContext;if(!c)return'';
 return` Next-frame guidance: ${c.guidance} Reported context: ${c.observations.join('; ')||'none'}. Visual checks: ${c.checks.join('; ')}. Untrusted advice only; the new image must independently support every observation.`;
}
function scheduleAssistanceRetry(){
 const s=lab.snapshot(),delay=2**assistCount;
 if(assistCount>=3||!assistIssue||!s.assistanceHold||s.time+delay>=s.assistanceHold.since+90)return false;
 assistRetry={episode:assistEpisodeId,generation,dueAt:s.time+delay};
 logActivity('hold',`Argon recheck scheduled in ${delay}s within the existing episode budget and hold deadline. Robot remains held.`);
 return true;
}
function renderAssistance(s){
 $('assist-count').textContent=`${assistCount} / 3 ATTEMPTS`;
 $('argon-assistance').textContent=assistInflight?'Argon is reviewing this issue. The robot holds position; physics and safety continue.':assistHolding&&baseError?baseError:lastAssist?`${lastAssist.action.toUpperCase()} · ${lastAssist.reason} Source: ${lastAssist.model}; ${lastAssist.clientLatencyMs??lastAssist.latencyMs}ms.${assistanceContextText(lastAssist)} Advisory only; no visual gate bypass.`:assistHolding?baseError:'Uncertain perception, drops, excessive current or service failures can request bounded Argon help while the robot holds. Only rescan, hold or abort; no proceed command.';
 $('retry-assist').hidden=!assistHolding||!!assistInflight||assistCount>=3||['complete','aborted'].includes(s.phase);$('abort-assist').hidden=!assistHolding||['complete','aborted'].includes(s.phase);
 if(assistHolding){$('retry-gemini').hidden=true;}
}
function maybeRequestAssistance(){
 if(snapshot.controller!=='base_station'||snapshot.pilot?.mode==='manual'||!snapshot.running||['idle','complete','aborted'].includes(snapshot.phase))return false;
 const current=Math.hypot(...(snapshot.water.currentVector||[snapshot.water.current,0,0]))>.42;
 if(current&&!assistCurrentActive){assistCurrentSince=snapshot.time;assistCurrentHandled=false;}
 if(!current){assistCurrentSince=null;assistCurrentHandled=false;}assistCurrentActive=current;
 const newDrop=snapshot.metrics.drops>assistLastDrop;
 if(assistInflight||assistHolding){
  if(newDrop){assistLastDrop=snapshot.metrics.drops;assistCurrentHandled=current;const update='The same incident now includes a dropped fragment; fresh recovery inspection is required.';if(assistIssue)assistIssue.reason=`${assistIssue.reason} ${update}`.slice(-1200);logActivity('hold',`${update} Existing assistance request/hold retained; no duplicate request.`);}
  if(assistRetry&&(assistRetry.episode!==assistEpisodeId||assistRetry.generation!==generation))assistRetry=null;
  if(assistRetry&&!assistInflight&&snapshot.time>=assistRetry.dueAt){assistRetry=null;requestAssistance(assistIssue,{retry:true});}
  return true;
 }
 if(newDrop){assistLastDrop=snapshot.metrics.drops;assistCurrentHandled=current;requestAssistance({kind:'fragment_drop',key:`drop-${assistLastDrop}`,reason:'The tracked fragment was dropped, possibly during the current disturbance. Review current recovery conditions; require fresh fragment and gripper inspection before any recovery motion.'});return true;}
 if(current&&!assistCurrentHandled&&snapshot.targetId){
  if(snapshot.time-assistCurrentSince<2)return true;
  assistCurrentHandled=true;requestAssistance({kind:'excessive_current',key:`current-${Math.round(assistCurrentSince*1000)}`,reason:'Observed current has exceeded the nominal operating threshold for at least two simulation seconds. Local environmental safety has held the robot; assess whether to rescan, remain held or abort.'});return true;
 }
 return false;
}
function assistanceObservation(){const s=snapshot,fragmentId=s.robot.holding||s.fragmentId||(s.perceptionRequest?.targetKind==='fragment'?s.perceptionRequest.targetId:null)||s.pendingDecision?.observation?.fragment?.id,f=s.fragments.find(f=>f.id===fragmentId);return{...assistanceTarget(s),targetId:s.targetId,donorId:s.donorId,fragmentId:s.fragmentId,phase:s.phase,time:s.time,held:!!s.assistanceHold,restorationMode:s.restorationMode,robot:{position:s.robot.position,velocity:s.robot.velocity,holding:s.robot.holding},water:{current:s.water.current,currentVector:s.water.currentVector,visibility:s.water.visibility},metrics:s.metrics,grip:s.grip,fragment:f?{id:f.id,state:f.state,position:f.position,detachedAtStart:f.detachedAtStart}:null,registryGroundTruth:s.registryGroundTruth,onboardPerception:{observations:(s.intelligence?.onboard?.observations||[]).filter(o=>[s.donorId,s.targetId].includes(o.id)).slice(-4)},route:{mode:s.route?.mode,alternatives:(s.route?.alternatives||[]).map(r=>({id:r.id,points:r.points.slice(0,12)}))},assistanceAttemptsRemaining:3-assistCount};}
async function requestAssistance(issue,{retry=false}={}){
 snapshot=lab.snapshot();
 if(snapshot.controller!=='base_station'||snapshot.pilot?.mode==='manual'||['idle','complete','aborted'].includes(snapshot.phase)||assistInflight)return;
 if(snapshot.assistanceHold&&snapshot.time>=snapshot.assistanceHold.since+90)return;
 if(!retry&&assistIssues.has(issue.key))return;assistIssues.add(issue.key);assistIssue={kind:String(issue.kind).slice(0,64),key:issue.key,reason:String(issue.reason).slice(0,1200)};
 assistRetry=null;assistContext=null;
 baseInflight?.abort();baseInflight=null;baseAttempted.clear();const token=++generation,episode=assistEpisodeId;
 evidenceHold=true;modelUnavailable=false;assistHolding=true;baseError='Requesting Argon assistance. Robot held; fresh Gemma evidence remains required.';
 if(!command({action:'set_assistance_hold',active:true,reason:assistIssue.reason})){assistHolding=false;return;}
 if(assistCount>=3){baseError='Argon assistance budget exhausted (3 attempts). Robot held; request a fresh rescan or abort.';logActivity('hold',baseError);renderUI(true);return;}
 const id=`assist-${episode}-${++assistCount}`,controller=new AbortController();assistInflight=controller;const started=performance.now(),remainingHoldMs=Math.max(1,(snapshot.assistanceHold.since+90-snapshot.time)*1000),timer=setTimeout(()=>controller.abort(),Math.min(60000,remainingHoldMs));
 const perception=lastPerception?Object.fromEntries(['source','model','provider','requestId','frameTime','targetId','targetKind','summary','uncertainty','observations','fragmentVisible','gripperState'].filter(k=>lastPerception[k]!==undefined).map(k=>[k,lastPerception[k]])):undefined;
 const payload={id,episodeId:episode,issue:{kind:assistIssue.kind,reason:assistIssue.reason},observation:assistanceObservation(),...(perception?{perception}:{})};
 logActivity('request',`Sending ${assistIssue.kind} at T+ ${clock(snapshot.time)} to Argon assistance (${assistCount}/3). Robot held; permitted suggestions: rescan / hold / abort. Awaiting actual response.`);renderUI(true);
 try{
  if(new TextEncoder().encode(JSON.stringify(payload)).length>30*1024)throw Error('Assistance context exceeds bounded request size');
  const response=await fetch('/api/lab/assist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal}),result=await response.json();
  if(token!==generation||episode!==assistEpisodeId||assistInflight!==controller||['complete','aborted'].includes(lab.phase))return;
  if(!response.ok){const error=Error(result.error||'Assistance service unavailable');error.retryable=typeof result.retryable==='boolean'?result.retryable:response.status===429||response.status>=500;throw error;}
  if(result.source!=='argon_assist'||result.requestId!==id||result.episodeId!==episode||result.advisoryOnly!==true||result.controlAuthority!==false||!['rescan','hold','abort'].includes(result.action)||typeof result.reason!=='string'||typeof result.model!=='string')throw Error('Invalid or unauthorized assistance response');
  stageAssistanceContext(result,payload,started);
  result.clientLatencyMs=Math.round(performance.now()-started);lastAssist=result;packetCount++;logActivity('response',`Argon assistance ${result.model} (${result.clientLatencyMs}ms): ${result.action.toUpperCase()} — ${result.reason}.${assistanceContextText(result)} Advisory only; fresh Gemma gates remain authoritative.`);
  if(result.action==='abort'){baseError='Argon recommended a safe abort.';command({action:'abort',reason:`Argon assistance recommended abort: ${result.reason}`});assistHolding=false;}
  else if(result.action==='rescan'){
   if(!snapshot.targetId||!snapshot.donorId){assistContext=null;baseError='Argon requested a rescan, but no target is assigned. The robot remains held.';return;}
   assistLastDrop=snapshot.metrics.drops;command({action:'set_assistance_hold',active:false});assistHolding=false;const reason=`Argon assistance requested fresh evidence: ${result.reason}`;
   if(command({action:'request_rescan',reason})){baseError='';evidenceHold=false;transportState='Argon requested a fresh physical rescan; no handling approval granted.';}
   else{assistContext=null;assistHolding=true;baseError='Requested rescan could not start; robot remains held.';command({action:'set_assistance_hold',active:true,reason:baseError});}
  }else{baseError=`Argon requested HOLD: ${result.reason} Robot remains held.`;scheduleAssistanceRetry();}
 }catch(error){if(token===generation&&episode===assistEpisodeId&&assistInflight===controller&&!['complete','aborted'].includes(lab.phase)){baseError=`Argon assistance unavailable: ${error.name==='AbortError'?'request timed out':error.message}. Robot remains held.`;logActivity('error',baseError);if(error.retryable||error.name==='AbortError'||error instanceof TypeError)scheduleAssistanceRetry();}}
 finally{clearTimeout(timer);if(assistInflight===controller)assistInflight=null;if(token===generation)renderUI(true);}
}
$('retry-assist').onclick=()=>{if(assistIssue)requestAssistance(assistIssue,{retry:true});};
$('abort-assist').onclick=()=>{cancelAssistance();command({action:'abort',reason:'Operator aborted the held mission.'});};

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
 $('memory-records').replaceChildren(...(records.length?records.slice(-5).reverse().map(record=>{const paragraph=document.createElement('p');paragraph.textContent=`${record.id} · ${label(record.appearance||record.health)} · ${(record.confidence*100).toFixed(0)}% provider score. ${record.model} / T+ ${clock(record.frameTime)}. Historical, not a control approval.`;return paragraph;}):[Object.assign(document.createElement('p'),{textContent:'No accepted Gemma observations saved for this scene.'})]));
}
$('export-memory').onclick=()=>{try{download(`reef-rescue-memory-${snapshot.seed}.json`,JSON.parse(semanticMemory.exportJSON()));}catch(error){toast(error.message);}};
$('import-memory').onclick=()=>$('memory-file').click();
$('memory-file').onchange=async()=>{const file=$('memory-file').files[0];if(file){try{if(file.size>1024*1024)throw new Error('Memory file exceeds1MiB');bindMemoryScene();const result=semanticMemory.importJSON(await file.text());memoryUiSignature='';renderMemory();toast(`${result.imported} historical records restored for this exact scene. Fresh camera approval is still required.`);}catch(error){toast(error.message);}}$('memory-file').value='';};
$('clear-memory').onclick=()=>{semanticMemory.clear();memoryUiSignature='';renderMemory();toast('Observation memory cleared for this scene.');};

function planningObservation(pending){
 const observation={...pending.observation,decisionKind:pending.kind,robot:{holding:snapshot.robot.holding},frameTime:snapshot.time,route:snapshot.route,semanticMemory:semanticMemory.planningContext?.([snapshot.donorId,snapshot.targetId])};
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

$('review-mission').onclick=async()=>{
 if(reviewInflight||!['complete','aborted'].includes(snapshot.phase))return;
 const terminal=JSON.parse(JSON.stringify(snapshot)),token=generation;reviewAbort=new AbortController();reviewInflight=true;renderArchitecture(snapshot);
 try{
  const episode=Object.fromEntries(['phase','completed','time','metrics','events','decision','intelligence','physics'].map(k=>[k,terminal[k]]));
  const response=await fetch('/api/lab/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:`review-${terminal.seed}-${Math.round(terminal.time*1000)}`,episode,transportActivity:activityLog.slice(-40)}),signal:AbortSignal.any([reviewAbort.signal,AbortSignal.timeout(60000)])});
  const result=await response.json();if(token!==generation)return;if(!response.ok||result.source!=='argon_review'||result.reviewOnly!==true)throw Error(result.error||'Invalid post-mission review');lastReview=result;logActivity('review',`Argon post-mission review (${result.latencyMs}ms): ${result.summary}. No control or software change applied.`);
 }catch(error){if(token===generation)logActivity('error',`Post-mission review unavailable: ${error.message}`);}finally{reviewInflight=false;renderArchitecture(snapshot);}
};

let liveRecorder=null;
function startContinuousCapture(){
  if(!scene?.ready)throw Error('Wait for the reef camera to load');
  if(!liveRecorder)liveRecorder=new LiveDemoRecorder({reefCanvas:$('reef'),pipCanvas:$('robot-camera-pip'),sonarCanvas:$('sonar-map'),getSnapshot:()=>snapshot,getLog:()=>activityLog,getSpeed:()=>speed,
   onStatus:state=>{$('record-demo').textContent=state.state==='recording'?`Recording ${Math.ceil(state.remaining||0)}s…`:'Record continuous 60-second take';$('record-demo').disabled=['recording','encoding'].includes(state.state);$('record-status').textContent=state.state==='complete'?'Take saved in memory. Download raw video + evidence; verify duration before submission.':`Live capture: ${state.state}. Keep this tab visible throughout.`;},
   onComplete:result=>{$('download-take').hidden=false;$('download-take-evidence').hidden=false;$('download-take').onclick=()=>result.downloadVideo();$('download-take-evidence').onclick=()=>result.downloadEvidence();}});
  liveRecorder.start();
}
$('record-demo').onclick=()=>{try{startContinuousCapture();}catch(error){toast(error.message);}};
