/** Seeded ecological composition; scenario labels, not a reconstructed survey. */
const random=(seed)=>()=>{seed|=0;seed=seed+0x6d2b79f5|0;let t=Math.imul(seed^seed>>>15,1|seed);t^=t+Math.imul(t^t>>>7,61|t);return((t^t>>>14)>>>0)/4294967296;};
const cache=new Map();
export function reefRegions(seed=42){
 if(cache.has(seed))return cache.get(seed).map(r=>({...r,center:[...r.center],healthMix:{...r.healthMix}}));
 const rand=random((seed^0x72b3d159)>>>0),yaw=(rand()-.5)*.65,c=Math.cos(yaw),s=Math.sin(yaw);
 const definitions=[['healthy-west','Living western thicket','healthy',[-4,3.1],2.8],['healthy-east','Living eastern crest','healthy',[3.5,-3.8],3],['bleached-east','Pale eastern patch','bleached_alive',[4.2,3.6],2.7],['bleached-west','Pale western pocket','bleached_alive',[-3.7,-3.6],2.6],['transition','Mixed central saddle','mixed',[.1,.2],2.3]];
 const result=definitions.map(([id,name,kind,p,radius])=>({id,name,kind,center:[p[0]*c-p[1]*s+(rand()-.5)*.65,p[0]*s+p[1]*c+(rand()-.5)*.65],radius:radius*(.91+rand()*.18),healthMix:kind==='healthy'?{healthy:.91,bleached_alive:.07,dead:.02}:kind==='bleached_alive'?{healthy:.1,bleached_alive:.86,dead:.04}:{healthy:.46,bleached_alive:.36,dead:.18}}));
 if(cache.size>32)cache.delete(cache.keys().next().value);cache.set(seed,result);return result.map(r=>({...r,center:[...r.center],healthMix:{...r.healthMix}}));
}
export function reefRegionAt(x,y,seed=42){
 const regions=reefRegions(seed),mix={healthy:.055,bleached_alive:.035,dead:.01};let total=.1,strongest=0,region=regions.at(-1);
 for(const r of regions){const dx=x-r.center[0],dy=y-r.center[1],warp=1+.14*Math.sin(x*.65+y*.37),w=Math.exp(-(dx*dx+dy*dy)/(r.radius*r.radius*warp)*1.45);total+=w;for(const key of Object.keys(mix))mix[key]+=w*r.healthMix[key];if(w>strongest){strongest=w;region=r;}}
 for(const key of Object.keys(mix))mix[key]/=total;
 return{regionId:region.id,kind:region.kind,healthMix:mix};
}
export const regionDefinitions=reefRegions;
export const classifyRegion=reefRegionAt;
