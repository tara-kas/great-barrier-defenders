/** Shared Z-up reef relief in metres. Artistic limestone bathymetry, not survey data. */
export function terrainHeight(x,y) {
  // Smooth regional slope and limestone shelf, with broad sand gullies and local divots.
  // No floor clamp or terrace discontinuity: the same continuous surface drives contacts.
  const slope=.95*Math.tanh(x/14);
  const shelf=.32*Math.tanh((x+.25*y-1)/3.8);
  const crest=.52*Math.exp(-((x-4)**2/18+(y+3)**2/30));
  const outcrop=.38*Math.exp(-((x+4)**2/8+(y-4)**2/12));
  const gully=-.27*Math.exp(-((y-.35*x+.8)**2/3.5+x*x/200));
  const divots=-.18*Math.exp(-((x+1.7)**2/2+(y-1)**2/2.6))-.14*Math.exp(-((x-6)**2/3+(y-4)**2/3));
  const texture=.018*Math.sin(x*2)*Math.sin(y*1.6);
  return 1.4+slope+shelf+crest+outcrop+gully+divots+texture;
}
/** Unit Z-up normal shared by seafloor orientation and contact inspection. */
export function terrainNormal(x,y) {
  const e=.01,dx=(terrainHeight(x+e,y)-terrainHeight(x-e,y))/(2*e),dy=(terrainHeight(x,y+e)-terrainHeight(x,y-e))/(2*e),length=Math.hypot(dx,dy,1);
  return [-dx/length,-dy/length,1/length];
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
