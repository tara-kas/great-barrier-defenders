/** Continuous wall-clock capture of actual application canvases, never a replay.
 * Rendering, policy and operator controls remain owned by the running app.
 */
export const CAPTURE_SECONDS=60;
const numeric=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
const text=(v,max=300)=>typeof v==='string'?v.slice(0,max):'';
const vec=v=>Array.isArray(v)?v.slice(0,3).map(numeric):null;
function provenance(p){return p?{requestId:text(p.requestId??p.id),source:text(p.source),model:text(p.model),provider:text(p.provider),frameTime:numeric(p.frameTime),receivedTime:numeric(p.receivedTime),inputImageSha256:text(p.inputImageSha256),decision:text(p.decision??p.action),reason:text(p.reason,800),routeMode:text(p.routeMode),optimizer:p.optimizer?{source:text(p.optimizer.source),solverStatus:text(p.optimizer.solverStatus),requestId:text(p.optimizer.requestId),routeMode:text(p.optimizer.routeMode),objectiveCost:numeric(p.optimizer.objectiveCost)}:null}:null;}
export function capturePresentation(snapshot={},speed=1){
 const scripted=snapshot.controller==='scripted';
 return {mode:scripted?'scripted_demo':'model_guided_capture',label:scripted?'Reef Rescue — Final Demo':'MODEL-GUIDED CAPTURE',speedLabel:`${Number(speed)||1}× SIMULATION`,perceptionLabel:scripted?'Synthetic scene observations':'Received model evidence',policyLabel:scripted?'Deterministic local policy':'Inspectable policy / received solver',modelCallsClaimed:false};
}
export const SUBTITLE_BAND={x:0,y:810,width:1600,height:90};
export function captureEvidence(s={},wallSeconds=0,speed=1){
 const onboard=s.intelligence?.onboard||{},base=s.intelligence?.baseStation||{};
 return {presentation:capturePresentation(s,speed),wallSeconds,time:numeric(s.time),phase:text(s.phase),status:text(s.status),controller:text(s.controller),pilot:text(s.pilot?.mode),speed:numeric(speed),completed:s.completed===true,
  robot:{position:vec(s.robot?.position),holding:text(s.robot?.holding)},targetId:text(s.targetId),donorId:text(s.donorId),
  metrics:Object.fromEntries(Object.entries(s.metrics||{}).filter(([,v])=>numeric(v)!==null).slice(0,30)),
  fragments:(s.fragments||[]).slice(0,64).map(f=>({id:text(f.id),state:text(f.state),donorId:text(f.donorId),targetId:text(f.targetId),position:vec(f.position)})),
  grip:{loadN:numeric(s.grip?.loadN),thresholdN:numeric(s.grip?.thresholdN)},
  perception:provenance(onboard.lastPacket),observations:(onboard.observations||[]).slice(-12).map(o=>({id:text(o.id),health:text(o.health),appearance:text(o.appearance),confidence:numeric(o.confidence),source:text(o.source),frameTime:numeric(o.frameTime)})),
  planning:provenance(base.plan),decision:provenance(s.decision),pendingDecision:s.pendingDecision?{id:text(s.pendingDecision.id),kind:text(s.pendingDecision.kind)}:null,
  events:(s.events||[]).slice(-6).map(e=>({time:numeric(e.time),type:text(e.type),message:text(e.message,600)})),
 };
}
export function assessCapture(metadata){
 const samples=metadata.samples||[],first=samples[0],last=samples.at(-1),issues=[...(metadata.issues||[])];
 if(metadata.wallDurationSeconds<60)issues.push('Capture ended before 60 wall-clock seconds');
 if(metadata.wallDurationSeconds>61)issues.push('Capture exceeded 61 seconds; verify and trim only excess final frames');
 for(let i=1;i<samples.length;i++)if(samples[i].time<samples[i-1].time)issues.push('Simulation clock moved backwards during capture');
 if(samples.some(s=>s.pilot==='manual'))issues.push('Manual pilot input occurred in the captured interval');
 return {continuous:issues.length===0,issues:[...new Set(issues)],startPhase:first?.phase??null,endPhase:last?.phase??null,
  placementDelta:(last?.metrics?.placed??0)-(first?.metrics?.placed??0),dropDelta:(last?.metrics?.drops??0)-(first?.metrics?.drops??0),recoveryDelta:(last?.metrics?.recoveries??0)-(first?.metrics?.recoveries??0),
  completed:last?.completed===true,recordingMode:[...new Set(samples.map(s=>s.presentation?.mode).filter(Boolean))].join(' / ')||'unspecified',simulationSpeeds:[...new Set(samples.map(s=>s.speed).filter(Number.isFinite))],taskOutcomeVerified:false,
  limitation:'Continuity and observed counters alone do not verify visual recognition, fragment identity, physical realism or the judging outcome; review source evidence and decoded footage.'};
}
export function fitCaptureText(value,width,measure){const chars=Array.from(String(value));if(measure(chars.join(''))<=width)return chars.join('');while(chars.length&&measure(chars.join('')+'…')>width)chars.pop();return chars.length?chars.join('')+'…':'';}
export class LiveDemoRecorder{
 constructor({reefCanvas,pipCanvas,sonarCanvas,getSnapshot,getLog=()=>[],getSpeed=()=>1,onStatus=()=>{},onComplete=()=>{}}){
  if(!reefCanvas||typeof getSnapshot!=='function')throw Error('Recorder needs the actual reef canvas and snapshot getter');
  Object.assign(this,{reefCanvas,pipCanvas,sonarCanvas,getSnapshot,getLog,getSpeed,onStatus,onComplete});this.active=false;this.raf=null;this.timer=null;this.lastResult=null;
 }
 static supported(){return typeof document!=='undefined'&&typeof MediaRecorder!=='undefined'&&typeof HTMLCanvasElement.prototype.captureStream==='function';}
 start(){
  if(this.active)throw Error('A continuous take is already recording');if(!LiveDemoRecorder.supported())throw Error('This browser does not support canvas MediaRecorder capture');
  this.canvas=document.createElement('canvas');this.canvas.width=1600;this.canvas.height=900;this.ctx=this.canvas.getContext('2d',{alpha:false});
  this.chunks=[];this.started=performance.now();this.lastSample=-1;this.metadata={schema:'reef-rescue-live-capture/v1',startedAt:new Date().toISOString(),targetWallSeconds:CAPTURE_SECONDS,width:1600,height:900,requestedFPS:30,tailGuardSeconds:.25,source:'Actual running browser canvases; continuous wall-clock capture',layout:'original-dashboard/v2',subtitleBand:{...SUBTITLE_BAND},presentation:capturePresentation(this.getSnapshot(),this.getSpeed()),edited:false,retimed:false,samples:[],issues:[],logs:[]};
  this.active=true;this.draw();this.stream=this.canvas.captureStream(30);
  const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime){this.active=false;this.stream.getTracks().forEach(t=>t.stop());throw Error('No supported video recording codec');}
  try{this.recorder=new MediaRecorder(this.stream,{mimeType:mime,videoBitsPerSecond:6500000});}catch(e){this.active=false;this.stream.getTracks().forEach(t=>t.stop());throw e;}
  this.recorder.ondataavailable=e=>{if(e.data.size)this.chunks.push(e.data);};
  this.recorder.onerror=e=>{this.metadata.issues.push('MediaRecorder error: '+(e.error?.message||'unknown'));this.stop();};
  this.recorder.onstop=()=>this.finish();
  this.visibility=()=>{if(document.hidden&&this.active)this.metadata.issues.push('Browser tab became hidden; rendered frames may have stalled');};document.addEventListener('visibilitychange',this.visibility);
  this.recorder.start(1000);this.timer=setTimeout(()=>this.stop(),(CAPTURE_SECONDS+.25)*1000);this.onStatus({state:'recording',elapsed:0,remaining:60});
  const tick=()=>{if(!this.active)return;this.draw();this.raf=requestAnimationFrame(tick);};this.raf=requestAnimationFrame(tick);return this.metadata.startedAt;
 }
 stop(){if(!this.active)return;this.draw();this.metadata.wallDurationSeconds=(performance.now()-this.started)/1000;this.active=false;clearTimeout(this.timer);cancelAnimationFrame(this.raf);document.removeEventListener('visibilitychange',this.visibility);if(this.recorder?.state!=='inactive')this.recorder.stop();this.onStatus({state:'encoding',elapsed:this.metadata.wallDurationSeconds});}
 finish(){
  this.stream.getTracks().forEach(t=>t.stop());this.metadata.assessment=assessCapture(this.metadata);const mime=this.recorder.mimeType;const blob=new Blob(this.chunks,{type:mime});const stamp=this.metadata.startedAt.replaceAll(':','-').replaceAll('.','-');
  const save=(value,name)=>{const url=URL.createObjectURL(value),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);};
  const result={blob,metadata:this.metadata,filename:`reef-rescue-${this.metadata.presentation?.mode==='scripted_demo'?'scripted-demo':'live'}-${stamp}.${mime.includes('mp4')?'mp4':'webm'}`};
  result.downloadVideo=()=>save(blob,result.filename);
  result.downloadEvidence=()=>save(new Blob([JSON.stringify(result.metadata,null,2)],{type:'application/json'}),result.filename.replace(/\.[^.]+$/,'.evidence.json'));
  // Legacy calls trigger only one download; the UI offers evidence as its own user action.
  result.download=()=>result.downloadVideo();
  this.lastResult=result;this.onStatus({state:'complete',elapsed:this.metadata.wallDurationSeconds,assessment:this.metadata.assessment});this.onComplete(result);
 }
 draw(){
  const s=this.getSnapshot(),elapsed=(performance.now()-this.started)/1000,speed=this.getSpeed(),c=this.ctx;
  if(elapsed-this.lastSample>=.5||elapsed>=60){const sample=captureEvidence(s,elapsed,speed);this.metadata.samples.push(sample);this.lastSample=elapsed;
   this.metadata.logs=(this.getLog()||[]).slice(-120).map(e=>({time:numeric(e.time),type:text(e.type),message:text(e.message,1200),receivedAt:text(e.receivedAt)}));this.onStatus({state:'recording',elapsed,remaining:Math.max(0,60-elapsed)});}
  // Recompose the existing dashboard, not a separate four-panel video layout.
  // Only the actual viewport/PiP/sonar canvases supply image pixels.
  const P={bg:'#0a161a',panel:'#102126',line:'#24383b',mint:'#a8e7cf',text:'#d4e3df',muted:'#829995',amber:'#e9b978'},view=capturePresentation(s,speed);
  const rect=(x,y,w,h,fill)=>{c.fillStyle=fill;c.fillRect(x,y,w,h);};
  const line=(value,x,y,w=220,size=14,color=P.text,font='DM Sans')=>{c.font=`${size}px "${font}",sans-serif`;c.fillStyle=color;c.fillText(fitCaptureText(value,w,t=>c.measureText(t).width),x,y);};
  const rule=(x,y,w)=>rect(x,y,w,1,P.line);
  const wrap=(value,x,y,w,rows=3,size=14,color=P.muted)=>{c.font=`${size}px "DM Sans",sans-serif`;const words=String(value||'').split(/\s+/);let row='';for(let n=0;n<rows&&words.length;n++){row='';while(words.length&&c.measureText(row+(row?' ':'')+words[0]).width<=w)row+=(row?' ':'')+words.shift();if(!row)row=words.shift();line(row+(n===rows-1&&words.length?'…':''),x,y+n*(size+6),w,size,color);}};
  const paste=(canvas,x,y,w,h)=>{rect(x,y,w,h,'#0b2931');if(canvas?.width&&canvas?.height){try{const scale=Math.min(w/canvas.width,h/canvas.height);c.drawImage(canvas,x+(w-canvas.width*scale)/2,y+(h-canvas.height*scale)/2,canvas.width*scale,canvas.height*scale);}catch(e){if(!this.metadata.issues.includes('Canvas unavailable during capture'))this.metadata.issues.push('Canvas unavailable during capture');}}else line('Source view unavailable',x+10,y+30,w-20,13,P.muted);};
  rect(0,0,1600,900,P.bg);rect(0,0,1600,72,'#0e2025');rule(0,71,1600);
  line('REEF RESCUE',24,34,240,23,P.text,'Space Grotesk');line('AUTONOMOUS CORAL RESTORATION',25,54,240,9,P.muted);
  line('Mission control',286,42,160,14,P.mint);line('Environment',463,42,130,14,P.muted);line('Robot + base',610,42,150,14,P.muted);
  rect(282,68,135,3,P.mint);line(view.label,1095,32,475,17,view.mode==='scripted_demo'?P.amber:P.mint);line(`${view.speedLabel}  ·  REC ${elapsed.toFixed(1)} / 60.0s`,1095,54,475,13,P.muted);
  // Original left mission panel, main viewport and right telemetry proportions.
  rect(0,72,250,738,P.panel);rect(1320,72,280,738,P.panel);rect(249,72,1,738,P.line);rect(1320,72,1,738,P.line);
  line('RESTORATION MISSION',22,108,208,11,P.muted);line('Restore the reef.',22,155,214,25,P.text,'Space Grotesk');
  wrap('Collect loose coral stock. Transfer, recover and verify placement.',22,187,208,3,14);
  line(view.mode==='scripted_demo'?'DEMONSTRATION MODE':view.label,22,272,208,14,view.mode==='scripted_demo'?P.amber:P.mint);wrap(view.mode==='scripted_demo'?'Simulated sensing and local scenario control.':'Actual responses retain model provenance. Missing results remain unverified.',22,299,208,4,13);
  rule(22,391,206);line('ENVIRONMENT',22,419,208,11,P.muted);line(`Current     ${Number(s.water?.current||0).toFixed(2)} m/s`,22,450,208,15);line(`Visibility    ${Number(s.water?.visibility||0).toFixed(1)} m`,22,480,208,15);
  line('RECOVERY SEQUENCE',22,529,208,11,P.muted);const stages=['Survey & pair','Inspect source / recipient','Grasp loose fragment','Transport / recover','Align & secure','Verify placement'];const phase=s.phase||'idle';const active=/survey|idle/.test(phase)?0:/inspect|approval/.test(phase)?1:/grasp|approach|retract/.test(phase)?2:/transport|recover|regrasp/.test(phase)?3:/align|secure|release/.test(phase)?4:5;stages.forEach((title,i)=>{line(`${i+1}.  ${title}`,22,559+i*29,208,13,i===active?P.mint:P.muted);});
  paste(this.reefCanvas,250,72,1070,652);line('FIELD SITE / CONTINUOUS SIMULATION',270,100,530,11,P.mint);
  // Tool view stays overlaid in the same place as the dashboard PiP.
  rect(1002,112,300,256,P.panel);line('ROBOT CAMERA / ACTUAL PIXELS',1013,134,278,11,P.mint);paste(this.pipCanvas,1007,144,290,217);line('Synthetic rendered camera',1014,385,280,11,P.text);
  rect(267,657,1036,53,'#102126');line(`T+ ${Number(s.time||0).toFixed(1)}s`,283,691,155,22,P.text,'Space Grotesk');line(phase.replaceAll('_',' ').toUpperCase(),465,689,534,15,P.mint);line(`${speed}×`,1227,689,60,18,P.amber);
  // One actual latest action, with a dedicated empty band below for subtitles.
  const events=view.mode==='scripted_demo'?(s.events||[]):this.metadata.logs.length?this.metadata.logs:(s.events||[]),latest=events.at(-1);
  line('ACTION TRACE',270,750,190,11,P.muted);if(view.mode==='scripted_demo')line('Simulated sensing and local scenario control',270,800,1025,11,P.muted);wrap(latest?`${finiteTime(latest.time)}${latest.message||''}`:s.status||'Awaiting mission activity',270,777,1025,1,14,P.text);
  line('MISSION TELEMETRY',1340,108,240,11,P.muted);line('RESTORE–02',1340,145,240,22,P.text,'Space Grotesk');line('AUTONOMOUS RESTORATION VEHICLE',1340,166,240,9,P.muted);rule(1340,187,240);
  line('CURRENT OPERATION',1340,214,240,10,P.muted);wrap(phase.replaceAll('_',' '),1340,242,240,2,19,P.text);rect(1340,283,240,3,P.line);rect(1340,283,240*Math.max(0,Math.min(1,s.phaseProgress||0)),3,P.mint);
  const metric=(value,label,x,y)=>{line(String(value),x,y,112,27,P.text,'Space Grotesk');line(label,x,y+20,112,9,P.muted);};
  metric(`${s.metrics?.placed||0}/${s.missionGoal||1}`,'VERIFIED',1340,327);metric(s.metrics?.recoveries||0,'RECOVERIES',1470,327);metric(Number(s.metrics?.distance||0).toFixed(1)+' m','DISTANCE',1340,393);metric(s.metrics?.drops||0,'DROPS',1470,393);rule(1340,431,240);
  const onboard=s.intelligence?.onboard,plan=s.intelligence?.baseStation?.plan,packet=onboard?.lastPacket;
  line('PERCEPTION / CONTROL SOURCE',1340,461,240,10,P.muted);wrap(view.mode==='scripted_demo'?'Synthetic scene observations + deterministic local policy.':packet?`${packet.model||packet.source} · actual response received`:'No model response received',1340,489,240,3,13,P.text);
  line(`Held: ${s.robot?.holding||'none'}`,1340,560,240,14,P.mint);line(`Grip ${Number(s.grip?.loadN||0).toFixed(2)} / ${s.grip?.thresholdN??'?'} N`,1340,584,240,13,P.muted);
  line('FORWARD SONAR / SIMULATED',1340,617,240,10,P.muted);paste(this.sonarCanvas,1340,630,240,129);
  line(view.mode==='scripted_demo'?'No model calls claimed':`Solver: ${plan?.optimizer?.source||'no result'}`,1340,785,240,12,P.muted);
  // No text, image, metrics or controls enter this subtitle-safe 90px band.
  rect(SUBTITLE_BAND.x,SUBTITLE_BAND.y,SUBTITLE_BAND.width,SUBTITLE_BAND.height,P.bg);rule(0,SUBTITLE_BAND.y,1600);

 }
}
function finiteTime(v){return numeric(v)!==null?`T+${v.toFixed(1)} `:'';}
