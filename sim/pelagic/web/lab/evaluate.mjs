import { ReefLab } from './simulation.mjs';
self.onmessage=({data})=>{
 const conditions=['baseline','drop','bad_cut','bad_placement','current_surge','sensor_dropout'].filter(c=>c!=='bad_cut'||data.scene.restorationMode!=='loose_fragment');
 const count=Math.min(10,Math.max(1,Number(data.count)||3));
 const report={version:1,controller:'scripted',model:'Browser reduced hydrodynamics and synthetic fault models',budgetSeconds:600,conditions,scene:data.scene,runs:[],limits:'Finite modeled scenarios only. No Isaac contact parity, image perception or biological recovery claims. Seeds vary modeled cut quality; geometry remains the supplied scene.'};
 for(const condition of conditions)for(let i=0;i<count;i++){
  const seed=(data.scene.seed+i)>>>0,sim=new ReefLab({...data.scene,seed});
  if(condition!=='baseline')sim.command({action:'inject_fault',kind:condition});
  sim.command({action:'run'});
  for(let t=0;t<600&&sim.running;t++)sim.step(1);
  const s=sim.snapshot(),exposed=condition==='baseline'||!s.queuedFaults.includes(condition);
  report.runs.push({condition,seed,success:s.completed&&exposed,faultExposed:exposed,time:s.time,phase:s.phase,reason:s.running?'Simulation budget exceeded':s.status,metrics:s.metrics,events:s.events,unconsumedFaults:s.queuedFaults});
  self.postMessage({type:'progress',done:report.runs.length,total:conditions.length*count,scenario:condition});
 }
 self.postMessage({type:'result',report});
};
