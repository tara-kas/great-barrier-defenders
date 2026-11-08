/** Shared Z-up reef relief in metres. Artistic limestone bathymetry, not survey data. */
export function terrainHeight(x,y) {
  const slope=.045*(Math.max(-12,Math.min(12,x))+12);
  const ridge=.32*Math.exp(-((x+3.5)**2/8+(y-4)**2/15));
  const mound=.28*Math.exp(-((x-4.5)**2/12+(y+3.5)**2/10));
  const relief=.055*(1+Math.sin(x*.65)*Math.cos(y*.55));
  return .04+slope+ridge+mound+relief;
}
export function coralHeight(colony) {
  return Math.min(colony.radius,colony.height/1.0776135)*1.0776135;
}
/** Centroid of hero mesh triangle 98258; preserve renderer yaw and uniform scale. */
export function coralContactPoint(colony) {
  const hash=[...String(colony.id)].reduce((n,c)=>(n*31+c.charCodeAt(0))|0,7);
  const a=(hash%360)*Math.PI/180,s=Math.min(colony.radius,colony.height/1.0776135);
  const x=.053246633460124336*s,y=-.8726685047149658*s,z=.5864475965499878*s;
  return [colony.position[0]+x*Math.cos(a)-y*Math.sin(a),colony.position[1]+x*Math.sin(a)+y*Math.cos(a),colony.position[2]+z];
}
