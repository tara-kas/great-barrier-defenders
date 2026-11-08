import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  CoralCluster,
  CoralStatus,
  computeOptimalClumpHubAndPath,
} from '../domain/reefEngine';
import { Eye, Compass, Layers, Focus, Anchor } from 'lucide-react';

interface SpatialView3DProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  holdingFragment?: boolean;
  clumpSpreadProgress?: number;
}

const STATUS_HEX: Record<CoralStatus, number> = {
  Living: 0x38d996,
  Bleached: 0xf5a623,
  Dead: 0xe5534b,
  Placed: 0x38bdf8,
};

/**
 * 13 Reef Bommie & Spur Formations baked seamlessly into the continuous seabed heightmap
 * and populated with dense, multi-tiered Acropora coral thickets.
 */
interface ReefBommieSpec {
  id: string;
  name: string;
  cx: number;
  cz: number;
  radius: number;
  height: number;
  dominantType: 'staghorn' | 'corymbose' | 'tabulate' | 'boulder';
  healthBias: 'healthy' | 'mixed' | 'stressed' | 'restored';
}

const REEF_BOMMIE_FORMATIONS: ReefBommieSpec[] = [
  { id: 'BM-01', name: 'West Spur Acropora Thicket (Clump Alpha)', cx: -35.8, cz: 25.0, radius: 5.2, height: 1.45, dominantType: 'staghorn', healthBias: 'restored' },
  { id: 'BM-02', name: 'SW Staghorn & Table Gardens', cx: -32.2, cz: 19.8, radius: 5.5, height: 1.55, dominantType: 'staghorn', healthBias: 'healthy' },
  { id: 'BM-03', name: 'NW Sunlit Acropora Crest', cx: -21.5, cz: -12.0, radius: 6.2, height: 1.85, dominantType: 'staghorn', healthBias: 'healthy' },
  { id: 'BM-04', name: 'East Crest Staghorn Bank', cx: -11.5, cz: 15.5, radius: 5.8, height: 1.6, dominantType: 'staghorn', healthBias: 'mixed' },
  { id: 'BM-05', name: 'Central Reef Staghorn Forest', cx: -6.5, cz: -2.0, radius: 6.8, height: 1.95, dominantType: 'staghorn', healthBias: 'healthy' },
  { id: 'BM-06', name: 'North Pinnacle Acropora Garden', cx: 3.5, cz: -17.0, radius: 6.4, height: 2.1, dominantType: 'staghorn', healthBias: 'healthy' },
  { id: 'BM-07', name: 'South Lagoon Staghorn Meadow', cx: 2.5, cz: 23.0, radius: 5.6, height: 1.35, dominantType: 'staghorn', healthBias: 'healthy' },
  { id: 'BM-08', name: 'Mid-Channel Patch Bommie', cx: 14.0, cz: 14.0, radius: 6.0, height: 1.5, dominantType: 'corymbose', healthBias: 'mixed' },
  { id: 'BM-09', name: 'NE Spur Table & Staghorn Crest', cx: 21.0, cz: -19.5, radius: 6.5, height: 2.15, dominantType: 'tabulate', healthBias: 'healthy' },
  { id: 'BM-10', name: 'SE Outer Reef Wall & Terrace', cx: 30.5, cz: 4.0, radius: 7.2, height: 1.85, dominantType: 'staghorn', healthBias: 'mixed' },
  { id: 'BM-11', name: 'West Canyon Rim Outcrop', cx: -27.5, cz: 4.5, radius: 5.2, height: 1.65, dominantType: 'corymbose', healthBias: 'healthy' },
  { id: 'BM-12', name: 'Central Ridge Table Terrace', cx: 7.5, cz: 2.0, radius: 5.5, height: 1.7, dominantType: 'tabulate', healthBias: 'healthy' },
  { id: 'BM-13', name: 'Far East Deep Drop-Off Spur', cx: 33.0, cz: -12.0, radius: 5.8, height: 1.75, dominantType: 'staghorn', healthBias: 'healthy' },
];

/**
 * Continuous Seabed & Reef Bommie Heightmap Function
 * Integrates both the macro reef canyon topology AND the 13 raised limestone reef bommies
 * into one continuous, seamless seabed surface so there are zero floating rock polygons.
 */
function getTerrainElevation(wx: number, wz: number): number {
  const ridge1 = Math.sin(wx * 0.085 + wz * 0.065) * 1.45;
  const ridge2 = Math.cos(wx * 0.055 - wz * 0.095) * 1.15;
  const canyon = -Math.exp(-((wx + 2) * (wx + 2) + (wz - 4) * (wz - 4)) / 260) * 2.1;
  const eastTerrace = Math.atan((wx - 8) * 0.12) * 1.05;
  const northCrest = Math.exp(-((wz + 18) * (wz + 18)) / 180) * 1.65;
  const microBommie =
    Math.sin(wx * 0.34 + Math.cos(wz * 0.28) * 1.6) *
    Math.cos(wz * 0.31 - Math.sin(wx * 0.25) * 1.4) *
    0.32;

  let bommieLift = 0;
  for (let i = 0; i < REEF_BOMMIE_FORMATIONS.length; i++) {
    const b = REEF_BOMMIE_FORMATIONS[i];
    const dx = wx - b.cx;
    const dz = wz - b.cz;
    const d2 = dx * dx + dz * dz;
    const r2 = b.radius * b.radius;
    if (d2 < r2 * 2.4) {
      const falloff = Math.exp(-d2 / (r2 * 0.68));
      // Organic rocky terrace profile with flat-ish reef top for coral attachment
      const terrace = Math.pow(falloff, 0.72) * b.height;
      const rugosity = (Math.sin(wx * 1.3 + i) * Math.cos(wz * 1.3 - i) * 0.14 + 0.14) * falloff;
      bommieLift = Math.max(bommieLift, terrace + rugosity);
    }
  }

  return ridge1 + ridge2 + canyon + eastTerrace + northCrest + microBommie + bommieLift - 2.3;
}

/** Returns 0..1 indicating how strongly a world coordinate sits on a raised reef bommie vs sandy channel */
function getBommieRockFactor(wx: number, wz: number): number {
  let maxFactor = 0;
  for (let i = 0; i < REEF_BOMMIE_FORMATIONS.length; i++) {
    const b = REEF_BOMMIE_FORMATIONS[i];
    const dx = wx - b.cx;
    const dz = wz - b.cz;
    const d2 = dx * dx + dz * dz;
    const r2 = b.radius * b.radius;
    if (d2 < r2 * 2.0) {
      const f = Math.exp(-d2 / (r2 * 0.75));
      if (f > maxFactor) maxFactor = f;
    }
  }
  return Math.min(1, maxFactor);
}

/**
 * Procedural 512x512 Seabed Color + Bump Texture
 * Combines carbonate sand ripples, crustose coralline limestone texture, and underwater solar caustics.
 */
