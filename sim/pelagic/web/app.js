import * as THREE from "./vendor/three.module.js";

const $ = (id) => document.getElementById(id);
const canvas = $("ocean");
const state = {
  snapshot: null,
  paused: false,
  follow: false,
  connected: false,
  lastSeed: null,
  pointer: null,
  dragging: false,
  distance: 13.8,
  azimuth: 0.69,
  elevation: 0.34,
  cameraTarget: new THREE.Vector3(0, 0.35, 0),
  draggingInput: false,
  rtx: false,
  rtxAutoSelected: false,
  rtxPending: false,
};
const scene = new THREE.Scene();
const oceanColor = new THREE.Color("#0b3b43");
scene.background = oceanColor;
scene.fog = new THREE.FogExp2(oceanColor, 0.085);
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.13;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const camera = new THREE.PerspectiveCamera(
  48,
  innerWidth / innerHeight,
  0.05,
  100,
);
const hemisphere = new THREE.HemisphereLight(0x8ce2d8, 0x31382b, 2.1);
scene.add(hemisphere);
const sun = new THREE.DirectionalLight(0xb1f4de, 3.8);
sun.position.set(-4, 11, 3);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -9;
sun.shadow.camera.right = 9;
sun.shadow.camera.top = 9;
sun.shadow.camera.bottom = -9;
sun.shadow.normalBias = 0.04;
scene.add(sun);
scene.add(new THREE.AmbientLight(0x2a6b77, 0.6));
const reefGroup = new THREE.Group();
scene.add(reefGroup);
const coralGroups = new Map(),
  robotGroups = new Map(),
  trailLines = new Map();
let seabed, particles, causticPlane, waterSurface, seedRandom;
const clock = new THREE.Clock();
const clamp = THREE.MathUtils.clamp;
const xyz = (p) =>
  new THREE.Vector3(
    Number(p?.[0] || 0),
    Number(p?.[2] || 0),
    -Number(p?.[1] || 0),
  );
