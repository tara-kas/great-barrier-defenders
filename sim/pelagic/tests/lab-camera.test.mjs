import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from '../web/vendor/three.module.js';
import { ReefScene } from '../web/lab/scene.mjs';
import { ReefLab } from '../web/lab/simulation.mjs';

const raw=readFileSync(new URL('../web/lab/assets/pocillopora-hero.bin',import.meta.url));
const binary=raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength),count=new Uint32Array(binary,0,2)[0];
const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(binary,8,count*3),3));
const compact=JSON.parse(readFileSync(new URL('../configs/reef_lab_compact_recovery.json',import.meta.url)));
const vec=p=>new THREE.Vector3(p[0],p[2],-p[1]);
function inspection(phase){
 const sim=new ReefLab({...compact,controller:'scripted',restorationMode:'donor_cut'});sim.command({action:'run'});
 let state;do{state=sim.step(.02);}while(state.time<180&&!(state.phase===phase&&state.perceptionRequest?.ready));
 assert.equal(state.phase,phase);return state;
}
function optic(state){
 const scene=Object.create(ReefScene.prototype);Object.assign(scene,{scene:new THREE.Scene(),geometries:new Set(),colonies:new Map(),coralMats:[new THREE.MeshBasicMaterial()],bleachedMat:new THREE.MeshBasicMaterial(),deadMat:new THREE.MeshBasicMaterial(),scan:geometry,heroScan:geometry,selection:new THREE.Object3D(),targetMarker:new THREE.Object3D(),donorMarker:new THREE.Object3D(),toolCamera:new THREE.PerspectiveCamera(58,4/3,.015,35),snapshot:state,ready:true});
 scene.syncColonies(state);const yaw=state.robot.yaw,forward=new THREE.Vector3(Math.cos(yaw),0,-Math.sin(yaw)),right=new THREE.Vector3(Math.sin(yaw),0,Math.cos(yaw));
 scene.toolCamera.position.copy(vec(state.robot.gripper)).addScaledVector(right,.38).addScaledVector(forward,-.46).add(new THREE.Vector3(0,.3,0));return scene;
}
function fit(scene,state){const aim=scene.fitColonyOptic(state);scene.toolCamera.updateProjectionMatrix();scene.toolCamera.updateMatrixWorld(true);return aim;}
function assertInside(point,camera){const p=point.clone().project(camera);assert(Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z));assert(Math.abs(p.x)<1&&Math.abs(p.y)<1&&Math.abs(p.z)<1,`Point outside view: ${p.toArray()}`);}
for(const phase of ['inspect_recipient','inspect_donor'])test(`${phase} frames every actual specimen vertex, target and seabed junction`,()=>{
 const state=inspection(phase),scene=optic(state);fit(scene,state);const entry=scene.colonies.get(state.perceptionRequest.targetId),positions=geometry.attributes.position;
 for(let i=0;i<positions.count;i++)assertInside(new THREE.Vector3().fromBufferAttribute(positions,i).applyMatrix4(entry.mesh.matrixWorld),scene.toolCamera);
 assertInside(vec(state.perceptionRequest.targetPosition),scene.toolCamera);assertInside(vec(state.colonies.find(c=>c.id===state.perceptionRequest.targetId).position),scene.toolCamera);
 assert(scene.toolCamera.fov>=46&&scene.toolCamera.fov<=100);
});
test('repeated colony rescans change bounded optical context without moving robot, camera mount or specimen',()=>{
 const state=inspection('inspect_donor'),scene=optic(state),original=JSON.stringify(state),mount=scene.toolCamera.position.clone(),mesh=scene.colonies.get(state.donorId).mesh;mesh.updateWorldMatrix(true,false);const transform=mesh.matrixWorld.clone();
 const first=fit(scene,state),firstFov=scene.toolCamera.fov,firstQuaternion=scene.toolCamera.quaternion.clone();fit(scene,state);assert.equal(scene.toolCamera.fov,firstFov);assert(scene.toolCamera.quaternion.equals(firstQuaternion));
 const rescanned=structuredClone(state);rescanned.time+=10;rescanned.perceptionRequest.id='new-capture';const second=fit(scene,rescanned);assert(second.y<first.y);assert(scene.toolCamera.fov>firstFov);assert(scene.toolCamera.position.equals(mount));assert.equal(JSON.stringify(state),original);assert(mesh.matrixWorld.equals(transform));
 for(let i=0;i<10;i++){rescanned.time++;rescanned.perceptionRequest.id=`rescan-${i}`;fit(scene,rescanned);assert(scene.toolCamera.fov<=100);assert.equal(scene.colonyViews.get(state.donorId).revision,2);}
 state.time=0;fit(scene,state);assert.equal(scene.colonyViews.get(state.donorId).revision,0);assert.equal(scene.toolCamera.fov,firstFov);
});
test('colony framing does not act on fragment inspections or absent target geometry',()=>{
 const state=inspection('inspect_donor'),scene=optic(state),before=scene.toolCamera.quaternion.clone();state.perceptionRequest.targetKind='fragment';assert.equal(fit(scene,state),null);assert(scene.toolCamera.quaternion.equals(before));state.perceptionRequest.targetKind='colony';state.perceptionRequest.targetId='absent';assert.equal(fit(scene,state),null);
});
test('preview and inference share the actual tool optic rather than secretly aiming at the contact point',()=>{
 const state=inspection('inspect_donor'),scene=optic(state);fit(scene,state);const renders=[];
 const pixels=new Uint8Array(768*576*4),canvas={toDataURL:()=> 'data:image/jpeg;base64,fixture'},context={putImageData(){}};
 scene.cameraBuffers=new Map([['768x576',{target:{},canvas,context,pixels,image:{data:new Uint8Array(pixels.length)}}]]);
 scene.renderer={shadowMap:{autoUpdate:true},getRenderTarget:()=>null,setRenderTarget(){},render(world,camera){renders.push({position:camera.position.clone(),quaternion:camera.quaternion.clone(),fov:camera.fov});},readRenderTargetPixels(){}};
 scene.renderPreview({width:768,height:576,getContext:()=>({drawImage(){}})});
 const image=scene.captureObservation({targetPosition:state.perceptionRequest.targetPosition,includeProjection:true});assert.equal(renders.length,2);
 assert(renders[0].position.equals(renders[1].position));assert(renders[0].quaternion.equals(renders[1].quaternion));assert.equal(renders[0].fov,renders[1].fov);assert(renders[1].quaternion.equals(scene.toolCamera.quaternion));assert.equal(image.imageFocus.source,'tracked_camera_projection');assert(image.imageFocus.target.every(v=>v>=0&&v<=1));
 const contactOnly=scene.toolCamera.clone();contactOnly.lookAt(vec(state.perceptionRequest.targetPosition));assert(!renders[1].quaternion.equals(contactOnly.quaternion));
 const expected=new THREE.Box3().setFromObject(scene.colonies.get(state.donorId).mesh).getCenter(new THREE.Vector3()).project(scene.toolCamera);
 assert(Math.abs(image.imageFocus.target[0]-(expected.x+1)/2)<1e-9);assert(Math.abs(image.imageFocus.target[1]-(1-expected.y)/2)<1e-9);
 const contact=vec(state.perceptionRequest.targetPosition).project(scene.toolCamera);assert(Math.abs(image.imageFocus.target[0]-(contact.x+1)/2)>1e-3||Math.abs(image.imageFocus.target[1]-(1-contact.y)/2)>1e-3);
});
