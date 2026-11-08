import * as THREE from 'three';
import { CoralCluster } from '../domain/reefEngine';

// Convert local reef metres (0..38m X, 0..26m Y) to expansive 3D world (vx, vz)
export function toReefWorldXZ(lx: number, ly: number): [number, number] {
  const vx = (lx - 15.5) * 1.15;
  const vz = (12.0 - ly) * 1.15;
  return [vx, vz];
}

// 14 Reef Bommie Mounds & Ridges across the expansive 80 x 64m seabed
const REEF_BOMMIE_MOUNDS: Array<{
  x: number;
  y: number;
  h: number;
  r: number;
  label?: string;
}> = [
  { x: 2.8, y: 5.8, h: 1.15, r: 4.6, label: 'Clump Alpha' },
  { x: 4.3, y: 2.2, h: 0.95, r: 4.0, label: 'Kidney Crest' },
  { x: 8.2, y: 5.9, h: 1.1, r: 4.6, label: 'Staghorn Bank' },
  { x: 16.8, y: 19.6, h: 1.65, r: 5.4, label: 'North Pinnacle' },
  { x: 19.8, y: 7.7, h: 1.05, r: 4.4, label: 'Star Bommie' },
  { x: 31.8, y: 18.1, h: 0.95, r: 4.8, label: 'Deep Wall Ledge' },
  // Surrounding Canyon Bommies for deep horizon exploration
  { x: -3.2, y: 11.2, h: 1.35, r: 5.0 },
  { x: -3.8, y: 2.2, h: 1.1, r: 4.4 },
  { x: 9.8, y: 14.8, h: 1.45, r: 5.2 },
  { x: 12.4, y: -1.8, h: 1.15, r: 4.5 },
  { x: 24.5, y: 14.0, h: 1.3, r: 4.8 },
  { x: 26.2, y: 2.8, h: 1.1, r: 4.4 },
  { x: 35.5, y: 8.5, h: 1.0, r: 4.6 },
  { x: 6.0, y: 22.8, h: 1.5, r: 5.0 },
];

// Deterministic, continuous seabed elevation at any 3D world (vx, vz) coordinate
export function getSeabedHeight(vx: number, vz: number): number {
  const lx = vx / 1.15 + 15.5;
  const ly = 12.0 - vz / 1.15;

  let moundLift = 0;
  for (const b of REEF_BOMMIE_MOUNDS) {
    const d = Math.hypot(lx - b.x, ly - b.y);
    if (d < b.r * 1.5) {
      const t = Math.max(0, 1 - (d / (b.r * 1.4)) ** 2);
      moundLift += b.h * t * t;
    }
  }

  const slopeDrop = lx > 25 ? (lx - 25) * 0.1 : 0;
  const westRidge = lx < 0 ? Math.min(0.9, -lx * 0.11) : 0;

  const ridges =
    Math.sin(vx * 0.36 + vz * 0.22) * 0.26 +
    Math.cos(vz * 0.44 - vx * 0.24) * 0.2 +
    Math.sin(vx * 0.9 - vz * 0.8) * 0.08;

  return moundLift + westRidge - slopeDrop + ridges - 0.55;
}

// Creates a single smoothly curved, tapering 3D coral branch along a CatmullRomCurve3 spline
function createTaperedCurvedBranchGeometry(
  curve: THREE.CatmullRomCurve3,
  tabularSegments: number,
  baseRadius: number,
  tipRadius: number,
  radialSegments = 7
): THREE.BufferGeometry {
  const tubeGeo = new THREE.TubeGeometry(curve, tabularSegments, baseRadius, radialSegments, false);
  const pos = tubeGeo.attributes.position;
  const splinePts = curve.getSpacedPoints(tabularSegments);

  // Taper radius smoothly from baseRadius (t=0) to tipRadius (t=1) with a rounded dome cap at the end
  for (let i = 0; i <= tabularSegments; i++) {
    const t = i / tabularSegments;
    const center = splinePts[i];
    const scale =
      i === tabularSegments
        ? 0.08
        : (1 - t) + (tipRadius / baseRadius) * t * Math.sin((1 - t * 0.35) * (Math.PI / 2));

    for (let j = 0; j <= radialSegments; j++) {
      const idx = i * (radialSegments + 1) + j;
      if (idx < pos.count) {
        const vx = pos.getX(idx) - center.x;
        const vy = pos.getY(idx) - center.y;
        const vz = pos.getZ(idx) - center.z;
        pos.setXYZ(
          idx,
          center.x + vx * scale,
          center.y + vy * scale,
          center.z + vz * scale
        );
      }
    }
  }
  tubeGeo.computeVertexNormals();
  return tubeGeo;
}

