const $ = (id) => document.getElementById(id);
const state = { registry: [], decisions: [], detections: [], filter: 'ALL', selectedCluster: null, selectedDecision: null, paused: false, boxes: true, link: true, frameUpdated: null, lastPayload: null };
const statusNames = { LIVE: 'Live', DEAD: 'Dead', BLEACHED: 'Bleached', RESTORED: 'Restored' };
const colors = { LIVE: '#a6ddba', DEAD: '#eb8f83', BLEACHED: '#e6be80', RESTORED: '#77bdf0' };

function safe(value) { return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])); }
function number(value, digits = 1) { return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—'; }
function timeOf(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); }
function titleCase(value) { return String(value || '').toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' '); }
function evidenceValue(value) { return Array.isArray(value) ? value.map((v) => typeof v === 'number' ? number(v, 2) : String(v)).join(', ') : typeof value === 'number' ? number(value, 2) : String(value ?? '—'); }

function renderMetrics() {
  const entries = state.registry;
  const count = (status) => entries.filter((entry) => entry.health_status === status).length;
  $('metric-clusters').textContent = entries.length;
  $('metric-restored').textContent = count('RESTORED');
  $('metric-attention').textContent = count('DEAD') + count('BLEACHED');
  for (const status of ['LIVE','DEAD','BLEACHED','RESTORED']) $('count-' + status.toLowerCase()).textContent = count(status);
  $('count-all').textContent = entries.length;
  const latest = state.decisions.at(-1);
  $('mission-phase').textContent = latest ? titleCase(latest.state) : 'Awaiting decisions';
  $('mission-subphase').textContent = latest ? (latest.outcome || latest.action || 'Decision recorded') : 'No decision events yet';
  $('decision-count').textContent = `${state.decisions.length} EVENTS`;
}

function bounds() {
  const points = state.registry.map((entry) => entry.position_world).filter((point) => Array.isArray(point) && point.length >= 2);
  const xs = points.map((point) => Number(point[0])).filter(Number.isFinite);
  const ys = points.map((point) => Number(point[1])).filter(Number.isFinite);
  if (!xs.length || !ys.length) return { minX: 0, maxX: 10, minY: 0, maxY: 10 };
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  return { minX: minX - .8, maxX: maxX + .8, minY: minY - .8, maxY: maxY + .8 };
}
function coords(entry, b) {
  const p = Array.isArray(entry.position_world) ? entry.position_world : [0,0,0];
  return { x: 8 + 84 * ((Number(p[0]) - b.minX) / (b.maxX - b.minX || 1)), y: 9 + 82 * ((Number(p[1]) - b.minY) / (b.maxY - b.minY || 1)) };
}
function renderMap(focusSelection = false) {
  const points = $('map-points'); points.replaceChildren();
  const b = bounds();
  $('map-scale-label').textContent = `${number((b.maxX - b.minX) * 37 / (Math.max(1, $('map-stage').clientWidth) * .84), 1)} m`;
  for (const entry of state.registry) {
    const pos = coords(entry, b);
    const pin = document.createElement('button');
    pin.type = 'button'; pin.className = 'map-pin';
    if (state.filter !== 'ALL' && entry.health_status !== state.filter) pin.classList.add('dimmed');
    if (entry.cluster_id === state.selectedCluster) pin.classList.add('selected');
    pin.dataset.status = entry.health_status || '';
    pin.style.left = `${pos.x}%`; pin.style.top = `${pos.y}%`;
    pin.title = `${entry.cluster_id} · ${statusNames[entry.health_status] || entry.health_status}`;
    pin.setAttribute('aria-label', pin.title);
    pin.addEventListener('click', () => { state.selectedCluster = entry.cluster_id; renderMap(true); renderScene(); });
    points.append(pin);
  }
  if (focusSelection) points.querySelector('.map-pin.selected')?.focus({ preventScroll: true });
  const entry = state.registry.find((item) => item.cluster_id === state.selectedCluster);
  const detail = $('cluster-detail');
  if (entry) {
    detail.innerHTML = `<span>${safe(entry.cluster_id)} <span class="status-text ${safe(entry.health_status)}">${safe(entry.health_status)}</span></span><p><strong>${safe(entry.species_class)}</strong> · Health ${number(Number(entry.health_score) * 100,0)}% · ${Array.isArray(entry.position_world) ? entry.position_world.map((v) => number(v)).join(', ') : '—'} m</p>`;
  } else {
    detail.innerHTML = '<span>SELECT A MAP PIN</span><p>Inspect a cluster’s health, species and position.</p>';
  }
}

