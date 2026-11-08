/** Read-only Mission Control adapters. Team registry/log contracts are preserved;
 * browser scenario truth, model estimates and biological outcomes remain distinct. */
export const HEALTH_STATUSES=Object.freeze(['LIVE','BLEACHED','DEAD','TREATED','RECOVERED','NOT_RECOVERED']);
const MAX_REGISTRY=2000,MAX_DECISIONS=300;
const plain=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const text=(v,max=240)=>typeof v==='string'?v.slice(0,max):'';
const vector=(v,n=3)=>Array.isArray(v)&&v.length===n&&v.every(finite)?v.slice():null;
const hash=s=>{let h=2166136261;for(const c of s)h=Math.imul(h^c.charCodeAt(0),16777619);return(h>>>0).toString(16);};
function evidence(v,depth=0){
 if(depth>5)return '[depth limit]';
 if(v===null||typeof v==='boolean')return v;
 if(typeof v==='number')return finite(v)?v:null;
 if(typeof v==='string')return v.slice(0,800);
 if(Array.isArray(v))return v.slice(0,24).map(x=>evidence(x,depth+1));
 if(plain(v))return Object.fromEntries(Object.entries(v).filter(([k])=>!['__proto__','constructor','prototype','image','dataUrl','jpeg','png'].includes(k)&&(!/secret|credential|authorization|api.?key|token|base64|raw.?image|image.?data/i.test(k)||k==='inputImageSha256')).slice(0,32).map(([k,x])=>[k.slice(0,100),evidence(x,depth+1)]));
 return null;
}
function boundedEvidence(value){const out=evidence(value);return JSON.stringify(out).length<=8192?out:{truncated:true,reason:'Evidence exceeds the 8 KiB display limit'};}
function registryEntry(c,source){
 if(!plain(c)||!text(c.cluster_id)||!HEALTH_STATUSES.includes(c.health_status)||!vector(c.position_world))throw Error('Invalid mission registry entry');
 if(c.health_score!=null&&(!finite(c.health_score)||c.health_score<0||c.health_score>1))throw Error('Invalid mission health score');
 const extent=c.bounding_box_extent==null?null:vector(c.bounding_box_extent);if(c.bounding_box_extent!=null&&(!extent||extent.some(v=>v<0)))throw Error('Invalid mission bounding extent');
 let graft=null;if(c.optimal_graft_pose_world!=null){const g=c.optimal_graft_pose_world;if(!plain(g)||!vector(g.position)||!vector(g.orientation_quat,4)||!vector(g.surface_normal))throw Error('Invalid mission graft pose');graft={position:g.position.slice(),orientation_quat:g.orientation_quat.slice(),surface_normal:g.surface_normal.slice()};}
 return {cluster_id:text(c.cluster_id),species_class:text(c.species_class),health_status:c.health_status,health_score:c.health_score??null,position_world:c.position_world.slice(),bounding_box_extent:extent,optimal_graft_pose_world:graft,sampled_or_restored:c.sampled_or_restored===true,genet_id:c.genet_id==null?null:text(c.genet_id),uv_signature:c.uv_signature==null?null:vector(c.uv_signature),provenance:source};
}
function decisions(rows,source){
 if(!Array.isArray(rows)||rows.length>10000)throw Error('Invalid mission decision list');
 const seen=new Map();return rows.slice(-MAX_DECISIONS).map(d=>{
  if(!plain(d)||typeof d.state!=='string'||typeof d.action!=='string'||!plain(d.evidence))throw Error('Invalid mission decision entry');
  if(d.timestamp!=null&&typeof d.timestamp!=='string')throw Error('Invalid decision timestamp');
  const item={timestamp:text(d.timestamp),state:text(d.state),action:text(d.action,1500),evidence:boundedEvidence(d.evidence),outcome:text(d.outcome,1500),source:text(d.source)||source,simulationTime:finite(d.simulationTime)?d.simulationTime:null};
  const key=text(d.id)||`decision-${hash(JSON.stringify([item.timestamp,item.simulationTime,item.state,item.action,item.outcome,item.source]))}`;const n=seen.get(key)||0;seen.set(key,n+1);return {...item,id:n?`${key}-${n}`:key};
 });
}
function stamp(v){if(v==null)return null;if(!finite(v)||v<0)throw Error('Invalid source update timestamp');return v;}
function frameUrl(v){if(v==null||v==='')return null;if(typeof v!=='string'||v.length>2000||!v.startsWith('/')||v.startsWith('//')||/[\\\u0000-\u0020]/.test(v))throw Error('Frame URL must be a same-origin path');return v;}
export function normalizeMissionFeed(payload){
 if(!plain(payload)||!Array.isArray(payload.registry)||payload.registry.length>MAX_REGISTRY)throw Error('Invalid mission feed registry');
 const source='external_mission',registry=payload.registry.map(c=>registryEntry(c,source));if(new Set(registry.map(c=>c.cluster_id)).size!==registry.length)throw Error('Duplicate mission colony ID');
 const raw=payload.detections??[];if(!Array.isArray(raw)||raw.length>MAX_REGISTRY)throw Error('Invalid mission detections');
 const ids=new Set(registry.map(c=>c.cluster_id));const detections=raw.map(d=>{if(!plain(d)||!vector(d.box,4)||d.box.some(v=>v<0||v>1)||d.box[0]+d.box[2]>1.000001||d.box[1]+d.box[3]>1.000001||!ids.has(d.cluster_id))throw Error('Invalid mission detection box');return {cluster_id:text(d.cluster_id),box:d.box.slice(),source:'supplied_file_detection'};});
 return {mode:text(payload.mode)||'file source',source,readOnly:true,registry,detections,decisions:decisions(payload.decisions??[],source),registry_updated:stamp(payload.registry_updated),decisions_updated:stamp(payload.decisions_updated),frame_updated:stamp(payload.frame_updated),frame_synthetic:payload.frame_synthetic===true,frameUrl:frameUrl(payload.frameUrl),limits:{registry:MAX_REGISTRY,decisions:MAX_DECISIONS,omittedDecisions:Math.max(0,(payload.decisions?.length||0)-MAX_DECISIONS)},provenance:{registry:'External mission file; observations are not independently verified by this viewer',frame:payload.frame_synthetic===true?'Declared synthetic frame':'File frame; camera origin not verified',control:'Read-only observation; no vehicle commands'}};
}
export function fromLabSnapshot(snapshot,history=[]){
 if(!plain(snapshot)||!Array.isArray(snapshot.colonies)||snapshot.colonies.length>MAX_REGISTRY||!finite(snapshot.time)||snapshot.time<0||!Array.isArray(history)||history.length>10000)throw Error('Invalid browser mission snapshot');
 const treated=new Set((snapshot.fragments||[]).filter(f=>f.state==='placed').map(f=>f.targetId));
 const registry=snapshot.colonies.map(c=>{const health={healthy:'LIVE',bleached_alive:'BLEACHED',dead:'DEAD'}[c.health];return registryEntry({cluster_id:c.id,species_class:c.species,health_status:treated.has(c.id)&&health==='BLEACHED'?'TREATED':health,health_score:null,position_world:c.position,bounding_box_extent:[2*c.radius,2*c.radius,c.height],sampled_or_restored:treated.has(c.id),genet_id:c.genet||null},'browser_scenario_registry');});
 const rows=[...(snapshot.events||[]),...history].map(e=>{
  if(plain(e)&&typeof e.action==='string'&&typeof e.state==='string'&&plain(e.evidence))return e;
  if(!plain(e)||typeof e.message!=='string'||!finite(e.time))throw Error('Invalid browser history event');
  return {timestamp:text(e.receivedAt),simulationTime:e.time,state:text(e.type)||'event',action:e.message,evidence:{eventType:text(e.type),simulationTime:e.time},outcome:'Event recorded; see explicit decision evidence for model output',source:'browser_event'};
 });
 const d=snapshot.decision;if(plain(d)&&d.id){rows.push({id:`model-${d.id}`,timestamp:'',simulationTime:finite(d.time)?d.time:null,state:'controller_decision',action:text(d.decision??d.action)||'decision',evidence:d,outcome:text(d.reason,1500),source:text(d.source)||'unreported'});}
 // Event duplicates may arrive both in the snapshot and caller's rolling history.
 const unique=[...new Map(rows.map(r=>[JSON.stringify([r.state==='controller_decision'?r.id:null,r.timestamp,r.simulationTime,r.state,r.action,r.source]),r])).values()];unique.sort((a,b)=>(a.simulationTime??Infinity)-(b.simulationTime??Infinity));
 return {mode:'browser simulation',source:'browser_simulation',readOnly:true,registry,detections:[],decisions:decisions(unique,'browser_event'),registry_updated:snapshot.time,decisions_updated:snapshot.time,frame_updated:snapshot.time,frame_synthetic:true,frameUrl:null,limits:{registry:MAX_REGISTRY,decisions:MAX_DECISIONS,omittedDecisions:Math.max(0,unique.length-MAX_DECISIONS)},provenance:{registry:'Known scenario registry; health scores are not inferred',frame:'Rendered robot camera; no fabricated detection boxes',control:'Read-only panel; the simulation controls remain separate',outcome:'TREATED means mechanically verified placement, not biological recovery'}};
}
const entries=input=>Array.isArray(input)?input:input?.registry??[];
export function statusCounts(input){const counts={ALL:entries(input).length,...Object.fromEntries(HEALTH_STATUSES.map(s=>[s,0]))};for(const c of entries(input))if(HEALTH_STATUSES.includes(c.health_status))counts[c.health_status]++;return counts;}
export function filterRegistry(input,status='ALL'){if(status!=='ALL'&&!HEALTH_STATUSES.includes(status))throw Error('Unknown health filter');return entries(input).filter(c=>status==='ALL'||c.health_status===status);}
export function mapBounds(input){const ps=entries(input).map(c=>vector(c.position_world)).filter(Boolean);if(!ps.length)return {minX:0,maxX:10,minY:0,maxY:10};const xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]);return {minX:Math.min(...xs)-.8,maxX:Math.max(...xs)+.8,minY:Math.min(...ys)-.8,maxY:Math.max(...ys)+.8};}
export function reconcileSelection(previous={},feed){const rows=feed?.decisions??[],selected=rows.some(d=>d.id===previous.selectedDecision);const followLatest=previous.followLatest??previous.selectedDecision==null;return {selectedCluster:entries(feed).some(c=>c.cluster_id===previous.selectedCluster)?previous.selectedCluster:null,selectedDecision:followLatest||!selected?rows.at(-1)?.id??null:previous.selectedDecision,followLatest};}