// Builds an organic, high-realism 3D Acropora coral colony (curved tapering antlers, ruffled table plates, or ridged brain coral)
function populateRealisticCoralColony(
  targetGroup: THREE.Group,
  morphology: CoralCluster['morphology'],
  radiusM: number,
  heightM: number,
  primaryMat: THREE.Material,
  secondaryMat: THREE.Material,
  rand: () => number,
  highDetail = true
) {
  if (morphology === 'tabulate') {
    // Organic multi-tiered Acropora hyacinthus table coral with wavy scalloped fan plates & sturdy pedicel
    const tierCount = highDetail ? 4 : 3;
    for (let t = 0; t < tierCount; t++) {
      const plateRad = radiusM * (0.88 - t * 0.14);
      const plateGeo = new THREE.CylinderGeometry(plateRad, plateRad * 0.42, 0.042, 28, 2);
      const pAttr = plateGeo.attributes.position;
      for (let v = 0; v < pAttr.count; v++) {
        const vx = pAttr.getX(v);
        const vy = pAttr.getY(v);
        const vz = pAttr.getZ(v);
        const r = Math.hypot(vx, vz);
        const ang = Math.atan2(vz, vx);
        const ruffle = 1 + 0.18 * Math.sin(ang * 5 + t * 2.1) + 0.08 * Math.cos(ang * 9);
        const cupLift = (r / Math.max(0.01, plateRad)) ** 1.6 * 0.055;
        pAttr.setXYZ(v, vx * ruffle, vy + cupLift, vz * ruffle);
      }
      plateGeo.computeVertexNormals();
      const plateMesh = new THREE.Mesh(
        plateGeo,
        t % 2 === 0 ? primaryMat : secondaryMat
      );
      plateMesh.position.set(
        (rand() - 0.5) * radiusM * 0.22,
        0.08 + t * (heightM * 0.18),
        (rand() - 0.5) * radiusM * 0.22
      );
      plateMesh.rotation.set(
        (rand() - 0.5) * 0.1,
        rand() * Math.PI * 2,
        (rand() - 0.5) * 0.1
      );
      targetGroup.add(plateMesh);
    }
    return;
  }

  if (morphology === 'boulder') {
    // Sculpted brain/boulder coral dome with continuous sinusoidal meandroid grooves
    const lobeCount = highDetail ? 4 : 2;
    for (let l = 0; l < lobeCount; l++) {
      const lRad = radiusM * (0.48 - l * 0.06);
      const domeGeo = new THREE.IcosahedronGeometry(lRad, 3);
      const dPos = domeGeo.attributes.position;
      for (let v = 0; v < dPos.count; v++) {
        const vx = dPos.getX(v);
        const vy = dPos.getY(v);
        const vz = dPos.getZ(v);
        const ridge = 1 + 0.09 * Math.sin(vx * 22 + vz * 18) * Math.cos(vy * 20);
        dPos.setXYZ(
          v,
          vx * ridge * 1.15,
          Math.max(-0.02, vy * ridge * 0.78),
          vz * ridge * 1.1
        );
      }
      domeGeo.computeVertexNormals();
      const dome = new THREE.Mesh(
        domeGeo,
        l % 2 === 0 ? primaryMat : secondaryMat
      );
      const ang = (l / lobeCount) * Math.PI * 2 + rand();
      const dist = l === 0 ? 0 : radiusM * 0.28;
      dome.position.set(Math.cos(ang) * dist, 0.04, Math.sin(ang) * dist);
      targetGroup.add(dome);
    }
    return;
  }

  // Smoothly curved, tapering 3D spline Acropora Staghorn / Elkhorn / Corymbose thicket
  const isCorymbose = morphology === 'corymbose';
  const stemCount = highDetail ? (isCorymbose ? 16 : 12) : 8;

  for (let b = 0; b < stemCount; b++) {
    const az = (b / stemCount) * Math.PI * 2 + (rand() - 0.5) * 0.35;
    const ring = b < 3 ? 0.1 * rand() : b < 9 ? 0.35 + rand() * 0.2 : 0.65 + rand() * 0.22;
    const spreadR = radiusM * (isCorymbose ? 0.58 : 0.78) * ring;
    const reachH = heightM * (isCorymbose ? 0.55 - ring * 0.14 : 0.68 + rand() * 0.28);

    const p0 = new THREE.Vector3(
      Math.cos(az) * spreadR * 0.22,
      0.02,
      Math.sin(az) * spreadR * 0.22
    );
    const p1 = new THREE.Vector3(
      Math.cos(az) * spreadR * 0.65,
      reachH * 0.36,
      Math.sin(az) * spreadR * 0.65
    );
    const p2 = new THREE.Vector3(
      Math.cos(az + (rand() - 0.5) * 0.25) * spreadR * 0.95,
      reachH * 0.74,
      Math.sin(az + (rand() - 0.5) * 0.25) * spreadR * 0.95
    );
    const p3 = new THREE.Vector3(
      Math.cos(az + (rand() - 0.5) * 0.3) * spreadR * 1.05,
      reachH,
      Math.sin(az + (rand() - 0.5) * 0.3) * spreadR * 1.05
    );

    const mainCurve = new THREE.CatmullRomCurve3([p0, p1, p2, p3]);
    const rBase = isCorymbose ? 0.026 : 0.036;
    const rTip = isCorymbose ? 0.014 : 0.016;
    const mainGeo = createTaperedCurvedBranchGeometry(mainCurve, 10, rBase, rTip, 6);
    const mainMesh = new THREE.Mesh(
      mainGeo,
      b % 2 === 0 ? primaryMat : secondaryMat
    );
    targetGroup.add(mainMesh);

    // Organic Y-forked secondary antler spline splitting smoothly off the main curve
    if (highDetail && b % 2 === 0) {
      const forkAz = az + (b % 4 === 0 ? 0.42 : -0.42);
      const fp0 = p1.clone().lerp(p2, 0.35);
      const fp1 = new THREE.Vector3(
        fp0.x + Math.cos(forkAz) * radiusM * 0.24,
        fp0.y + reachH * 0.22,
        fp0.z + Math.sin(forkAz) * radiusM * 0.24
      );
      const fp2 = new THREE.Vector3(
        fp1.x + Math.cos(forkAz) * radiusM * 0.16,
        fp0.y + reachH * 0.46,
        fp1.z + Math.sin(forkAz) * radiusM * 0.16
      );
      const forkCurve = new THREE.CatmullRomCurve3([fp0, fp1, fp2]);
      const forkGeo = createTaperedCurvedBranchGeometry(
        forkCurve,
        7,
        rBase * 0.72,
        rTip * 0.85,
        6
      );
      const forkMesh = new THREE.Mesh(forkGeo, secondaryMat);
      targetGroup.add(forkMesh);
    }
  }
}