function renderCamera(payload) {
  const image = $('camera-image');
  if (payload.frame_updated !== state.frameUpdated) { state.frameUpdated = payload.frame_updated; image.src = `/api/frame?v=${encodeURIComponent(payload.frame_updated)}`; }
  $('frame-label').textContent = payload.frame_synthetic ? 'SYNTHETIC FRAME' : 'FILE FRAME';
  $('camera-source-note').textContent = payload.frame_synthetic ? 'Source image is generated for this demo' : 'Frame updates from selected file';
  $('camera-overlay-note').lastChild.textContent = payload.mode === 'synthetic demo' ? ' Boxes in demo are illustrative' : (state.detections.length ? ' Boxes from source file' : ' No detection boxes supplied');
  image.alt = payload.frame_synthetic ? 'Synthetic underwater reef scene' : 'Camera frame from selected image file';
  const layer = $('detections-layer'); layer.replaceChildren();
  let detections = state.detections;
  if (!detections.length && payload.mode === 'synthetic demo') {
    const live = state.registry.find((item) => item.health_status === 'LIVE');
    const pale = state.registry.find((item) => item.health_status === 'BLEACHED');
    detections = [live && {cluster_id:live.cluster_id,box:[.06,.37,.31,.46]},pale && {cluster_id:pale.cluster_id,box:[.54,.37,.31,.4]}].filter(Boolean);
  }
  if (!state.boxes) { $('camera-detection-count').textContent = 'OVERLAYS HIDDEN'; return; }
  let count = 0;
  for (const detection of detections) {
    const box = detection.box;
    if (!Array.isArray(box) || box.length !== 4 || !box.every((v) => Number.isFinite(Number(v)))) continue;
    const entry = state.registry.find((item) => item.cluster_id === detection.cluster_id);
    const boxEl = document.createElement('div');
    boxEl.className = 'detection' + (entry?.health_status === 'BLEACHED' ? ' bleached' : '');
    boxEl.style.left = `${Math.max(0,Math.min(100,Number(box[0])*100))}%`;
    boxEl.style.top = `${Math.max(0,Math.min(100,Number(box[1])*100))}%`;
    boxEl.style.width = `${Math.max(0,Math.min(100,Number(box[2])*100))}%`;
    boxEl.style.height = `${Math.max(0,Math.min(100,Number(box[3])*100))}%`;
    const label = document.createElement('span');
    label.textContent = `${detection.cluster_id || 'DETECTION'} · ${entry?.health_status || 'OBSERVED'}${entry && Number.isFinite(Number(entry.health_score)) ? ` ${Math.round(Number(entry.health_score)*100)}%` : ''}`;
    boxEl.append(label); layer.append(boxEl); count++;
  }
  $('camera-detection-count').textContent = `${count} ${payload.mode === 'synthetic demo' && !state.detections.length ? 'ILLUSTRATIVE BOXES' : 'DETECTIONS'}`;
}