function createSeabedTextures(): { colorMap: THREE.CanvasTexture; bumpMap: THREE.CanvasTexture } {
  const size = 512;
  const colorCanvas = document.createElement('canvas');
  colorCanvas.width = size;
  colorCanvas.height = size;
  const cCtx = colorCanvas.getContext('2d');

  const bumpCanvas = document.createElement('canvas');
  bumpCanvas.width = size;
  bumpCanvas.height = size;
  const bCtx = bumpCanvas.getContext('2d');

  if (cCtx && bCtx) {
    cCtx.fillStyle = '#183c4e';
    cCtx.fillRect(0, 0, size, size);

    bCtx.fillStyle = '#808080';
    bCtx.fillRect(0, 0, size, size);

    // Sand ripple bands & porous reef rock grain
    for (let y = 0; y < size; y += 3) {
      const wave = Math.sin(y * 0.11) * 14 + Math.cos(y * 0.05) * 9;
      cCtx.fillStyle = y % 6 === 0 ? 'rgba(42, 98, 120, 0.22)' : 'rgba(12, 34, 48, 0.20)';
      cCtx.fillRect(0, y, size, 2);

      const bVal = Math.floor(128 + wave * 1.9);
      bCtx.fillStyle = `rgb(${bVal},${bVal},${bVal})`;
      bCtx.fillRect(0, y, size, 2);
    }

    // Coralline limestone patches & organic reef sediment mottling
    let seed = 1337;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return (seed & 0xfffffff) / 0xfffffff;
    };

    for (let i = 0; i < 650; i++) {
      const x = rand() * size;
      const y = rand() * size;
      const r = 4 + rand() * 22;
      const isCoralline = rand() > 0.68;
      cCtx.fillStyle = isCoralline
        ? `rgba(130, 74, 112, ${0.09 + rand() * 0.11})`
        : `rgba(56, 126, 146, ${0.08 + rand() * 0.12})`;
      cCtx.beginPath();
      cCtx.arc(x, y, r, 0, Math.PI * 2);
      cCtx.fill();

      const bumpShade = Math.floor(105 + rand() * 50);
      bCtx.fillStyle = `rgba(${bumpShade},${bumpShade},${bumpShade},0.35)`;
      bCtx.beginPath();
      bCtx.arc(x, y, r * 0.7, 0, Math.PI * 2);
      bCtx.fill();
    }

    // Subtle sunlit underwater caustic network
    cCtx.strokeStyle = 'rgba(110, 225, 245, 0.12)';
    cCtx.lineWidth = 1.4;
    for (let i = 0; i < 95; i++) {
      const cx = rand() * size;
      const cy = rand() * size;
      const rad = 14 + rand() * 34;
      cCtx.beginPath();
      for (let a = 0; a <= Math.PI * 2; a += 0.4) {
        const rr = rad + Math.sin(a * 3 + i) * 5;
        const px = cx + Math.cos(a) * rr;
        const py = cy + Math.sin(a) * rr;
        if (a === 0) cCtx.moveTo(px, py);
        else cCtx.lineTo(px, py);
      }
      cCtx.closePath();
      cCtx.stroke();
    }
  }

  const colorMap = new THREE.CanvasTexture(colorCanvas);
  colorMap.wrapS = THREE.RepeatWrapping;
  colorMap.wrapT = THREE.RepeatWrapping;
  colorMap.repeat.set(14, 12);
  colorMap.colorSpace = THREE.SRGBColorSpace;

  const bumpMap = new THREE.CanvasTexture(bumpCanvas);
  bumpMap.wrapS = THREE.RepeatWrapping;
  bumpMap.wrapT = THREE.RepeatWrapping;
  bumpMap.repeat.set(18, 16);

  return { colorMap, bumpMap };
}

/**
 * Procedural Porous Corallite Bump Texture for Acropora Coral Branches
 */