// Builds the expansive 82 x 66m sculpted 3D seabed terrain + 14 reef bommie outcrops + ambient coral thickets
export function createDetailedSeabedScene(): {
  terrainGroup: THREE.Group;
  causticPoints: THREE.Points;
} {
  const terrainGroup = new THREE.Group();

  const terrainGeo = new THREE.PlaneGeometry(82, 66, 140, 112);
  terrainGeo.rotateX(-Math.PI / 2);
  const posAttr = terrainGeo.attributes.position;
  const colors: number[] = [];
  const cTmp = new THREE.Color();

  for (let i = 0; i < posAttr.count; i++) {
    const vx = posAttr.getX(i);
    const vz = posAttr.getZ(i);
    const y = getSeabedHeight(vx, vz);
    posAttr.setY(i, y);

    // Deep, high-contrast underwater bathymetry so vibrant corals stand out vividly
    if (y > 0.65) {
      cTmp.setHex(0x133c48); // Sunlit carbonate reef bommie crest
    } else if (y > 0.1) {
      cTmp.setHex(0x0e2d3b); // Limestone spur slope
    } else if (y > -0.35) {
      cTmp.setHex(0x0a212e); // Deep reef sand channel
    } else {
      cTmp.setHex(0x061520); // Abyssal mesophotic canyon floor
    }
    const n = (Math.sin(vx * 2.4 + vz * 2.1) * 0.5 + 0.5) * 0.03;
    colors.push(cTmp.r + n, cTmp.g + n * 1.1, cTmp.b + n * 1.2);
  }

  terrainGeo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  terrainGeo.computeVertexNormals();

  const terrainMat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.92,
    metalness: 0.04,
    flatShading: true,
  });
  const terrainMesh = new THREE.Mesh(terrainGeo, terrainMat);
  terrainGroup.add(terrainMesh);

  const rockMat = new THREE.MeshStandardMaterial({
    color: 0x163240,
    roughness: 0.92,
    metalness: 0.05,
    flatShading: true,
  });
  const corallineMat = new THREE.MeshStandardMaterial({
    color: 0x224252,
    roughness: 0.86,
    metalness: 0.06,
    flatShading: true,
  });

  // Naturalistic reef materials for surrounding background bommie clusters
  const ambCoralTeal = new THREE.MeshStandardMaterial({
    color: 0x14b8a6,
    roughness: 0.45,
    metalness: 0.06,
    emissive: 0x0f766e,
    emissiveIntensity: 0.22,
  });
  const ambCoralAmber = new THREE.MeshStandardMaterial({
    color: 0xf59e0b,
    roughness: 0.48,
    metalness: 0.06,
    emissive: 0xb45309,
    emissiveIntensity: 0.2,
  });
  const ambCoralTerracotta = new THREE.MeshStandardMaterial({
    color: 0xe07a5f,
    roughness: 0.46,
    metalness: 0.06,
    emissive: 0x9a3412,
    emissiveIntensity: 0.2,
  });

  REEF_BOMMIE_MOUNDS.forEach((bm, bIdx) => {
    const [bx, bz] = toReefWorldXZ(bm.x, bm.y);
    const by = getSeabedHeight(bx, bz);
    const outcropGroup = new THREE.Group();
    outcropGroup.position.set(bx, by, bz);

    // Sculpted carbonate rock base boulders
    for (let k = 0; k < 8; k++) {
      const ang = (k / 8) * Math.PI * 2 + bIdx * 0.6;
      const dist = k === 0 ? 0 : 0.8 + (k % 3) * 0.65;
      const rad = k === 0 ? 1.25 : 0.6 + (k % 2) * 0.32;
      const rockGeo = new THREE.DodecahedronGeometry(rad, 1);
      const rPos = rockGeo.attributes.position;
      for (let v = 0; v < rPos.count; v++) {
        const px = rPos.getX(v);
        const py = rPos.getY(v);
        const pz = rPos.getZ(v);
        const warp = 1 + 0.16 * Math.sin(px * 3 + bIdx + k) * Math.cos(pz * 3);
        rPos.setXYZ(v, px * warp * 1.4, py * 0.3, pz * warp * 1.2);
      }
      rockGeo.computeVertexNormals();
      const rockMesh = new THREE.Mesh(rockGeo, k % 2 === 0 ? rockMat : corallineMat);
      const rx = bx + Math.cos(ang) * dist;
      const rz = bz + Math.sin(ang) * dist;
      const localY = getSeabedHeight(rx, rz) - by;
      rockMesh.position.set(Math.cos(ang) * dist, localY + 0.03, Math.sin(ang) * dist);
      rockMesh.rotation.y = ang * 1.3;
      outcropGroup.add(rockMesh);
    }

    // Populate outer reef bommies with mixed Acropora tables, staghorns & brain corals
    if (bIdx >= 6) {
      let s = 918273 ^ (bIdx * 4177);
      const rand = () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return (s & 0xfffffff) / 0xfffffff;
      };
      const morphs: CoralCluster['morphology'][] = [
        'staghorn',
        'tabulate',
        'corymbose',
        'boulder',
        'staghorn',
      ];
      for (let c = 0; c < 5; c++) {
        const cAng = (c / 5) * Math.PI * 2 + rand() * 0.4;
        const cDist = c === 0 ? 0 : 1.05 + rand() * 1.25;
        const tx = bx + Math.cos(cAng) * cDist;
        const tz = bz + Math.sin(cAng) * cDist;
        const ty = getSeabedHeight(tx, tz) - by;
        const thicket = new THREE.Group();
        thicket.position.set(Math.cos(cAng) * cDist, ty + 0.04, Math.sin(cAng) * cDist);
        populateRealisticCoralColony(
          thicket,
          morphs[c],
          0.75 + rand() * 0.35,
          0.55 + rand() * 0.25,
          c % 2 === 0 ? ambCoralTeal : ambCoralAmber,
          ambCoralTerracotta,
          rand,
          false
        );
        outcropGroup.add(thicket);
      }
    }

    terrainGroup.add(outcropGroup);
  });

  // Underwater suspended marine snow / plankton particles
  const particleCount = 240;
  const pPositions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    const s1 = Math.sin(i * 12.9898) * 43758.5453;
    const s2 = Math.sin(i * 78.233) * 43758.5453;
    const s3 = Math.sin(i * 39.425) * 43758.5453;
    const rx = (s1 - Math.floor(s1) - 0.5) * 60;
    const rz = (s2 - Math.floor(s2) - 0.5) * 48;
    const ry = getSeabedHeight(rx, rz) + 0.4 + (s3 - Math.floor(s3)) * 4.8;
    pPositions[i * 3] = rx;
    pPositions[i * 3 + 1] = ry;
    pPositions[i * 3 + 2] = rz;
  }
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
  const pMat = new THREE.PointsMaterial({
    color: 0x7dd3fc,
    size: 0.06,
    transparent: true,
    opacity: 0.4,
  });
  const causticPoints = new THREE.Points(pGeo, pMat);

  return { terrainGroup, causticPoints };
}

