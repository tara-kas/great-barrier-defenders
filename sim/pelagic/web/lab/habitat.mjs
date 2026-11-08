import { terrainHeight } from './terrain.mjs';
const random=(seed=527)=>()=>{seed|=0;seed=seed+0x6d2b79f5|0;let t=Math.imul(seed^seed>>>15,1|seed);t^=t+Math.imul(t^t>>>7,61|t);return((t^t>>>14)>>>0)/4294967296;};
/** Deterministic, grounded specimen layout shared by renderer, collisions and sonar.
 * radius/height conservatively enclose the scan at the recorded visual scale.
 * Habitat colonies are never eligible mission donors or recipients.
 */
export function generateHabitat(registered=[]){
  const rand=random();for(let i=0;i<1200;i++)rand();const colonies=[];
  for(let ix=-12;ix<=12;ix++)for(let iz=-12;iz<=12;iz++){
    const x=ix*.74+(rand()-.5)*.35,z=iz*.74+(rand()-.5)*.35;
    if(Math.abs(z-Math.sin(x*.75)*.65)<.32)continue;
    if([-2.6,0,2.6].some(cx=>Math.hypot(x-cx,z-2.2)<.68||Math.hypot(x-cx,z+2)<.68))continue;
    const scale=.32+rand()*.32,yaw=rand()*6.283,index=colonies.length,acropora=index%6===5;
    colonies.push({id:`habitat-coral-${index}`,type:'coral',position:[x,-z,terrainHeight(x,-z)-.018],radius:scale,height:scale*(acropora?.90959067:1.0776135),scale,yaw,materialIndex:index%6,morphology:'branching',species:acropora?'Acropora secale':'Pocillopora damicornis'});
  }
  return colonies.filter(h=>!registered.some(c=>c.genet && Math.hypot(h.position[0]-c.position[0],h.position[1]-c.position[1])<Math.max(1,c.radius+.55)+h.radius));
}
export function generateHabitatRocks(registered=[]){
  const rand=random(),rocks=[];
  for(let i=0;i<200;i++){
    const x=(rand()-.5)*23,z=(rand()-.5)*23,rotation=[rand()*.2,rand()*6,rand()*.2],scale=.12+rand()*.55;
    rocks.push({id:`habitat-rock-${i}`,type:'rock',position:[x,-z,terrainHeight(x,-z)],radius:scale*1.8,height:scale*1.15,scale,rotation});
  }
  return rocks.filter(h=>!registered.some(c=>c.genet && Math.hypot(h.position[0]-c.position[0],h.position[1]-c.position[1])<Math.max(1,c.radius+.55)+h.radius));
}
