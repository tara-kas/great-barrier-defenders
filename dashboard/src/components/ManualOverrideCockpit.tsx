import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import {
  CoralCluster,
  computeOptimalClumpHubAndPath,
} from '../domain/reefEngine';
import { PelagicRobotId } from '../domain/pelagicRobotSpec';
import { createPelagicRobot3D } from './PelagicRobot3D';
import {
  toReefWorldXZ,
  getSeabedHeight,
  createDetailedSeabedScene,
  createDetailedCoralCluster3D,
} from './ReefScape3D';
import {
  Gamepad2,
  ShieldAlert,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  RotateCcw,
  RotateCw,
  Sparkles,
  Wrench,
  Camera,
  Video,
} from 'lucide-react';

interface ManualOverrideCockpitProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  onUpdateVehiclePos: (nextPos: [number, number, number]) => void;
  holdingFragment: boolean;
  onSetHoldingFragment: (holding: boolean) => void;
  onTriggerHarvestToClumpSave: (donorId: string, hubId: string) => void;
  onPauseAutoPatrol: () => void;
}

export const ManualOverrideCockpit: React.FC<ManualOverrideCockpitProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  onUpdateVehiclePos,
  holdingFragment,
  onSetHoldingFragment,
  onTriggerHarvestToClumpSave,
  onPauseAutoPatrol,
}) => {
  const sim3dMountRef = useRef<HTMLDivElement | null>(null);
  const liveFeedCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement | null>(null);

  const [robotVariant, setRobotVariant] = useState<PelagicRobotId>('restore-02');
  const [speedMode, setSpeedMode] = useState<'Slow' | 'Normal' | 'Fast'>('Normal');
  const [simCameraMode, setSimCameraMode] = useState<'chase' | 'orbit' | 'claw'>('chase');
  const [feedMode, setFeedMode] = useState<'optical' | 'uv'>('optical');
  const [headingDeg, setHeadingDeg] = useState<number>(42);
  const [armExtensionPct, setArmExtensionPct] = useState<number>(55);
  const [wristPitchDeg, setWristPitchDeg] = useState<number>(-12);
  const [uvLightsOn, setUvLightsOn] = useState<boolean>(true);
  const [webcamActive, setWebcamActive] = useState<boolean>(false);

  // Joy-Con visual stick deflection
  const [leftStick, setLeftStick] = useState<[number, number]>([0, 0]);
  const [rightStick, setRightStick] = useState<[number, number]>([0, 0]);

  const [pendingSafetyCmd, setPendingSafetyCmd] = useState<
    null | 'HOLD' | 'SURFACE' | 'ABORT'
  >(null);

  const clumpPlan = computeOptimalClumpHubAndPath(clusters, 'C-13', [
    'C-03',
    'C-04',
    'C-06',
  ]);

  const stepMultiplier =
    speedMode === 'Fast' ? 1.6 : speedMode === 'Slow' ? 0.45 : 1.0;

  const applyPilotDelta = (
    dSurge: number,
    dStrafe: number,
    dHeave: number,
    dYawDeg: number,
    stickTag: 'left' | 'right'
  ) => {
    onPauseAutoPatrol();

    const nextHeading = (headingDeg + dYawDeg + 360) % 360;
    setHeadingDeg(nextHeading);
    const rad = (nextHeading * Math.PI) / 180;

    const scaledSurge = dSurge * stepMultiplier;
    const scaledStrafe = dStrafe * stepMultiplier;
    const scaledHeave = dHeave * stepMultiplier;

    const dx = Math.cos(rad) * scaledSurge - Math.sin(rad) * scaledStrafe;
    const dy = Math.sin(rad) * scaledSurge + Math.cos(rad) * scaledStrafe;

    const nextX = Number(Math.max(0.4, Math.min(38.5, vehiclePos[0] + dx)).toFixed(2));
    const nextY = Number(Math.max(0.4, Math.min(30.5, vehiclePos[1] + dy)).toFixed(2));
    const nextZ = Number(Math.max(15.5, Math.min(26.5, vehiclePos[2] + scaledHeave)).toFixed(2));

    onUpdateVehiclePos([nextX, nextY, nextZ]);

    if (stickTag === 'left') {
      setLeftStick([
        Math.max(-1, Math.min(1, dStrafe * 1.4)),
        Math.max(-1, Math.min(1, dSurge * 1.4)),
      ]);
      window.setTimeout(() => setLeftStick([0, 0]), 220);
    } else {
      setRightStick([
        Math.max(-1, Math.min(1, dYawDeg / 18)),
        Math.max(-1, Math.min(1, -dHeave * 1.8)),
      ]);
      window.setTimeout(() => setRightStick([0, 0]), 220);
    }
  };

  // Keyboard WASD + Arrow + E/R (arm extend/retract) support
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) return;
      if (e.key === 'w' || e.key === 'W') {
        applyPilotDelta(0.75, 0, 0, 0, 'left');
      } else if (e.key === 's' || e.key === 'S') {
        applyPilotDelta(-0.75, 0, 0, 0, 'left');
      } else if (e.key === 'a' || e.key === 'A') {
        applyPilotDelta(0, 0.75, 0, 0, 'left');
      } else if (e.key === 'd' || e.key === 'D') {
        applyPilotDelta(0, -0.75, 0, 0, 'left');
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        applyPilotDelta(0, 0, -0.4, 0, 'right');
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        applyPilotDelta(0, 0, 0.4, 0, 'right');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        applyPilotDelta(0, 0, 0, -15, 'right');
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        applyPilotDelta(0, 0, 0, 15, 'right');
      } else if (e.key === 'e' || e.key === 'E') {
        setArmExtensionPct((p) => Math.min(100, p + 15));
      } else if (e.key === 'r' || e.key === 'R') {
        setArmExtensionPct((p) => Math.max(0, p - 15));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const toggleWebcam = async () => {
    if (webcamActive) {
      if (webcamVideoRef.current?.srcObject) {
        const tracks = (webcamVideoRef.current.srcObject as MediaStream).getTracks();
        tracks.forEach((t) => t.stop());
      }
      setWebcamActive(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (webcamVideoRef.current) {
        webcamVideoRef.current.srcObject = stream;
        await webcamVideoRef.current.play();
        setWebcamActive(true);
      }
    } catch {
      setWebcamActive(false);
    }
  };

  const simStateRef = useRef({
    clusters,
    selectedClusterId,
    vehiclePos,
    headingDeg,
    armExtensionPct,
    wristPitchDeg,
    holdingFragment,
    simCameraMode,
    feedMode,
    uvLightsOn,
    webcamActive,
    robotVariant,
    onSelectCluster,
  });

  useEffect(() => {
    simStateRef.current = {
      clusters,
      selectedClusterId,
      vehiclePos,
      headingDeg,
      armExtensionPct,
      wristPitchDeg,
      holdingFragment,
      simCameraMode,
      feedMode,
      uvLightsOn,
      webcamActive,
      robotVariant,
      onSelectCluster,
    };
  }, [
    clusters,
    selectedClusterId,
    vehiclePos,
    headingDeg,
    armExtensionPct,
    wristPitchDeg,
    holdingFragment,
    simCameraMode,
    feedMode,
    uvLightsOn,
    webcamActive,
    robotVariant,
    onSelectCluster,
  ]);

  const threeControlsRef = useRef<{
    rotateLeft: () => void;
    rotateRight: () => void;
    resetView: () => void;
    syncScene: () => void;
  } | null>(null);

  // 1. REAL THREE.JS 3D PELAGIC SUBMARINE & REEF SIMULATOR (Center Viewport)
  useEffect(() => {
    const container = sim3dMountRef.current;
    if (!container) return;

    const isSoftwareGl = (() => {
      const probeCanvas = document.createElement('canvas');
      const gl = probeCanvas.getContext('webgl2');
      if (!gl) return true;
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      const param = ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER;
      const gpu = String(gl.getParameter(param));
      gl.getExtension('WEBGL_lose_context')?.loseContext();
      return /SwiftShader|llvmpipe|softpipe|Software|Basic Render/i.test(gpu);
    })();

    const width = container.clientWidth || 720;
    const height = container.clientHeight || 450;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05131d);
    scene.fog = new THREE.FogExp2(0x05131d, 0.014);

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 220);
    camera.position.set(-5.6, 3.6, 5.8);

    const renderer = new THREE.WebGLRenderer({
      antialias: !isSoftwareGl,
      powerPreference: 'high-performance',
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.22;
    renderer.setPixelRatio(isSoftwareGl ? 1 : Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
    pmremGenerator.dispose();

    const hemiLight = new THREE.HemisphereLight(0x38bdf8, 0x071a24, 1.55);
    scene.add(hemiLight);

    const keyLight = new THREE.DirectionalLight(0xe0f2fe, 2.0);
    keyLight.position.set(8, 16, 10);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x34d399, 1.1);
    rimLight.position.set(-10, 6, -8);
    scene.add(rimLight);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !isSoftwareGl;
    controls.dampingFactor = 0.08;
    controls.minDistance = 1.0;
    controls.maxDistance = 65;
    controls.maxPolarAngle = Math.PI * 0.49;

    const { terrainGroup, causticPoints } = createDetailedSeabedScene();
    scene.add(terrainGroup);
    scene.add(causticPoints);

    const clusterEntries = new Map<
      string,
      { root: THREE.Group; ring: THREE.Mesh; hitbox: THREE.Mesh }
    >();
    const interactables: THREE.Object3D[] = [];

    simStateRef.current.clusters.forEach((cluster, cIdx) => {
      const entry = createDetailedCoralCluster3D(cluster, cIdx);
      interactables.push(entry.hitbox);
      scene.add(entry.root);
      clusterEntries.set(cluster.id, {
        root: entry.root,
        ring: entry.selectionRing,
        hitbox: entry.hitbox,
      });
    });

    // Shortest-Path Rescue Arc (C-13 -> C-03) & Clump Spread Arcs (C-03 -> C-04, C-06)
    const arcPairs: Array<[string, string, number]> = [
      ['C-13', 'C-03', 0x38bdf8],
      ['C-03', 'C-04', 0x34d399],
      ['C-03', 'C-06', 0x34d399],
    ];
    arcPairs.forEach(([idA, idB, hex]) => {
      const a = clusterEntries.get(idA);
      const b = clusterEntries.get(idB);
      if (!a || !b) return;
      const pA = a.root.position.clone().add(new THREE.Vector3(0, 0.28, 0));
      const pB = b.root.position.clone().add(new THREE.Vector3(0, 0.28, 0));
      const mid = pA.clone().lerp(pB, 0.5);
      mid.y += 0.85;
      const curve = new THREE.QuadraticBezierCurve3(pA, mid, pB);
      const tube = new THREE.Mesh(
        new THREE.TubeGeometry(curve, 20, 0.028, 6, false),
        new THREE.MeshBasicMaterial({ color: hex, transparent: true, opacity: 0.75 })
      );
      scene.add(tube);
    });

    // Exact PELAGIC / Isaac Sim Robot Geometry (SCOUT-01 / RESTORE-02)
    const pelagicRig = createPelagicRobot3D(simStateRef.current.robotVariant);
    pelagicRig.setRenderStyle('solid');
    pelagicRig.root.scale.setScalar(1.32);

    // 3D UV / Optical Light Cone attached to front of PELAGIC robot
    const uvConeMesh = new THREE.Mesh(
      new THREE.ConeGeometry(0.65, 1.8, 16, 1, true).rotateZ(Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.14,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    uvConeMesh.position.set(1.3, 0, 0);
    pelagicRig.root.add(uvConeMesh);

    const shadowRing = new THREE.Mesh(
      new THREE.RingGeometry(0.35, 0.75, 24).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.45,
      })
    );
    scene.add(shadowRing);
    scene.add(pelagicRig.root);

    let frameId = 0;
    let renderBusy = false;
    let renderDirty = false;
    let lastCameraMode = '';

    function afterDraw(cb: () => void) {
      const gl = renderer.getContext() as WebGL2RenderingContext;
      if (!gl || !gl.fenceSync) {
        frameId = window.setTimeout(cb, 80);
        return;
      }
      const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
      gl.flush();
      const poll = () => {
        const state = sync && gl.getSyncParameter(sync, gl.SYNC_STATUS);
        if (state === gl.UNSIGNALED) {
          frameId = window.setTimeout(poll, 5);
        } else {
          if (sync) gl.deleteSync(sync);
          frameId = window.setTimeout(cb, 80);
        }
      };
      frameId = window.setTimeout(poll, 5);
    }

    function syncSceneState() {
      const st = simStateRef.current;
      const [vx, vz] = toReefWorldXZ(st.vehiclePos[0], st.vehiclePos[1]);
      const floorY = getSeabedHeight(vx, vz);
      const hoverY = floorY + 0.95;
      pelagicRig.root.position.set(vx, hoverY, vz);

      const yawRad = ((st.headingDeg - 90) * Math.PI) / 180;
      pelagicRig.root.rotation.y = yawRad;
      shadowRing.position.set(vx, floorY + 0.04, vz);

      pelagicRig.setVariant(st.robotVariant);
      pelagicRig.setPose({
        armExtensionPct: st.armExtensionPct,
        wristPitchDeg: st.wristPitchDeg,
        holdingFragment: st.holdingFragment,
      });
      uvConeMesh.visible = st.uvLightsOn;

      clusterEntries.forEach((entry, id) => {
        const isSel = id === st.selectedClusterId;
        entry.ring.visible = isSel || id === 'C-13' || id === 'C-03';
        entry.root.scale.setScalar(isSel ? 1.15 : 1.0);
      });

      if (st.simCameraMode === 'chase') {
        controls.target.set(vx, hoverY - 0.15, vz);
        if (lastCameraMode !== 'chase') {
          const backX = vx - Math.cos(yawRad) * 3.8;
          const backZ = vz + Math.sin(yawRad) * 3.8;
          camera.position.set(backX, hoverY + 1.8, backZ);
        }
      } else if (st.simCameraMode === 'claw') {
        const clawWorld = new THREE.Vector3();
        pelagicRig.armAssembly.gripperGroup.getWorldPosition(clawWorld);
        controls.target.copy(clawWorld);
        if (lastCameraMode !== 'claw') {
          camera.position.set(clawWorld.x - 1.3, clawWorld.y + 0.75, clawWorld.z + 1.3);
        }
      }
      lastCameraMode = st.simCameraMode;
    }

    function requestRender() {
      if (renderBusy) {
        renderDirty = true;
        return;
      }
      renderBusy = true;
      frameId = requestAnimationFrame(() => {
        renderDirty = false;
        syncSceneState();
        controls.update();
        renderer.render(scene, camera);
        const done = () => {
          renderBusy = false;
          if (renderDirty) requestRender();
        };
        if (isSoftwareGl) afterDraw(done);
        else done();
      });
    }

    controls.addEventListener('change', requestRender);

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let downPos = { x: 0, y: 0 };

    const onPointerDown = (e: PointerEvent) => {
      downPos = { x: e.clientX, y: e.clientY };
    };
    const onPointerUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 6) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(interactables, false);
      if (hits.length > 0 && hits[0].object.userData.clusterId) {
        simStateRef.current.onSelectCluster(hits[0].object.userData.clusterId);
        requestRender();
      }
    };

    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointerup', onPointerUp);

    const onResize = () => {
      if (!container) return;
      const w = container.clientWidth || 720;
      const h = container.clientHeight || 450;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      requestRender();
    };
    window.addEventListener('resize', onResize);

    threeControlsRef.current = {
      rotateLeft: () => {
        const offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 6);
        camera.position.copy(controls.target).add(offset);
        requestRender();
      },
      rotateRight: () => {
        const offset = camera.position.clone().sub(controls.target);
        offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), -Math.PI / 6);
        camera.position.copy(controls.target).add(offset);
        requestRender();
      },
      resetView: () => {
        lastCameraMode = '';
        setSimCameraMode('chase');
        requestRender();
      },
      syncScene: () => {
        requestRender();
      },
    };

    if (!isSoftwareGl) {
      renderer.compile(scene, camera);
    }
    requestRender();

    return () => {
      cancelAnimationFrame(frameId);
      clearTimeout(frameId);
      window.removeEventListener('resize', onResize);
      renderer.domElement.removeEventListener('pointerdown', onPointerDown);
      renderer.domElement.removeEventListener('pointerup', onPointerUp);
      controls.dispose();
      renderer.dispose();
    };
  }, []);

  useEffect(() => {
    threeControlsRef.current?.syncScene();
  }, [
    vehiclePos,
    headingDeg,
    armExtensionPct,
    wristPitchDeg,
    holdingFragment,
    simCameraMode,
    uvLightsOn,
    robotVariant,
    selectedClusterId,
  ]);

  // 2. LIVE 3D FIRST-PERSON BOW CAMERA FEED (Right Column Live Feed)
  useEffect(() => {
    const canvas = liveFeedCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let timerId = 0;
    let tick = 0;

    const renderLiveFeed = () => {
      tick += 1;
      const st = simStateRef.current;
      const w = canvas.width;
      const h = canvas.height;

      if (st.webcamActive && webcamVideoRef.current && webcamVideoRef.current.readyState >= 2) {
        ctx.drawImage(webcamVideoRef.current, 0, 0, w, h);
        ctx.fillStyle = 'rgba(6, 24, 38, 0.28)';
        ctx.fillRect(0, 0, w, h);
      } else {
        const skyGrad = ctx.createLinearGradient(0, 0, 0, h);
        if (st.feedMode === 'uv') {
          skyGrad.addColorStop(0, '#040F1E');
          skyGrad.addColorStop(0.55, '#09243C');
          skyGrad.addColorStop(1, '#04121E');
        } else {
          skyGrad.addColorStop(0, '#072235');
          skyGrad.addColorStop(0.55, '#0B334B');
          skyGrad.addColorStop(1, '#061A28');
        }
        ctx.fillStyle = skyGrad;
        ctx.fillRect(0, 0, w, h);

        for (let i = 0; i < 4; i++) {
          const bx = ((i * 110 + tick * 0.6) % (w + 120)) - 60;
          const beam = ctx.createLinearGradient(bx, 0, bx + 60, h * 0.75);
          beam.addColorStop(0, 'rgba(56, 189, 248, 0.12)');
          beam.addColorStop(1, 'rgba(56, 189, 248, 0)');
          ctx.fillStyle = beam;
          ctx.beginPath();
          ctx.moveTo(bx, 0);
          ctx.lineTo(bx + 45, 0);
          ctx.lineTo(bx + 105, h * 0.8);
          ctx.lineTo(bx + 25, h * 0.8);
          ctx.closePath();
          ctx.fill();
        }

        const horizonY = h * 0.44;
        const floorGrad = ctx.createLinearGradient(0, horizonY, 0, h);
        floorGrad.addColorStop(0, '#082233');
        floorGrad.addColorStop(1, '#04121C');
        ctx.fillStyle = floorGrad;
        ctx.beginPath();
        ctx.moveTo(0, horizonY);
        for (let x = 0; x <= w; x += 40) {
          const wave = Math.sin(x * 0.03 + st.headingDeg * 0.05) * 8;
          ctx.lineTo(x, horizonY + wave);
        }
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fill();

        const [vx, vy] = st.vehiclePos;
        const headingRad = (st.headingDeg * Math.PI) / 180;
        const fwdX = Math.cos(headingRad);
        const fwdY = Math.sin(headingRad);
        const rightX = Math.sin(headingRad);
        const rightY = -Math.cos(headingRad);

        const visibleCorals = st.clusters
          .map((c) => {
            const dx = c.localX - vx;
            const dy = c.localY - vy;
            const forwardDist = dx * fwdX + dy * fwdY;
            const sideOffset = dx * rightX + dy * rightY;
            const totalDist = Math.hypot(dx, dy);
            return { c, forwardDist, sideOffset, totalDist };
          })
          .filter((item) => item.totalDist < 12)
          .sort((a, b) => b.totalDist - a.totalDist);

        visibleCorals.forEach(({ c, forwardDist, sideOffset, totalDist }) => {
          const effZ = Math.max(0.9, forwardDist + 2.2);
          const screenX = w * 0.5 + (sideOffset / effZ) * 145;
          const screenY = horizonY + 18 + (1.8 / effZ) * 95;
          if (screenX < -40 || screenX > w + 40) return;

          const r = Math.max(10, Math.min(44, (c.boundsM[0] * 48) / effZ));
          const col =
            c.status === 'Living'
              ? '#34D399'
              : c.status === 'Placed'
              ? '#38BDF8'
              : c.status === 'Bleached'
              ? '#FBBF24'
              : '#F87171';

          ctx.fillStyle = 'rgba(2, 8, 14, 0.55)';
          ctx.beginPath();
          ctx.ellipse(screenX, screenY + r * 0.32, r * 1.1, r * 0.42, 0, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = col;
          ctx.strokeStyle = c.id === st.selectedClusterId ? '#FFFFFF' : '#05131D';
          ctx.lineWidth = c.id === st.selectedClusterId ? 2 : 1;

          if (c.morphology === 'staghorn') {
            for (let b = -2; b <= 2; b++) {
              ctx.beginPath();
              ctx.moveTo(screenX + b * (r * 0.15), screenY + 4);
              ctx.lineTo(screenX + b * (r * 0.42), screenY - r * (0.9 + (Math.abs(b) % 2) * 0.2));
              ctx.strokeStyle = col;
              ctx.lineWidth = Math.max(2.5, r * 0.16);
              ctx.lineCap = 'round';
              ctx.stroke();
            }
          } else {
            for (let lobe = 0; lobe < 4; lobe++) {
              const lx = screenX + (lobe - 1.5) * r * 0.28;
              const ly = screenY - (lobe % 2) * r * 0.22;
              ctx.beginPath();
              ctx.arc(lx, ly, r * 0.48, 0, Math.PI * 2);
              ctx.fill();
              ctx.stroke();
            }
          }

          if (c.id === st.selectedClusterId || c.id === 'C-13' || c.id === 'C-03') {
            ctx.strokeStyle = col;
            ctx.lineWidth = 1.4;
            ctx.strokeRect(screenX - r - 4, screenY - r - 6, r * 2 + 8, r * 1.5 + 10);
            ctx.fillStyle = 'rgba(5, 16, 24, 0.85)';
            ctx.fillRect(screenX - r - 4, screenY - r - 20, 68, 14);
            ctx.fillStyle = '#FFFFFF';
            ctx.font = '600 10px "JetBrains Mono", monospace';
            ctx.fillText(`${c.id} ${totalDist.toFixed(1)}m`, screenX - r, screenY - r - 10);
          }
        });
      }

      // PELAGIC Articulated ArmUpper (Orange/Teal) + Silver ArmFore + Black Gripper in Live Bow Feed
      const reachPx = 28 + (st.armExtensionPct / 100) * 68;
      const clawX = w * 0.52;
      const clawY = h - reachPx;

      // Colored ArmUpper from right side
      ctx.strokeStyle = st.robotVariant === 'restore-02' ? '#C8681C' : '#0D7A8A';
      ctx.lineWidth = 10;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(w * 0.84, h + 6);
      ctx.lineTo(w * 0.72, clawY + 34);
      ctx.stroke();

      // Silver ArmFore folding to center-front Gripper
      ctx.strokeStyle = '#DBE4E8';
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(w * 0.72, clawY + 34);
      ctx.lineTo(clawX, clawY);
      ctx.stroke();

      // Black Gripper Jaws & SoftPads
      const jawGap = st.holdingFragment ? 9 : 18;
      ctx.strokeStyle = '#111820';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(clawX, clawY);
      ctx.lineTo(clawX - jawGap, clawY - 18);
      ctx.moveTo(clawX, clawY);
      ctx.lineTo(clawX + jawGap, clawY - 18);
      ctx.stroke();

      if (st.holdingFragment) {
        ctx.fillStyle = '#34D399';
        ctx.strokeStyle = '#A7F3D0';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(clawX, clawY - 14, 9, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }

      // Optical Dome Crosshair
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(w * 0.5, h * 0.48, 18, 0, Math.PI * 2);
      ctx.stroke();

      timerId = window.setTimeout(renderLiveFeed, 95);
    };

    renderLiveFeed();
    return () => clearTimeout(timerId);
  }, []);

  return (
    <div className="space-y-4">
      <video ref={webcamVideoRef} className="hidden" playsInline muted />

      {/* Clean Single-Row Top Header */}
      <div className="bg-[#0D1A22] border border-[#1B313E] px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Gamepad2 className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="text-base font-bold text-white tracking-tight">
              Manual Submarine Sim
            </h2>
          </div>

          {/* Robot Variant Toggle (RESTORE-02 / SCOUT-01) */}
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs font-mono">
            {(['restore-02', 'scout-01'] as const).map((vid) => (
              <button
                key={vid}
                type="button"
                onClick={() => setRobotVariant(vid)}
                className={`px-2 py-0.5 uppercase cursor-pointer ${
                  robotVariant === vid
                    ? vid === 'restore-02'
                      ? 'bg-[#C8681C] text-white font-semibold'
                      : 'bg-[#0D7A8A] text-white font-semibold'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {vid}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Speed Selector */}
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs">
            {(['Slow', 'Normal', 'Fast'] as const).map((spd) => (
              <button
                key={spd}
                type="button"
                onClick={() => setSpeedMode(spd)}
                className={`px-2 py-0.5 font-medium cursor-pointer ${
                  speedMode === spd
                    ? 'bg-[#15394A] text-white'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {spd}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => {
              onTriggerHarvestToClumpSave(clumpPlan.donorClusterId, clumpPlan.optimalHubId);
            }}
            className="px-2.5 py-1 text-xs font-semibold bg-[#0F312B] hover:bg-[#15443C] border border-[#34D399] text-[#6EE7B7] cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Auto-Rescue (C-13 → C-03)
          </button>

          <button
            type="button"
            onClick={() => setPendingSafetyCmd('HOLD')}
            className="px-2.5 py-1 text-xs font-medium bg-[#162430] hover:bg-[#1E3242] border border-[#475569] text-white cursor-pointer"
          >
            Hold
          </button>
          <button
            type="button"
            onClick={() => setPendingSafetyCmd('SURFACE')}
            className="px-2.5 py-1 text-xs font-medium bg-[#2B2010] hover:bg-[#3D2E16] border border-[#FBBF24]/70 text-[#FDE68A] cursor-pointer"
          >
            Surface
          </button>
          <button
            type="button"
            onClick={() => setPendingSafetyCmd('ABORT')}
            className="px-2.5 py-1 text-xs font-medium bg-[#351218] hover:bg-[#4A1922] border border-[#F87171]/80 text-[#FCA5A5] cursor-pointer"
          >
            Abort
          </button>
        </div>
      </div>

      {/* Safety Confirmation Bar */}
      {pendingSafetyCmd && (
        <div className="bg-[#1C140D] border border-[#FBBF24] px-4 py-2.5 flex items-center justify-between gap-4 text-xs">
          <span className="text-[#FDE68A] flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            Confirm {pendingSafetyCmd} command?
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                onPauseAutoPatrol();
                if (pendingSafetyCmd === 'ABORT') {
                  setArmExtensionPct(0);
                  onSetHoldingFragment(false);
                } else if (pendingSafetyCmd === 'SURFACE') {
                  onUpdateVehiclePos([vehiclePos[0], vehiclePos[1], 16.0]);
                }
                setPendingSafetyCmd(null);
              }}
              className="px-3 py-1 font-semibold bg-[#FBBF24] text-[#091318] cursor-pointer"
            >
              Confirm {pendingSafetyCmd}
            </button>
            <button
              type="button"
              onClick={() => setPendingSafetyCmd(null)}
              className="px-2.5 py-1 bg-[#091318] border border-[#334155] text-[#CFE3EE] cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* CLEAN 3-COLUMN LAYOUT: LEFT JOY-CON & ARM (3) | 3D PELAGIC SUBMARINE SIMULATOR (6) | LIVE BOW CAMERA FEED & RIGHT JOY-CON (3) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
        {/* LEFT COLUMN (3 cols): Joy-Con (L) Horizontal Move + Robotic Arm & Gripper */}
        <div className="xl:col-span-3 bg-[#0B1922] border border-[#23475C] p-4 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#193545]">
              <span className="text-xs font-bold text-[#38BDF8] tracking-wide">
                JOY-CON (L) · MOVE
              </span>
              <span className="text-[11px] font-mono text-[#8BA6B8]">WASD</span>
            </div>

            <div className="grid grid-cols-3 gap-2 max-w-[210px] mx-auto">
              <div />
              <button
                type="button"
                onClick={() => applyPilotDelta(0.75, 0, 0, 0, 'left')}
                aria-label="Surge forward"
                className="p-2.5 bg-[#102E40] hover:bg-[#163F57] border border-[#38BDF8] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowUp className="w-4 h-4 text-[#38BDF8]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">W</span>
              </button>
              <div />

              <button
                type="button"
                onClick={() => applyPilotDelta(0, 0.75, 0, 0, 'left')}
                aria-label="Strafe port left"
                className="p-2.5 bg-[#102E40] hover:bg-[#163F57] border border-[#38BDF8] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowLeft className="w-4 h-4 text-[#38BDF8]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">A</span>
              </button>

              <div className="p-2 bg-[#061017] border border-[#23485E] flex items-center justify-center">
                <div
                  className="w-6 h-6 rounded-full bg-[#38BDF8] border-2 border-white transition-transform"
                  style={{
                    transform: `translate(${leftStick[0] * 8}px, ${-leftStick[1] * 8}px)`,
                  }}
                />
              </div>

              <button
                type="button"
                onClick={() => applyPilotDelta(0, -0.75, 0, 0, 'left')}
                aria-label="Strafe starboard right"
                className="p-2.5 bg-[#102E40] hover:bg-[#163F57] border border-[#38BDF8] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowRight className="w-4 h-4 text-[#38BDF8]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">D</span>
              </button>

              <div />
              <button
                type="button"
                onClick={() => applyPilotDelta(-0.75, 0, 0, 0, 'left')}
                aria-label="Reverse aft"
                className="p-2.5 bg-[#102E40] hover:bg-[#163F57] border border-[#38BDF8] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowDown className="w-4 h-4 text-[#38BDF8]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">S</span>
              </button>
              <div />
            </div>
          </div>

          {/* 3D Robotic Arm & Gripper Controls */}
          <div className="p-3 bg-[#071219] border border-[#1E3B4B] space-y-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white flex items-center gap-1.5">
                <Wrench className="w-3.5 h-3.5 text-[#38BDF8]" />
                Robotic Arm
              </span>
              <span className="font-mono font-bold text-[#34D399] tabular-nums">
                {armExtensionPct}%
              </span>
            </div>

            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={armExtensionPct}
              onChange={(e) => setArmExtensionPct(parseInt(e.target.value, 10))}
              aria-label="Robotic arm extension percentage"
              className="w-full accent-[#38BDF8] cursor-pointer"
            />

            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => setArmExtensionPct(0)}
                className="py-1.5 px-2 bg-[#112634] hover:bg-[#183548] border border-[#38BDF8]/50 text-white font-mono text-[11px] cursor-pointer"
              >
                ◀ Retract
              </button>
              <button
                type="button"
                onClick={() => setArmExtensionPct(95)}
                className="py-1.5 px-2 bg-[#112634] hover:bg-[#183548] border border-[#38BDF8]/50 text-white font-mono text-[11px] cursor-pointer"
              >
                Extend ▶
              </button>
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                onClick={() => setWristPitchDeg((p) => Math.max(-45, p - 10))}
                className="py-1 px-2 bg-[#0B1C26] border border-[#1E3B4B] text-[#94B4C7] hover:text-white font-mono text-[10px] cursor-pointer"
              >
                Tilt Down ({wristPitchDeg}°)
              </button>
              <button
                type="button"
                onClick={() => setWristPitchDeg((p) => Math.min(25, p + 10))}
                className="py-1 px-2 bg-[#0B1C26] border border-[#1E3B4B] text-[#94B4C7] hover:text-white font-mono text-[10px] cursor-pointer"
              >
                Tilt Up (+10°)
              </button>
            </div>

            <button
              type="button"
              onClick={() => {
                const nextHold = !holdingFragment;
                onSetHoldingFragment(nextHold);
                setArmExtensionPct(nextHold ? 65 : 85);
              }}
              className={`w-full py-2 px-3 font-semibold text-xs border cursor-pointer transition-colors ${
                holdingFragment
                  ? 'bg-[#10332B] border-[#34D399] text-[#6EE7B7]'
                  : 'bg-[#122E3E] border-[#38BDF8] text-white'
              }`}
            >
              {holdingFragment ? 'Release Coral' : 'Pick Up Coral'}
            </button>
          </div>
        </div>

        {/* CENTER COLUMN (6 cols): REAL THREE.JS 3D PELAGIC SUBMARINE & REEF SIMULATOR */}
        <div className="xl:col-span-6 bg-[#0D1A22] border border-[#1B313E] flex flex-col">
          {/* Compact 3D Header */}
          <div className="px-4 py-2.5 border-b border-[#1B313E] flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <h3 className="text-sm font-semibold text-white">3D Submarine & Reef Sim</h3>
              <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs">
                {(
                  [
                    ['chase', '3D Chase'],
                    ['orbit', '3D Orbit'],
                    ['claw', '3D Claw'],
                  ] as const
                ).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSimCameraMode(mode)}
                    className={`px-2 py-0.5 font-medium cursor-pointer whitespace-nowrap ${
                      simCameraMode === mode
                        ? 'bg-[#15394A] text-white'
                        : 'text-[#8BA6B8] hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setUvLightsOn((u) => !u)}
                className={`px-2 py-1 text-[11px] font-mono border cursor-pointer ${
                  uvLightsOn
                    ? 'bg-[#10332C] border-[#34D399]/60 text-[#6EE7B7]'
                    : 'bg-[#091318] border-[#233F4F] text-[#94B4C7]'
                }`}
              >
                UV {uvLightsOn ? 'ON' : 'OFF'}
              </button>
              <button
                type="button"
                onClick={() => threeControlsRef.current?.rotateLeft()}
                title="Orbit 3D view left"
                aria-label="Orbit 3D simulator left"
                className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => threeControlsRef.current?.rotateRight()}
                title="Orbit 3D view right"
                aria-label="Orbit 3D simulator right"
                className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                <RotateCw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => threeControlsRef.current?.resetView()}
                className="px-2 py-1 text-[11px] font-mono bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                Reset
              </button>
            </div>
          </div>

          {/* Full Unobstructed 3D WebGL Viewport */}
          <div className="relative flex-1 min-h-[430px] bg-[#05131D] overflow-hidden">
            <div
              ref={sim3dMountRef}
              data-testid="manual-override-sim-canvas"
              className="w-full h-full cursor-grab active:cursor-grabbing"
            />

            {/* Single Clean Top-Left Position Badge */}
            <div className="absolute top-2.5 left-2.5 bg-[#06131D]/90 border border-[#1E3B4B] px-2.5 py-1 text-[11px] font-mono text-[#CFE3EE] tabular-nums flex items-center gap-2 pointer-events-none">
              <span className="text-[#38BDF8] font-bold uppercase">{robotVariant}</span>
              <span>X {vehiclePos[0].toFixed(1)}m</span>
              <span>Y {vehiclePos[1].toFixed(1)}m</span>
              <span className="text-[#34D399]">-{vehiclePos[2].toFixed(1)}m</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN (3 cols): LIVE BOW CAMERA FEED + JOY-CON (R) DEPTH & TURN */}
        <div className="xl:col-span-3 bg-[#0B1922] border border-[#23475C] p-4 flex flex-col justify-between space-y-4">
          {/* Top Half: Live Bow Camera Feed */}
          <div className="space-y-2">
            <div className="flex items-center justify-between pb-1.5 border-b border-[#193545]">
              <span className="text-xs font-bold text-white flex items-center gap-1.5">
                <Video className="w-3.5 h-3.5 text-[#34D399]" />
                Live Bow Camera
              </span>

              <div className="flex items-center gap-1 text-[10px] font-mono">
                {(['optical', 'uv'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setFeedMode(m)}
                    className={`px-1.5 py-0.5 border cursor-pointer uppercase ${
                      feedMode === m
                        ? 'bg-[#143748] border-[#38BDF8] text-white'
                        : 'bg-[#071219] border-[#1A3342] text-[#8BA6B8]'
                    }`}
                  >
                    {m}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={toggleWebcam}
                  title="Toggle live webcam feed"
                  aria-label="Toggle live webcam feed"
                  className={`p-1 border cursor-pointer ${
                    webcamActive
                      ? 'bg-[#10332C] border-[#34D399] text-[#6EE7B7]'
                      : 'bg-[#071219] border-[#1A3342] text-[#8BA6B8] hover:text-white'
                  }`}
                >
                  <Camera className="w-3 h-3" />
                </button>
              </div>
            </div>

            <div className="relative h-48 bg-[#041019] border border-[#1E3B4B] overflow-hidden">
              <canvas
                ref={liveFeedCanvasRef}
                width={320}
                height={192}
                className="w-full h-full block"
              />
              <div className="absolute top-1.5 left-2 text-[10px] font-mono text-[#7DD3FC] bg-[#05121B]/85 px-1.5 py-0.5">
                HDG {Math.round(headingDeg)}°
              </div>
            </div>
          </div>

          {/* Bottom Half: Joy-Con (R) Vertical Depth & Turn */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between pb-1.5 border-b border-[#193545]">
              <span className="text-xs font-bold text-[#34D399] tracking-wide">
                JOY-CON (R) · DEPTH & TURN
              </span>
              <span className="text-[11px] font-mono text-[#8BA6B8]">Arrows</span>
            </div>

            <div className="grid grid-cols-3 gap-2 max-w-[210px] mx-auto">
              <div />
              <button
                type="button"
                onClick={() => applyPilotDelta(0, 0, -0.45, 0, 'right')}
                aria-label="Ascend heave up"
                className="p-2.5 bg-[#0F2E28] hover:bg-[#164239] border border-[#34D399] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowUp className="w-4 h-4 text-[#34D399]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">UP</span>
              </button>
              <div />

              <button
                type="button"
                onClick={() => applyPilotDelta(0, 0, 0, -18, 'right')}
                aria-label="Yaw rotate counter-clockwise"
                className="p-2.5 bg-[#0F2E28] hover:bg-[#164239] border border-[#34D399] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <RotateCcw className="w-4 h-4 text-[#34D399]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">TURN L</span>
              </button>

              <div className="p-2 bg-[#061017] border border-[#1F4E42] flex items-center justify-center">
                <div
                  className="w-6 h-6 rounded-full bg-[#34D399] border-2 border-white transition-transform"
                  style={{
                    transform: `translate(${rightStick[0] * 8}px, ${-rightStick[1] * 8}px)`,
                  }}
                />
              </div>

              <button
                type="button"
                onClick={() => applyPilotDelta(0, 0, 0, 18, 'right')}
                aria-label="Yaw rotate clockwise"
                className="p-2.5 bg-[#0F2E28] hover:bg-[#164239] border border-[#34D399] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <RotateCw className="w-4 h-4 text-[#34D399]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">TURN R</span>
              </button>

              <div />
              <button
                type="button"
                onClick={() => applyPilotDelta(0, 0, 0.45, 0, 'right')}
                aria-label="Descend heave down"
                className="p-2.5 bg-[#0F2E28] hover:bg-[#164239] border border-[#34D399] text-white flex flex-col items-center justify-center cursor-pointer active:scale-95"
              >
                <ArrowDown className="w-4 h-4 text-[#34D399]" />
                <span className="text-[10px] font-mono font-bold mt-0.5">DOWN</span>
              </button>
              <div />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