function createCoralliteBumpTexture(): THREE.CanvasTexture {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.fillStyle = '#808080';
    ctx.fillRect(0, 0, size, size);
    let s = 4099;
    const rng = () => {
      s = (s * 1664525 + 1013904223) >>> 0;
      return (s & 0xfffffff) / 0xfffffff;
    };
    for (let i = 0; i < 420; i++) {
      const x = rng() * size;
      const y = rng() * size;
      const r = 1.2 + rng() * 2.8;
      ctx.fillStyle = '#e0e0e0';
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#303030';
      ctx.beginPath();
      ctx.arc(x, y, r * 0.45, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(2, 6);
  return tex;
}

export const SpatialView3D: React.FC<SpatialView3DProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  holdingFragment = true,
  clumpSpreadProgress = 0.65,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const orbitRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const auvGroupRef = useRef<THREE.Group | null>(null);
  const auvShadowRef = useRef<THREE.Mesh | null>(null);
  const carriedCoralRef = useRef<THREE.Group | null>(null);
  const manipulatorShoulderRef = useRef<THREE.Group | null>(null);
  const manipulatorElbowRef = useRef<THREE.Group | null>(null);
  const thrusterBladesRef = useRef<THREE.Object3D[]>([]);
  const spreadPulseMeshesRef = useRef<Array<{ mesh: THREE.Mesh; start: THREE.Vector3; end: THREE.Vector3; phase: number }>>([]);
  const targetAuvWorldRef = useRef<THREE.Vector3>(
    new THREE.Vector3(vehiclePos[0] - 40, getTerrainElevation(vehiclePos[0] - 40, -(vehiclePos[1] - 32)) + 0.65, -(vehiclePos[1] - 32))
  );

  const [showBounds, setShowBounds] = useState<boolean>(false);
  const [showClumpArcs, setShowClumpArcs] = useState<boolean>(true);
  const [cameraPreset, setCameraPreset] = useState<'auv_closeup' | 'mid_reef' | 'wide_canyon' | 'cluster_focus'>('auv_closeup');

  const selectedCluster = clusters.find((c) => c.id === selectedClusterId) || clusters[0];
  const clumpPlan = computeOptimalClumpHubAndPath(clusters, 'C-13');

  // Keep target AUV world coordinate updated whenever vehiclePos changes
  useEffect(() => {
    const vx = vehiclePos[0] - 40;
    const vz = -(vehiclePos[1] - 32);
    const seabedY = getTerrainElevation(vx, vz);
    targetAuvWorldRef.current.set(vx, seabedY + 0.62, vz);
    if (carriedCoralRef.current) {
      carriedCoralRef.current.visible = holdingFragment;
    }
  }, [vehiclePos, holdingFragment]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 640;
    const height = container.clientHeight || 450;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x061a28);
    scene.fog = new THREE.FogExp2(0x071f30, 0.0115);

    const camera = new THREE.PerspectiveCamera(44, width / height, 0.1, 240);
    // Start with a dramatic, clear close-up angle showing the AUV on the seabed beside West Spur Acropora Thicket
    const initAx = vehiclePos[0] - 40;
    const initAz = -(vehiclePos[1] - 32);
    const initAy = getTerrainElevation(initAx, initAz);
    camera.position.set(initAx + 5.8, initAy + 3.8, initAz + 6.8);
    cameraRef.current = camera;

    let renderer: THREE.WebGLRenderer | null = null;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.22;
      container.innerHTML = '';
      container.appendChild(renderer.domElement);
    } catch {
      return;
    }

    const glContext = renderer.getContext();
    const debugRenderer = glContext.getExtension('WEBGL_debug_renderer_info');
    const rendererInfo = debugRenderer
      ? String(glContext.getParameter(debugRenderer.UNMASKED_RENDERER_WEBGL))
      : '';
    const isSoftwareGl = /SwiftShader|llvmpipe|Software/i.test(rendererInfo);

    let rafId = 0;
    let isDisposed = false;
    const renderScene = () => {
      if (!renderer || isDisposed) return;
      renderer.render(scene, camera);
    };
    const afterDraw = (cb: () => void) => {
      if (isSoftwareGl) setTimeout(cb, 45);
      else rafId = requestAnimationFrame(cb);
    };

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !isSoftwareGl;
    controls.dampingFactor = 0.07;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;
    controls.minDistance = 1.8;
    controls.maxDistance = 115;
    // Target right between the AUV and West Spur Acropora Thicket so both are front-and-center
    controls.target.set(initAx - 0.8, initAy + 0.55, initAz - 0.8);
    controls.update();
    orbitRef.current = controls;

    // 1. Underwater Sunlit & Caustic Lighting Rig
    const hemiLight = new THREE.HemisphereLight(0x6ee7ff, 0x091e2c, 1.55);
    scene.add(hemiLight);

    const sunLight = new THREE.DirectionalLight(0xa5f3fc, 2.1);
    sunLight.position.set(18, 45, 22);
    scene.add(sunLight);

    const rimLight = new THREE.DirectionalLight(0x38bdf8, 0.95);
    rimLight.position.set(-28, 24, -18);
    scene.add(rimLight);

    const warmCoralFillLight = new THREE.DirectionalLight(0xfda4af, 0.55);
    warmCoralFillLight.position.set(0, 18, 25);
    scene.add(warmCoralFillLight);

    // 2. Seamless High-Resolution Sculpted Seabed & Reef Bommie Terrain (84m x 70m)
    const { colorMap: seabedColorMap, bumpMap: seabedBumpMap } = createSeabedTextures();
    const coralliteBumpMap = createCoralliteBumpTexture();

    const terrainGeo = new THREE.PlaneGeometry(84, 70, 128, 108);
    terrainGeo.rotateX(-Math.PI / 2);
    const posAttr = terrainGeo.attributes.position;
    const colors: number[] = [];

    for (let i = 0; i < posAttr.count; i++) {
      const vx = posAttr.getX(i);
      const vz = posAttr.getZ(i);
      const vy = getTerrainElevation(vx, vz);
      posAttr.setY(i, vy);

      const rockFactor = getBommieRockFactor(vx, vz);
      const normH = Math.max(0, Math.min(1, (vy + 4.2) / 5.2));
      const c = new THREE.Color();

      if (rockFactor > 0.25) {
        // Raised coralline limestone reef bommie substrate (warm purple-grey & sunlit teal crust)
        c.setHSL(0.56 - rockFactor * 0.08, 0.34, 0.22 + normH * 0.16 + rockFactor * 0.06);
      } else {
        // Carbonate sand channels & deeper canyon floor
        c.setHSL(0.53 - normH * 0.03, 0.46, 0.14 + normH * 0.18);
      }
      colors.push(c.r, c.g, c.b);
    }
    terrainGeo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    terrainGeo.computeVertexNormals();

    const terrainMat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      map: seabedColorMap,
      bumpMap: seabedBumpMap,
      bumpScale: 0.22,
      roughness: 0.84,
      metalness: 0.05,
      flatShading: false,
    });
    const terrainMesh = new THREE.Mesh(terrainGeo, terrainMat);
    scene.add(terrainMesh);

    // Subtle seabed sediment apron below the main terrain
    const apronGeo = new THREE.PlaneGeometry(180, 160);
    apronGeo.rotateX(-Math.PI / 2);
    const apronMat = new THREE.MeshBasicMaterial({ color: 0x051522 });
    const apronMesh = new THREE.Mesh(apronGeo, apronMat);
    apronMesh.position.y = -6.2;
    scene.add(apronMesh);

    // 3. Curved 3D Spline-Tube Acropora Coral Geometries (Authentic Antler Branching + Axial Tips)
    const buildCurvedAcroporaBranchGeo = (height = 0.72, curveBend = 0.14, rBase = 0.058): THREE.BufferGeometry => {
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(curveBend * 0.45, height * 0.33, curveBend * 0.2),
        new THREE.Vector3(curveBend * 0.9, height * 0.68, -curveBend * 0.15),
        new THREE.Vector3(curveBend * 1.25, height, 0.04),
      ]);
      const tubeGeo = new THREE.TubeGeometry(curve, 10, rBase, 8, false);
      const p = tubeGeo.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const yRatio = Math.max(0, Math.min(1, p.getY(i) / height));
        const taper = 1 - yRatio * 0.36;
        const spineX = curveBend * Math.pow(yRatio, 1.15) * 1.25;
        const dx = p.getX(i) - spineX;
        const dz = p.getZ(i);
        p.setX(i, spineX + dx * taper);
        p.setZ(i, dz * taper);
      }
      tubeGeo.computeVertexNormals();
      return tubeGeo;
    };

    const heroCurvedBranchGeo = buildCurvedAcroporaBranchGeo(0.78, 0.16, 0.062);
    const heroSubBranchGeo = buildCurvedAcroporaBranchGeo(0.42, 0.11, 0.044);
    const heroAxialTipGeo = new THREE.SphereGeometry(0.048, 8, 8);
    heroAxialTipGeo.scale(0.88, 1.45, 0.88);

    const boulderDomeGeo = new THREE.IcosahedronGeometry(0.62, 3);
    const bPos = boulderDomeGeo.attributes.position;
    for (let i = 0; i < bPos.count; i++) {
      const vx = bPos.getX(i);
      const vy = bPos.getY(i);
      const vz = bPos.getZ(i);
      const ripple = 1 + 0.08 * Math.sin(vx * 9 + vz * 7) * Math.cos(vy * 8);
      bPos.setXYZ(i, vx * ripple, Math.max(-0.1, vy * 0.72 * ripple), vz * ripple);
    }
    boulderDomeGeo.computeVertexNormals();

    const tabulateTierPlateGeo = new THREE.CylinderGeometry(0.75, 0.42, 0.09, 18);
    const tPos = tabulateTierPlateGeo.attributes.position;
    for (let i = 0; i < tPos.count; i++) {
      const vx = tPos.getX(i);
      const vz = tPos.getZ(i);
      const ang = Math.atan2(vz, vx);
      const radMod = 1 + 0.12 * Math.sin(ang * 5) + 0.06 * Math.cos(ang * 8);
      tPos.setX(i, vx * radMod);
      tPos.setZ(i, vz * radMod);
    }
    tabulateTierPlateGeo.computeVertexNormals();

    // 4. Dense Background Instanced Acropora Staghorn Thickets across all 13 Reef Bommies
    const stemCount = 1350;
    const instancedStemGeo = buildCurvedAcroporaBranchGeo(0.68, 0.14, 0.055);
    const instancedStemMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      bumpMap: coralliteBumpMap,
      bumpScale: 0.04,
      roughness: 0.42,
      metalness: 0.05,
    });
    const instancedStems = new THREE.InstancedMesh(instancedStemGeo, instancedStemMat, stemCount);

    const instancedTipGeo = new THREE.SphereGeometry(0.046, 7, 7);
    instancedTipGeo.scale(0.9, 1.4, 0.9);
    const instancedTipMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.25,
      metalness: 0.05,
    });
    const instancedTips = new THREE.InstancedMesh(instancedTipGeo, instancedTipMat, stemCount);

    const dummy = new THREE.Object3D();
    const tipDummy = new THREE.Object3D();
    const stemColor = new THREE.Color();
    const tipColor = new THREE.Color();

    let sSeed = 918273;
    const sRand = () => {
      sSeed = (sSeed * 1664525 + 1013904223) >>> 0;
      return (sSeed & 0xfffffff) / 0xfffffff;
    };

    const HEALTHY_ACROPORA_PALETTE = [
      { body: 0xe87952, tip: 0xfef08a }, // Sunset orange-gold Acropora millepora
      { body: 0x2dd4bf, tip: 0xa7f3d0 }, // Bioluminescent cyan-mint Acropora tenuis
      { body: 0xf472b6, tip: 0xfce7f3 }, // Rose-magenta Acropora hyacinthus
      { body: 0x38d996, tip: 0xd9f99d }, // Emerald-lime Acropora cervicornis
      { body: 0xa78bfa, tip: 0xede9fe }, // Lavender-violet Acropora secale
      { body: 0xfb923c, tip: 0xffedd5 }, // Amber-peach staghorn
    ];

    let stemIdx = 0;
    REEF_BOMMIE_FORMATIONS.forEach((bommie, bIdx) => {
      const branchesForBommie = bIdx === 0 ? 145 : 100;
      const clusterCenters: Array<{ x: number; z: number; paletteIdx: number }> = [];
      const subClumps = 6;
      for (let sc = 0; sc < subClumps; sc++) {
        const ang = (sc / subClumps) * Math.PI * 2 + sRand() * 0.5;
        const dist = (0.18 + sRand() * 0.58) * bommie.radius;
        clusterCenters.push({
          x: bommie.cx + Math.cos(ang) * dist,
          z: bommie.cz + Math.sin(ang) * dist,
          paletteIdx: Math.floor(sRand() * HEALTHY_ACROPORA_PALETTE.length),
        });
      }

      for (let k = 0; k < branchesForBommie && stemIdx < stemCount; k++) {
        const clump = clusterCenters[k % clusterCenters.length];
        const localR = Math.pow(sRand(), 0.65) * 1.35;
        const localA = sRand() * Math.PI * 2;
        const wx = clump.x + Math.cos(localA) * localR;
        const wz = clump.z + Math.sin(localA) * localR;
        const wy = getTerrainElevation(wx, wz) - 0.03;

        const scaleXZ = 0.95 + sRand() * 0.75;
        const scaleY = 0.95 + sRand() * 1.15;
        const rotY = sRand() * Math.PI * 2;
        const tiltX = (sRand() - 0.5) * 0.58;
        const tiltZ = (sRand() - 0.5) * 0.58;

        dummy.position.set(wx, wy, wz);
        dummy.rotation.set(tiltX, rotY, tiltZ);
        dummy.scale.set(scaleXZ, scaleY, scaleXZ);
        dummy.updateMatrix();
        instancedStems.setMatrixAt(stemIdx, dummy.matrix);

        const localTip = new THREE.Vector3(0.14 * 1.25 * scaleXZ, 0.68 * scaleY, 0.04 * scaleXZ);
        localTip.applyEuler(dummy.rotation);
        tipDummy.position.set(wx + localTip.x, wy + localTip.y, wz + localTip.z);
        tipDummy.rotation.copy(dummy.rotation);
        tipDummy.scale.setScalar(scaleXZ * 1.08);
        tipDummy.updateMatrix();
        instancedTips.setMatrixAt(stemIdx, tipDummy.matrix);

        const roll = sRand();
        if (bommie.healthBias === 'restored' && roll < 0.36) {
          stemColor.setHex(0x38bdf8);
          tipColor.setHex(0xe0f2fe);
        } else if (bommie.healthBias === 'mixed' && roll < 0.25) {
          stemColor.setHex(0xfef3c7);
          tipColor.setHex(0xffffff);
        } else {
          const pal = HEALTHY_ACROPORA_PALETTE[clump.paletteIdx];
          stemColor.setHex(pal.body);
          tipColor.setHex(pal.tip);
        }

        instancedStems.setColorAt(stemIdx, stemColor);
        instancedTips.setColorAt(stemIdx, tipColor);
        stemIdx++;
      }
    });

    instancedStems.instanceMatrix.needsUpdate = true;
    if (instancedStems.instanceColor) instancedStems.instanceColor.needsUpdate = true;
    instancedTips.instanceMatrix.needsUpdate = true;
    if (instancedTips.instanceColor) instancedTips.instanceColor.needsUpdate = true;
    scene.add(instancedStems);
    scene.add(instancedTips);

    // 5. Build 42 Surveyed Hero Coral Colonies (C-01 to C-42) Seated Cleanly on the Sculpted Seabed
    const pickables: THREE.Object3D[] = [];

    clusters.forEach((cluster, idx) => {
      const isSelected = cluster.id === selectedClusterId;
      const baseHex = STATUS_HEX[cluster.status];
      const wx = (cluster.localX + 40) - 40;
      const wz = -((cluster.localY + 32) - 32);
      const surfaceY = getTerrainElevation(wx, wz);

      const colonyGroup = new THREE.Group();
      colonyGroup.position.set(wx, surfaceY, wz);
      colonyGroup.userData = { clusterId: cluster.id };

      const [bx, by, bz] = cluster.boundsM;
      // Generous visual scale so surveyed colonies stand out prominently on the reef
      const scaleFactor = Math.max(0.85, Math.min(1.85, (bx + by) * 0.58));

      let bodyHex = baseHex;
      let axialTipHex = 0xe0f2fe;
      if (cluster.status === 'Living') {
        const pal = HEALTHY_ACROPORA_PALETTE[idx % HEALTHY_ACROPORA_PALETTE.length];
        bodyHex = isSelected ? 0x38d996 : pal.body;
        axialTipHex = pal.tip;
      } else if (cluster.status === 'Bleached') {
        bodyHex = 0xfef08a;
        axialTipHex = 0xffffff;
      } else if (cluster.status === 'Dead') {
        bodyHex = 0x993d3d;
        axialTipHex = 0xc26d6d;
      } else if (cluster.status === 'Placed') {
        bodyHex = 0x38bdf8;
        axialTipHex = 0xe0f2fe;
      }

      const coralBodyMat = new THREE.MeshStandardMaterial({
        color: bodyHex,
        emissive: bodyHex,
        emissiveIntensity: isSelected ? 0.42 : cluster.status === 'Placed' ? 0.28 : 0.14,
        bumpMap: coralliteBumpMap,
        bumpScale: 0.045,
        roughness: cluster.status === 'Dead' ? 0.88 : 0.36,
        metalness: 0.06,
      });

      const axialTipMat = new THREE.MeshStandardMaterial({
        color: axialTipHex,
        emissive: axialTipHex,
        emissiveIntensity: isSelected ? 0.55 : 0.26,
        roughness: 0.22,
        metalness: 0.04,
      });

      // Calcareous basal holdfast disc anchored to the reef surface
      const holdfastGeo = new THREE.CylinderGeometry(0.32 * scaleFactor, 0.46 * scaleFactor, 0.16, 12);
      const holdfastMat = new THREE.MeshStandardMaterial({
        color: 0x26485a,
        roughness: 0.9,
      });
      const holdfast = new THREE.Mesh(holdfastGeo, holdfastMat);
      holdfast.position.y = 0.06;
      holdfast.userData = { clusterId: cluster.id };
      colonyGroup.add(holdfast);
      pickables.push(holdfast);

      let cSeed = idx * 4999 + 17;
      const cRand = () => {
        cSeed = (cSeed * 1664525 + 1013904223) >>> 0;
        return (cSeed & 0xfffffff) / 0xfffffff;
      };

      if (cluster.morphology === 'staghorn' || cluster.morphology === 'corymbose') {
        const isCorymbose = cluster.morphology === 'corymbose';
        const branchCount = isCorymbose ? 18 : 14;

        for (let b = 0; b < branchCount; b++) {
          const ringRatio = b < 4 ? 0.18 : b < 10 ? 0.55 : 0.92;
          const angle = (b / branchCount) * Math.PI * 2 + cRand() * 0.42;
          const spreadR = ringRatio * (isCorymbose ? 0.42 : 0.36) * scaleFactor;

          const branchWrapper = new THREE.Group();
          branchWrapper.position.set(Math.cos(angle) * spreadR, 0.08, Math.sin(angle) * spreadR);

          const outwardTilt = isCorymbose
            ? 0.22 + ringRatio * 0.34
            : 0.15 + ringRatio * 0.48 + (cRand() - 0.5) * 0.16;
          branchWrapper.rotation.y = -angle + Math.PI * 0.5;
          branchWrapper.rotation.x = outwardTilt;
          branchWrapper.rotation.z = (cRand() - 0.5) * 0.22;

          const hScale = isCorymbose
            ? (0.68 + (1 - ringRatio * 0.25) * 0.38) * scaleFactor
            : (0.85 + cRand() * 0.65) * scaleFactor;
          const rScale = (isCorymbose ? 0.85 : 1.05) * scaleFactor * 0.78;

          const stemMesh = new THREE.Mesh(heroCurvedBranchGeo, coralBodyMat);
          stemMesh.scale.set(rScale, hScale, rScale);
          stemMesh.userData = { clusterId: cluster.id };
          branchWrapper.add(stemMesh);
          pickables.push(stemMesh);

          const tipMesh = new THREE.Mesh(heroAxialTipGeo, axialTipMat);
          tipMesh.position.set(0.16 * 1.25 * rScale, 0.78 * hScale, 0.04 * rScale);
          tipMesh.scale.setScalar(rScale * 1.08);
          tipMesh.userData = { clusterId: cluster.id };
          branchWrapper.add(tipMesh);

          // Secondary Y-bifurcation antler forks on staghorn branches
          if (!isCorymbose && b % 2 === 0) {
            const forkGroup = new THREE.Group();
            forkGroup.position.set(0.09 * rScale, 0.38 * hScale, 0);
            forkGroup.rotation.z = b % 4 === 0 ? 0.52 : -0.52;
            forkGroup.rotation.x = 0.25;

            const forkStem = new THREE.Mesh(heroSubBranchGeo, coralBodyMat);
            forkStem.scale.set(rScale * 0.84, hScale * 0.75, rScale * 0.84);
            forkStem.userData = { clusterId: cluster.id };
            forkGroup.add(forkStem);

            const forkTip = new THREE.Mesh(heroAxialTipGeo, axialTipMat);
            forkTip.position.set(0.11 * 1.25 * rScale * 0.84, 0.42 * hScale * 0.75, 0.03 * rScale);
            forkTip.scale.setScalar(rScale * 0.88);
            forkGroup.add(forkTip);

            branchWrapper.add(forkGroup);
          }

          colonyGroup.add(branchWrapper);
        }
      } else if (cluster.morphology === 'tabulate') {
        const tiers = 3;
        for (let t = 0; t < tiers; t++) {
          const tierScale = (0.68 + t * 0.28) * scaleFactor;
          const tierY = 0.16 + t * 0.22 * scaleFactor;
          const plate = new THREE.Mesh(tabulateTierPlateGeo, coralBodyMat);
          plate.position.set((t - 1) * 0.08, tierY, (t % 2 === 0 ? 1 : -1) * 0.06);
          plate.scale.set(tierScale, 1, tierScale * 0.92);
          plate.userData = { clusterId: cluster.id };
          colonyGroup.add(plate);
          pickables.push(plate);

          const rimCount = 12 + t * 4;
          for (let r = 0; r < rimCount; r++) {
            const a = (r / rimCount) * Math.PI * 2;
            const rimR = 0.66 * tierScale;
            const branchlet = new THREE.Mesh(heroAxialTipGeo, axialTipMat);
            branchlet.position.set(Math.cos(a) * rimR, tierY + 0.06, Math.sin(a) * rimR * 0.92);
            branchlet.scale.setScalar(0.75 * scaleFactor);
            colonyGroup.add(branchlet);
          }
        }
      } else {
        // Massive Brain / Boulder Coral (Porites / Diploria)
        const dome = new THREE.Mesh(boulderDomeGeo, coralBodyMat);
        dome.position.y = 0.24 * scaleFactor;
        dome.scale.set(scaleFactor * 0.95, scaleFactor * 0.88, scaleFactor * 0.92);
        dome.userData = { clusterId: cluster.id };
        colonyGroup.add(dome);
        pickables.push(dome);
      }

      // Selection ring on the seabed around the active colony
      if (isSelected) {
        const ringGeo = new THREE.RingGeometry(0.68 * scaleFactor, 0.82 * scaleFactor, 36);
        ringGeo.rotateX(-Math.PI / 2);
        const ringMat = new THREE.MeshBasicMaterial({
          color: 0x38bdf8,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.92,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.position.y = 0.05;
        colonyGroup.add(ring);
      }

      if (showBounds || isSelected) {
        const boxGeo = new THREE.BoxGeometry(bx * 0.78, bz * 0.9, by * 0.78);
        const edges = new THREE.EdgesGeometry(boxGeo);
        const lineMat = new THREE.LineBasicMaterial({
          color: isSelected ? 0x7dd3fc : baseHex,
          transparent: true,
          opacity: isSelected ? 0.85 : 0.35,
        });
        const boxWire = new THREE.LineSegments(edges, lineMat);
        boxWire.position.y = (bz * 0.9) / 2;
        colonyGroup.add(boxWire);
      }

      scene.add(colonyGroup);
    });

    // 6. Clump-Centric Shortest-Path & Symbiont Recovery Arcs on Seabed
    spreadPulseMeshesRef.current = [];
    if (showClumpArcs) {
      const donorCluster = clusters.find((c) => c.id === 'C-13');
      const hubCluster = clusters.find((c) => c.id === 'C-03');
      if (donorCluster && hubCluster) {
        const dPos = new THREE.Vector3(
          (donorCluster.localX + 40) - 40,
          getTerrainElevation((donorCluster.localX + 40) - 40, -((donorCluster.localY + 32) - 32)) + 0.55,
          -((donorCluster.localY + 32) - 32)
        );
        const hPos = new THREE.Vector3(
          (hubCluster.localX + 40) - 40,
          getTerrainElevation((hubCluster.localX + 40) - 40, -((hubCluster.localY + 32) - 32)) + 0.55,
          -((hubCluster.localY + 32) - 32)
        );
        const mid = dPos.clone().lerp(hPos, 0.5);
        mid.y += 1.05;

        const pathCurve = new THREE.QuadraticBezierCurve3(dPos, mid, hPos);
        const pathGeo = new THREE.TubeGeometry(pathCurve, 28, 0.045, 8, false);
        const pathMat = new THREE.MeshBasicMaterial({
          color: 0x38bdf8,
          transparent: true,
          opacity: 0.82,
        });
        scene.add(new THREE.Mesh(pathGeo, pathMat));
      }

      [clumpPlan].forEach((clump) => {
        const hub = clusters.find((c) => c.id === clump.optimalHubId);
        if (!hub) return;
        const hPos = new THREE.Vector3(
          (hub.localX + 40) - 40,
          getTerrainElevation((hub.localX + 40) - 40, -((hub.localY + 32) - 32)) + 0.42,
          -((hub.localY + 32) - 32)
        );

        // Soft glowing recovery aura disc around each clump hub
        const auraGeo = new THREE.RingGeometry(0.45, 2.35, 36);
        auraGeo.rotateX(-Math.PI / 2);
        const auraMat = new THREE.MeshBasicMaterial({
          color: clump.clumpId === 'clump-alpha' ? 0x38bdf8 : 0x38d996,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.22,
        });
        const auraMesh = new THREE.Mesh(auraGeo, auraMat);
        auraMesh.position.set(hPos.x, hPos.y - 0.34, hPos.z);
        scene.add(auraMesh);

        clump.spreadLinks.forEach((link, mIdx) => {
          const mId = link.targetId;
          if (mId === hub.id) return;
          const member = clusters.find((c) => c.id === mId);
          if (!member) return;
          const mPos = new THREE.Vector3(
            (member.localX + 40) - 40,
            getTerrainElevation((member.localX + 40) - 40, -((member.localY + 32) - 32)) + 0.42,
            -((member.localY + 32) - 32)
          );
          const arcMid = hPos.clone().lerp(mPos, 0.5);
          arcMid.y += 0.65;

          const spreadCurve = new THREE.QuadraticBezierCurve3(hPos, arcMid, mPos);
          const spreadGeo = new THREE.TubeGeometry(spreadCurve, 20, 0.032, 6, false);
          const spreadMat = new THREE.MeshBasicMaterial({
            color: 0x38d996,
            transparent: true,
            opacity: 0.45 + clumpSpreadProgress * 0.45,
          });
          scene.add(new THREE.Mesh(spreadGeo, spreadMat));

          const beadGeo = new THREE.SphereGeometry(0.085, 8, 8);
          const beadMat = new THREE.MeshBasicMaterial({ color: 0xa7f3d0 });
          const beadMesh = new THREE.Mesh(beadGeo, beadMat);
          beadMesh.position.copy(hPos);
          scene.add(beadMesh);
          spreadPulseMeshesRef.current.push({
            mesh: beadMesh,
            start: hPos,
            end: mPos,
            phase: mIdx * 0.33,
          });
        });
      });
    }

    // 7. BLENDER-GRADE 22-PART ARTICULATED HOVERING SUBMARINE AUV ON THE SEABED
    const auvGroup = new THREE.Group();
    const startAx = vehiclePos[0] - 40;
    const startAz = -(vehiclePos[1] - 32);
    const startSeabedY = getTerrainElevation(startAx, startAz);
    auvGroup.position.set(startAx, startSeabedY + 0.62, startAz);
    auvGroupRef.current = auvGroup;
    thrusterBladesRef.current = [];

    // 7a. Syntactic Foam Hydrodynamic Upper Hull Fairing (High-Visibility Marine Yellow)
    const hullYellowMat = new THREE.MeshStandardMaterial({
      color: 0xfacc15,
      roughness: 0.26,
      metalness: 0.25,
    });
    const hullDarkMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.45,
      metalness: 0.68,
    });
    const hullCyanAccentMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x0284c7,
      emissiveIntensity: 0.35,
      roughness: 0.3,
      metalness: 0.4,
    });
    const steelMat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.32,
      metalness: 0.82,
    });

    // Main top buoyancy shell
    const topFairingGeo = new THREE.BoxGeometry(1.75, 0.42, 0.96);
    const topFairing = new THREE.Mesh(topFairingGeo, hullYellowMat);
    topFairing.position.set(0, 0.16, 0);
    auvGroup.add(topFairing);

    // Tapered front & rear fairing cones
    const noseConeGeo = new THREE.ConeGeometry(0.52, 0.48, 16);
    noseConeGeo.rotateZ(-Math.PI / 2);
    const noseCone = new THREE.Mesh(noseConeGeo, hullYellowMat);
    noseCone.scale.set(1, 0.62, 0.94);
    noseCone.position.set(1.06, 0.14, 0);
    auvGroup.add(noseCone);

    const sternConeGeo = new THREE.ConeGeometry(0.48, 0.42, 16);
    sternConeGeo.rotateZ(Math.PI / 2);
    const sternCone = new THREE.Mesh(sternConeGeo, hullYellowMat);
    sternCone.scale.set(1, 0.58, 0.92);
    sternCone.position.set(-1.04, 0.14, 0);
    auvGroup.add(sternCone);

    // Cyan side identification stripes
    [-0.49, 0.49].forEach((sideZ) => {
      const stripeGeo = new THREE.BoxGeometry(1.48, 0.08, 0.02);
      const stripe = new THREE.Mesh(stripeGeo, hullCyanAccentMat);
      stripe.position.set(0.02, 0.14, sideZ);
      auvGroup.add(stripe);
    });

    // Central Titanium Electronics & Pressure Cylinder
    const pressureHullGeo = new THREE.CylinderGeometry(0.24, 0.24, 1.45, 20);
    pressureHullGeo.rotateZ(Math.PI / 2);
    const pressureHull = new THREE.Mesh(pressureHullGeo, hullDarkMat);
    pressureHull.position.set(0, -0.06, 0);
    auvGroup.add(pressureHull);

    // Twin Port/Starboard Lower Battery Pods
    [-0.32, 0.32].forEach((podZ) => {
      const podGeo = new THREE.CylinderGeometry(0.11, 0.11, 1.25, 14);
      podGeo.rotateZ(Math.PI / 2);
      const pod = new THREE.Mesh(podGeo, hullDarkMat);
      pod.position.set(-0.04, -0.22, podZ);
      auvGroup.add(pod);
    });

    // Twin Tubular Seabed Landing Skids + Cross Struts
    [-0.42, 0.42].forEach((skidZ) => {
      const skidGeo = new THREE.CylinderGeometry(0.032, 0.032, 1.68, 10);
      skidGeo.rotateZ(Math.PI / 2);
      const skid = new THREE.Mesh(skidGeo, steelMat);
      skid.position.set(0, -0.42, skidZ);
      auvGroup.add(skid);

      [-0.55, 0.55].forEach((strutX) => {
        const strutGeo = new THREE.CylinderGeometry(0.022, 0.022, 0.34, 8);
        const strut = new THREE.Mesh(strutGeo, steelMat);
        strut.position.set(strutX, -0.26, skidZ);
        auvGroup.add(strut);
      });
    });

    // Top Stainless Recovery Bail Handle & Acoustic Beacon Mast
    const bailGeo = new THREE.TorusGeometry(0.18, 0.024, 8, 18, Math.PI);
    const bail = new THREE.Mesh(bailGeo, steelMat);
    bail.position.set(-0.15, 0.37, 0);
    auvGroup.add(bail);

    const dvlTurretGeo = new THREE.CylinderGeometry(0.18, 0.14, 0.1, 14);
    const dvlTurret = new THREE.Mesh(dvlTurretGeo, hullDarkMat);
    dvlTurret.position.set(0.28, 0.41, 0);
    auvGroup.add(dvlTurret);

    const mastGeo = new THREE.CylinderGeometry(0.022, 0.032, 0.42, 10);
    const mast = new THREE.Mesh(mastGeo, hullDarkMat);
    mast.position.set(-0.55, 0.56, 0);
    auvGroup.add(mast);

    const strobeGeo = new THREE.SphereGeometry(0.055, 10, 10);
    const strobeMat = new THREE.MeshBasicMaterial({ color: 0x38d996 });
    const strobe = new THREE.Mesh(strobeGeo, strobeMat);
    strobe.position.set(-0.55, 0.78, 0);
    auvGroup.add(strobe);

    // 7b. 4 Vectored Corner Ducted Thrusters with Spinning 4-Blade Propellers
    const thrusterCoords: Array<[number, number, number, number]> = [
      [0.74, -0.05, 0.62, -0.42],
      [0.74, -0.05, -0.62, 0.42],
      [-0.78, -0.05, 0.62, 0.42],
      [-0.78, -0.05, -0.62, -0.42],
    ];
    thrusterCoords.forEach(([tx, ty, tz, yawAngle]) => {
      const podGroup = new THREE.Group();
      podGroup.position.set(tx, ty, tz);
      podGroup.rotation.y = yawAngle;

      const shroudGeo = new THREE.CylinderGeometry(0.15, 0.15, 0.22, 16, 1, true);
      shroudGeo.rotateZ(Math.PI / 2);
      const shroud = new THREE.Mesh(shroudGeo, hullDarkMat);
      podGroup.add(shroud);

      const ringTrimGeo = new THREE.TorusGeometry(0.15, 0.018, 8, 18);
      ringTrimGeo.rotateY(Math.PI / 2);
      const ringTrim = new THREE.Mesh(ringTrimGeo, hullCyanAccentMat);
      ringTrim.position.x = 0.11;
      podGroup.add(ringTrim);

      const rotorGroup = new THREE.Group();
      for (let b = 0; b < 4; b++) {
        const bladeGeo = new THREE.BoxGeometry(0.02, 0.12, 0.045);
        const blade = new THREE.Mesh(bladeGeo, hullYellowMat);
        blade.rotation.x = (b * Math.PI) / 2;
        blade.position.y = Math.cos((b * Math.PI) / 2) * 0.05;
        blade.position.z = Math.sin((b * Math.PI) / 2) * 0.05;
        rotorGroup.add(blade);
      }
      podGroup.add(rotorGroup);
      thrusterBladesRef.current.push(rotorGroup);

      auvGroup.add(podGroup);
    });

    // 7c. Bow Stereo Optical Camera Dome & Dual Volumetric LED Spotlight Cones
    const domeGeo = new THREE.SphereGeometry(0.21, 18, 18, 0, Math.PI * 2, 0, Math.PI * 0.55);
    domeGeo.rotateZ(-Math.PI / 2);
    const domeMat = new THREE.MeshStandardMaterial({
      color: 0x0bae6f,
      emissive: 0x38bdf8,
      emissiveIntensity: 0.48,
      roughness: 0.08,
      metalness: 0.15,
      transparent: true,
      opacity: 0.86,
    });
    const cameraDome = new THREE.Mesh(domeGeo, domeMat);
    cameraDome.position.set(0.92, -0.06, 0);
    auvGroup.add(cameraDome);

    [-0.28, 0.28].forEach((beamZ) => {
      const coneGeo = new THREE.ConeGeometry(0.55, 2.4, 16, 1, true);
      coneGeo.rotateZ(Math.PI / 2);
            const coneMat = new THREE.MeshBasicMaterial({
        color: 0x7dd3fc,
        transparent: true,
        opacity: 0.11,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const lightCone = new THREE.Mesh(coneGeo, coneMat);
      lightCone.position.set(2.05, -0.28, beamZ);
      lightCone.rotation.z = 0.22;
      auvGroup.add(lightCone);
    });

    // 7d. Multi-Jointed 6-DoF Robotic Manipulator Arm & Soft-Finger Coral Gripper Underneath Bow
    const shoulderGroup = new THREE.Group();
    shoulderGroup.position.set(0.52, -0.26, 0);
    manipulatorShoulderRef.current = shoulderGroup;

    const shoulderMount = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.065, 0.12, 12), steelMat);
    shoulderGroup.add(shoulderMount);

    const upperArmGeo = new THREE.CylinderGeometry(0.038, 0.034, 0.42, 10);
    const upperArm = new THREE.Mesh(upperArmGeo, hullDarkMat);
    upperArm.position.set(0.14, -0.16, 0);
    upperArm.rotation.z = 0.65;
    shoulderGroup.add(upperArm);

    const elbowGroup = new THREE.Group();
    elbowGroup.position.set(0.28, -0.32, 0);
    manipulatorElbowRef.current = elbowGroup;

    const elbowJoint = new THREE.Mesh(new THREE.SphereGeometry(0.048, 10, 10), hullCyanAccentMat);
    elbowGroup.add(elbowJoint);

    const forearmGeo = new THREE.CylinderGeometry(0.032, 0.028, 0.36, 10);
    const forearm = new THREE.Mesh(forearmGeo, steelMat);
    forearm.position.set(0.16, -0.08, 0);
    forearm.rotation.z = 1.15;
    elbowGroup.add(forearm);

    // Dual soft-compliant silicone fingers at wrist
    const wristGroup = new THREE.Group();
    wristGroup.position.set(0.32, -0.15, 0);
    [-0.065, 0.065].forEach((fingerZ) => {
      const fingerGeo = new THREE.BoxGeometry(0.14, 0.028, 0.028);
      const finger = new THREE.Mesh(fingerGeo, hullCyanAccentMat);
      finger.position.set(0.06, 0, fingerZ);
      wristGroup.add(finger);
    });

    // Live branching coral fragment held inside the soft gripper
    const carriedCoralGroup = new THREE.Group();
    carriedCoralGroup.position.set(0.12, -0.02, 0);
    carriedCoralGroup.visible = holdingFragment;
    carriedCoralRef.current = carriedCoralGroup;

    const fragMat = new THREE.MeshStandardMaterial({
      color: 0x38d996,
      emissive: 0x10b981,
      emissiveIntensity: 0.45,
      roughness: 0.3,
    });
    for (let f = 0; f < 4; f++) {
      const miniBranch = new THREE.Mesh(heroSubBranchGeo, fragMat);
      miniBranch.scale.setScalar(0.52);
      miniBranch.rotation.set((f - 1.5) * 0.35, f * 1.1, (f % 2 === 0 ? 1 : -1) * 0.3);
      carriedCoralGroup.add(miniBranch);
    }
    wristGroup.add(carriedCoralGroup);
    elbowGroup.add(wristGroup);
    shoulderGroup.add(elbowGroup);
    auvGroup.add(shoulderGroup);

    scene.add(auvGroup);

    // 7e. Seabed Contact Shadow Disc Directly Under AUV to Anchor Depth Perception
    const shadowGeo = new THREE.CircleGeometry(1.15, 28);
    shadowGeo.rotateX(-Math.PI / 2);
    const shadowMat = new THREE.MeshBasicMaterial({
      color: 0x020810,
      transparent: true,
      opacity: 0.52,
    });
    const shadowDisc = new THREE.Mesh(shadowGeo, shadowMat);
    shadowDisc.position.set(startAx, startSeabedY + 0.04, startAz);
    auvShadowRef.current = shadowDisc;
    scene.add(shadowDisc);

    // 8. Water-Column Marine Snow Plankton Particles
    const particleCount = 180;
    const pGeo = new THREE.BufferGeometry();
    const pPositions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      pPositions[i * 3] = (sRand() - 0.5) * 76;
      pPositions[i * 3 + 1] = -3.0 + sRand() * 11;
      pPositions[i * 3 + 2] = (sRand() - 0.5) * 62;
    }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
    const pMat = new THREE.PointsMaterial({
      color: 0xbae6fd,
      size: 0.11,
      transparent: true,
      opacity: 0.42,
    });
    const planktonPoints = new THREE.Points(pGeo, pMat);
    scene.add(planktonPoints);

    // 9. Raycaster for Click Selection on Any 3D Coral Colony
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let pointerDownPos = { x: 0, y: 0 };

    const handlePointerDown = (e: MouseEvent) => {
      pointerDownPos = { x: e.clientX, y: e.clientY };
    };

    const handlePointerUp = (e: MouseEvent) => {
      const dist = Math.hypot(e.clientX - pointerDownPos.x, e.clientY - pointerDownPos.y);
      if (dist > 6) return;
      const rect = renderer!.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(pickables, false);
      if (intersects.length > 0) {
        const hitClusterId = intersects[0].object.userData?.clusterId;
        if (hitClusterId) {
          onSelectCluster(hitClusterId);
        }
      }
    };

    renderer.domElement.addEventListener('mousedown', handlePointerDown);
    renderer.domElement.addEventListener('mouseup', handlePointerUp);

    // 10. Continuous Paced Animation Loop (AUV Seabed Following, Thruster Spin, 6-DoF Arm & Spread Beads)
    let animPhase = 0;
    const tick = () => {
      if (isDisposed) return;
      animPhase += 0.045;

      if (auvGroupRef.current) {
        const cur = auvGroupRef.current.position;
        const tgt = targetAuvWorldRef.current;

        const dx = tgt.x - cur.x;
        const dz = tgt.z - cur.z;
        cur.x += dx * 0.08;
        cur.z += dz * 0.08;

        const seabedBelow = getTerrainElevation(cur.x, cur.z);
        const bobOffset = Math.sin(animPhase * 1.4) * 0.045;
        cur.y = seabedBelow + 0.62 + bobOffset;

        // Smooth heading orientation & subtle hydrodynamic pitch/roll
        if (Math.hypot(dx, dz) > 0.02) {
          const targetYaw = Math.atan2(-dz, dx);
          auvGroupRef.current.rotation.y += (targetYaw - auvGroupRef.current.rotation.y) * 0.08;
        }
        auvGroupRef.current.rotation.z = Math.sin(animPhase * 1.1) * 0.025;
        auvGroupRef.current.rotation.x = Math.cos(animPhase * 0.9) * 0.02;

        if (auvShadowRef.current) {
          auvShadowRef.current.position.set(cur.x, seabedBelow + 0.04, cur.z);
        }
      }

      // Spin all 4 ducted thruster propellers
      thrusterBladesRef.current.forEach((rotor, idx) => {
        rotor.rotation.x += (idx % 2 === 0 ? 1 : -1) * 0.38;
      });

      // Articulate 6-DoF robotic manipulator arm gently scanning/seating toward the seabed
      if (manipulatorShoulderRef.current && manipulatorElbowRef.current) {
        manipulatorShoulderRef.current.rotation.z = Math.sin(animPhase * 0.9) * 0.14;
        manipulatorElbowRef.current.rotation.z = -0.12 + Math.cos(animPhase * 0.9) * 0.16;
      }

      // Animate symbiont recovery beads traveling from Hub to neighbor corals
      spreadPulseMeshesRef.current.forEach((item) => {
        const t = (animPhase * 0.35 + item.phase) % 1;
        item.mesh.position.lerpVectors(item.start, item.end, t);
        item.mesh.position.y += Math.sin(t * Math.PI) * 0.52;
      });

      if (!isSoftwareGl) {
        controls.update();
      }
      renderScene();
      afterDraw(tick);
    };

    const onControlsChange = () => {
      if (isSoftwareGl) renderScene();
    };
    controls.addEventListener('change', onControlsChange);

    renderScene();
    afterDraw(tick);

    const handleResize = () => {
      if (!container || !renderer) return;
      const w = container.clientWidth || 640;
      const h = container.clientHeight || 450;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      renderScene();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      isDisposed = true;
      cancelAnimationFrame(rafId);
      controls.removeEventListener('change', onControlsChange);
      window.removeEventListener('resize', handleResize);
      if (renderer && renderer.domElement) {
        renderer.domElement.removeEventListener('mousedown', handlePointerDown);
        renderer.domElement.removeEventListener('mouseup', handlePointerUp);
        renderer.dispose();
      }
    };
  }, [clusters, selectedClusterId, showBounds, showClumpArcs]);

  // Camera Preset Handlers
  const applyCameraPreset = (preset: 'auv_closeup' | 'mid_reef' | 'wide_canyon' | 'cluster_focus') => {
    setCameraPreset(preset);
    if (!cameraRef.current || !orbitRef.current) return;

    if (preset === 'auv_closeup') {
      const ax = vehiclePos[0] - 40;
      const az = -(vehiclePos[1] - 32);
      const ay = getTerrainElevation(ax, az);
      cameraRef.current.position.set(ax + 5.8, ay + 3.8, az + 6.8);
      orbitRef.current.target.set(ax - 0.8, ay + 0.55, az - 0.8);
    } else if (preset === 'mid_reef') {
      cameraRef.current.position.set(-14, 15.5, 34);
      orbitRef.current.target.set(-16, -0.5, 10);
    } else if (preset === 'wide_canyon') {
      cameraRef.current.position.set(0, 32, 54);
      orbitRef.current.target.set(0, -1.5, 0);
    } else if (preset === 'cluster_focus') {
      const cx = (selectedCluster.localX + 40) - 40;
      const cz = -((selectedCluster.localY + 32) - 32);
      const cy = getTerrainElevation(cx, cz);
      cameraRef.current.position.set(cx + 4.8, cy + 3.4, cz + 5.4);
      orbitRef.current.target.set(cx, cy + 0.5, cz);
    }
    orbitRef.current.update();
  };

  const handleOrbitSpin = (deltaAngleRad: number) => {
    if (!cameraRef.current || !orbitRef.current) return;
    const target = orbitRef.current.target;
    const offset = cameraRef.current.position.clone().sub(target);
    const cos = Math.cos(deltaAngleRad);
    const sin = Math.sin(deltaAngleRad);
    const nx = offset.x * cos - offset.z * sin;
    const nz = offset.x * sin + offset.z * cos;
    offset.x = nx;
    offset.z = nz;
    cameraRef.current.position.copy(target).add(offset);
    orbitRef.current.update();
  };

  return (
    <div className="bg-[#0B1218] border border-slate-800/80 rounded-md flex flex-col h-full overflow-hidden">
      {/* Compact Header */}
      <div className="px-3.5 py-2.5 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-2 bg-slate-950/60">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <Compass className="w-3.5 h-3.5 text-sky-400" />
            3D seabed reef & articulated AUV simulation
          </h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            Seabed-grounded 3D Acropora coral gardens & 6-DoF robotic submarine · Drag to spin 360° & scroll to zoom
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => applyCameraPreset('auv_closeup')}
            className={`px-2 py-1 text-[10px] font-mono rounded border transition-colors flex items-center gap-1 ${
              cameraPreset === 'auv_closeup'
                ? 'bg-sky-500/20 border-sky-500/50 text-sky-200'
                : 'bg-slate-900 border-slate-700/80 text-slate-300 hover:text-white'
            }`}
            title="Focus close-up on the articulated AUV and nearby Acropora coral cluster on the seabed"
          >
            <Anchor className="w-3 h-3 text-sky-400" />
            Seabed & AUV Close-Up
          </button>
          <button
            type="button"
            onClick={() => applyCameraPreset('wide_canyon')}
            className={`px-2 py-1 text-[10px] font-mono rounded border transition-colors flex items-center gap-1 ${
              cameraPreset === 'wide_canyon'
                ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-200'
                : 'bg-slate-900 border-slate-700/80 text-slate-300 hover:text-white'
            }`}
            title="View the full 80x64m reef canyon and all 13 coral clusters"
          >
            <Compass className="w-3 h-3 text-emerald-400" />
            Wide 80×64m Reef
          </button>
          <button
            type="button"
            onClick={() => applyCameraPreset('cluster_focus')}
            className={`px-2 py-1 text-[10px] font-mono rounded border transition-colors flex items-center gap-1 ${
              cameraPreset === 'cluster_focus'
                ? 'bg-teal-500/20 border-teal-500/50 text-teal-200'
                : 'bg-slate-900 border-slate-700/80 text-slate-300 hover:text-white'
            }`}
            title={`Zoom directly onto selected coral colony ${selectedCluster.id}`}
          >
            <Focus className="w-3 h-3 text-teal-300" />
            Inspect {selectedCluster.id}
          </button>
          <button
            type="button"
            onClick={() => handleOrbitSpin(-0.4)}
            className="px-2 py-1 text-[10px] font-mono rounded border bg-slate-900 border-slate-700/80 text-slate-300 hover:text-white transition-colors"
            aria-label="Orbit 3D view counter-clockwise"
          >
            ↰
          </button>
          <button
            type="button"
            onClick={() => handleOrbitSpin(0.4)}
            className="px-2 py-1 text-[10px] font-mono rounded border bg-slate-900 border-slate-700/80 text-slate-300 hover:text-white transition-colors"
            aria-label="Orbit 3D view clockwise"
          >
            ↱
          </button>
        </div>
      </div>

      {/* 3D WebGL Viewport with Crisp Fixed Proportions */}
      <div className="relative h-[450px] bg-[#061a28] select-none overflow-hidden">
        <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

        {/* Top-Left Seabed & AUV Status Pill (Compact so it never overlaps top-right card) */}
        <div className="absolute top-2.5 left-2.5 bg-slate-950/85 backdrop-blur-md border border-slate-800/90 rounded px-2.5 py-1.5 text-[10px] font-mono text-slate-300 pointer-events-none space-y-0.5 max-w-[54%]">
          <div className="flex items-center gap-1.5 text-emerald-300 font-semibold truncate">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span className="truncate">80×64m Seabed · 13 Reef Clusters · 1,350 Acropora Stems</span>
          </div>
          <div className="text-sky-300 truncate">
            AUV-01 on Seabed: ({vehiclePos[0].toFixed(1)}m, {vehiclePos[1].toFixed(1)}m, -{vehiclePos[2].toFixed(1)}m) ·{' '}
            {holdingFragment ? 'Arm Carrying Coral' : 'Scanning Seabed'}
          </div>
        </div>

        {/* Top-Right Selected Colony Quick Card */}
        <div className="absolute top-2.5 right-2.5 bg-slate-950/90 backdrop-blur-md border border-slate-800/90 rounded px-2.5 py-1.5 text-[10px] font-mono text-slate-200 max-w-[205px]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-white">
              {selectedCluster.id} · {selectedCluster.morphology}
            </span>
            <span className="text-sky-400">-{(-selectedCluster.depthM).toFixed(1)}m</span>
          </div>
          <div className="text-[9px] text-slate-400 truncate mt-0.5">{selectedCluster.species}</div>
          <div className="text-[9px] text-emerald-300 mt-0.5">
            Size {selectedCluster.boundsM[0].toFixed(1)}×{selectedCluster.boundsM[1].toFixed(1)}m · Tilt{' '}
            {(Math.acos(Math.max(-1, Math.min(1, selectedCluster.surfaceNormal[2]))) * 180 / Math.PI).toFixed(1)}°
          </div>
        </div>

        {/* Bottom Camera & Layer Control Bar */}
        <div className="absolute bottom-2.5 left-2.5 right-2.5 bg-slate-950/90 backdrop-blur-md border border-slate-800/90 rounded px-2.5 py-1.5 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-300">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => applyCameraPreset('auv_closeup')}
              className="text-sky-400 hover:text-sky-300 font-semibold"
            >
              Seabed & AUV
            </button>
            <span className="text-slate-700">·</span>
            <button
              type="button"
              onClick={() => applyCameraPreset('mid_reef')}
              className="text-teal-300 hover:text-teal-200"
            >
              Mid-Reef Clusters
            </button>
            <span className="text-slate-700">·</span>
            <button
              type="button"
              onClick={() => applyCameraPreset('wide_canyon')}
              className="text-emerald-400 hover:text-emerald-300"
            >
              Full 80×64m Reef
            </button>
            <span className="text-slate-700">·</span>
            <button
              type="button"
              onClick={() => applyCameraPreset('cluster_focus')}
              className="text-amber-300 hover:text-amber-200"
            >
              Zoom to {selectedCluster.id}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowClumpArcs((v) => !v)}
              className={`px-1.5 py-0.5 rounded border transition-colors ${
                showClumpArcs
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                  : 'bg-slate-900 border-slate-800 text-slate-400'
              }`}
            >
              <Layers className="w-3 h-3 inline mr-1" />
              Spread Arcs
            </button>
            <button
              type="button"
              onClick={() => setShowBounds((v) => !v)}
              className={`px-1.5 py-0.5 rounded border transition-colors ${
                showBounds
                  ? 'bg-sky-500/15 border-sky-500/40 text-sky-300'
                  : 'bg-slate-900 border-slate-800 text-slate-400'
              }`}
            >
              <Eye className="w-3 h-3 inline mr-1" />
              CAD Boxes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
