/** Visual ROV assembly. Local forward is -Z; Y is up, metres.
 * Decorative engineering illustration, not validated CAD or a thruster model.
 * All meshes use the scene's add/material factories for ordinary disposal.
 */
export function buildVehicleBody({THREE,group,mat,add}){
 if(!THREE||!group||typeof mat!=='function'||typeof add!=='function')throw Error('Vehicle needs THREE, a group, and bound material/mesh factories');
 const materials={white:mat({color:0xd9e0dc,roughness:.58,metalness:.12},false),dark:mat({color:0x172c33,roughness:.56,metalness:.48},false),teal:mat({color:0x378c89,roughness:.53,metalness:.22},false),metal:mat({color:0x9aa9a7,roughness:.38,metalness:.72},false),glass:mat({color:0x092029,roughness:.12,metalness:.58},false)};
 const {white,dark,teal,metal,glass}=materials;
 const rubber=mat({color:0x101c21,roughness:.92,metalness:0},false),lens=mat({color:0xd3e8dd,emissive:0x34534c,emissiveIntensity:.3,roughness:.25,metalness:.12},false);
 const mesh=(geometry,material,position=[0,0,0],parent=group)=>{const m=add(geometry,material,parent);m.position.set(...position);return m;};
 const box=(size,position,material,parent=group)=>mesh(new THREE.BoxGeometry(...size),material,position,parent);
 const cylinder=(radius,length,position,material,parent=group,segments=16)=>mesh(new THREE.CylinderGeometry(radius,radius,length,segments),material,position,parent);
 const rod=(a,b,radius,material=dark,parent=group)=>{const start=new THREE.Vector3(...a),end=new THREE.Vector3(...b),delta=end.clone().sub(start);const m=mesh(new THREE.CylinderGeometry(radius,radius,delta.length(),8),material,start.clone().add(end).multiplyScalar(.5).toArray(),parent);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());return m;};
 const capsule=(radius,length,scale,position,material)=>{const geometry=new THREE.CapsuleGeometry(radius,length,6,20);geometry.rotateX(Math.PI/2);geometry.scale(...scale);return mesh(geometry,material,position);};
 const rim=(radius,tube,z,material,parent)=>mesh(new THREE.TorusGeometry(radius,tube,6,24),material,[0,0,z],parent);
 // Sealed central pressure vessel with restrained fairing and service joints.
 capsule(.215,.43,[1.18,.78,1],[0,.015,-.005],white).name='sealed-pressure-hull';
 capsule(.184,.37,[1.18,.48,1],[0,.133,-.025],teal).name='upper-equipment-fairing';
 for(const z of [-.255,.255]){
  const seam=mesh(new THREE.TorusGeometry(.207,.009,6,24),dark,[0,.015,z]);seam.scale.set(1.18,.78,1);
 }
 box([.34,.034,.30],[0,-.147,.02],dark).name='lower-equipment-tray';
 // Independent syntactic-foam style buoyancy pods with mounting straps.
 for(const sign of [-1,1]){
  const x=sign*.395;
  capsule(.105,.45,[1,.79,1],[x,.205,-.115],white).name='flotation-pod';
  for(const z of [-.27,.045]){
   const strap=mesh(new THREE.TorusGeometry(.106,.010,6,20),dark,[x,.205,z]);strap.scale.y=.79;
   rod([sign*.255,.12,z],[x,.13,z],.015,metal);
  }
  // Rounded rail ends and inclined supports protect the tool's working envelope.
  rod([sign*.455,-.311,-.49],[sign*.455,-.311,.49],.023,rubber);
  rod([sign*.455,-.311,-.49],[sign*.455,-.265,-.545],.023,rubber);
  rod([sign*.455,-.311,.49],[sign*.455,-.265,.545],.023,rubber);
  for(const z of [-.34,.32])rod([sign*.455,-.295,z],[sign*.32,-.085,z],.018,metal);
  rod([sign*.48,-.075,-.42],[sign*.48,-.075,.43],.015,dark);
 }
 for(const z of [-.38,.36])rod([-.45,-.265,z],[.45,-.265,z],.016,dark);
 // Low bow and stern bumpers connect the open frame without blanking the optics.
 for(const z of [-.50,.50])rod([-.43,-.105,z],[.43,-.105,z],.017,dark);
 const rotors=[];
 function thruster(position,axis,name){
  const g=new THREE.Group();g.name=name;g.position.set(...position);g.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),new THREE.Vector3(...axis).normalize());group.add(g);
  const shell=new THREE.CylinderGeometry(.116,.116,.134,24,1,true);shell.rotateX(Math.PI/2);mesh(shell,dark,[0,0,0],g);
  rim(.111,.010,-.069,teal,g);rim(.111,.010,.069,metal,g);
  for(const z of [-.069,.069]){const ring=mesh(new THREE.RingGeometry(.098,.116,24),metal,[0,0,z],g);if(z<0)ring.rotation.y=Math.PI;}
  const rotor=new THREE.Group();rotor.name='illustrative-propeller';g.add(rotor);rotors.push(rotor);
  const hub=cylinder(.024,.047,[0,0,0],metal,rotor);hub.rotation.x=Math.PI/2;
  const spinner=mesh(new THREE.SphereGeometry(.025,12,8),dark,[0,0,-.024],rotor);spinner.scale.z=.68;
  const bladeShape=new THREE.Shape();bladeShape.moveTo(.017,-.009);bladeShape.quadraticCurveTo(.058,-.019,.099,-.006);bladeShape.quadraticCurveTo(.105,.006,.089,.016);bladeShape.quadraticCurveTo(.057,.012,.021,.009);bladeShape.closePath();
  const bladeGeometry=new THREE.ExtrudeGeometry(bladeShape,{depth:.004,bevelEnabled:false,curveSegments:5});
  for(let i=0;i<3;i++){const blade=mesh(bladeGeometry,metal,[0,0,-.002],rotor);blade.rotation.z=i*Math.PI*2/3;}
  // Rear motor stays visibly centred on the duct axis, carried by actual struts.
  const motor=cylinder(.030,.055,[0,0,.037],dark,g);motor.rotation.x=Math.PI/2;
  for(const angle of [0,Math.PI])rod([Math.cos(angle)*.03,Math.sin(angle)*.03,.048],[Math.cos(angle)*.102,Math.sin(angle)*.102,.048],.004,metal,g);
  for(let i=0;i<4;i++){const a=i*Math.PI/2+.785;const screw=cylinder(.006,.005,[Math.cos(a)*.107,Math.sin(a)*.107,-.079],dark,g,6);screw.rotation.x=Math.PI/2;}
  return g;
 }
 // Two vectored horizontal units and two vertical units: illustrative hardware,
 // independent of the simulator's reduced three-axis force allocation.
 for(const sign of [-1,1]){
  thruster([sign*.387,-.071,-.175],[sign*.65,0,-.76],'vectored-horizontal-thruster');
  thruster([sign*.365,.018,.375],[0,1,0],'vertical-thruster');
  rod([sign*.25,-.04,-.175],[sign*.34,-.04,-.175],.018,metal);
  rod([sign*.24,.015,.345],[sign*.33,.015,.375],.018,metal);
 }
 function forwardHousing(x,y,z,radius,light=false){
  const housing=cylinder(radius,.075,[x,y,z],dark);housing.rotation.x=Math.PI/2;
  const face=mesh(new THREE.TorusGeometry(radius*.86,.006,5,20),metal,[x,y,z-.04]);
  const window=mesh(new THREE.CircleGeometry(radius*.76,20),light?lens:glass,[x,y,z-.047]);window.rotation.y=Math.PI;
  if(!light){const optic=mesh(new THREE.SphereGeometry(radius*.58,16,10),glass,[x,y,z-.045]);optic.scale.z=.34;}
  return {housing,face,window};
 }
 forwardHousing(0,.037,-.463,.065,false); // Sealed forward camera.
 for(const x of [-.19,.19])forwardHousing(x,-.025,-.438,.048,true);
 const sonar=forwardHousing(0,-.125,-.379,.045,false);sonar.housing.name='forward-sonar-housing';
 // Top service lid, captive fasteners and sealed rear electrical connectors.
 box([.21,.015,.18],[0,.229,-.045],dark);
 for(const x of [-.082,.082])for(const z of [-.108,.018])cylinder(.007,.006,[x,.241,z],metal,group,6);
 for(const x of [-.095,0,.095]){const plug=cylinder(.015,.032,[x,.035,.447],dark,group,10);plug.rotation.x=Math.PI/2;const cap=mesh(new THREE.TorusGeometry(.014,.004,5,12),teal,[x,.035,.466]);}
 // Handle lies inside the flotation profile, rather than an oversized mast.
 rod([-.09,.235,.14],[-.09,.282,.14],.010,metal);rod([-.09,.282,.14],[.09,.282,.14],.010,dark);rod([.09,.282,.14],[.09,.235,.14],.010,metal);
 let labelTexture=null;
 if(typeof document!=='undefined'){
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=160;const c=canvas.getContext('2d');
  if(c){c.fillStyle='#d9e0dc';c.fillRect(0,0,640,160);c.fillStyle='#286e6e';c.fillRect(12,18,10,122);c.fillStyle='#172c33';c.font='bold 54px sans-serif';c.fillText('REEF RESCUE',40,76);c.font='26px monospace';c.fillText('RESTORE–02',43,126);labelTexture=new THREE.CanvasTexture(canvas);labelTexture.colorSpace=THREE.SRGBColorSpace;
   const labelMaterial=mat({map:labelTexture,roughness:.65,metalness:.05,polygonOffset:true,polygonOffsetFactor:-1},false);
   for(const sign of [-1,1]){const label=mesh(new THREE.PlaneGeometry(.36,.09),labelMaterial,[sign*.256,.018,-.04]);label.rotation.y=sign*Math.PI/2;label.name='RESTORE-02-nameplate';}
  }
 }
 group.userData.vehicleVisual={model:'RESTORE-02 visual assembly',validatedCAD:false,actuatorPhysicsChanged:false};
 return {materials,labelTexture,rotors,visualOnly:true,envelope:{width:1.12,height:.65,length:1.15}};
}
