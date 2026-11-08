import { terrainHeight } from './terrain.mjs';
import { reefRegions,reefRegionAt } from './habitat-regions.mjs';
const random=(seed=527)=>()=>{seed|=0;seed=seed+0x6d2b79f5|0;let t=Math.imul(seed^seed>>>15,1|seed);t^=t+Math.imul(t^t>>>7,61|t);return((t^t>>>14)>>>0)/4294967296;};
/** Deterministic, grounded specimen layout shared by renderer, collisions and sonar.
 * radius/height conservatively enclose the scan at the recorded visual scale.
 * Habitat colonies are never eligible mission donors or recipients.
 */
export function generateHabitat(registered=[],seed=527){
  const rand=random(seed),regions=reefRegions(seed),colonies=[];
  for(let attempt=0;attempt<9000&&colonies.length<620;attempt++){
    let x,y;if(rand()<.52){const patch=regions[Math.floor(rand()*regions.length)],a=rand()*Math.PI*2,r=Math.sqrt(-2*Math.log(Math.max(.00001,rand())))*patch.radius*.72;x=patch.center[0]+Math.cos(a)*r;y=patch.center[1]+Math.sin(a)*r;}else{x=(rand()-.5)*22;y=(rand()-.5)*22;}
    const scale=.26+rand()*.4,yaw=rand()*6.283;
    if(Math.max(Math.abs(x),Math.abs(y))+scale>11.7)continue;
    // Winding sand channels and densely connected, irregular thickets; never rows.
    if(Math.abs(y-Math.sin(x*.62)*.7)<.22&&rand()<.8)continue;
    if(registered.some(c=>c.genet&&Math.hypot(x-c.position[0],y-c.position[1])<Math.max(1,c.radius+.55)+scale))continue;
    if(colonies.some(c=>Math.hypot(x-c.position[0],y-c.position[1])<.32))continue;
    const region=reefRegionAt(x,y,seed),choice=rand(),health=choice<region.healthMix.healthy?'healthy':choice<region.healthMix.healthy+region.healthMix.bleached_alive?'bleached_alive':'dead',index=colonies.length,acropora=health==='healthy'&&rand()<.18;
    colonies.push({id:`habitat-coral-${index}`,type:'coral',position:[x,y,terrainHeight(x,y)-.018],radius:scale,height:scale*(acropora?.90959067:1.0776135),scale,yaw,materialIndex:acropora?5:Math.floor(rand()*5),health,regionId:region.regionId,morphology:'branching',species:acropora?'Acropora secale':'Pocillopora damicornis'});
  }
  return colonies;
}
export function generateHabitatRocks(registered=[],seed=527){
  const rand=random(seed),rocks=[];
  for(let i=0;i<200;i++){
    const x=(rand()-.5)*23,z=(rand()-.5)*23,rotation=[rand()*.2,rand()*6,rand()*.2],scale=.12+rand()*.55;
    rocks.push({id:`habitat-rock-${i}`,type:'rock',position:[x,-z,terrainHeight(x,-z)],radius:scale*1.8,height:scale*1.15,scale,rotation});
  }
  return rocks.filter(h=>!registered.some(c=>c.genet && Math.hypot(h.position[0]-c.position[0],h.position[1]-c.position[1])<Math.max(1,c.radius+.55)+h.radius));
}