function rng(seed = 17) {
  let a = seed | 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const material = (color, roughness = 0.82) =>
  new THREE.MeshStandardMaterial({ color, roughness, metalness: 0.02 });
function mesh(geometry, mat, parent = reefGroup) {
  const o = new THREE.Mesh(geometry, mat);
  o.castShadow = true;
  o.receiveShadow = true;
  parent.add(o);
  return o;
}
function sphere(parent, p, r, mat, scale = [1, 1, 1], detail = 1) {
  const o = mesh(new THREE.IcosahedronGeometry(r, detail), mat, parent);
  o.position.copy(p);
  o.scale.set(...scale);
  return o;
}
function link(parent, a, b, r1, r2, mat, segments = 6) {
  const d = b.clone().sub(a),
    o = mesh(
      new THREE.CylinderGeometry(r2, r1, d.length(), segments, 1),
      mat,
      parent,
    );
  o.position.copy(a).add(b).multiplyScalar(0.5);
  o.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return o;
}
function sandTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const ctx = c.getContext("2d"),
    rand = rng(4);
  ctx.fillStyle = "#9b9b70";
  ctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 19000; i++) {
    let a = rand() * 0.14;
    ctx.fillStyle = `rgba(${rand() > 0.5 ? "232,226,180" : "44,75,61"},${a})`;
    let x = rand() * 512,
      y = rand() * 512;
    ctx.fillRect(x, y, 1.5, 1.5);
  }
  for (let y = 0; y < 512; y += 12) {
    ctx.beginPath();
    for (let x = 0; x <= 512; x += 5) {
      let yy = y + Math.sin(x * 0.028 + y * 0.024) * 3;
      if (x === 0) ctx.moveTo(x, yy);
      else ctx.lineTo(x, yy);
    }
    ctx.strokeStyle = "rgba(220,224,169,.13)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(7, 7);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function causticTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const ctx = c.getContext("2d"),
    rand = rng(12);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 130; i++) {
    const x = rand() * 512,
      y = rand() * 512,
      r = 12 + rand() * 38;
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * 0.6, rand() * 6, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(167,238,208,${0.08 + rand() * 0.18})`;
    ctx.lineWidth = 1.2 + rand() * 1.2;
    ctx.shadowColor = "#c6ffdf";
    ctx.shadowBlur = 3;
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(3, 3);
  return t;
}
function buildEnvironment() {
  const groundGeo = new THREE.PlaneGeometry(45, 45, 100, 100);
  groundGeo.rotateX(-Math.PI / 2);
  const pos = groundGeo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    let x = pos.getX(i),
      z = pos.getZ(i);
    pos.setY(
      i,
      -0.07 +
        Math.sin(x * 0.7) * Math.cos(z * 0.53) * 0.045 +
        Math.sin(z * 9 + x * 0.25) * 0.012,
    );
  }
  groundGeo.computeVertexNormals();
  seabed = mesh(
    groundGeo,
    new THREE.MeshStandardMaterial({
      color: 0xa7ad80,
      map: sandTexture(),
      roughness: 1,
    }),
  );
  const ct = causticTexture();
  causticPlane = mesh(
    new THREE.PlaneGeometry(26, 26),
    new THREE.MeshBasicMaterial({
      map: ct,
      transparent: true,
      opacity: 0.36,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  causticPlane.rotation.x = -Math.PI / 2;
  causticPlane.position.y = 0.012;
  causticPlane.castShadow = false;
  waterSurface = mesh(
    new THREE.PlaneGeometry(65, 65, 24, 24),
    new THREE.MeshBasicMaterial({
      color: 0x368e8b,
      transparent: true,
      opacity: 0.23,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  waterSurface.rotation.x = Math.PI / 2;
  waterSurface.position.y = 8;
  const rand = rng(27),
    rockMat = material(0x466c61);
  for (let i = 0; i < 55; i++) {
    const x = (rand() - 0.5) * 27,
      z = (rand() - 0.5) * 27;
    if (Math.abs(x) < 5 && Math.abs(z) < 5) continue;
    sphere(
      reefGroup,
      new THREE.Vector3(x, -0.05, z),
      0.1 + rand() * 0.5,
      rockMat,
      [1.8, 0.5 + rand() * 0.5, 1.2],
    );
  }
  const count = 2200,
    pts = new Float32Array(count * 3),
    colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    pts[i * 3] = (rand() - 0.5) * 30;
    pts[i * 3 + 1] = rand() * 8;
    pts[i * 3 + 2] = (rand() - 0.5) * 30;
    colors[i * 3] = 0.4 + rand() * 0.3;
    colors[i * 3 + 1] = 0.7;
    colors[i * 3 + 2] = 0.6;
  }
  const pg = new THREE.BufferGeometry();
  pg.setAttribute("position", new THREE.BufferAttribute(pts, 3));
  pg.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  particles = new THREE.Points(
    pg,
    new THREE.PointsMaterial({
      size: 0.018,
      transparent: true,
      opacity: 0.45,
      vertexColors: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  scene.add(particles);
  // Layered translucent beams are illustrative spectator lighting, not a sensor model.
  for (let i = 0; i < 6; i++) {
    const beam = mesh(
      new THREE.ConeGeometry(0.7 + i * 0.12, 11, 16, 1, true),
      new THREE.MeshBasicMaterial({
        color: 0x9cdcb8,
        transparent: true,
        opacity: 0.014,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
      }),
    );
    beam.position.set(-7 + i * 2.8, 3.5, -4 + i * 0.8);
    beam.rotation.z = -0.22;
    beam.castShadow = false;
  }
}
function coralMaterial(c, rand) {
  const health = c.health?.toLowerCase(),
    color =
      health === "healthy"
        ? new THREE.Color(
            [0x9a7282, 0xba917e, 0x879b6f, 0x8a85b6, 0xa89b6d, 0x658e8a][
              Math.floor(rand() * 6)
            ],
          )
        : health === "bleached_alive"
          ? new THREE.Color(0xd8d8b9)
          : new THREE.Color(0x657c66);
  color.multiplyScalar(0.85 + rand() * 0.3);
  return material(color);
}
function makeCoral(c) {
  const rand = rng(
      String(c.id)
        .split("")
        .reduce((v, x) => v + x.charCodeAt(0) * 31, 3),
    ),
    g = new THREE.Group();
  g.position.copy(xyz(c.position));
  const mat = coralMaterial(c, rand),
    tip = mat.clone();
  tip.color.lerp(new THREE.Color(0xe9dfba), 0.25);
  const h = Number(c.height || 0.55),
    r = Number(c.radius || 0.3);
  sphere(
    g,
    new THREE.Vector3(0, 0.035, 0),
    r * 0.9,
    material(c.health === "dead" ? 0x58695a : 0x727d62),
    [1, 0.3, 1],
  );
  if (c.morphology === "boulder") {
    for (let i = 0; i < 15; i++) {
      const a = rand() * Math.PI * 2,
        rad = rand() * r * 0.75;
      sphere(
        g,
        new THREE.Vector3(
          Math.cos(a) * rad,
          h * 0.3 + rand() * h * 0.2,
          Math.sin(a) * rad,
        ),
        h * (0.25 + rand() * 0.14),
        mat,
        [1, 0.9, 1],
        2,
      );
    }
    for (let i = 0; i < 65; i++) {
      const a = rand() * Math.PI * 2,
        v = rand(),
        radius = r * Math.sqrt(v),
        y = h * 0.37 + Math.sqrt(Math.max(0, 1 - v)) * h * 0.35;
      sphere(
        g,
        new THREE.Vector3(Math.cos(a) * radius, y, Math.sin(a) * radius),
        0.025 + rand() * 0.015,
        tip,
        [1, 1, 1],
        0,
      );
    }
  } else {
    const count = 7 + Math.floor(rand() * 5);
    for (let i = 0; i < count; i++) {
      let a = (i / count) * Math.PI * 2 + rand() * 0.4;
      const base = new THREE.Vector3(
          (rand() - 0.5) * r * 0.5,
          0.04,
          (rand() - 0.5) * r * 0.5,
        ),
        mid = new THREE.Vector3(
          Math.cos(a) * r * 0.45,
          h * 0.42,
          Math.sin(a) * r * 0.45,
        ),
        end = new THREE.Vector3(
          Math.cos(a) * r * 0.85,
          h * (0.65 + rand() * 0.4),
          Math.sin(a) * r * 0.85,
        );
      link(g, base, mid, 0.032, 0.025, mat);
      link(g, mid, end, 0.025, 0.013, mat);
      sphere(g, end, 0.017, tip, [1, 1, 1], 0);
      for (let j = 0; j < 3; j++) {
        const start = mid.clone().lerp(end, 0.12 + j * 0.23),
          aa = a + (j % 2 ? 1 : -1) * (0.7 + rand() * 0.4),
          branch = start
            .clone()
            .add(
              new THREE.Vector3(
                Math.cos(aa) * r * 0.52,
                h * 0.26,
                Math.sin(aa) * r * 0.52,
              ),
            );
        link(g, start, branch, 0.018, 0.009, mat);
        sphere(g, branch, 0.014, tip, [1, 1, 1], 0);
      }
    }
  }
  const plant = new THREE.Group();
  plant.name = "outplant";
  const pm = material(0xa2ccb0);
  link(
    plant,
    new THREE.Vector3(0, h, 0),
    new THREE.Vector3(0.02, h + 0.22, 0),
    0.015,
    0.01,
    pm,
  );
  link(
    plant,
    new THREE.Vector3(0.01, h + 0.1, 0),
    new THREE.Vector3(-0.09, h + 0.22, 0),
    0.01,
    0.005,
    pm,
  );
  link(
    plant,
    new THREE.Vector3(0.01, h + 0.14, 0),
    new THREE.Vector3(0.1, h + 0.25, 0.03),
    0.01,
    0.005,
    pm,
  );
  const ring = mesh(
    new THREE.TorusGeometry(r + 0.08, 0.007, 5, 48),
    new THREE.MeshBasicMaterial({
      color: 0x8ddbc9,
      transparent: true,
      opacity: 0.6,
    }),
    plant,
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.035;
  plant.visible = false;
  g.add(plant);
  g.userData.plant = plant;
  reefGroup.add(g);
  coralGroups.set(c.id, g);
}
function makeRobot(r) {
  const g = new THREE.Group(),
    rest = r.role === "restoration",
    bodyMat = material(0xd5ded1, 0.4),
    dark = material(0x132d33, 0.5),
    accent = material(rest ? 0xe5aa66 : 0x65c8b8, 0.45);
  const hull = mesh(new THREE.CapsuleGeometry(0.15, 0.38, 5, 12), bodyMat, g);
  hull.rotation.z = Math.PI / 2;
  hull.scale.z = 0.85;
  for (const z of [-0.22, 0.22]) {
    let bar = mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.65, 8), accent, g);
    bar.rotation.z = Math.PI / 2;
    bar.position.set(0, -0.1, z);
    for (const x of [-0.22, 0.22]) {
      const guard = mesh(new THREE.TorusGeometry(0.1, 0.024, 6, 16), dark, g);
      guard.rotation.x = Math.PI / 2;
      guard.position.set(x, 0.04, z);
      const rotor = mesh(
        new THREE.CylinderGeometry(0.072, 0.072, 0.04, 6),
        accent,
        g,
      );
      rotor.position.copy(guard.position);
    }
  }
  const eye = mesh(
    new THREE.CylinderGeometry(0.065, 0.065, 0.035, 12),
    dark,
    g,
  );
  eye.rotation.z = Math.PI / 2;
  eye.position.set(0.35, 0, 0);
  const lens = mesh(
    new THREE.CircleGeometry(0.044, 16),
    new THREE.MeshBasicMaterial({ color: 0xa3deda }),
    g,
  );
  lens.rotation.y = Math.PI / 2;
  lens.position.set(0.371, 0, 0);
  for (const z of [-0.1, 0.1]) {
    const light = mesh(
      new THREE.SphereGeometry(0.032, 8, 6),
      new THREE.MeshBasicMaterial({ color: 0xdffff0 }),
      g,
    );
    light.position.set(0.26, -0.035, z);
    const spotlight = new THREE.SpotLight(0xb7f4da, 4, 4.8, 0.38, 0.8, 1.5);
    spotlight.position.copy(light.position);
    const target = new THREE.Object3D();
    target.position.set(3, -1.3, z);
    g.add(target);
    spotlight.target = target;
    g.add(spotlight);
  }
  const arm = new THREE.Group();
  arm.name = "arm";
  arm.position.set(0.13, -0.13, 0);
  link(
    arm,
    new THREE.Vector3(),
    new THREE.Vector3(0.15, -0.14, 0),
    0.025,
    0.022,
    accent,
  );
  link(
    arm,
    new THREE.Vector3(0.15, -0.14, 0),
    new THREE.Vector3(0.3, -0.23, 0),
    0.022,
    0.018,
    bodyMat,
  );
  sphere(arm, new THREE.Vector3(0.15, -0.14, 0), 0.038, dark);
  for (const z of [-0.025, 0.025])
    link(
      arm,
      new THREE.Vector3(0.3, -0.23, z),
      new THREE.Vector3(0.36, -0.3, z),
      0.01,
      0.008,
      dark,
    );
  g.add(arm);
  if (!rest) arm.visible = false;
  g.userData.arm = arm;
  const fragment = sphere(
    g,
    new THREE.Vector3(0.48, -0.4, 0),
    0.07,
    material(0xadc5a1),
    [0.8, 1.5, 0.8],
  );
  fragment.visible = false;
  g.userData.fragment = fragment;
  const marker = new THREE.Mesh(
    new THREE.RingGeometry(0.36, 0.375, 48),
    new THREE.MeshBasicMaterial({
      color: rest ? 0xe4b780 : 0x84ded0,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  marker.rotation.x = -Math.PI / 2;
  marker.position.y = -0.37;
  g.add(marker);
  scene.add(g);
  robotGroups.set(r.id, g);
  const line = new THREE.Line(
    new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({
      color: rest ? 0xe4b780 : 0x84ded0,
      transparent: true,
      opacity: 0.34,
    }),
  );
  scene.add(line);
  trailLines.set(r.id, line);
  return g;
}
function buildWorld(s) {
  coralGroups.forEach((g) => {
    reefGroup.remove(g);
    g.traverse((o) => {
      o.geometry?.dispose();
      if (o.material?.dispose) o.material.dispose();
    });
  });
  coralGroups.clear();
  for (const c of s.corals || []) makeCoral(c);
  if (s.nursery?.position) {
    const rack = new THREE.Group(),
      p = xyz(s.nursery.position);
    rack.position.copy(p);
    const m = material(0xaac6b5);
    for (const z of [-0.26, 0.26])
      link(
        rack,
        new THREE.Vector3(-0.4, 0.22, z),
        new THREE.Vector3(0.4, 0.22, z),
        0.018,
        0.018,
        m,
      );
    for (const x of [-0.35, 0.35])
      for (const z of [-0.26, 0.26])
        link(
          rack,
          new THREE.Vector3(x, 0, z),
          new THREE.Vector3(x, 0.25, z),
          0.015,
          0.015,
          m,
        );
    for (let i = 0; i < 6; i++) {
      link(
        rack,
        new THREE.Vector3(-0.3 + i * 0.12, 0.22, -0.26),
        new THREE.Vector3(-0.3 + i * 0.12, 0.22, 0.26),
        0.01,
        0.01,
        m,
      );
      link(
        rack,
        new THREE.Vector3(-0.3 + i * 0.12, 0.24, 0),
        new THREE.Vector3(-0.3 + i * 0.12, 0.4, 0),
        0.012,
        0.006,
        material(0x95bba1),
      );
    }
    reefGroup.add(rack);
  }
  for (const obstacle of s.obstacles || []) {
    if (!obstacle.position && !obstacle.center) continue;
    const p = xyz(obstacle.position || obstacle.center),
      r = obstacle.radius || 0.35;
    sphere(reefGroup, p, r, material(0x4d655a), [1.25, 0.7, 1]);
  }
  state.lastSeed = s.seed;
}
function updateWorld(s) {
  if (state.lastSeed !== s.seed || coralGroups.size !== (s.corals || []).length)
    buildWorld(s);
  for (const c of s.corals || []) {
    const g = coralGroups.get(c.id);
    if (g)
      g.userData.plant.visible = Boolean(
        c.fragment_attached ||
        ["fragment_attached", "verified"].includes(c.task_status),
      );
  }
  for (const r of s.robots || []) {
    const g = robotGroups.get(r.id) || makeRobot(r);
    g.userData.targetPosition = xyz(r.position);
    g.userData.targetYaw = Number(r.yaw || 0);
    g.userData.fragment.visible = !!r.carrying;
    g.userData.arm.rotation.z = [
      "COLLECT",
      "COLLECT_FRAGMENT",
      "ATTACH",
      "PLANT",
      "VERIFY",
      "HARVEST_FRAGMENT",
      "TRANSPLANT_FRAGMENT",
    ].some((x) => r.state?.includes(x))
      ? -0.3
      : 0;
    g.visible = r.available !== false;
    const tr = trailLines.get(r.id);
    if (tr && r.trail?.length > 1) {
      tr.geometry.dispose();
      tr.geometry = new THREE.BufferGeometry().setFromPoints(
        r.trail.slice(-180).map(xyz),
      );
    }
  }
  const vis = Number(s.water?.visibility || 5);
  scene.fog.density = 0.043 + 0.24 / Math.max(1, vis);
  particles.material.opacity = clamp(0.24 + (10 - vis) * 0.035, 0.2, 0.65);
}
function escapeHtml(v) {
  return String(v ?? "").replace(
    /[&<>"']/g,
    (x) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        x
      ],
  );
}
function human(v) {
  return String(v || "Standing by")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (x) => x.toUpperCase());
}
function updateUI(s) {
  const m = s.metrics || {},
    observed = m.observed ?? (s.corals || []).filter((c) => c.observed).length,
    total = m.total_corals ?? s.corals?.length ?? 0;
  let coverage = Number(m.coverage ?? (total ? observed / total : 0));
  if (coverage <= 1) coverage *= 100;
  coverage = clamp(coverage, 0, 100);
  $("coverage-label").textContent = `${Math.round(coverage)}%`;
  $("coverage-bar").style.width = `${coverage}%`;
  $("metric-observed").innerHTML =
    `${String(observed).padStart(2, "0")}<span> / ${total}</span>`;
  $("metric-planted").textContent = String(
    m.verified ?? m.attached ?? 0,
  ).padStart(2, "0");
  $("metric-stock").textContent = String(
    m.inventory ?? s.nursery?.inventory ?? "—",
  ).padStart(2, "0");
  let secs = Math.floor(Number(s.time || 0));
  $("elapsed").textContent =
    `T+ ${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  const isaac = s.mode === "isaac";
  $("rtx-toggle").hidden = !isaac;
  $("rtx-toggle").disabled = !s.runtime?.overview_available && !state.rtx;
  if (isaac && s.runtime?.overview_available && !state.rtxAutoSelected) {
    state.rtxAutoSelected = true;
    setRtxView(true);
  }
  if (!isaac && state.rtx) setRtxView(false);
  updateViewLabels();
  $("robot-list").innerHTML = (s.robots || [])
    .map(
      (r, i) =>
        `<div class="robot-row"><div class="robot-icon">${i ? "⌖" : "◇"}</div><div class="robot-copy"><div class="robot-name">${escapeHtml(String(r.id).toUpperCase())}<span style="color:#718e8c; margin-left:6px; font-size:7px">${r.role === "survey" ? "SURVEY" : "RESTORE"}</span></div><div class="robot-state">${r.available === false ? "Offline" : escapeHtml(human(r.state))}${r.carrying ? " · Fragment secured" : ""}</div></div><span class="robot-led" style="${r.available === false ? "background:#63726d" : ""}"></span></div>`,
    )
    .join("");
  if (!state.draggingInput) {
    $("visibility").value = s.water?.visibility ?? 5;
    $("current").value = Math.hypot(
      ...(s.water?.current || [0, 0]).slice(0, 2),
    );
  }
  $("visibility-value").textContent = Number($("visibility").value).toFixed(1);
  $("current-value").textContent = Number($("current").value).toFixed(2);
  state.paused = !!s.paused;
  $("pause").querySelector(".pause-text").textContent = state.paused
    ? "Resume"
    : "Pause";
  $("pause").querySelector("span").textContent = state.paused ? "▷" : "Ⅱ";
  const ev = s.events?.at(-1);
  $("event-text").textContent =
    typeof ev === "string"
      ? ev
      : ev?.message ||
        ev?.detail ||
        ev?.event ||
        ev?.type ||
        "Survey and restoration mission in progress";
  drawMap(s);
  if (s.runtime?.camera_available) {
    let feed = $("optical-feed");
    if (!feed) {
      feed = document.createElement("section");
      feed.id = "optical-feed";
      feed.className = "optical-feed glass";
      feed.innerHTML =
        '<div class="eyebrow">ROV OPTICAL FEED · ISAAC RTX</div><img alt="Latest underwater camera image from Isaac Sim" />';
      $("mission").appendChild(feed);
    }
    feed.querySelector("img").src =
      `/api/frame.png?t=${Math.floor(s.time * 2)}`;
  } else $("optical-feed")?.remove();
}
function drawMap(s) {
  const c = $("map"),
    ctx = c.getContext("2d"),
    w = c.width,
    h = c.height,
    pad = 27,
    scale = (h - 2 * pad) / 10,
    ox = w / 2,
    oy = h / 2;
  ctx.clearRect(0, 0, w, h);
  const X = (x) => ox + x * scale,
    Y = (y) => oy - y * scale;
  ctx.strokeStyle = "#719b8c18";
  ctx.lineWidth = 1;
  for (let x = -5; x <= 5; x++) {
    ctx.beginPath();
    ctx.moveTo(X(x), Y(-5));
    ctx.lineTo(X(x), Y(5));
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(X(-5), Y(x));
    ctx.lineTo(X(5), Y(x));
    ctx.stroke();
  }
  ctx.strokeStyle = "#92bcab36";
  ctx.strokeRect(X(-5), Y(5), 10 * scale, 10 * scale);
  for (const region of s.regions || []) {
    const p = region.center || [0, 0],
      r = region.radius || 1.7;
    ctx.beginPath();
    ctx.arc(X(p[0]), Y(p[1]), r * scale, 0, Math.PI * 2);
    ctx.fillStyle = String(region.id || "").includes("hazard")
      ? "#e4b7800b"
      : "#8bbaaa07";
    ctx.fill();
    ctx.setLineDash([3, 6]);
    ctx.strokeStyle = "#a5cdb621";
    ctx.stroke();
    ctx.setLineDash([]);
  }
  for (const c of s.corals || []) {
    if (!c.observed) continue;
    const planted = c.fragment_attached || c.task_status === "verified";
    ctx.fillStyle = planted
      ? "#80b8f0"
      : c.health === "healthy"
        ? "#84ded0"
        : c.health === "bleached_alive"
          ? "#e2dfcd"
          : "#e4b780";
    ctx.beginPath();
    ctx.arc(X(c.position[0]), Y(c.position[1]), 4.3, 0, Math.PI * 2);
    ctx.fill();
    if (planted) {
      ctx.strokeStyle = "#80b8f055";
      ctx.beginPath();
      ctx.arc(X(c.position[0]), Y(c.position[1]), 8, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  (s.robots || []).forEach((r, i) => {
    ctx.strokeStyle = i ? "#e4b78077" : "#84ded066";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (let j = 0; j < (r.trail || []).length; j++) {
      const p = r.trail[j];
      j ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]));
    }
    ctx.stroke();
    ctx.save();
    ctx.translate(X(r.position[0]), Y(r.position[1]));
    ctx.rotate(-Number(r.yaw || 0));
    ctx.beginPath();
    ctx.moveTo(8, 0);
    ctx.lineTo(-5, -5);
    ctx.lineTo(-3, 0);
    ctx.lineTo(-5, 5);
    ctx.closePath();
    ctx.fillStyle = i ? "#e4b780" : "#84ded0";
    ctx.fill();
    ctx.restore();
  });
  ctx.fillStyle = "#719b8c";
  ctx.font = "12px monospace";
  ctx.textAlign = "center";
  ctx.fillText("N", ox, Y(5) - 12);
  ctx.fillStyle = "#668a7c";
  ctx.font = "10px monospace";
  ctx.fillText("LOCAL FRAME · METRES", ox, h - 5);
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $("toast").classList.remove("show"), 2600);
}
async function command(body) {
  try {
    const r = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const result = await r.json();
    if (!r.ok || result.ok === false)
      throw new Error(result.error || result.message || "Command rejected");
    await poll();
    return result;
  } catch (e) {
    toast(e.message);
  }
}
function updateViewLabels() {
  const isaac = state.snapshot?.mode === "isaac";
  $("runtime").textContent = state.rtx
    ? "ISAAC RTX · LIVE CAMERA"
    : isaac
      ? "ISAAC SIM 6.0 · TELEMETRY"
      : "PREVIEW RUNTIME · LIVE TELEMETRY";
  $("rtx-toggle").classList.toggle("active", state.rtx);
  $("rtx-toggle").querySelector(".rtx-button-label").textContent = state.rtx
    ? "Explore 3D"
    : "RTX view";
  $("view-badge-title").textContent = state.rtx
    ? "ISAAC RTX CAMERA"
    : "3D PREVIEW";
  $("view-badge-detail").textContent = state.rtx
    ? "Live renderer · approximate seawater optics"
    : "Live mission telemetry · not an RTX camera feed";
  document.querySelector(".scene-label small").textContent = state.rtx
    ? "Processed live camera · approximate seawater optics"
    : "Drag to orbit · scroll to explore";
}
function setRtxView(enabled) {
  state.rtx = !!enabled;
  $("mission").classList.toggle("rtx-active", state.rtx);
  $("rtx-frame").hidden = !state.rtx;
  canvas.style.visibility = state.rtx ? "hidden" : "visible";
  updateViewLabels();
  if (state.rtx) refreshRtxFrame();
}
function refreshRtxFrame() {
  if (!state.rtx || !state.connected || state.rtxPending) return;
  state.rtxPending = true;
  const frame = new Image();
  const timeout = setTimeout(() => fail(), 5000);
  function fail() {
    clearTimeout(timeout);
    frame.onload = frame.onerror = null;
    state.rtxPending = false;
    if (!state.rtx) return;
    setRtxView(false);
    toast("RTX frame unavailable · showing explorable 3D preview");
  }
  frame.onload = () => {
    clearTimeout(timeout);
    state.rtxPending = false;
    if (state.rtx) $("rtx-frame").src = frame.src;
  };
  frame.onerror = fail;
  frame.src = `/api/overview.png?t=${Date.now()}`;
}
$("rtx-toggle").addEventListener("click", () => {
  state.rtxAutoSelected = true;
  setRtxView(!state.rtx);
});
setInterval(refreshRtxFrame, 333);

