/** Bounded browser-local semantic observations. Restored records are context only:
 * they NEVER satisfy live camera freshness, registry, or execution gates. */
const copy=v=>JSON.parse(JSON.stringify(v));
const text=(v,max=160)=>typeof v==='string'?v.slice(0,max):null;
const finite=v=>typeof v==='number'&&Number.isFinite(v)?v:null;
function stable(value){if(Array.isArray(value))return `[${value.map(stable).join(',')}]`;if(value&&typeof value==='object')return `{${Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')}}`;return JSON.stringify(value);}
function signature(scene){
  if(!scene||!Number.isInteger(scene.seed)||!Array.isArray(scene.colonies)||!Array.isArray(scene.obstacles))throw new Error('Semantic memory requires a valid scene');
  const colonies=scene.colonies.map(c=>({id:c.id,position:c.position,health:c.health,genet:c.genet,species:c.species,radius:c.radius,height:c.height,morphology:c.morphology})).sort((a,b)=>a.id.localeCompare(b.id));
  const obstacles=scene.obstacles.map(o=>({id:o.id,position:o.position,radius:o.radius})).sort((a,b)=>a.id.localeCompare(b.id));
  return stable({seed:scene.seed,colonies,obstacles});
}
function hash(value){let a=0x811c9dc5,b=0x9e3779b9;for(let i=0;i<value.length;i++){a=Math.imul(a^value.charCodeAt(i),0x01000193);b=Math.imul(b^value.charCodeAt(i),0x85ebca6b);}return `reef-${(a>>>0).toString(16).padStart(8,'0')}${(b>>>0).toString(16).padStart(8,'0')}`;}
export function sceneFingerprint(scene){return hash(signature(scene));}
export class SemanticMemory {
  constructor({storage,maxRecords=128,maxAgeSeconds=7*86400,clock=()=>Date.now()}={}){
    if(!Number.isInteger(maxRecords)||maxRecords<1||maxRecords>256)throw new Error('Memory capacity must be 1–256 records');
    if(!Number.isFinite(maxAgeSeconds)||maxAgeSeconds<=0||maxAgeSeconds>30*86400)throw new Error('Memory age must be positive and at most 30 days');
    if(storage===undefined){try{storage=globalThis.localStorage;}catch{storage=null;}}
    this.storage=storage??null;this.maxRecords=maxRecords;this.maxAgeSeconds=maxAgeSeconds;this.clock=clock;this.records=[];this.sceneHash=null;this.sceneSignature=null;this.restoredCount=0;this.lastError=null;
  }
  get status(){return {available:!!this.storage&&!this.lastError,sceneHash:this.sceneHash,count:this.records.length,restoredCount:this.restoredCount,lastError:this.lastError,usableForControl:false,persistence:this.storage&&!this.lastError?'local_storage':'memory_only'};}
  _key(){if(!this.sceneHash)throw new Error('Bind a scene before using semantic memory');return `reef-rescue.semantic-memory.v1.${this.sceneHash}`;}
  _prune(){const now=this.clock();this.records=this.records.filter(r=>r.expiresAt>now&&r.storedAt<=now+60000&&r.sceneHash===this.sceneHash).slice(-this.maxRecords);}
  _write(){this._prune();if(!this.storage)return;try{this.storage.setItem(this._key(),this.exportJSON());this.lastError=null;}catch{this.lastError='Browser storage unavailable or full; observations remain in this session only.';}}
  bindScene(scene){this.sceneSignature=signature(scene);this.sceneIds=new Set(scene.colonies.map(c=>c.id));this.sceneHash=hash(this.sceneSignature);this.records=[];this.restoredCount=0;this.lastError=null;if(this.storage){try{const raw=this.storage.getItem(this._key());if(raw){this._read(raw);this.restoredCount=this.records.length;}}catch{this.records=[];this.lastError='Stored semantic memory could not be validated and was ignored.';}}return {sceneHash:this.sceneHash,restoredCount:this.restoredCount,usableForControl:false};}
  _record(input){
    if(!input||!this.sceneIds?.has(input.id)||input.source!=='gemma'||typeof input.id!=='string'||!['healthy','bleached_alive','dead','unknown'].includes(input.health))throw new Error('Memory accepts only explicit Gemma health observations');
    const confidence=finite(input.confidence);if(confidence===null||confidence<0||confidence>1)throw new Error('Invalid remembered confidence');
    const frameTime=finite(input.frameTime),storedAt=finite(input.storedAt),expiresAt=finite(input.expiresAt);if(frameTime===null||frameTime<0||storedAt===null||expiresAt===null||expiresAt<=storedAt||expiresAt-storedAt>this.maxAgeSeconds*1000+1)throw new Error('Invalid memory timing');
    if(input.sceneHash!==this.sceneHash)throw new Error('Observation belongs to another scene');
    for(const field of ['requestId','model','provider'])if(!text(input[field]))throw new Error('Memory requires explicit model/request provenance');
    return {id:text(input.id),health:input.health,confidence,source:'gemma',model:text(input.model),provider:text(input.provider),requestId:text(input.requestId),frameTime,receivedTime:finite(input.receivedTime),storedAt,expiresAt,sceneHash:this.sceneHash,usableForControl:false,genotypeInferred:false,notice:'Historical model estimate; obtain a fresh matched camera frame before any action'};
  }
  remember(snapshot){
    this._key();if(signature(snapshot)!==this.sceneSignature)throw new Error('Scene changed; bind the new scene before storing observations');
    const observations=snapshot.intelligence?.onboard?.observations??[];let added=0;const now=this.clock();
    for(const observation of observations){if(observation.source!=='gemma')continue;if(this.records.some(r=>r.id===observation.id&&r.requestId===observation.requestId&&r.frameTime===observation.frameTime))continue;const r=this._record({...observation,sceneHash:this.sceneHash,storedAt:now,expiresAt:now+this.maxAgeSeconds*1000});this.records.push(r);added++;}
    this._write();return {added,...this.status};
  }
  entries(){this._prune();return copy(this.records);}
  planningContext(ids=[]){this._prune();const selected=this.records.filter(r=>!ids.length||ids.includes(r.id)).slice(-4);return {source:'historical_semantic_memory',sceneHash:this.sceneHash,usableForControl:false,notice:'Context only; fresh matched camera inference and local registry gates remain mandatory',records:selected.map(r=>({id:r.id,health:r.health,confidence:r.confidence,model:r.model,provider:r.provider,frameTime:r.frameTime,storedAt:r.storedAt,requestId:r.requestId}))};}
  clear(){this.records=[];this.restoredCount=0;if(this.storage){try{this.storage.removeItem(this._key());this.lastError=null;}catch{this.lastError='Unable to clear browser persistence; in-session memory was cleared.';}}return this.status;}
  exportJSON(){this._prune();return JSON.stringify({schema:'reef-rescue-semantic-memory/v1',sceneHash:this.sceneHash,sceneSignature:this.sceneSignature,usableForControl:false,records:this.records},null,2);}
  _read(raw){if(typeof raw!=='string'||raw.length>1024*1024)throw new Error('Memory import exceeds 1 MiB');const data=JSON.parse(raw);if(data.schema!=='reef-rescue-semantic-memory/v1'||data.sceneHash!==this.sceneHash||data.sceneSignature!==this.sceneSignature)throw new Error('Semantic memory belongs to a different scene');if(!Array.isArray(data.records)||data.records.length>256)throw new Error('Invalid memory record count');const records=data.records.map(r=>this._record(r));this.records=records;this._prune();}
  importJSON(raw){this._key();this._read(raw);this.restoredCount=this.records.length;this._write();return {...this.status,imported:this.records.length};}
}