// Builds a realistic, multi-colony 3D coral cluster grounded directly on the seabed
export function createDetailedCoralCluster3D(
  cluster: CoralCluster,
  cIdx: number
): {
  root: THREE.Group;
  boxFrame: THREE.LineSegments;
  selectionRing: THREE.Mesh;
  hitbox: THREE.Mesh;
} {
  let seed = 2166136261 ^ (cIdx * 7919);
  for (let i = 0; i < cluster.id.length; i++) {
    seed ^= cluster.id.charCodeAt(i);
    seed = Math.imul(seed, 16777619);
  }
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return (seed & 0xfffffff) / 0xfffffff;
  };

  const [sx, sz] = toReefWorldXZ(cluster.localX, cluster.localY);
  const sy = getSeabedHeight(sx, sz);

  const root = new THREE.Group();
  root.position.set(sx, sy, sz);

  const bw = Math.max(0.95, cluster.boundsM[0] * 1.42);
  const bl = Math.max(0.95, cluster.boundsM[1] * 1.42);
  const bh = Math.max(0.52, cluster.boundsM[2] * 1.18);

  // Naturalistic underwater coral coloration (no harsh primary red/green)
  const palette =
    cluster.status === 'Living'
      ? {
          primary: 0x10b981,   // Healthy seafoam-emerald Acropora
          secondary: 0x2dd4bf, // Turquoise-mint polyps
          emissive: 0x065f46,
          emissiveIntensity: 0.25,
        }
      : cluster.status === 'Placed'
      ? {
          primary: 0x0ea5e9,   // Restored bioluminescent cyan-blue colony
          secondary: 0x38bdf8,
          emissive: 0x0369a1,
          emissiveIntensity: 0.32,
        }
      : cluster.status === 'Bleached'
      ? {
          primary: 0xfde68a,   // Warm ivory-amber bleached Acropora
          secondary: 0xfef3c7,
          emissive: 0xb45309,
          emissiveIntensity: 0.18,
        }
      : {
          primary: 0xd97757,   // Warm terracotta-coral weathered reef skeleton
          secondary: 0xb4533c,
          emissive: 0x7c2d12,
          emissiveIntensity: 0.15,
        };

  const coralGroup = new THREE.Group();

  // Basal limestone reef rock fused into the seabed
  const baseRockMat = new THREE.MeshStandardMaterial({
    color: 0x1b3746,
    roughness: 0.9,
    metalness: 0.05,
    flatShading: true,
  });
  for (let r = 0; r < 4; r++) {
    const rGeo = new THREE.DodecahedronGeometry(bw * (0.34 - r * 0.04), 1);
    const rMesh = new THREE.Mesh(rGeo, baseRockMat);
    const ang = (r / 4) * Math.PI * 2 + rand();
    const dist = r === 0 ? 0 : bw * 0.22;
    rMesh.scale.set(1.3, 0.26, 1.15);
    rMesh.position.set(Math.cos(ang) * dist, 0.03, Math.sin(ang) * dist);
    rMesh.rotation.y = ang;
    coralGroup.add(rMesh);
  }

  const primaryMat = new THREE.MeshStandardMaterial({
    color: palette.primary,
    roughness: 0.42,
    metalness: 0.06,
    emissive: palette.emissive,
    emissiveIntensity: palette.emissiveIntensity,
  });
  const secondaryMat = new THREE.MeshStandardMaterial({
    color: palette.secondary,
    roughness: 0.36,
    metalness: 0.08,
    emissive: palette.emissive,
    emissiveIntensity: palette.emissiveIntensity * 1.15,
  });

  // 4 clustered sub-colonies per cluster site (combining main morphology with companion staghorn/table/boulder heads)
  const subColonies: Array<{
    ox: number;
    oz: number;
    scale: number;
    morph: CoralCluster['morphology'];
  }> = [
    { ox: 0, oz: 0, scale: 1.05, morph: cluster.morphology },
    { ox: bw * 0.32, oz: bl * 0.2, scale: 0.78, morph: 'staghorn' },
    {
      ox: -bw * 0.28,
      oz: bl * 0.24,
      scale: 0.72,
      morph: cluster.morphology === 'tabulate' ? 'corymbose' : 'tabulate',
    },
    { ox: bw * 0.18, oz: -bl * 0.3, scale: 0.68, morph: 'boulder' },
  ];

  subColonies.forEach(({ ox, oz, scale, morph }, idx) => {
    const subGroup = new THREE.Group();
    const localGroundOffset = getSeabedHeight(sx + ox, sz + oz) - sy;
    subGroup.position.set(ox, localGroundOffset + 0.03, oz);
    subGroup.scale.setScalar(scale);

    populateRealisticCoralColony(
      subGroup,
      morph,
      bw * 0.46,
      bh * 0.78,
      primaryMat,
      secondaryMat,
      rand,
      idx < 2
    );

    coralGroup.add(subGroup);
  });

  root.add(coralGroup);

  const boxGeo = new THREE.BoxGeometry(bw * 1.05, bh, bl * 1.05);
  const edgesGeo = new THREE.EdgesGeometry(boxGeo);
  const edgesMat = new THREE.LineBasicMaterial({
    color: palette.secondary,
    transparent: true,
    opacity: 0.65,
  });
  const boxFrame = new THREE.LineSegments(edgesGeo, edgesMat);
  boxFrame.position.y = bh * 0.5;
  boxFrame.visible = false;
  root.add(boxFrame);

  const ringGeo = new THREE.RingGeometry(bw * 0.58, bw * 0.72, 36);
  ringGeo.rotateX(-Math.PI / 2);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x22d3ee,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.9,
  });
  const selectionRing = new THREE.Mesh(ringGeo, ringMat);
  selectionRing.position.y = 0.05;
  root.add(selectionRing);

  const hitGeo = new THREE.BoxGeometry(
    Math.max(1.1, bw * 1.2),
    Math.max(0.9, bh * 1.3),
    Math.max(1.1, bl * 1.2)
  );
  const hitMat = new THREE.MeshBasicMaterial({ visible: false });
  const hitbox = new THREE.Mesh(hitGeo, hitMat);
  hitbox.position.y = bh * 0.5;
  hitbox.userData.clusterId = cluster.id;
  root.add(hitbox);

  return {
    root,
    boxFrame,
    selectionRing,
    hitbox,
  };
}