let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const r = await fetch("/api/state", {
      cache: "no-store",
      signal: AbortSignal.timeout(3500),
    });
    if (!r.ok) throw new Error("Telemetry unavailable");
    const s = await r.json();
    state.snapshot = s;
    state.connected = true;
    $("offline").hidden = true;
    $("connection-dot").classList.remove("disconnected");
    updateWorld(s);
    updateUI(s);
  } catch (e) {
    state.connected = false;
    $("offline").hidden = false;
    $("connection-dot").classList.add("disconnected");
    $("runtime").textContent = "TELEMETRY DISCONNECTED";
  } finally {
    polling = false;
  }
}
$("pause").addEventListener("click", () =>
  command({ action: state.paused ? "resume" : "pause" }),
);
$("reset").addEventListener("click", async () => {
  await command({ action: "reset" });
  toast("Mission reset · same reef, fresh survey");
});
$("overview").addEventListener("click", () => {
  state.follow = false;
  state.cameraTarget.set(0, 0.35, 0);
  state.distance = 13.8;
  state.elevation = 0.34;
  state.azimuth = 0.69;
  $("overview").classList.add("active");
  $("follow").classList.remove("active");
  $("camera-label").textContent = "REEF OVERVIEW";
  if (state.snapshot?.mode === "isaac")
    command({ action: "set_camera", mode: "overview" });
});
$("follow").addEventListener("click", () => {
  state.follow = true;
  state.distance = 3.3;
  state.elevation = 0.15;
  const selected =
    state.snapshot?.robots?.find((r) => r.role === "restoration") ||
    state.snapshot?.robots?.[0];
  if (selected) state.cameraTarget.copy(xyz(selected.position));
  $("follow").classList.add("active");
  $("overview").classList.remove("active");
  $("camera-label").textContent = "RESTORATION VEHICLE";
  if (state.snapshot?.mode === "isaac")
    command({ action: "set_camera", mode: "follow" });
});
for (const id of ["visibility", "current"]) {
  $(id).addEventListener("input", () => {
    state.draggingInput = true;
    $(id + "-value").textContent = Number($(id).value).toFixed(
      id === "visibility" ? 1 : 2,
    );
  });
  $(id).addEventListener("change", async () => {
    const data =
      id === "visibility"
        ? { visibility: Number($(id).value) }
        : { current: [Number($(id).value), 0, 0] };
    await command({ action: "set_water", ...data });
    state.draggingInput = false;
    toast("Water conditions updated");
  });
}
$("about").addEventListener("click", () => $("about-dialog").showModal());
$("close-about").addEventListener("click", () => $("about-dialog").close());
canvas.addEventListener("pointerdown", (e) => {
  state.pointer = { x: e.clientX, y: e.clientY };
  state.dragging = true;
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!state.dragging) return;
  state.azimuth -= (e.clientX - state.pointer.x) * 0.005;
  state.elevation = clamp(
    state.elevation + (e.clientY - state.pointer.y) * 0.004,
    -0.04,
    0.7,
  );
  state.pointer = { x: e.clientX, y: e.clientY };
});
canvas.addEventListener("pointerup", () => (state.dragging = false));
canvas.addEventListener("pointercancel", () => (state.dragging = false));
canvas.addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    state.distance = clamp(state.distance + e.deltaY * 0.009, 1.2, 23);
  },
  { passive: false },
);
function resize() {
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);
resize();
buildEnvironment();
let last = 0;
function animate(t) {
  requestAnimationFrame(animate);
  const dt = Math.min(0.05, (t - last) / 1000 || 0.016);
  last = t;
  const time = clock.getElapsedTime();
  for (const [id, g] of robotGroups) {
    if (g.userData.targetPosition) {
      g.position.lerp(g.userData.targetPosition, 1 - Math.exp(-dt * 10));
      let d =
        (((g.userData.targetYaw || 0) - g.rotation.y + Math.PI * 3) %
          (Math.PI * 2)) -
        Math.PI;
      g.rotation.y += d * (1 - Math.exp(-dt * 8));
    }
  }
  let target = new THREE.Vector3(0, 0.35, 0);
  if (state.follow) {
    const r =
      state.snapshot?.robots?.find((r) => r.role === "restoration") ||
      state.snapshot?.robots?.[0];
    if (r) target = xyz(r.position).add(new THREE.Vector3(0.25, 0, 0));
  }
  state.cameraTarget.lerp(target, 1 - Math.exp(-dt * 3));
  const d = state.distance,
    el = state.elevation;
  camera.position.set(
    state.cameraTarget.x + Math.sin(state.azimuth) * d * Math.cos(el),
    Math.min(7.55, state.cameraTarget.y + Math.sin(el) * d),
    state.cameraTarget.z + Math.cos(state.azimuth) * d * Math.cos(el),
  );
  camera.lookAt(state.cameraTarget);
  const cp = causticPlane.material.map;
  cp.offset.set(Math.sin(time * 0.025) * 0.05, time * 0.004);
  waterSurface.material.opacity = 0.2 + Math.sin(time * 0.1) * 0.015;
  particles.rotation.y = Math.sin(time * 0.01) * 0.025;
  particles.position.x = Math.sin(time * 0.02) * 0.3;
  if (!state.rtx) renderer.render(scene, camera);
}
requestAnimationFrame(animate);
poll();
setInterval(poll, 180);
