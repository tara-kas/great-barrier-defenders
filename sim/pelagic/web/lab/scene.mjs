import * as THREE from '../vendor/three.module.js';
import { terrainHeight, terrainNormal, coralContactPoint } from './terrain.mjs';
import { reefRegions } from './habitat-regions.mjs';
import { generateHabitat, generateHabitatRocks } from './habitat.mjs';

const UP = new THREE.Vector3(0, 1, 0);
const asset = (name) => new URL(`./assets/${name}`, import.meta.url).href;
const vec = (p = [0, 0, 0]) => new THREE.Vector3(p[0], p[2], -p[1]);
const random = (seed = 51) => () => { seed |= 0; seed = seed + 0x6d2b79f5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const hash = (id) => [...String(id)].reduce((n, c) => (n * 31 + c.charCodeAt(0)) | 0, 7);

/** Browser rendering of the laboratory state. No mission decisions live here. */
export class ReefScene {
  constructor(canvas, { onSelect = () => {}, onProgress = () => {} } = {}) {
    this.canvas = canvas; this.onSelect = onSelect; this.onProgress = onProgress;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance', preserveDrawingBuffer: true });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#126474');
    this.scene.fog = new THREE.FogExp2('#126474', .065);
    this.camera = new THREE.PerspectiveCamera(46, 1, .025, 90);
    this.cameraMode = 'orbit'; this.azimuth = .5; this.elevation = .46; this.distance = 14;
    this.target = new THREE.Vector3(0, .4, 0);
    this.colonies = new Map(); this.fragments = new Map(); this.obstacles = new Map();
    this.textures = new Map(); this.materials = new Set(); this.geometries = new Set();
    this.wildlife = new Map(); this.overlays = { routes: true, sonar: false, currents: true, regions: true };this.currentGroup=new THREE.Group();this.regionGroup=new THREE.Group();this.scene.add(this.currentGroup,this.regionGroup); this.routeGroup = new THREE.Group(); this.sonarGroup = new THREE.Group(); this.scene.add(this.routeGroup,this.sonarGroup);
    this.timeUniform = { value: 0 }; this.fans = []; this.fish = []; this.shafts = [];
    this.pickables = []; this.raycaster = new THREE.Raycaster(); this.pointer = new THREE.Vector2();
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(canvas);
    this.handlers = [];
    this.bindControls(); this.resize(); this.ready = false; this.disposed = false;
  }
  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  listen(type, handler, opts) { this.canvas.addEventListener(type, handler, opts); this.handlers.push([type, handler, opts]); }
  bindControls() {
    this.canvas.style.touchAction = 'none';
    this.listen('pointerdown', e => { this.drag = { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY, button: e.button }; this.canvas.setPointerCapture(e.pointerId); });
    this.listen('pointermove', e => {
      if (!this.drag) return;
      const dx = e.clientX - this.drag.x, dy = e.clientY - this.drag.y;
      if (Math.hypot(e.clientX - this.drag.startX, e.clientY - this.drag.startY) > 5) this.drag.moved = true;
      this.cameraMode = 'orbit';
      if (this.drag.button === 2 || e.shiftKey) { const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0); this.target.addScaledVector(right, -dx * this.distance / 700); this.target.z -= dy * this.distance / 700; }
      else { this.azimuth -= dx * .005; this.elevation = THREE.MathUtils.clamp(this.elevation + dy * .004, .09, 1.48); }
      this.drag.x = e.clientX; this.drag.y = e.clientY;
    });
    this.listen('pointerup', e => {
      if (this.drag && !this.drag.moved && e.button === 0) {
        const r = this.canvas.getBoundingClientRect(); this.pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
        this.raycaster.setFromCamera(this.pointer, this.camera);
        const hit = this.raycaster.intersectObjects(this.pickables, true)[0];
        if (hit) { let o = hit.object; while (o && !o.userData.colonyId) o = o.parent; if (o) this.onSelect(o.userData.colonyId); }
      }
      this.drag = null;
    });
    this.listen('pointercancel', () => { this.drag = null; });
    this.listen('wheel', e => { e.preventDefault(); this.distance = THREE.MathUtils.clamp(this.distance * Math.exp(e.deltaY * .001), 1.1, 30); this.cameraMode = 'orbit'; }, { passive: false });
    this.listen('contextmenu', e => e.preventDefault());
  }
  async loadGeometry(name) {
    const response = await fetch(asset(name)); if (!response.ok) throw new Error(`Coral geometry unavailable: ${name}`);
    const buffer = await response.arrayBuffer(), header = new Uint32Array(buffer, 0, 2), vertices = header[0], count = header[1];
    if (buffer.byteLength !== 8 + vertices * 32 + count * 4) throw new Error(`Invalid coral geometry: ${name}`);
    let offset = 8; const geometry = new THREE.BufferGeometry();
    for (const [name, size] of [['position', 3], ['normal', 3], ['uv', 2]]) { geometry.setAttribute(name, new THREE.BufferAttribute(new Float32Array(buffer, offset, vertices * size), size)); offset += vertices * size * 4; }
    geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(buffer, offset, count), 1)); geometry.computeBoundingSphere(); this.geometries.add(geometry); return geometry;
  }
  async texture(name, srgb = false, repeat = 1) {
    if (this.textures.has(`${name}:${repeat}`)) return this.textures.get(`${name}:${repeat}`);
    const texture = await new THREE.TextureLoader().loadAsync(asset(name));
    texture.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    texture.flipY = !['healthy-', 'bleached', 'dead', 'coral-normal', 'coral-roughness', 'acropora-'].some(p => name.startsWith(p));
    texture.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping; texture.repeat.set(repeat, repeat);
    this.textures.set(`${name}:${repeat}`, texture); return texture;
  }
  mat(options, caustics = true) {
    const mat = new THREE.MeshStandardMaterial(options); this.materials.add(mat);
    if (caustics) {
      mat.onBeforeCompile = shader => {
        shader.uniforms.reefTime = this.timeUniform;
        shader.vertexShader = 'varying vec3 reefWorld;\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace('#include <worldpos_vertex>', `#include <worldpos_vertex>\nvec4 reefP = vec4(transformed, 1.0);\n#ifdef USE_INSTANCING\nreefP = instanceMatrix * reefP;\n#endif\nreefWorld = (modelMatrix * reefP).xyz;`);
        shader.fragmentShader = 'varying vec3 reefWorld;\nuniform float reefTime;\n' + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>\nfloat ca = abs(sin(reefWorld.x*3.8 + sin(reefWorld.z*3.1 + reefTime*.28)) * cos(reefWorld.z*4.1 + sin(reefWorld.x*2.7 - reefTime*.2)));\nfloat cb = pow(max(0.0, 1.0-ca), 15.0);\ndiffuseColor.rgb *= .92 + cb*.24;`);
      };
      mat.customProgramCacheKey = () => 'reef-caustics-v1';
    }
    return mat;
  }
  add(geo, mat, parent = this.scene) { this.geometries.add(geo); const m = new THREE.Mesh(geo, mat); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m; }
  async init() {
    this.onProgress('Loading specimen geometry');
    const [standard, hero, acropora, normal, roughness] = await Promise.all([this.loadGeometry('pocillopora.bin'), this.loadGeometry('pocillopora-hero.bin'), this.loadGeometry('acropora.bin'), this.texture('coral-normal.jpg'), this.texture('coral-roughness.jpg')]);
    this.scan = standard; this.heroScan = hero; this.acropora = acropora;
    const colors = ['tan', 'pink', 'green', 'tan', 'tan'];
    this.coralMats = await Promise.all(colors.map(async color => this.mat({ map: await this.texture(`healthy-${color}.jpg`, true), normalMap: normal, normalScale: new THREE.Vector2(.62, .62), roughnessMap: roughness, roughness: .95, metalness: 0 })));
    this.bleachedMat = this.mat({ map: await this.texture('bleached.jpg', true), normalMap: normal, normalScale: new THREE.Vector2(.55, .55), roughness: .98, roughnessMap: roughness });
    this.deadMat = this.mat({ map: await this.texture('dead.jpg', true), normalMap: normal, normalScale: new THREE.Vector2(.8, .8), roughness: 1 });
    this.branchNormal = await this.texture('branch-normal.jpg', false, 3);
    this.acroporaMat = this.mat({map: await this.texture('acropora-color.jpg',true),normalMap: await this.texture('acropora-normal.jpg'),normalScale:new THREE.Vector2(.6,.6),color:0xa8bfa6,roughness:.95});
    this.onProgress('Building reef habitat');
    await this.buildHabitat(); this.buildRobot(); this.buildMarkers();
    this.ready = true; this.onProgress('Reef ready');
    return this;
  }
  async buildHabitat() {
    const hemisphere = new THREE.HemisphereLight(0x9bd9e7, 0x53624b, 2.1); this.scene.add(hemisphere);
    const sun = new THREE.DirectionalLight(0xffedcc, 3.0); sun.position.set(-7, 14, -5); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.camera.left = sun.shadow.camera.bottom = -12; sun.shadow.camera.right = sun.shadow.camera.top = 12; sun.shadow.camera.far = 40; sun.shadow.normalBias = .035; sun.shadow.bias = -.0001; this.scene.add(sun); this.sun = sun;
    this.scene.add(new THREE.AmbientLight(0x408f9d, .45));
    const [sand, sandNormal, sandRough, rubble, rubbleNormal] = await Promise.all([this.texture('fine_sand-diffuse.jpg', true, 64), this.texture('fine_sand-normal_gl.jpg', false, 64), this.texture('fine_sand-roughness.jpg', false, 64), this.texture('rubble-diffuse.jpg', true, 2), this.texture('rubble-normal_gl.jpg', false, 2)]);
    // Nonuniform tessellation concentrates real relief geometry near the mission.
    const ground = new THREE.PlaneGeometry(160,160,256,256);ground.rotateX(-Math.PI/2);const p=ground.attributes.position,uv=ground.attributes.uv,blend=[];
    const stretch=v=>{const u=Math.abs(v)/80;return Math.sign(v)*(u<=.5?u*40:20+(u-.5)*120);};
    for(let i=0;i<p.count;i++){const x=stretch(p.getX(i)),z=stretch(p.getZ(i)),height=terrainHeight(x,-z),normal=terrainNormal(x,-z),slope=Math.hypot(normal[0],normal[1])/normal[2];p.setXYZ(i,x,height,z);uv.setXY(i,(x+80)/160,(80-z)/160);blend.push(THREE.MathUtils.clamp(slope*2.8+(height-1)*.22+.12*Math.sin(x*.6)*Math.cos(z*.5),0,.88));}
    ground.setAttribute('terrainMix',new THREE.Float32BufferAttribute(blend,1));ground.computeVertexNormals();
    const floorMat=this.mat({map:sand,normalMap:sandNormal,normalScale:new THREE.Vector2(.6,.6),roughnessMap:sandRough,roughness:1,color:0xc1c8b8});
    const prepare=floorMat.onBeforeCompile;floorMat.onBeforeCompile=shader=>{prepare(shader);shader.uniforms.terrainRubble={value:rubble};shader.vertexShader='attribute float terrainMix;\nvarying float vTerrainMix;\n'+shader.vertexShader;shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nvTerrainMix=terrainMix;');shader.fragmentShader='uniform sampler2D terrainRubble;\nvarying float vTerrainMix;\n'+shader.fragmentShader;shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>','#include <map_fragment>\nvec3 rockColor=texture2D(terrainRubble,reefWorld.xz*.25).rgb;\ndiffuseColor.rgb=mix(diffuseColor.rgb,rockColor*vec3(.82,.9,.82),vTerrainMix);');};floorMat.customProgramCacheKey=()=> 'reef-topology-v2';
    this.add(ground,floorMat);
    this.rockMat = this.mat({map:rubble,normalMap:rubbleNormal,normalScale:new THREE.Vector2(.95,.95),roughness:1,color:0x8b9988});
    const rand=random(527), dummy=new THREE.Object3D();
    const rockGeo = new THREE.IcosahedronGeometry(1, 2); const rp=rockGeo.attributes.position;
    for(let i=0;i<rp.count;i++){const x=rp.getX(i),y=rp.getY(i),z=rp.getZ(i),noise=1+.12*Math.sin(x*12+z*17)*Math.sin(y*11);rp.setXYZ(i,x*noise,y*noise,z*noise);}rockGeo.computeVertexNormals();this.rockGeo=rockGeo;this.geometries.add(rockGeo);
    this.habitatGroup=new THREE.Group();this.scene.add(this.habitatGroup);this.rebuildHabitat([]);
    this.buildOuterHabitat();this.buildParticles(rand);
    const surface=this.add(new THREE.PlaneGeometry(80,80),new THREE.MeshBasicMaterial({color:0x9bdaca,transparent:true,opacity:.16,side:THREE.DoubleSide,depthWrite:false}));surface.position.y=8;surface.rotation.x=Math.PI/2;surface.castShadow=false;
    for(let i=0;i<7;i++){
      const geo=new THREE.ConeGeometry(.5+i*.12,12,12,1,true), mat=new THREE.MeshBasicMaterial({color:0xa5e4d4,transparent:true,opacity:.017,side:THREE.DoubleSide,blending:THREE.AdditiveBlending,depthWrite:false});this.materials.add(mat);
      const shaft=this.add(geo,mat);shaft.position.set(-8+i*2.5,4,-6+i*.5);shaft.rotation.z=-.27;shaft.castShadow=false;shaft.receiveShadow=false;this.shafts.push(shaft);
    }
  }
  scenicGeometry(source) {
    // Coarse vertex clustering retains specimen silhouette for distant context.
    const positions=source.attributes.position,normals=source.attributes.normal,uv=source.attributes.uv,clusters=new Map(),remap=new Uint32Array(positions.count),vertices=[],normalValues=[],uvValues=[],counts=[];
    const cell=.18;
    for(let i=0;i<positions.count;i++){
      const x=positions.getX(i),y=positions.getY(i),z=positions.getZ(i),key=`${Math.round(x/cell)},${Math.round(y/cell)},${Math.round(z/cell)}`;
      let id=clusters.get(key);if(id===undefined){id=clusters.size;clusters.set(key,id);vertices.push(0,0,0);normalValues.push(0,0,0);uvValues.push(uv.getX(i),uv.getY(i));counts.push(0);}
      remap[i]=id;counts[id]++;vertices[id*3]+=x;vertices[id*3+1]+=y;vertices[id*3+2]+=z;normalValues[id*3]+=normals.getX(i);normalValues[id*3+1]+=normals.getY(i);normalValues[id*3+2]+=normals.getZ(i);
    }
    for(let i=0;i<counts.length;i++){for(let k=0;k<3;k++)vertices[i*3+k]/=counts[i];const length=Math.hypot(...normalValues.slice(i*3,i*3+3))||1;for(let k=0;k<3;k++)normalValues[i*3+k]/=length;}
    const indices=[],seen=new Set();for(let i=0;i<source.index.count;i+=3){const a=remap[source.index.getX(i)],b=remap[source.index.getX(i+1)],c=remap[source.index.getX(i+2)];if(a===b||a===c||b===c)continue;const key=[a,b,c].sort((x,y)=>x-y).join(',');if(seen.has(key))continue;seen.add(key);indices.push(a,b,c);}
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normalValues,3));geometry.setAttribute('uv',new THREE.Float32BufferAttribute(uvValues,2));geometry.setIndex(indices);geometry.computeBoundingSphere();this.geometries.add(geometry);return geometry;
  }
  buildOuterHabitat() {
    // Scenic continuation strictly beyond the editable ±12 m working zone.
    // These coarse distant scans never participate in robot observations/physics.
    const rand=random(1947),dummy=new THREE.Object3D(),entries=[],rocks=[];
    for(let ix=-24;ix<=24;ix++)for(let iz=-24;iz<=24;iz++){
      const x=ix*1.45+(rand()-.5)*.7,z=iz*1.45+(rand()-.5)*.7,scale=.5+rand()*.65;
      if(Math.max(Math.abs(x),Math.abs(z))-scale<12.05)continue;
      if(Math.abs(z-Math.sin(x*.21)*6)<.5&&rand()<.8)continue;
      entries.push({x,z,scale,yaw:rand()*6.283});if(rand()<.2){const rockScale=.8+rand()*1.4;if(Math.max(Math.abs(x),Math.abs(z))-rockScale*1.15>12.05)rocks.push({x,z,scale:rockScale});}
    }
    const lowScan=this.scenicGeometry(this.scan),lowAcropora=this.scenicGeometry(this.acropora);
    this.scenicHabitatCount=entries.length;
    for(let k=0;k<4;k++){
      const subset=entries.filter((_,i)=>i%4===k),mesh=new THREE.InstancedMesh(k===3?lowAcropora:lowScan,k===3?this.acroporaMat:this.coralMats[k],subset.length);mesh.castShadow=false;mesh.receiveShadow=false;this.scene.add(mesh);
      subset.forEach((c,i)=>{dummy.position.set(c.x,terrainHeight(c.x,-c.z)-.02,c.z);dummy.rotation.set(0,c.yaw,0);dummy.scale.setScalar(c.scale);dummy.updateMatrix();mesh.setMatrixAt(i,dummy.matrix);mesh.setColorAt(i,new THREE.Color().setRGB(.82+rand()*.15,.84+rand()*.1,.72+rand()*.15));});
    }
    const mesh=new THREE.InstancedMesh(this.rockGeo,this.rockMat,rocks.length);mesh.castShadow=false;mesh.receiveShadow=false;this.scene.add(mesh);
    rocks.forEach((c,i)=>{dummy.position.set(c.x,terrainHeight(c.x,-c.z)+c.scale*.18,c.z);dummy.rotation.set(0,rand()*6.283,0);dummy.scale.set(c.scale,c.scale*.32,c.scale*.75);dummy.updateMatrix();mesh.setMatrixAt(i,dummy.matrix);});
  }
  rebuildHabitat(registered,seed=527) {
    for(const mesh of this.habitatGroup.children)mesh.dispose?.();this.habitatGroup.clear();const dummy=new THREE.Object3D(),rand=random(527);
    const rockLayout=generateHabitatRocks(registered,seed),rocks=new THREE.InstancedMesh(this.rockGeo,this.rockMat,rockLayout.length); rocks.castShadow=true;rocks.receiveShadow=true;this.habitatGroup.add(rocks);
    rockLayout.forEach((r,i)=>{dummy.position.copy(vec(r.position));dummy.position.y+=r.scale*.35;dummy.rotation.set(...r.rotation);dummy.scale.set(r.scale*1.6,r.scale*.35,r.scale);dummy.updateMatrix();rocks.setMatrixAt(i,dummy.matrix);});
    const colonies=generateHabitat(registered,seed);this.decorativeColonyCount=colonies.length;
    for(const health of ['healthy','bleached_alive','dead'])for(let k=0;k<6;k++){
      const entries=colonies.filter(c=>c.materialIndex===k&&c.health===health);if(!entries.length)continue;
      const material=health==='bleached_alive'?this.bleachedMat:health==='dead'?this.deadMat:k===5?this.acroporaMat:this.coralMats[k%5],inst=new THREE.InstancedMesh(k===5?this.acropora:this.scan,material,entries.length);
      inst.castShadow=false;inst.receiveShadow=true;this.habitatGroup.add(inst);
      entries.forEach((c,i)=>{dummy.position.copy(vec(c.position));dummy.rotation.set(0,c.yaw,0);dummy.scale.setScalar(c.scale);dummy.updateMatrix();inst.setMatrixAt(i,dummy.matrix);inst.setColorAt(i,new THREE.Color().setRGB(.92+rand()*.08,.9+rand()*.1,.86+rand()*.12));});
    }
    this.updateRegionLabels(seed);
  }
  updateRegionLabels(seed){
    for(const child of this.regionGroup.children){child.material?.map?.dispose();child.material?.dispose();}this.regionGroup.clear();
    for(const region of reefRegions(seed)){
      const canvas=document.createElement('canvas');canvas.width=512;canvas.height=100;const ctx=canvas.getContext('2d');ctx.fillStyle='rgba(7,35,42,.76)';ctx.beginPath();ctx.roundRect(2,8,508,80,15);ctx.fill();ctx.strokeStyle=region.kind==='bleached_alive'?'#e8d9bc':region.kind==='healthy'?'#a5d4a2':'#c9bda1';ctx.lineWidth=2;ctx.stroke();ctx.fillStyle=ctx.strokeStyle;ctx.font='500 25px sans-serif';ctx.textAlign='center';ctx.fillText(region.name.toUpperCase(),256,41);ctx.font='18px sans-serif';ctx.fillStyle='#abc1b7';ctx.fillText(region.kind==='mixed'?'MIXED TRANSITION':region.kind==='healthy'?'HEALTHY DOMINANT':'BLEACHED / LIVING DOMINANT',256,70);
      const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const material=new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false,opacity:.9}),sprite=new THREE.Sprite(material);sprite.position.set(region.center[0],terrainHeight(...region.center)+1.15,-region.center[1]);sprite.scale.set(2.4,.47,1);this.regionGroup.add(sprite);
    }
    this.regionGroup.visible=!!this.overlays.regions;
  }
  syncHabitat(state) {
    const key=JSON.stringify([state.seed,(state.colonies||[]).filter(c=>c.genet).map(c=>[c.id,c.position,c.radius,c.genet])]);
    if(key!==this.habitatKey){this.habitatKey=key;this.rebuildHabitat(state.colonies||[],state.seed);}
  }
  plateGeometry() {
    const vertices=[],uv=[],indices=[];const rings=10,segments=80;
    for(let r=0;r<=rings;r++)for(let j=0;j<=segments;j++){const a=j/segments*Math.PI*2,v=r/rings,rad=v*(1+.04*Math.sin(a*11)+.025*Math.sin(a*19));vertices.push(Math.cos(a)*rad,.15*v*v+.025*Math.sin(a*9)*v*v,Math.sin(a)*rad);uv.push(j/segments,v);}
    for(let r=0;r<rings;r++)for(let j=0;j<segments;j++){const a=r*(segments+1)+j,b=a+segments+1;indices.push(a,b,a+1,b,b+1,a+1);}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));g.setIndex(indices);g.computeVertexNormals();this.geometries.add(g);return g;
  }
  makeFan(position, rand) {
    const group=new THREE.Group();group.position.copy(position);group.rotation.y=rand()*6;this.scene.add(group);
    const mat=this.mat({color:new THREE.Color().setHSL(.02+rand()*.08,.32,.35),roughness:1});
    const paths=[];
    for(let k=0;k<18;k++){const a=(k/17-.5)*2.5;let previous=new THREE.Vector3(0,0,0);for(let j=1;j<7;j++){const t=j/6,p=new THREE.Vector3(Math.sin(a)*t*.65,t*.95,.04*Math.sin(t*4+a));paths.push(previous.x,previous.y,previous.z,p.x,p.y,p.z);previous=p;}}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(paths,3));this.geometries.add(g);const lineMat=new THREE.LineBasicMaterial({color:mat.color,transparent:true,opacity:.9});this.materials.add(lineMat);group.add(new THREE.LineSegments(g,lineMat));
    const stalk=this.add(new THREE.CylinderGeometry(.012,.023,.55,7),mat,group);stalk.position.y=.275;
    this.fans.push({group,phase:rand()*6});
  }
  buildParticles(rand) {
    const pts=[],colors=[];for(let i=0;i<1300;i++){pts.push((rand()-.5)*35,rand()*8,(rand()-.5)*35);colors.push(.56+rand()*.25,.8,.78);}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pts,3));g.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));this.geometries.add(g);
    const mat=new THREE.PointsMaterial({size:.018,vertexColors:true,transparent:true,opacity:.42,depthWrite:false,blending:THREE.AdditiveBlending});this.materials.add(mat);this.particles=new THREE.Points(g,mat);this.scene.add(this.particles);
  }
  makeAnimal(type) {
    const g=new THREE.Group(),olive=this.mat({color:0x77785a,roughness:.9}),dark=this.mat({color:0x1c302b,roughness:.6}),sand=this.mat({color:0xa78a63,roughness:.85});
    const ellipsoid=(scale,pos,mat=olive)=>{const m=this.add(new THREE.SphereGeometry(1,14,10),mat,g);m.scale.set(...scale);m.position.set(...pos);return m;};
    g.userData.limbs=[];
    if(type==='crab'){
      ellipsoid([.11,.045,.085],[0,.055,0],sand);ellipsoid([.085,.026,.07],[0,.025,0],dark);
      for(const sign of [-1,1])for(let i=0;i<4;i++){
        const leg=new THREE.Group();leg.position.set(sign*.075,.04,(i-1.5)*.038);g.add(leg);
        const a=new THREE.Vector3(),b=new THREE.Vector3(sign*.075,.015,(i-1.5)*.022),c=new THREE.Vector3(sign*.13,-.037,(i-1.5)*.04);
        for(const [from,to]of [[a,b],[b,c]]){const m=this.add(new THREE.CylinderGeometry(.005,.008,1,6),sand,leg);this.segment(m,from,to);}g.userData.limbs.push(leg);
      }
      for(const sign of [-1,1]){ellipsoid([.015,.015,.015],[sign*.045,.095,-.065],dark);const claw=ellipsoid([.042,.024,.065],[sign*.12,.07,-.12],sand);claw.rotation.y=sign*.45;ellipsoid([.018,.015,.05],[sign*.15,.07,-.16],sand);}
    }else if(type==='turtle'){
      ellipsoid([.24,.1,.17],[0,.11,0],olive);ellipsoid([.21,.035,.15],[0,.045,0],sand);ellipsoid([.085,.055,.065],[.27,.07,0],olive);
      for(const sign of [-1,1])for(const front of [-1,1]){const limb=ellipsoid([front===1?.17:.09,.018,.055],[front*.15,.045,sign*.21],olive);limb.rotation.y=sign*front*.55;g.userData.limbs.push(limb);}
      for(const sign of [-1,1])ellipsoid([.009,.009,.009],[.31,.09,sign*.045],dark);
      for(let i=0;i<7;i++){const scute=ellipsoid([.06,.006,.052],[(i%3-1)*.11,.205-Math.abs(i%3-1)*.025,(Math.floor(i/3)-1)*.09],sand);scute.material=olive;}
    }else{
      const bodyMat=this.mat({color:0xa9b1a3,roughness:.5,metalness:.12});
      ellipsoid([.12,.05,.027],[0,0,0],bodyMat);
      const triangle=(points,color)=>{const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(points,3));geo.computeVertexNormals();return this.add(geo,this.mat({color,side:THREE.DoubleSide,roughness:.8}),g);};
      const tail=triangle([-.095,0,0,-.18,.065,0,-.17,-.055,0],0x919f7e);g.userData.tail=tail;
      triangle([-.06,.035,0,.055,.035,0,-.025,.085,0],0xc4b981);triangle([.005,-.015,0,-.055,-.065,.045,-.045,-.02,0],0xb4c0a6);
      for(const sign of [-1,1])ellipsoid([.009,.009,.004],[.083,.016,sign*.022],dark);
    }
    return g;
  }
  syncWildlife(state) {
    const ids=new Set();for(const animal of state.wildlife||[]){
      ids.add(animal.id);let g=this.wildlife.get(animal.id);if(!g){g=this.makeAnimal(animal.type);this.scene.add(g);this.wildlife.set(animal.id,g);}g.position.copy(vec(animal.position));const v=animal.velocity||[1,0,0],speed=Math.hypot(...v),heading=Math.hypot(v[0],v[1])>.0001?Math.atan2(v[1],v[0]):(g.userData.heading||0);g.userData.heading=heading;
      if(animal.type==='crab'){
        const n=vec(terrainNormal(animal.position[0],animal.position[1]));g.quaternion.setFromUnitVectors(UP,n);g.rotateY(heading);g.position.y-=.065;
        const gait=(state.time||0)*(4+Math.min(speed,1)*12)+hash(animal.id);g.userData.limbs.forEach((limb,i)=>{limb.rotation.z=Math.sin(gait+i*1.7)*.1;limb.position.y=.04+Math.max(0,Math.sin(gait+i*1.7))*.012;});
      }else{
        g.rotation.set(0,heading,0);g.rotateZ(speed>.001?Math.asin(THREE.MathUtils.clamp(v[2]/speed,-.5,.5)):0);
        const t=(state.time||0)*(4+Math.min(speed,1)*5)+hash(animal.id);if(g.userData.tail)g.userData.tail.rotation.y=Math.sin(t)*.3;g.userData.limbs.forEach((limb,i)=>limb.rotation.z=Math.sin(t+i*1.7)*.12);
      }
    }
    for(const[id,g]of this.wildlife)if(!ids.has(id)){this.scene.remove(g);this.wildlife.delete(id);}
  }
  buildRobot() {
    this.robot=new THREE.Group();this.scene.add(this.robot);this.robot.name='RESTORE-02';
    const white=this.mat({color:0xe4e5d7,roughness:.45,metalness:.16},false),dark=this.mat({color:0x142b32,roughness:.55,metalness:.55},false),teal=this.mat({color:0x35b6ad,roughness:.42,metalness:.3},false),metal=this.mat({color:0x9faeac,roughness:.3,metalness:.7},false),glass=this.mat({color:0x092332,roughness:.14,metalness:.7},false);
    const box=(size,p,mat,parent=this.robot)=>{const m=this.add(new THREE.BoxGeometry(...size),mat,parent);m.position.set(...p);return m;};
    box([.65,.27,.92],[0,0,0],white);box([.52,.1,.7],[0,.18,0],teal);box([.4,.08,.44],[0,.25,-.08],dark);
    for(const x of [-.42,.42]){
      const skid=this.add(new THREE.CylinderGeometry(.027,.027,1.15,10),dark,this.robot);skid.rotation.x=Math.PI/2;skid.position.set(x,-.35,0);
      for(const z of [-.35,.35]){box([.04,.2,.04],[x,-.24,z],metal);const cage=this.add(new THREE.CylinderGeometry(.14,.14,.18,20,1,true),dark,this.robot);cage.rotation.z=Math.PI/2;cage.position.set(x,0,z);const prop=this.add(new THREE.BoxGeometry(.02,.19,.045),metal,cage);prop.rotation.y=.5;}
    }
    for(const x of [-.24,.24]){const lamp=this.add(new THREE.CylinderGeometry(.055,.06,.065,16),dark,this.robot);lamp.rotation.x=Math.PI/2;lamp.position.set(x,-.04,-.49);const lens=this.add(new THREE.CircleGeometry(.043,16),new THREE.MeshBasicMaterial({color:0xd1fbff}),lamp);lens.rotation.x=-Math.PI/2;lens.position.y=.035;}
    const eye=this.add(new THREE.SphereGeometry(.075,16,12),glass,this.robot);eye.position.set(0,.06,-.49);
    const texCanvas=document.createElement('canvas');texCanvas.width=512;texCanvas.height=128;const ctx=texCanvas.getContext('2d');ctx.fillStyle='#e4e5d7';ctx.fillRect(0,0,512,128);ctx.fillStyle='#12343e';ctx.font='bold 53px sans-serif';ctx.font='bold 42px sans-serif';ctx.fillText('REEF RESCUE',24,76);ctx.font='18px monospace';ctx.fillText('R E S T O R E – 0 2',280,102);const tex=new THREE.CanvasTexture(texCanvas);tex.colorSpace=THREE.SRGBColorSpace;this.textures.set('robot-label',tex);const label=this.add(new THREE.PlaneGeometry(.59,.148),new THREE.MeshBasicMaterial({map:tex}),this.robot);label.position.set(0,.041,.466);
    this.arm=new THREE.Group();this.scene.add(this.arm);this.armMat=metal;
    this.armA=this.add(new THREE.CylinderGeometry(.038,.045,1,12),dark,this.arm);this.armB=this.add(new THREE.CylinderGeometry(.025,.03,1,12),metal,this.arm);
    this.shoulder=this.add(new THREE.SphereGeometry(.07,14,10),teal,this.arm);this.elbow=this.add(new THREE.SphereGeometry(.06,14,10),dark,this.arm);
    this.tool=new THREE.Group();this.scene.add(this.tool);
    // Parallel-jaw carriage sits above the grasp centre; pads meet the cutting stem.
    box([.17,.045,.075],[0,.17,0],dark,this.tool);box([.19,.014,.018],[0,.135,.025],metal,this.tool);
    const actuator=this.add(new THREE.CylinderGeometry(.024,.024,.11,16),metal,this.tool);actuator.rotation.z=Math.PI/2;actuator.position.set(0,.2,0);
    this.jaws=[];this.fingerLinks=[];
    for(const sign of [-1,1]){
      const carriage=new THREE.Group();carriage.position.x=sign*.07;this.tool.add(carriage);
      box([.022,.135,.04],[0,.075,0],metal,carriage);box([.025,.04,.05],[-sign*.007,.018,0],dark,carriage);
      const pivot=this.add(new THREE.CylinderGeometry(.015,.015,.055,12),teal,carriage);pivot.rotation.x=Math.PI/2;pivot.position.set(0,.14,0);
      const linkage=this.add(new THREE.CylinderGeometry(.008,.008,.07,8),metal,carriage);linkage.position.set(-sign*.025,.185,0);linkage.rotation.z=sign*.55;this.fingerLinks.push(linkage);this.jaws.push(carriage);
    }
    // Cutter blade approaches beside the jaws; its stroke is phase-driven below.
    this.cutter=box([.075,.005,.035],[.035,-.018,.02],metal,this.tool);
    const cableCurve=new THREE.CatmullRomCurve3([new THREE.Vector3(-.05,.18,.04),new THREE.Vector3(-.08,.3,.08),new THREE.Vector3(0,.34,.08),new THREE.Vector3(.04,.18,.04)]);
    this.add(new THREE.TubeGeometry(cableCurve,20,.008,6,false),dark,this.tool);
    this.toolCamera=new THREE.PerspectiveCamera(58,4/3,.015,35);
    const beamMat=new THREE.MeshBasicMaterial({color:0x976bff,transparent:true,opacity:.035,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending});this.materials.add(beamMat);this.uvBeam=this.add(new THREE.ConeGeometry(1,1,24,1,true),beamMat);this.uvBeam.castShadow=false;this.uvBeam.receiveShadow=false;this.uvBeam.visible=false;
    this.lamp=new THREE.SpotLight(0xc0ecff,3,4,Math.PI/4,.65,1.5);this.lamp.castShadow=false;this.scene.add(this.lamp);this.scene.add(this.lamp.target);
    this.umbilicalMat=new THREE.LineBasicMaterial({color:0xacc2aa,transparent:true,opacity:.35});this.materials.add(this.umbilicalMat);
  }
  buildMarkers() {
    const make=(color)=>{const mat=new THREE.MeshBasicMaterial({color,transparent:true,opacity:.85,side:THREE.DoubleSide,depthWrite:false});this.materials.add(mat);const m=this.add(new THREE.RingGeometry(.97,1,80),mat);m.rotation.x=-Math.PI/2;m.castShadow=false;m.visible=false;return m;};
    this.selection=make(0xd6f6e0);this.targetMarker=make(0xffd08a);this.donorMarker=make(0x58e1c4);
  }
  syncColonies(state) {
    const ids=new Set();
    for(const c of state.colonies || []){
      ids.add(c.id);let entry=this.colonies.get(c.id);
      const key=`${c.health}:${c.morphology}`;
      if(!entry || entry.key!==key){
        if(entry)this.scene.remove(entry.mesh);
        const colorIndex=Math.abs(hash(c.id))%this.coralMats.length, mat=c.health==='bleached_alive'?this.bleachedMat:c.health==='dead'?this.deadMat:this.coralMats[colorIndex];
        const geo=this.scan;
        const mesh=this.add(geo,mat);mesh.userData.colonyId=c.id;mesh.rotation.y=(hash(c.id)%360)*Math.PI/180;
        entry={mesh,key};this.colonies.set(c.id,entry);
      }
      entry.mesh.position.copy(vec(c.position));const radius=Number(c.radius)||.55,height=Number(c.height)||.6;
      const scale=Math.min(radius,height/1.0776135);entry.mesh.scale.setScalar(scale);
      // Preserve original UV seams on the two close-up work specimens.
      entry.mesh.geometry=(c.id===state.targetId||c.id===state.donorId||c.id===this.selected)?this.heroScan:this.scan;
    }
    for(const [id,e] of this.colonies)if(!ids.has(id)){this.scene.remove(e.mesh);this.colonies.delete(id);}
    this.pickables=[...this.colonies.values()].map(e=>e.mesh);
    for(const [id,marker]of[[this.selected,this.selection],[state.targetId,this.targetMarker],[state.donorId,this.donorMarker]]){
      const c=(state.colonies||[]).find(c=>c.id===id);marker.visible=!!c;if(c){marker.position.copy(vec(c.position));marker.position.y+=.018;marker.scale.setScalar((c.radius||.55)*1.1);}
    }
  }
  syncObstacles(state) {
    const ids=new Set();for(const o of state.obstacles||[]){ids.add(o.id);let mesh=this.obstacles.get(o.id);if(!mesh){mesh=this.add(this.rockGeo,this.rockMat);this.obstacles.set(o.id,mesh);}mesh.position.copy(vec(o.position));mesh.position.y+=(o.radius||.4)*.75;mesh.scale.set(o.radius||.4,(o.radius||.4)*.75,o.radius||.4);}
    for(const[id,m]of this.obstacles)if(!ids.has(id)){this.scene.remove(m);this.obstacles.delete(id);}
  }
  syncFragments(state) {
    const ids=new Set();
    for(const f of state.fragments||[]){ids.add(f.id);let group=this.fragments.get(f.id);if(!group){group=new THREE.Group();const mat=this.mat({color:0xb7a7a0,normalMap:this.branchNormal,roughness:.95});const stem=this.add(new THREE.CylinderGeometry(.014,.025,.16,9),mat,group);stem.position.y=.08;for(let i=0;i<4;i++){const b=this.add(new THREE.CylinderGeometry(.006,.012,.08,7),mat,group);b.position.set((i%2?1:-1)*.025,.07+i*.025,0);b.rotation.z=(i%2?1:-1)*.6;}this.scene.add(group);this.fragments.set(f.id,group);}group.position.copy(vec(f.position));group.visible=!['consumed','lost','quarantined','rejected'].includes(f.state);group.rotation.z=f.state==='dropped'?Math.sin(state.time||0)*.15:0;}
    for(const[id,g]of this.fragments)if(!ids.has(id)){this.scene.remove(g);g.traverse(o=>{if(o.isMesh)o.geometry.dispose();});this.fragments.delete(id);}
  }
  segment(mesh,a,b) { const d=new THREE.Vector3().subVectors(b,a);mesh.position.copy(a).add(b).multiplyScalar(.5);mesh.scale.y=d.length();mesh.quaternion.setFromUnitVectors(UP,d.normalize()); }
  update(state, dt = 1/60) {
    if(!this.ready||this.disposed)return;
    this.snapshot=state;const t=Number(state.time)||0;this.timeUniform.value=t;
    this.syncHabitat(state);this.syncColonies(state);this.syncObstacles(state);this.syncFragments(state);this.syncWildlife(state);this.syncOverlays(state);this.syncCurrents(state);this.syncSoftTissue(state);
    const robot=state.robot||{},p=vec(robot.position),gripper=vec(robot.gripper||robot.position);
    const yaw=Number(robot.yaw)||0,forward=new THREE.Vector3(Math.cos(yaw),0,-Math.sin(yaw)),right=new THREE.Vector3(Math.sin(yaw),0,Math.cos(yaw));
    this.robot.position.copy(p);this.robot.rotation.y=yaw-Math.PI/2;
    const shoulder=p.clone().addScaledVector(forward,.24).add(new THREE.Vector3(0,-.15,0)),elbow=shoulder.clone().lerp(gripper,.48);elbow.y=Math.max(gripper.y+.24,shoulder.y-.25);
    this.shoulder.position.copy(shoulder);this.elbow.position.copy(elbow);this.segment(this.armA,shoulder,elbow);this.segment(this.armB,elbow,gripper);this.tool.position.copy(gripper);this.tool.rotation.y=this.robot.rotation.y;
    const open=Number.isFinite(robot.gripperOpen)?robot.gripperOpen:1;this.jaws[0].position.x=-.028-open*.045;this.jaws[1].position.x=.028+open*.045;this.fingerLinks.forEach((link,i)=>link.rotation.z=(i?1:-1)*(.2+open*.45));this.cutter.position.x=String(state.phase).includes('cut')?.005:.06;
    this.updateInspectionLight(state,p,gripper,forward);
    const visibility=state.water?.visibility??8;this.scene.fog.density=THREE.MathUtils.clamp(.34/visibility,.022,.24);
    const current=Number(state.water?.current)||0;for(const f of this.fans){f.group.rotation.z=Math.sin(t*.65+f.phase)*(.025+current*.12);}
    if(this.particles){const flow=vec(state.water?.currentVector||[current,0,0]),elapsed=Math.max(0,Math.min(1,t-(this.lastWaterTime??t))),positions=this.particles.geometry.attributes.position;for(let i=0;i<positions.count;i++){const px=positions.getX(i),py=positions.getY(i),pz=positions.getZ(i);let vx=flow.x,vy=flow.y,vz=flow.z,best=Infinity;for(const sample of state.water?.currentSamples||[]){const distance=(sample.position[0]-px)**2+(sample.position[1]+pz)**2;if(distance<best){best=distance;vx=sample.vector[0];vy=sample.vector[2];vz=-sample.vector[1];}}let x=px+vx*elapsed,y=py+vy*elapsed,z=pz+vz*elapsed;x=((x+17.5)%35+35)%35-17.5;z=((z+17.5)%35+35)%35-17.5;y=((y%8)+8)%8;positions.setXYZ(i,x,y,z);}positions.needsUpdate=true;this.lastWaterTime=t;}
    const smoothing=1-Math.exp(-Math.min(dt,.1)*5),desired=new THREE.Vector3(),aim=this.target.clone();
    if(this.cameraMode==='pilot'){desired.copy(p).addScaledVector(forward,.7).add(new THREE.Vector3(0,.08,0));aim.copy(desired).addScaledVector(forward,4).add(new THREE.Vector3(0,-.45,0));}
    else if(this.cameraMode==='follow'){aim.copy(p).lerp(gripper,.2);desired.copy(p).addScaledVector(forward,-3.2).addScaledVector(right,2.0).add(new THREE.Vector3(0,1.6,0));}
    else if(this.cameraMode==='wrist'){desired.copy(gripper).addScaledVector(right,.38).addScaledVector(forward,-.46).add(new THREE.Vector3(0,.3,0));aim.copy(gripper).add(new THREE.Vector3(0,.015,0));}
    else if(this.cameraMode==='top'){aim.set(0,1.3,0);const fit=7.2/(Math.tan(THREE.MathUtils.degToRad(this.camera.fov/2))*Math.min(1,this.camera.aspect));desired.set(0,Math.max(18,3.5+fit),.001);}
    else{desired.set(Math.sin(this.azimuth)*Math.cos(this.elevation)*this.distance,Math.sin(this.elevation)*this.distance,Math.cos(this.azimuth)*Math.cos(this.elevation)*this.distance).add(this.target);}
    if(!this.cameraInitialized||this.cameraMode==='pilot'){this.camera.position.copy(desired);this.lookAt=aim.clone();this.cameraInitialized=true;}else{this.camera.position.lerp(desired,smoothing);this.lookAt.lerp(aim,smoothing);}
    this.camera.up.set(0,this.cameraMode==='top'?0:1,this.cameraMode==='top'?-1:0);this.camera.lookAt(this.lookAt);this.toolCamera.position.copy(gripper).addScaledVector(right,.38).addScaledVector(forward,-.46).add(new THREE.Vector3(0,.3,0));this.toolCamera.lookAt(gripper.clone().add(new THREE.Vector3(0,.015,0)));this.renderer.render(this.scene,this.camera);
  }
  updateInspectionLight(state,body,gripper,forward) {
    const inspecting=['inspect_recipient','inspect_donor'].includes(state.phase),id=inspecting?(state.perception?.targetId||(state.phase==='inspect_recipient'?state.targetId:state.donorId)):null;
    const colony=(state.colonies||[]).find(c=>c.id===id),entry=this.colonies.get(id),live=colony&&colony.health!=='dead';
    if(this.uvActive&&(!live||this.uvActive.id!==id||this.uvActive.mesh!==entry?.mesh)){this.uvActive.mesh.material=this.uvActive.base;this.uvActive.material.dispose();this.uvActive=null;}
    this.uvBeam.visible=!!(inspecting&&live);
    if(inspecting&&live&&entry){
      const target=vec(coralContactPoint(colony)),origin=body.clone().addScaledVector(forward,.27).add(new THREE.Vector3(0,-.11,0)),distance=origin.distanceTo(target);
      this.lamp.position.copy(origin);this.lamp.target.position.copy(target);this.lamp.color.set(0x9667ff);this.lamp.angle=Math.PI*50/180;this.lamp.penumbra=.48;this.lamp.intensity=12;this.lamp.distance=3.5;
      this.uvBeam.visible=distance<=3.5;this.uvBeam.position.copy(origin).add(target).multiplyScalar(.5);this.uvBeam.scale.set(Math.min(.8,distance*.7),distance,Math.min(.8,distance*.7));this.uvBeam.quaternion.setFromUnitVectors(UP,origin.clone().sub(target).normalize());
      if(!this.uvActive){const base=entry.mesh.material,material=base.clone();material.emissiveMap=base.map;material.emissive.set(hash(colony.genet||'G1')%2?0x83bd91:0xc78d9f);entry.mesh.material=material;this.uvActive={id,mesh:entry.mesh,base,material};}
      // Scenario-marker fluorescence only, gated by the engine's measured synthetic exposure.
      const exposure=Number(state.perception?.exposure??state.phaseProgress??0),visible=distance<=3.5&&state.water?.visibility>1;
      this.uvActive.material.emissiveIntensity=visible?.24*Math.min(1,Math.max(0,exposure)):0;
    }else{this.lamp.position.copy(gripper).add(new THREE.Vector3(0,.12,0));this.lamp.target.position.copy(gripper).add(new THREE.Vector3(0,-.5,-.1));this.lamp.color.set(0xdbf5ff);this.lamp.angle=Math.PI/4;this.lamp.penumbra=.65;this.lamp.intensity=2;this.lamp.distance=4;}
  }
  syncCurrents(state){
    if(!this.currentLines){const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(64*18),3));const material=new THREE.LineBasicMaterial({color:0xc5fff0,transparent:true,opacity:.82,depthWrite:false,depthTest:false,fog:false,toneMapped:false});this.currentLines=new THREE.LineSegments(geometry,material);this.currentLines.renderOrder=500;this.currentGroup.add(this.currentLines);}
    const samples=(state.water?.currentSamples||[]).slice(0,64),attribute=this.currentLines.geometry.attributes.position;let count=0;
    for(const sample of samples){const direction=vec(sample.vector),speed=direction.length();if(speed<.003)continue;direction.normalize();const origin=vec(sample.position),length=Math.min(1.6,speed*5),drift=((state.time||0)*speed)%1;origin.addScaledVector(direction,(drift-.5)*.35);const end=origin.clone().addScaledVector(direction,length),side=new THREE.Vector3().crossVectors(direction,UP).normalize().multiplyScalar(Math.min(.11,length*.22));
      for(const p of [origin,end,end,end.clone().addScaledVector(direction,-Math.min(.18,length*.3)).add(side),end,end.clone().addScaledVector(direction,-Math.min(.18,length*.3)).sub(side)])attribute.setXYZ(count++,p.x,p.y,p.z);
    }
    attribute.needsUpdate=true;this.currentLines.geometry.setDrawRange(0,count);this.currentGroup.visible=!!this.overlays.currents;this.regionGroup.visible=!!this.overlays.regions;
  }
  syncSoftTissue(state){
    if(!this.tissue){const geometry=new THREE.CylinderGeometry(.0007,.001,.005,5),material=this.mat({color:0xc9b8a1,roughness:1});this.tissue=new THREE.InstancedMesh(geometry,material,240);this.tissue.castShadow=false;this.tissue.receiveShadow=false;this.scene.add(this.tissue);}
    const targets=[state.targetId,state.donorId].filter(Boolean),positions=this.heroScan.attributes.position,normals=this.heroScan.attributes.normal,dummy=new THREE.Object3D(),flow=vec(state.water?.currentVector||[state.water?.current||0,0,0]);let count=0;
    for(const id of targets){const entry=this.colonies.get(id),colony=(state.colonies||[]).find(c=>c.id===id);if(!entry||!colony||colony.health==='dead')continue;entry.mesh.updateWorldMatrix(true,false);const normalMatrix=new THREE.Matrix3().getNormalMatrix(entry.mesh.matrixWorld);
      for(let j=0;j<20;j++){const index=(Math.abs(hash(id))+j*3931)%positions.count,base=new THREE.Vector3().fromBufferAttribute(positions,index).applyMatrix4(entry.mesh.matrixWorld),normal=new THREE.Vector3().fromBufferAttribute(normals,index).applyMatrix3(normalMatrix).normalize(),tangent=new THREE.Vector3().crossVectors(normal,Math.abs(normal.y)>.9?new THREE.Vector3(1,0,0):UP).normalize(),bitangent=new THREE.Vector3().crossVectors(normal,tangent),bend=flow.clone().addScaledVector(normal,-flow.dot(normal)).multiplyScalar(.004*Math.sin((state.time||0)*1.9+j));if(bend.length()>.002)bend.setLength(.002);
        for(let k=0;k<6;k++){const angle=k/6*Math.PI*2,start=base.clone().addScaledVector(normal,.001),end=start.clone().addScaledVector(normal,.005).addScaledVector(tangent,Math.cos(angle)*.002).addScaledVector(bitangent,Math.sin(angle)*.002).add(bend),direction=end.clone().sub(start);dummy.position.copy(start).add(end).multiplyScalar(.5);dummy.quaternion.setFromUnitVectors(UP,direction.clone().normalize());dummy.scale.set(1,direction.length()/.005,1);dummy.updateMatrix();this.tissue.setMatrixAt(count++,dummy.matrix);}
      }
    }
    this.tissue.count=count;this.tissue.instanceMatrix.needsUpdate=true;
  }
  setOverlays(options={}) {this.overlays={...this.overlays,...options};this.routeGroup.visible=!!this.overlays.routes;this.sonarGroup.visible=!!this.overlays.sonar;this.currentGroup.visible=!!this.overlays.currents;this.regionGroup.visible=!!this.overlays.regions;}
  syncOverlays(state) {
    const routes=state.route?.alternatives||[];const key=JSON.stringify([routes,state.route?.mode]);
    if(key!==this.routeKey){this.routeKey=key;while(this.routeGroup.children.length){const child=this.routeGroup.children[0];this.routeGroup.remove(child);child.geometry?.dispose();child.material?.dispose();}
      for(const route of routes){const points=(route.points||[]).map(vec);if(points.length<2)continue;const selected=route.id===state.route?.mode,geo=new THREE.BufferGeometry().setFromPoints(points),mat=new THREE.LineDashedMaterial({color:selected?0x86e4c3:0xe7c48f,transparent:true,opacity:selected?.7:.3,dashSize:selected?.14:.07,gapSize:.08,depthTest:true});const line=new THREE.Line(geo,mat);line.computeLineDistances();this.routeGroup.add(line);}
    }
    this.routeGroup.visible=!!this.overlays.routes;this.sonarGroup.visible=!!this.overlays.sonar;
    if(!this.sonarRing){const mat=new THREE.MeshBasicMaterial({color:0x82dce3,transparent:true,opacity:.2,side:THREE.DoubleSide,depthWrite:false});this.sonarRing=this.add(new THREE.RingGeometry(.985,1,80),mat,this.sonarGroup);this.sonarRing.rotation.x=-Math.PI/2;this.sonarRing.castShadow=false;}
    this.sonarRing.position.copy(vec(state.robot?.position));const phase=((state.time||0)%3)/3;this.sonarRing.scale.setScalar(.1+phase*(state.sonar?.range||4));this.sonarRing.material.opacity=(1-phase)*.35;
    if(!this.sonarContacts){const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(256*3),3));geo.setAttribute('color',new THREE.Float32BufferAttribute(new Float32Array(256*3),3));const mat=new THREE.PointsMaterial({vertexColors:true,size:.065,transparent:true,opacity:.8,depthWrite:false});this.sonarContacts=new THREE.Points(geo,mat);this.sonarGroup.add(this.sonarContacts);}
    const contacts=(state.sonar?.contacts||[]).slice(0,256),positions=this.sonarContacts.geometry.attributes.position;contacts.forEach((contact,i)=>{const p=vec(contact.position);positions.setXYZ(i,p.x,p.y,p.z);const color=new THREE.Color(['fish','crab','turtle','wildlife'].includes(contact.type)?0xecc681:contact.type==='coral'?0x75d1b3:contact.type==='terrain'?0xa4ab9c:0xc8d8e5);this.sonarContacts.geometry.attributes.color.setXYZ(i,color.r,color.g,color.b);});this.sonarContacts.geometry.attributes.color.needsUpdate=true;positions.needsUpdate=true;this.sonarContacts.geometry.setDrawRange(0,contacts.length);
  }
  captureObservation() {
    if(!this.ready||!this.snapshot)throw new Error('Robot camera is not ready');
    const target=new THREE.WebGLRenderTarget(768,576,{depthBuffer:true});target.texture.colorSpace=THREE.SRGBColorSpace;
    const previous=this.renderer.getRenderTarget(),routeVisible=this.routeGroup.visible,sonarVisible=this.sonarGroup.visible,currentVisible=this.currentGroup.visible,regionVisible=this.regionGroup.visible;
    try{this.routeGroup.visible=false;this.sonarGroup.visible=false;this.currentGroup.visible=false;this.regionGroup.visible=false;this.renderer.setRenderTarget(target);this.renderer.render(this.scene,this.toolCamera);const pixels=new Uint8Array(768*576*4);this.renderer.readRenderTargetPixels(target,0,0,768,576,pixels);const canvas=document.createElement('canvas');canvas.width=768;canvas.height=576;const ctx=canvas.getContext('2d'),image=ctx.createImageData(768,576);for(let y=0;y<576;y++)image.data.set(pixels.subarray(y*768*4,(y+1)*768*4),(575-y)*768*4);ctx.putImageData(image,0,0);return{mimeType:'image/jpeg',data:canvas.toDataURL('image/jpeg',.83).split(',')[1],camera:'tool',time:this.snapshot.time};}
    finally{this.renderer.setRenderTarget(previous);this.routeGroup.visible=routeVisible;this.sonarGroup.visible=sonarVisible;this.currentGroup.visible=currentVisible;this.regionGroup.visible=regionVisible;target.dispose();}
  }
  setCamera(mode) { if(!['orbit','follow','top','wrist','pilot'].includes(mode))throw new Error('Unknown camera mode');this.cameraMode=mode; }
  setQuality(quality) {this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,quality==='high'?2:1));this.renderer.shadowMap.enabled=quality==='high';this.resize();}
  setSelected(id) {this.selected=id;}
  capture() {return this.canvas.toDataURL('image/png');}
  dispose() {this.disposed=true;this.resizeObserver.disconnect();for(const[type,fn,opts]of this.handlers)this.canvas.removeEventListener(type,fn,opts);this.scene.traverse(o=>{if(o.isMesh||o.isLine||o.isPoints){o.geometry?.dispose();if(Array.isArray(o.material))o.material.forEach(m=>m.dispose());else o.material?.dispose();}});for(const t of this.textures.values())t.dispose();for(const g of this.geometries)g.dispose();for(const m of this.materials)m.dispose();this.renderer.dispose();}
}