function renderScene() {
  const svg = $('scene-svg');
  const b = bounds();
  const project = (x,y,z=0) => {
    const nx = (x-b.minX)/(b.maxX-b.minX||1), ny = (y-b.minY)/(b.maxY-b.minY||1);
    return [350 + (nx-.5)*430 + (ny-.5)*225, 225 + (ny-.5)*105 - (nx-.5)*65 - z*13];
  };
  const lines = [];
  for (let i=0;i<=10;i++) {
    const t=i/10, a=project(b.minX+(b.maxX-b.minX)*t,b.minY), c=project(b.minX+(b.maxX-b.minX)*t,b.maxY);
    const d=project(b.minX,b.minY+(b.maxY-b.minY)*t), e=project(b.maxX,b.minY+(b.maxY-b.minY)*t);
    lines.push(`<path d="M${a[0]},${a[1]} L${c[0]},${c[1]}"/><path d="M${d[0]},${d[1]} L${e[0]},${e[1]}"/>`);
  }
  const floor = `<defs><linearGradient id="reefFloor" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#164752"/><stop offset="1" stop-color="#0b303d"/></linearGradient><radialGradient id="rovGlow"><stop stop-color="#b6e4d4" stop-opacity=".24"/><stop offset="1" stop-color="#b6e4d4" stop-opacity="0"/></radialGradient></defs><path d="M${project(b.minX,b.minY)} L${project(b.maxX,b.minY)} L${project(b.maxX,b.maxY)} L${project(b.minX,b.maxY)}Z" fill="url(#reefFloor)" stroke="#548086" stroke-opacity=".5"/><g fill="none" stroke="#6fa5a6" stroke-opacity=".16" stroke-width="1">${lines.join('')}</g>`;
  const corals = [...state.registry].sort((a,c) => Number(a.position_world?.[1]||0)-Number(c.position_world?.[1]||0)).map((entry,index) => {
    const [x,y] = project(Number(entry.position_world?.[0]||0), Number(entry.position_world?.[1]||0));
    const color = colors[entry.health_status] || '#a8c0bf';
    const size = 7 + (index % 3)*2;
    const selected = entry.cluster_id === state.selectedCluster;
    return `<g opacity="${state.filter !== 'ALL' && entry.health_status !== state.filter ? '.17' : '1'}"><ellipse cx="${x}" cy="${y+4}" rx="${size+4}" ry="4" fill="#041e27" opacity=".65"/><path d="M${x},${y+2}v-${size+6}m0,7l-${size/1.5},-${size/1.5}m${size/1.5},${size/1.5}l${size/1.4},-${size/1.8}m-${size/1.4},${size/1.8}l-${size/2},2m${size/2},-2l${size/2},2" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/><circle cx="${x}" cy="${y-size-4}" r="${selected?4:2}" fill="${color}"/>${selected?`<circle cx="${x}" cy="${y}" r="${size+9}" fill="none" stroke="${color}" stroke-opacity=".7"/>`:''}</g>`;
  }).join('');
  const [rx,ry]=project(b.minX+(b.maxX-b.minX)*.53,b.minY+(b.maxY-b.minY)*.55,3.2);
  const rov=`<g><ellipse cx="${rx}" cy="${ry+25}" rx="47" ry="21" fill="url(#rovGlow)"/><path d="M${rx-25},${ry+8}l25,-10 25,10 -25,10z" fill="#a6d8d1" stroke="#d8f0df" stroke-width="1.5"/><path d="M${rx-14},${ry-1}l14,-13 14,13" fill="#c1eadd" stroke="#e7f5e8" stroke-width="1"/><path d="M${rx-27},${ry+7}l-13,6 14,4M${rx+27},${ry+7}l13,6 -14,4" fill="none" stroke="#8cbbc0" stroke-width="3" stroke-linecap="round"/><circle cx="${rx}" cy="${ry+8}" r="3" fill="#f2f3d6"/><path d="M${rx},${ry+18}v22" stroke="#a5d4cb" stroke-dasharray="3 4" stroke-opacity=".5"/><text x="${rx+34}" y="${ry-12}" fill="#d8eee8" font-family="monospace" font-size="11" letter-spacing="2">ROV</text></g>`;
  svg.innerHTML = floor + corals + rov;
  const depths=state.registry.map((entry)=>Number(entry.position_world?.[2])).filter(Number.isFinite);
  $('scene-depth').textContent = depths.length ? `DEPTH ${number(Math.abs(depths.reduce((a,c)=>a+c,0)/depths.length),1)} M` : 'DEPTH — M';
}

function renderDecisions(focusSelection = false) {
  const list = $('decision-list');
  const previousScroll = list.scrollTop;
  list.replaceChildren();
  const ordered = [...state.decisions].map((entry,index)=>({...entry,_index:index})).reverse();
  for (const entry of ordered) {
    const button=document.createElement('button'); button.type='button'; button.className='decision-item';
    if (state.selectedDecision===entry._index) button.classList.add('selected');
    button.innerHTML=`<span class="decision-top"><span>${safe(timeOf(entry.timestamp))}</span><span>${safe(titleCase(entry.state))}</span></span><span class="decision-title">${safe(entry.action || 'Decision recorded')}</span><span class="decision-sub">${safe(entry.outcome || 'Evidence recorded')}</span>`;
    button.addEventListener('click',()=>{state.selectedDecision=entry._index;renderDecisions(true);}); list.append(button);
  }
  list.scrollTop = previousScroll;
  if (focusSelection) list.querySelector('.decision-item.selected')?.focus({ preventScroll: true });
  const entry=state.decisions[state.selectedDecision];
  const inspector=$('decision-inspector');
  if (!entry) {inspector.innerHTML='<div class="inspector-kicker">EVIDENCE / OUTCOME</div><p>Select a decision to inspect the sensor evidence behind it.</p>';return;}
  const rows=Object.entries(entry.evidence||{}).map(([key,value])=>`<div class="evidence-row"><span>${safe(titleCase(key))}</span><strong>${safe(evidenceValue(value))}</strong></div>`).join('');
  inspector.innerHTML=`<div class="inspector-kicker">EVIDENCE / OUTCOME</div><div class="inspector-state">${safe(entry.state)} · ${safe(timeOf(entry.timestamp))}</div><h3>${safe(entry.action)}</h3>${rows || '<p>No evidence fields supplied.</p>'}<div class="outcome"><span>OUTCOME</span><strong>${safe(entry.outcome || 'Not recorded')}</strong></div>`;
}

