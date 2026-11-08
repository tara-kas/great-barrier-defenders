import test from 'node:test';
import assert from 'node:assert/strict';
import {captureEvidence,assessCapture,fitCaptureText} from '../web/lab/recorder.mjs';
test('capture retains actual identity and model provenance without raw pixels or credentials',()=>{const s={time:5,phase:'transport',controller:'onboard',pilot:{mode:'autonomous'},robot:{holding:'f-1',position:[1,2,3]},fragments:[{id:'f-1',state:'carried'}],metrics:{placed:0,drops:0,recoveries:0},intelligence:{onboard:{lastPacket:{requestId:'p1',source:'gemma',model:'gemma-test',inputImageSha256:'abc',rawImage:'forbidden',apiKey:'forbidden'},observations:[{id:'c1',appearance:'pale_or_bleached',confidence:.8}]}}};const e=captureEvidence(s,1,1);assert.equal(e.robot.holding,'f-1');assert.equal(e.perception.source,'gemma');assert.equal(e.perception.inputImageSha256,'abc');assert.ok(!JSON.stringify(e).includes('forbidden'));assert.equal(e.observations[0].appearance,'pale_or_bleached');});
test('continuity assessment rejects early stop, reset and hidden-tab evidence',()=>{const a=captureEvidence({time:5,pilot:{mode:'autonomous'}},0),b=captureEvidence({time:1,pilot:{mode:'manual'}},59);const r=assessCapture({wallDurationSeconds:59,issues:['Browser tab became hidden'],samples:[a,b]});assert.equal(r.continuous,false);assert.ok(r.issues.some(x=>x.includes('backwards')));assert.ok(r.issues.some(x=>x.includes('before 60')));assert.ok(r.issues.some(x=>x.includes('Manual')));});
test('a full capture reports observed outcome deltas without declaring unproven task success',()=>{const a=captureEvidence({time:50,phase:'transport',pilot:{mode:'autonomous'},metrics:{placed:0,drops:0,recoveries:0}},0);const b=captureEvidence({time:110,phase:'complete',completed:true,pilot:{mode:'autonomous'},metrics:{placed:1,drops:1,recoveries:1}},60);const r=assessCapture({wallDurationSeconds:60.02,samples:[a,b],issues:[]});assert.equal(r.continuous,true);assert.equal(r.placementDelta,1);assert.equal(r.dropDelta,1);assert.equal(r.recoveryDelta,1);assert.equal(r.taskOutcomeVerified,false);});

test('capture labels fit measured right-panel width without drawing outside the canvas',()=>{const measure=s=>[...s].reduce((n,c)=>n+(c==='W'?16:8),0);const label=fitCaptureText('WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW',246,measure);assert.ok(measure(label)<=246);assert.ok(label.endsWith('…'));assert.equal(fitCaptureText('Gemma',246,measure),'Gemma');assert.equal(fitCaptureText('Too narrow',1,measure),'');});
test('video and evidence downloads are separate single user actions',async t=>{
 const {LiveDemoRecorder}=await import('../web/lab/recorder.mjs');let result;const clicks=[];
 t.mock.method(globalThis,'setTimeout',()=>0);
 const oldDocument=globalThis.document;globalThis.document={createElement:()=>({click(){clicks.push(this.download);}})};
 try{
  const instance=Object.assign(Object.create(LiveDemoRecorder.prototype),{stream:{getTracks:()=>[]},metadata:{startedAt:'2026-11-08T13:00:00.000Z',wallDurationSeconds:60.25,samples:[],issues:[]},recorder:{mimeType:'video/webm'},chunks:[new Blob(['fixture-not-video'])],onStatus:()=>{},onComplete:r=>result=r});
  instance.finish();assert.equal(clicks.length,0);result.downloadVideo();assert.deepEqual(clicks,[result.filename]);result.downloadEvidence();assert.equal(clicks.length,2);assert.ok(clicks[1].endsWith('.evidence.json'));result.download();assert.equal(clicks.length,3);assert.equal(clicks[2],result.filename);
 }finally{if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument;}
});

test('scripted 2x capture is explicit while keeping wall-clock continuity and real provenance',async()=>{
 const {capturePresentation}=await import('../web/lab/recorder.mjs');
 const state={controller:'scripted',pilot:{mode:'autonomous'},time:0,metrics:{placed:0}};
 const a=captureEvidence(state,0,2),b=captureEvidence({...state,time:120,metrics:{placed:1}},60,2);
 assert.equal(capturePresentation(state,2).label,'Reef Rescue — Final Demo');assert.equal(a.presentation.speedLabel,'2× SIMULATION');
 const result=assessCapture({wallDurationSeconds:60.25,samples:[a,b],issues:[]});
 assert.equal(result.continuous,true);assert.equal(result.recordingMode,'scripted_demo');assert.deepEqual(result.simulationSpeeds,[2]);assert.equal(result.taskOutcomeVerified,false);
});
test('dashboard compositor uses source canvases, hides stale model claims in scripted mode and reserves subtitle band',async()=>{
 const {LiveDemoRecorder,SUBTITLE_BAND}=await import('../web/lab/recorder.mjs');
 const labels=[],images=[],rectangles=[];const ctx={fillRect:(...a)=>rectangles.push(a),fillText:(...a)=>labels.push(a),measureText:v=>({width:String(v).length*7}),drawImage:(...a)=>images.push(a)};
 const reef={width:1200,height:800},pip={width:384,height:288},sonar={width:448,height:240};
 const s={controller:'scripted',time:42,phase:'transport',pilot:{mode:'autonomous'},water:{current:.2,visibility:8},robot:{holding:'fragment-1'},metrics:{placed:0,drops:1,recoveries:1},events:[{time:40,message:'Recovered the same fragment'}],intelligence:{onboard:{lastPacket:{model:'STALE_MODEL_RESULT'}}}};
 const recorder=Object.assign(Object.create(LiveDemoRecorder.prototype),{ctx,reefCanvas:reef,pipCanvas:pip,sonarCanvas:sonar,getSnapshot:()=>s,getSpeed:()=>2,getLog:()=>[{message:'OLD_MODEL_LOG'}],onStatus:()=>{},started:performance.now(),lastSample:-1,metadata:{samples:[],logs:[],issues:[]}});
 recorder.draw();assert.deepEqual(images.map(a=>a[0]),[reef,pip,sonar]);
 const written=labels.map(a=>a[0]).join('\n');assert.match(written,/Reef Rescue — Final Demo/);assert.match(written,/Simulated sensing and local scenario control/);assert.match(written,/2× SIMULATION/);assert.doesNotMatch(written,/STALE_MODEL_RESULT|OLD_MODEL_LOG|CONTINUOUS LIVE TAKE/);
 assert.ok(labels.every(([,x,y])=>x>=0&&y<SUBTITLE_BAND.y));assert.ok(rectangles.some(a=>a[0]===0&&a[1]===810&&a[2]===1600&&a[3]===90));
});
