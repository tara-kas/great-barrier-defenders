import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import {
  AuvSubsystem,
  computeCarryAwareThrusters,
} from '../domain/reefEngine';
import {
  PelagicRobotId,
  PELAGIC_ROBOT_SPECS,
  summarizeRobotVolumeByGroup,
} from '../domain/pelagicRobotSpec';
import {
  createPelagicRobot3D,
  RobotRenderStyle,
  PelagicRobotRig,
} from './PelagicRobot3D';
import {
  ShieldAlert,
  CheckCircle2,
  Sliders,
  RotateCcw,
  RotateCw,
  Wrench,
  Sparkles,
  Box,
} from 'lucide-react';

interface VehicleSystemsViewProps {
  subsystems: AuvSubsystem[];
  selectedSubsystemId: string;
  onSelectSubsystem: (id: string) => void;
  onRecalibrateThruster: () => void;
  vehiclePos: [number, number, number];
  currentSpeedMs: number;
  holdingFragment: boolean;
  onToggleGripper: () => void;
  navMode: 'Survey' | 'Transplant' | 'Station-Keep';
  onChangeNavMode: (mode: 'Survey' | 'Transplant' | 'Station-Keep') => void;
}

export const VehicleSystemsView: React.FC<VehicleSystemsViewProps> = ({
  subsystems,
  selectedSubsystemId,
  onSelectSubsystem,
  onRecalibrateThruster,
  vehiclePos,
  currentSpeedMs,
  holdingFragment,
  onToggleGripper,
  navMode,
  onChangeNavMode,
}) => {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [robotVariant, setRobotVariant] = useState<PelagicRobotId>('restore-02');
  const [renderStyle, setRenderStyle] = useState<RobotRenderStyle>('hologram');
  const [explodeFactor, setExplodeFactor] = useState<number>(0);
  const [armExtensionPct, setArmExtensionPct] = useState<number>(60);
  const [customDamagedIds, setCustomDamagedIds] = useState<string[]>([]);

  const robotSpec = PELAGIC_ROBOT_SPECS[robotVariant];
  const volumeGroups = summarizeRobotVolumeByGroup(robotVariant);

  const portWarning =
    subsystems.find((s) => s.id === 'sub-thruster-port')?.status === 'Warning';

  const activeWarningIds = [
    ...(portWarning ? ['sub-thruster-port'] : []),
    ...customDamagedIds,
  ];

  const thrusterAllocation = computeCarryAwareThrusters({
    surgeSpeedMs: 0.3,
    currentSpeedMs,
    holdingFragment,
    fragmentMassKg: 0.45,
    portThrusterDegraded: activeWarningIds.includes('sub-thruster-port'),
  });

  const selectedGroup =
    volumeGroups.find((g) => g.subsystemId === selectedSubsystemId) ||
    volumeGroups[0];

  const selectedParts = robotSpec.parts.filter(
    (p) => p.subsystemId === selectedGroup.subsystemId
  );

  const stateRef = useRef({
    robotVariant,
    renderStyle,
    selectedSubsystemId: selectedGroup.subsystemId,
    activeWarningIds,
    explodeFactor,
    armExtensionPct,
    holdingFragment,
    onSelectSubsystem,
  });

  useEffect(() => {
    stateRef.current = {
      robotVariant,
      renderStyle,
      selectedSubsystemId: selectedGroup.subsystemId,
      activeWarningIds,
      explodeFactor,
      armExtensionPct,
      holdingFragment,
      onSelectSubsystem,
    };
  }, [
    robotVariant,
    renderStyle,
    selectedGroup.subsystemId,
    activeWarningIds,
    explodeFactor,
    armExtensionPct,
    holdingFragment,
    onSelectSubsystem,
  ]);

  const controlsRef = useRef<{
    rotateLeft: () => void;
    rotateRight: () => void;
    resetCamera: () => void;
    requestRender: () => void;
  } | null>(null);

  useEffect(() => {
    const container = mountRef.current;
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
    const height = container.clientHeight || 480;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x051017);
    scene.fog = new THREE.FogExp2(0x051017, 0.08);

    const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 40);
    camera.position.set(1.45, 0.92, 1.52);

    const renderer = new THREE.WebGLRenderer({
      antialias: !isSoftwareGl,
      powerPreference: 'high-performance',
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.setPixelRatio(isSoftwareGl ? 1 : Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();

    const hemi = new THREE.HemisphereLight(0x7dd3fc, 0x071824, 1.55);
    scene.add(hemi);
    const key = new THREE.DirectionalLight(0xf8fafc, 2.2);
    key.position.set(3, 5, 4);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x38bdf8, 1.35);
    rim.position.set(-3, 2, -3);
    scene.add(rim);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !isSoftwareGl;
    controls.dampingFactor = 0.08;
    controls.minDistance = 0.75;
    controls.maxDistance = 4.5;
    controls.target.set(0, 0.02, 0);

    // Holographic Projector Pedestal Rings & Polar Grid
    const holoBaseGroup = new THREE.Group();
    holoBaseGroup.position.y = -0.42;

    const polarGrid = new THREE.PolarGridHelper(1.05, 12, 5, 48, 0x1e4963, 0x102a3a);
    holoBaseGroup.add(polarGrid);

    const outerRing = new THREE.Mesh(
      new THREE.RingGeometry(0.82, 0.86, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.45,
      })
    );
    outerRing.position.y = 0.01;
    holoBaseGroup.add(outerRing);

    const innerRing = new THREE.Mesh(
      new THREE.RingGeometry(0.46, 0.49, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({
        color: 0x34d399,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.4,
      })
    );
    innerRing.position.y = 0.012;
    holoBaseGroup.add(innerRing);

    scene.add(holoBaseGroup);

    // Build Exact PELAGIC / Isaac Sim STEP Assembly (SCOUT-01 / RESTORE-02)
    const pelagicRig: PelagicRobotRig = createPelagicRobot3D(
      stateRef.current.robotVariant
    );
    scene.add(pelagicRig.root);

    let frameId = 0;
    let renderBusy = false;
    let renderDirty = false;

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

    function syncScene() {
      const st = stateRef.current;
      pelagicRig.setVariant(st.robotVariant);
      pelagicRig.setPose({
        explodeFactor: st.explodeFactor,
        armExtensionPct: st.armExtensionPct,
        holdingFragment: st.holdingFragment,
      });
      pelagicRig.setRenderStyle(
        st.renderStyle,
        st.selectedSubsystemId,
        st.activeWarningIds
      );
    }

    function requestRender() {
      if (renderBusy) {
        renderDirty = true;
        return;
      }
      renderBusy = true;
      frameId = requestAnimationFrame(() => {
        renderDirty = false;
        syncScene();
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
    let downPt = { x: 0, y: 0 };

    const onPointerDown = (e: PointerEvent) => {
      downPt = { x: e.clientX, y: e.clientY };
    };
    const onPointerUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - downPt.x, e.clientY - downPt.y) > 6) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(pelagicRig.interactables, false);
      if (hits.length > 0 && hits[0].object.userData.subsystemId) {
        stateRef.current.onSelectSubsystem(hits[0].object.userData.subsystemId);
        requestRender();
      }
    };

    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointerup', onPointerUp);

    const onResize = () => {
      if (!container) return;
      const w = container.clientWidth || 720;
      const h = container.clientHeight || 480;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      requestRender();
    };
    window.addEventListener('resize', onResize);

    controlsRef.current = {
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
      resetCamera: () => {
        setExplodeFactor(0);
        controls.target.set(0, 0.02, 0);
        camera.position.set(1.45, 0.92, 1.52);
        requestRender();
      },
      requestRender,
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
    controlsRef.current?.requestRender();
  }, [
    robotVariant,
    renderStyle,
    selectedSubsystemId,
    explodeFactor,
    armExtensionPct,
    holdingFragment,
    portWarning,
    customDamagedIds,
  ]);

  const toggleSimulatedDamage = (subId: string) => {
    setCustomDamagedIds((prev) =>
      prev.includes(subId) ? prev.filter((id) => id !== subId) : [...prev, subId]
    );
  };

  return (
    <div className="space-y-4">
      {/* Clean Single-Row Top Header */}
      <div className="bg-[#0D1A22] border border-[#1B313E] px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Box className="w-4 h-4 text-[#38BDF8]" />
            <h2 className="text-base font-bold text-white tracking-tight">
              3D Hologram Topology & Damage Inspector
            </h2>
          </div>

          {/* Robot Geometry Switcher (RESTORE-02 vs SCOUT-01) */}
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs font-mono">
            {(['restore-02', 'scout-01'] as const).map((vid) => (
              <button
                key={vid}
                type="button"
                onClick={() => setRobotVariant(vid)}
                className={`px-2.5 py-0.5 uppercase cursor-pointer ${
                  robotVariant === vid
                    ? vid === 'restore-02'
                      ? 'bg-[#C8681C] text-white font-semibold'
                      : 'bg-[#0D7A8A] text-white font-semibold'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {vid} ({PELAGIC_ROBOT_SPECS[vid].solid_count} Solids)
              </button>
            ))}
          </div>
        </div>

        {/* Essential Controls Only */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5">
            {(['Survey', 'Transplant', 'Station-Keep'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onChangeNavMode(m)}
                className={`px-2 py-0.5 font-medium cursor-pointer ${
                  navMode === m
                    ? 'bg-[#15394A] text-white'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={onToggleGripper}
            className={`px-2.5 py-1 font-mono border cursor-pointer ${
              holdingFragment
                ? 'bg-[#10332C] border-[#34D399] text-[#6EE7B7]'
                : 'bg-[#091318] border-[#233F4F] text-[#CFE3EE]'
            }`}
          >
            {holdingFragment ? 'Gripper: Holding Coral' : 'Gripper: Open'}
          </button>
        </div>
      </div>

      {/* FRONT-AND-CENTRE HOLOGRAM LAYOUT: LEFT CAD VOLUME GROUPS (3) | CENTER HOLOGRAM MESH INSPECTOR (6) | RIGHT ACTIVE ALERTS ONLY (3) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
        {/* LEFT COLUMN (3 cols): STEP CAD Structural Groups & Volume Graph */}
        <div className="xl:col-span-3 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-4">
          <div className="space-y-2.5">
            <div className="flex items-center justify-between pb-2 border-b border-[#1B313E]">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#38BDF8]">
                STEP Structural Solids ({robotSpec.solid_count})
              </h3>
              <span className="text-[11px] font-mono text-[#8BA6B8]">
                959×676×715 mm
              </span>
            </div>

            <div className="space-y-1.5">
              {volumeGroups.map((grp) => {
                const isSel = grp.subsystemId === selectedGroup.subsystemId;
                const isWarn = activeWarningIds.includes(grp.subsystemId);
                return (
                  <button
                    key={grp.subsystemId}
                    type="button"
                    onClick={() => onSelectSubsystem(grp.subsystemId)}
                    className={`w-full text-left p-2 border transition-colors cursor-pointer ${
                      isSel
                        ? 'bg-[#122D3D] border-[#38BDF8]'
                        : 'bg-[#081218] border-[#162934] hover:border-[#244659]'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-white truncate">
                        {grp.groupLabel}
                      </span>
                      <span
                        className={`font-mono text-[10px] shrink-0 ml-1 ${
                          isWarn ? 'text-[#FBBF24] font-bold' : 'text-[#8BA6B8]'
                        }`}
                      >
                        {isWarn ? '⚠ Alert' : `${grp.partCount} solid${grp.partCount > 1 ? 's' : ''}`}
                      </span>
                    </div>

                    {/* Volume Share Bar */}
                    <div className="h-1.5 bg-[#050C10] mt-1.5 overflow-hidden">
                      <div
                        style={{ width: `${Math.max(5, grp.sharePct)}%` }}
                        className={`h-full ${
                          isWarn
                            ? 'bg-[#FBBF24]'
                            : isSel
                            ? 'bg-[#38BDF8]'
                            : 'bg-[#34D399]/75'
                        }`}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Selected Assembly STEP Solids List */}
          <div className="p-3 bg-[#081218] border border-[#182E3B] space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white truncate">
                {selectedGroup.groupLabel}
              </span>
              <span className="font-mono text-[10px] text-[#38BDF8] shrink-0">
                {selectedGroup.totalVolumeCm3.toLocaleString()} cm³
              </span>
            </div>

            <div className="max-h-28 overflow-y-auto space-y-1 pr-1 font-mono text-[11px]">
              {selectedParts.map((pt) => (
                <div
                  key={pt.name}
                  className="flex items-center justify-between text-[#94B4C7] py-0.5 border-b border-[#11222C]"
                >
                  <span className="truncate text-[#CFE3EE]">{pt.name}</span>
                  <span className="tabular-nums shrink-0 ml-2">
                    {Math.round(pt.volume_mm3 / 1000)} cm³
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* CENTER COLUMN (6 cols — FRONT AND CENTRE): 3D HOLOGRAM & MESH STRUCTURAL INSPECTOR */}
        <div className="xl:col-span-6 bg-[#0D1A22] border-2 border-[#38BDF8]/70 flex flex-col justify-between shadow-lg">
          {/* Hologram Header Controls */}
          <div className="px-4 py-2.5 border-b border-[#1B313E] flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs">
                {(
                  [
                    ['hologram', 'Hologram Mesh'],
                    ['wireframe', 'Wireframe'],
                    ['solid', 'Solid CAD'],
                  ] as const
                ).map(([styleKey, label]) => (
                  <button
                    key={styleKey}
                    type="button"
                    onClick={() => setRenderStyle(styleKey)}
                    className={`px-2.5 py-0.5 font-medium cursor-pointer whitespace-nowrap ${
                      renderStyle === styleKey
                        ? 'bg-[#15394A] text-[#38BDF8] font-semibold'
                        : 'text-[#8BA6B8] hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 bg-[#091318] border border-[#233F4F] px-2.5 py-1 text-xs">
                <Sliders className="w-3.5 h-3.5 text-[#38BDF8]" />
                <label htmlFor="explode-slider" className="text-[#B8CEDC] whitespace-nowrap">
                  Explode
                </label>
                <input
                  id="explode-slider"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={explodeFactor}
                  onChange={(e) => setExplodeFactor(parseFloat(e.target.value))}
                  className="w-16 accent-[#38BDF8] cursor-pointer"
                />
              </div>

              <button
                type="button"
                onClick={() => controlsRef.current?.rotateLeft()}
                title="Rotate left"
                aria-label="Rotate hologram left"
                className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => controlsRef.current?.rotateRight()}
                title="Rotate right"
                aria-label="Rotate hologram right"
                className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                <RotateCw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => controlsRef.current?.resetCamera()}
                className="px-2 py-1 text-[11px] font-mono bg-[#091318] border border-[#233F4F] text-[#94B4C7] hover:text-white cursor-pointer"
              >
                Reset
              </button>
            </div>
          </div>

          {/* Front-and-Centre 3D Hologram Viewport */}
          <div className="relative flex-1 min-h-[430px] bg-[#051017] overflow-hidden">
            <div
              ref={mountRef}
              data-testid="auv-3d-canvas"
              className="w-full h-full cursor-grab active:cursor-grabbing"
            />

            {/* Minimal Top-Left Hologram Spec Badge */}
            <div className="absolute top-3 left-3 bg-[#06131D]/90 border border-[#1E3B4B] px-3 py-1.5 text-xs font-mono space-y-0.5 pointer-events-none">
              <div className="text-white font-bold flex items-center gap-2">
                <span>{robotSpec.label}</span>
                <span className="text-[#38BDF8]">{robotSpec.solid_count} STEP Solids</span>
              </div>
              <div className="text-[11px] text-[#8BA6B8]">
                Selected: <span className="text-[#34D399]">{selectedGroup.groupLabel}</span>
              </div>
            </div>

            {/* Bottom Arm Pose Slider inside Hologram Viewport */}
            <div className="absolute bottom-3 inset-x-3 bg-[#06131D]/90 border border-[#1E3B4B] px-3 py-2 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2 flex-1">
                <span className="font-mono text-[#94B4C7] whitespace-nowrap">
                  Arm Pose ({armExtensionPct}%)
                </span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={armExtensionPct}
                  onChange={(e) => setArmExtensionPct(parseInt(e.target.value, 10))}
                  aria-label="Hologram arm pose slider"
                  className="w-28 accent-[#34D399] cursor-pointer"
                />
              </div>

              <button
                type="button"
                onClick={() => toggleSimulatedDamage(selectedGroup.subsystemId)}
                className={`px-2.5 py-1 font-mono text-[11px] border cursor-pointer ${
                  activeWarningIds.includes(selectedGroup.subsystemId)
                    ? 'bg-[#2E2210] border-[#FBBF24] text-[#FDE68A]'
                    : 'bg-[#09151E] border-[#234356] text-[#7DD3FC] hover:text-white'
                }`}
              >
                {activeWarningIds.includes(selectedGroup.subsystemId)
                  ? 'Clear Damage Flag'
                  : 'Test Damage Highlight'}
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN (3 cols): ACTIVE ALERTS ONLY + THRUSTER LOAD GRAPH */}
        <div className="xl:col-span-3 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-4">
          {/* Active Alerts Only Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#1B313E]">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#FBBF24] flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4 text-[#FBBF24]" />
                Active Alerts ({activeWarningIds.length})
              </h3>
            </div>

            {activeWarningIds.length === 0 ? (
              <div className="p-4 bg-[#081816] border border-[#34D399]/50 text-xs space-y-1.5">
                <div className="font-semibold text-[#34D399] flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  All {robotSpec.solid_count} Solids Nominal
                </div>
                <p className="text-[#94B4C7]">
                  No structural faults or thruster drag alerts detected.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {portWarning && (
                  <div className="p-3.5 bg-[#1D160B] border border-[#FBBF24] space-y-2.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#FDE68A]">
                        Thruster0 / Port Drag
                      </span>
                      <span className="font-mono text-[10px] text-[#FBBF24]">
                        Action Needed
                      </span>
                    </div>
                    <p className="text-[#E6F0F5]">
                      Minor seaweed drag on Port Thruster shroud.
                    </p>
                    <button
                      type="button"
                      onClick={onRecalibrateThruster}
                      className="w-full py-2 px-3 bg-[#FBBF24] hover:bg-[#F59E0B] text-[#091318] font-semibold cursor-pointer flex items-center justify-center gap-1.5"
                    >
                      <Wrench className="w-3.5 h-3.5" />
                      Purge & Fix Thruster
                    </button>
                  </div>
                )}

                {customDamagedIds.map((id) => {
                  const grp = volumeGroups.find((g) => g.subsystemId === id);
                  if (!grp) return null;
                  return (
                    <div
                      key={id}
                      className="p-3 bg-[#1D160B] border border-[#FBBF24]/80 space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#FDE68A]">
                          {grp.groupLabel}
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleSimulatedDamage(id)}
                          className="text-[11px] font-mono text-[#34D399] hover:underline cursor-pointer"
                        >
                          Resolve
                        </button>
                      </div>
                      <p className="text-[#94B4C7]">
                        Highlighted in amber on the 3D hologram mesh.
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Clean Live Thruster & Power Graphs */}
          <div className="space-y-3">
            <div className="p-3 bg-[#081218] border border-[#182E3B] space-y-2.5 text-xs">
              <div className="font-semibold text-white">Thruster Load Balance</div>

              {[
                {
                  label: 'Port (T0/T1)',
                  pct: thrusterAllocation.portForwardPct,
                  warn: activeWarningIds.includes('sub-thruster-port'),
                },
                {
                  label: 'Starboard (T2/T3)',
                  pct: thrusterAllocation.starboardForwardPct,
                  warn: false,
                },
                {
                  label: 'Vertical (V0/V1)',
                  pct: thrusterAllocation.verticalBowPct,
                  warn: false,
                },
              ].map((bar) => (
                <div key={bar.label} className="space-y-1 font-mono text-[11px]">
                  <div className="flex justify-between text-[#94B4C7]">
                    <span>{bar.label}</span>
                    <span className={bar.warn ? 'text-[#FBBF24]' : 'text-white'}>
                      {bar.pct}%
                    </span>
                  </div>
                  <div className="h-2 bg-[#050C10]">
                    <div
                      style={{ width: `${bar.pct}%` }}
                      className={`h-full ${
                        bar.warn ? 'bg-[#FBBF24]' : 'bg-[#38BDF8]'
                      }`}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div className="p-3 bg-[#081218] border border-[#182E3B] grid grid-cols-2 gap-2 text-xs font-mono tabular-nums">
              <div>
                <span className="text-[10px] font-sans text-[#8BA6B8] block">
                  Battery Reserve
                </span>
                <span className="text-sm font-bold text-[#34D399]">84%</span>
              </div>
              <div>
                <span className="text-[10px] font-sans text-[#8BA6B8] block">
                  Operating Depth
                </span>
                <span className="text-sm font-bold text-[#38BDF8]">
                  -{vehiclePos[2].toFixed(1)}m
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
