import {fromLabSnapshot,normalizeMissionFeed,statusCounts,mapBounds,filterRegistry,reconcileSelection} from './mission-control.mjs';
const $=id=>document.getElementById(id);
const STATUS=['ALL','LIVE','BLEACHED','DEAD','TREATED','RECOVERED','NOT_RECOVERED'];
const COLORS={LIVE:'#a6ddba',BLEACHED:'#e6be80',DEAD:'#eb8f83',TREATED:'#77bdf0',RECOVERED:'#6fe0c8',NOT_RECOVERED:'#c7a4e8',UNKNOWN:'#a8bcbc'};
const text=value=>String(value??'—').replace(/scripted/gi,'local fallback');
const readable=value=>typeof value==='object'&&value!==null?JSON.stringify(value,null,2):text(value);
const element=(tag,content,className)=>Object.assign(document.createElement(tag),{textContent:content,className:className||''});
const stamp=value=>{if(value===null||value===undefined||value==='')return 'Not supplied';const date=new Date(typeof value==='number'&&value<1e12?value*1000:value);return Number.isNaN(date.getTime())?text(value):date.toLocaleTimeString();};
export class MissionPanel{
 constructor({onSelect=()=>{}}={}){
  this.onSelect=onSelect;this.source='lab';this.active=false;this.paused=false;this.filter='ALL';this.selection={selectedCluster:null,selectedDecision:null,followLatest:true};this.cache={lab:null,team:null,recorded:null};this.recordedMeta=null;this.recordedAttempted=false;this.feed=null;this.history=[];this.lastTime=-1;this.seed=null;this.lastLabRefresh=0;this.lastTeamPoll=0;this.request=null;this.error='';this.lastReceipt=0;this.frameKey='';this.teamStatus='unconfigured';
  $('evidence-source').onchange=()=>this.setSource($('evidence-source').value);
  $('evidence-pause').onclick=()=>{this.paused=!this.paused;if(!this.paused){this.accept(this.cache[this.source]);this.lastTeamPoll=0;this.poll();}this.renderStatus();};
  $('evidence-filter').onchange=()=>{this.filter=$('evidence-filter').value;this.renderRegistry();};
  $('evidence-follow').onchange=()=>{this.selection.followLatest=$('evidence-follow').checked;this.reconcile();this.renderDecisions();};
  $('evidence-refresh').onclick=()=>{if(this.paused){this.error='View paused. Resume the evidence view to fetch updates.';this.renderStatus();return;}this.lastTeamPoll=0;if(this.source==='recorded')this.recordedAttempted=false;this.poll();};
  $('evidence-boxes').onchange=()=>this.renderFrame();
  $('team-evidence-frame').onerror=()=>{$('team-frame-note').textContent='The supplied frame could not be loaded. Registry and decision evidence remain available.';};
  this.timer=setInterval(()=>{this.poll();if(this.active)this.renderStatus();},1000);this.renderStatus();
 }
 setActive(active){this.active=active;if(active){this.accept(this.cache[this.source]);this.poll();}}
 setSource(source){this.source=['team','recorded'].includes(source)?source:'lab';this.request?.abort();this.request=null;if(!this.cache.recorded)this.recordedAttempted=false;this.error='';this.selection={selectedCluster:null,selectedDecision:null,followLatest:true};$('evidence-follow').checked=true;this.feed=this.cache[this.source];this.frameKey='';this.render();this.lastTeamPoll=0;this.poll();}
 update(snapshot,activity=[]){
  const now=performance.now();if(now-this.lastLabRefresh<500&&this.cache.lab)return;this.lastLabRefresh=now;
  if(snapshot.seed!==this.seed||snapshot.time<this.lastTime){this.history=[];this.cache.lab=null;if(this.source==='lab')this.selection={selectedCluster:null,selectedDecision:null,followLatest:true};}
  this.seed=snapshot.seed;this.lastTime=snapshot.time;
  const next=fromLabSnapshot(snapshot,[...this.history,...activity.slice(-80)]);this.history=next.decisions.slice(-300);this.cache.lab=next;
  if(this.active&&this.source==='lab'&&!this.paused)this.accept(next);
 }
 selectColony(id){if(this.source!=='lab'||this.paused)return;this.selection.selectedCluster=id;if(this.active)this.renderRegistry();}
 accept(feed){if(!feed||this.paused)return;this.feed=feed;this.reconcile();if(this.active)this.render();}
 reconcile(){if(this.feed)this.selection=reconcileSelection(this.selection,this.feed);}
 async loadRecorded(){
  if(this.recordedAttempted||this.cache.recorded||this.request)return;this.recordedAttempted=true;
  const controller=new AbortController();this.request=controller;const timeout=setTimeout(()=>controller.abort(),8000);
  try{const response=await fetch('./assets/team-mission-recorded.json',{signal:controller.signal,cache:'force-cache'});if(!response.ok)throw new Error('Recorded team mission asset is unavailable');const body=await response.json();const feed=normalizeMissionFeed(body);if(this.request!==controller)return;if(body.recorded!==true)throw new Error('This asset is not identified as a recorded mission');this.recordedMeta={mode:body.mode,recordedAt:body.recordedAt,sourceNote:body.sourceNote,summary:body.summary};this.cache.recorded=feed;this.error='';this.accept(feed);}
  catch(error){if(this.request===controller){this.error=error.name==='AbortError'?'Recorded mission download timed out.':error.message;this.renderStatus();}}
  finally{clearTimeout(timeout);if(this.request===controller)this.request=null;}
 }
 async poll(){
  if(this.source==='recorded'){if(this.active&&!this.paused&&!document.hidden)this.loadRecorded();return;}
  if(!this.active||this.source!=='team'||this.paused||document.hidden||this.request||Date.now()-this.lastTeamPoll<2000)return;
  this.lastTeamPoll=Date.now();const controller=new AbortController();this.request=controller;const timeout=setTimeout(()=>controller.abort(),6000);
  try{const response=await fetch('/api/lab/team-state',{signal:controller.signal,cache:'no-store'});const body=await response.json();if(this.request!==controller)return;this.teamStatus=body.status||'ready';
   if(!response.ok||body.ok===false){if(body.stale&&Array.isArray(body.registry)){const held=normalizeMissionFeed(body);this.cache.team=held;this.accept(held);}throw new Error(body.error||body.message||'Team mission source unavailable');}
   const next=normalizeMissionFeed(body);this.cache.team=next;this.lastReceipt=Date.now();this.error=body.configured===false?'Team mission source is not configured. No sample mission is substituted.':body.stale?'Team mission files are stale.':'';this.accept(next);
  }catch(error){if(this.request===controller){this.error=error.name==='AbortError'?'Team source request timed out.':error.message;this.renderStatus();}}
  finally{clearTimeout(timeout);if(this.request===controller)this.request=null;}
 }
 renderStatus(){
  const recorded=this.source==='recorded',external=this.source!=='lab',age=this.lastReceipt?Math.floor((Date.now()-this.lastReceipt)/1000):null;
  $('evidence-pause').textContent=this.paused?'▶ Resume view':'Ⅱ Pause view';$('evidence-view-state').textContent=this.paused?'VIEW PAUSED':recorded?(this.error?'RECORDING ERROR':'RECORDED'):external&&this.teamStatus==='unconfigured'?'NOT CONFIGURED':external&&this.error?'STALE / ERROR':external&&!this.feed?'NO SOURCE':'LIVE VIEW';
  $('evidence-source-note').textContent=recorded?'Recorded team FSM output · read only · reduced physics and synthetic premapped perception. This is not a live Gemma run.':external?'Read-only team mission files. This feed never commands or replaces the browser robot.':'Browser simulation registry and recorded controller decisions. Map selection highlights the same colony in 3D.';
  $('evidence-feed-status').textContent=this.error?`${this.error}${this.feed?.registry?.length?' Showing the last good feed.':''}`:this.paused?'Evidence display is frozen. Simulation and robot control continue independently.':recorded?this.recordedMeta?`${this.recordedMeta.mode||'Recorded mission'} · ${this.recordedMeta.recordedAt?new Date(this.recordedMeta.recordedAt).toLocaleString():'date not supplied'}. ${text(this.recordedMeta.sourceNote||'Canonical mission registry and decision log; no source camera frame supplied.')}`:'Loading the recorded team mission file…':external?this.lastReceipt?`Last successful read ${age}s ago · registry ${stamp(this.feed?.registry_updated)} · decisions ${stamp(this.feed?.decisions_updated)}`:'Awaiting a configured team mission source.':`Lab source · T+ ${Number(this.lastTime<0?0:this.lastTime).toFixed(1)}s · simulated world coordinates`;
  $('evidence-refresh').hidden=!external||recorded&&!this.error;$('evidence-refresh').textContent=recorded?'Retry recorded file':'Refresh source';$('team-frame-section').hidden=!external;
 }
 render(){this.renderStatus();this.renderRegistry();this.renderDecisions();this.renderFrame();}
 renderRegistry(){
  const feed=this.feed,registry=feed?.registry||[],counts=statusCounts(feed||registry),visible=filterRegistry(feed||registry,this.filter),bounds=mapBounds(feed||registry);
  $('evidence-counts').replaceChildren(...STATUS.map(status=>{const button=element('button',`${status.replaceAll('_',' ')} ${status==='ALL'?registry.length:counts[status]||0}`);button.classList.toggle('active',this.filter===status);button.onclick=()=>{this.filter=status;$('evidence-filter').value=status;this.renderRegistry();};return button;}));
  const stage=$('evidence-map-points');stage.replaceChildren();
  for(const entry of visible){const position=entry.position_world;if(!Array.isArray(position)||!Number.isFinite(position[0])||!Number.isFinite(position[1]))continue;const pin=element('button','',`evidence-pin${entry.cluster_id===this.selection.selectedCluster?' selected':''}`);pin.style.left=`${8+84*(position[0]-bounds.minX)/(bounds.maxX-bounds.minX||1)}%`;pin.style.top=`${92-84*(position[1]-bounds.minY)/(bounds.maxY-bounds.minY||1)}%`;pin.style.setProperty('--pin',COLORS[entry.health_status]||COLORS.UNKNOWN);pin.title=`${entry.cluster_id} · ${entry.health_status}`;pin.setAttribute('aria-label',pin.title);pin.onclick=()=>{this.selection.selectedCluster=entry.cluster_id;this.renderRegistry();if(this.source==='lab')this.onSelect(entry.cluster_id);};stage.append(pin);}
  $('evidence-map-range').textContent=registry.length?`${(bounds.maxX-bounds.minX).toFixed(1)} × ${(bounds.maxY-bounds.minY).toFixed(1)} m · +Y ↑`:'No spatial observations';
  const detail=$('evidence-cluster'),selected=registry.find(row=>row.cluster_id===this.selection.selectedCluster);detail.replaceChildren();
  if(!selected){detail.append(element('p',registry.length?'Select a map pin to inspect its recorded state.':'No registry observations available.','small'));return;}
  detail.append(element('strong',`${selected.cluster_id} · ${selected.health_status}`));
  const score=selected.health_score===null||selected.health_score===undefined?'Not supplied':Number.isFinite(Number(selected.health_score))?`${Math.round(Number(selected.health_score)*100)}% (source score)`:'Not supplied';
  for(const[key,value]of[['Species',selected.species_class],['Health score',score],['Position',selected.position_world?.map(n=>Number(n).toFixed(2)).join(', ')+' m'],['Source',selected.source||selected.provenance||feed.source]]){const row=element('div','','evidence-field');row.append(element('span',key),element('b',readable(value)));detail.append(row);}
  if(this.source==='lab')detail.append(element('p','Treated records mean verified mechanical placement in this simulator; biological recovery is not inferred.','small note'));
 }
 renderDecisions(){
  const decisions=this.feed?.decisions||[],list=$('evidence-decisions'),scroll=list.scrollTop;list.replaceChildren();$('evidence-decision-count').textContent=`${decisions.length} RECORDS`;
  for(const decision of decisions.slice(-300).reverse()){const button=element('button','','evidence-decision');button.classList.toggle('active',decision.id===this.selection.selectedDecision);const when=Number.isFinite(decision.simulationTime)?`T+ ${decision.simulationTime.toFixed(1)}s`:stamp(decision.timestamp);button.append(element('span',`${when} · ${text(decision.state)}`),element('strong',text(decision.action)),element('small',text(decision.outcome)));button.onclick=()=>{this.selection.selectedDecision=decision.id;this.selection.followLatest=false;$('evidence-follow').checked=false;this.renderDecisions();};list.append(button);}list.scrollTop=scroll;
  const current=decisions.find(row=>row.id===this.selection.selectedDecision),detail=$('evidence-decision-detail');detail.replaceChildren();
  if(!current){detail.append(element('p','No decision selected. Historical selection stays fixed as new records arrive.','small'));return;}
  detail.append(element('h3',text(current.action)),element('p',`${text(current.state)} · source ${text(current.source||this.feed.source)}`,'small'));
  const evidence=element('pre',JSON.stringify(current.evidence||{},null,2),'evidence-json');detail.append(element('span','RECORDED EVIDENCE','field-label'),evidence,element('span','OUTCOME','field-label'),element('p',readable(current.outcome)));
 }
 renderFrame(){
  if(this.source==='lab')return;const feed=this.feed,image=$('team-evidence-frame'),layer=$('team-evidence-boxes'),allowed=typeof feed?.frameUrl==='string'&&/^\/api\/lab\/team-frame(?:\?|$)/.test(feed.frameUrl);
  image.hidden=!allowed;layer.replaceChildren();$('team-frame-note').textContent=allowed?`${feed.frame_synthetic?'Synthetic source frame':'File frame · camera origin unverified'} · ${stamp(feed.frame_updated)} · overlays only from supplied detections.`:'No frame supplied by the team mission source.';
  if(!allowed){image.removeAttribute('src');return;}const key=`${feed.frameUrl}:${feed.frame_updated}`;if(key!==this.frameKey){this.frameKey=key;const frameUrl=new URL(feed.frameUrl,location.origin);frameUrl.searchParams.set('v',String(Math.round(Number(feed.frame_updated||0)*1000)));image.src=frameUrl.pathname+frameUrl.search;}
  if(!$('evidence-boxes').checked)return;for(const detection of feed.detections||[]){const box=detection.box;if(!Array.isArray(box)||box.length!==4||box.some(n=>!Number.isFinite(n)||n<0||n>1))continue;const mark=element('div','','team-detection');mark.style.left=box[0]*100+'%';mark.style.top=box[1]*100+'%';mark.style.width=Math.min(box[2],1-box[0])*100+'%';mark.style.height=Math.min(box[3],1-box[1])*100+'%';mark.append(element('span',text(detection.cluster_id)));layer.append(mark);}
 }
 dispose(){clearInterval(this.timer);this.request?.abort();}
}