function render(payload) {
  const followLatest = state.selectedDecision === null || state.selectedDecision === state.decisions.length - 1;
  state.lastPayload=payload;
  state.registry=Array.isArray(payload.registry)?payload.registry:[];
  state.decisions=Array.isArray(payload.decisions)?payload.decisions:[];
  state.detections=Array.isArray(payload.detections)?payload.detections:[];
  if (followLatest || !state.decisions[state.selectedDecision]) state.selectedDecision=state.decisions.length-1;
  if (state.selectedCluster && !state.registry.some((entry)=>entry.cluster_id===state.selectedCluster)) state.selectedCluster=null;
  $('source-label').textContent=payload.mode === 'synthetic demo' ? 'SYNTHETIC DEMO' : 'FILE SOURCE';
  $('sector-label').textContent=payload.mode === 'synthetic demo' ? 'SECTOR B–04' : 'MISSION FEED';
  $('sync-label').textContent=state.paused?'UPDATES PAUSED':'SYNCED · '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  $('sync-label').classList.remove('problem'); $('error-banner').hidden=true;
  renderMetrics();renderMap();renderCamera(payload);renderScene();renderDecisions();
}

async function refresh() {
  if (state.paused) return;
  try {
    const response=await fetch('/api/state',{cache:'no-store'});
    const payload=await response.json();
    if (!response.ok) throw new Error(payload.error || `Source error ${response.status}`);
    if (state.lastPayload && ['registry_updated','decisions_updated','frame_updated','mode','frame_synthetic'].every((key) => state.lastPayload[key] === payload[key])) {
      $('sync-label').textContent='SYNCED · '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
      $('sync-label').classList.remove('problem'); $('error-banner').hidden=true;
      return;
    }
    render(payload);
  } catch(error) {
    $('sync-label').textContent='SOURCE UNAVAILABLE'; $('sync-label').classList.add('problem');
    $('error-banner').textContent=`Data source unavailable: ${error.message}. The dashboard will retry automatically.`;
    $('error-banner').hidden=false;
  }
}

$('map-legend').addEventListener('click',(event)=>{
  const button=event.target.closest('button[data-filter]');if(!button)return;
  state.filter=button.dataset.filter;
  for(const item of $('map-legend').querySelectorAll('button')) item.classList.toggle('selected',item===button);
  renderMap();renderScene();
});
$('boxes-toggle').addEventListener('click',()=>{state.boxes=!state.boxes;$('boxes-toggle').classList.toggle('active',state.boxes);$('boxes-toggle').setAttribute('aria-pressed',String(state.boxes));if(state.lastPayload)renderCamera(state.lastPayload);});
$('pause-toggle').addEventListener('click',()=>{state.paused=!state.paused;$('pause-toggle').textContent=state.paused?'RESUME UPDATES':'PAUSE UPDATES';$('pause-toggle').setAttribute('aria-pressed',String(state.paused));$('sync-label').textContent=state.paused?'UPDATES PAUSED':'RESUMING';if(!state.paused)refresh();});
$('link-toggle').addEventListener('click',()=>{state.link=!state.link;$('link-toggle').classList.toggle('off',!state.link);$('link-toggle').setAttribute('aria-pressed',String(state.link));$('link-text').textContent=state.link?'Connected':'Offline';});
$('info-button').addEventListener('click',()=>$('about-dialog').showModal());
refresh();setInterval(refresh,2000);
