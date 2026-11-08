import * as THREE from 'three';
import { PelagicRobotId } from '../domain/pelagicRobotSpec';

export type RobotRenderStyle = 'hologram' | 'solid' | 'wireframe';

export interface PelagicRobotRig {
  root: THREE.Group;
  partGroups: Map<
    string,
    {
      group: THREE.Group;
      basePos: THREE.Vector3;
      explodeDir: THREE.Vector3;
      meshes: THREE.Mesh[];
      wireframes: THREE.LineSegments[];
      baseColors: number[];
    }
  >;
  interactables: THREE.Object3D[];
  armAssembly: {
    shoulderGroup: THREE.Group;
    upperArmMesh: THREE.Mesh;
    elbowGroup: THREE.Group;
    forearmGroup: THREE.Group;
    gripperGroup: THREE.Group;
    jawLeft: THREE.Mesh;
    jawRight: THREE.Mesh;
    heldCoralMesh: THREE.Mesh;
    multispectralPod: THREE.Group;
  };
  buoyancyMesh: THREE.Mesh;
  beaconSphere: THREE.Mesh;
  setVariant: (variant: PelagicRobotId) => void;
  setRenderStyle: (
    style: RobotRenderStyle,
    selectedSubsystemId?: string,
    warningSubsystemIds?: string[]
  ) => void;
  setPose: (opts: {
    explodeFactor?: number;
    armExtensionPct?: number;
    wristPitchDeg?: number;
    holdingFragment?: boolean;
  }) => void;
}

/**
 * Builds the exact PELAGIC / Isaac Sim STEP Robot Geometry (SCOUT-01 & RESTORE-02)
 * matching `reefsim/isaac_scene.py` (958.52 × 676.0 × 715.0 mm, 50/52 solids).
 */
export function createPelagicRobot3D(initialVariant: PelagicRobotId = 'restore-02'): PelagicRobotRig {
  const root = new THREE.Group();
  const partGroups = new Map<
    string,
    {
      group: THREE.Group;
      basePos: THREE.Vector3;
      explodeDir: THREE.Vector3;
      meshes: THREE.Mesh[];
      wireframes: THREE.LineSegments[];
      baseColors: number[];
    }
  >();
  const interactables: THREE.Object3D[] = [];

  const registerSubsystem = (
    subId: string,
    basePos: [number, number, number],
    explodeDir: [number, number, number],
    builder: (
      g: THREE.Group,
      addMesh: (geo: THREE.BufferGeometry, hexColor: number, roughness?: number, metalness?: number) => THREE.Mesh
    ) => void
  ) => {
    const g = new THREE.Group();
    g.position.set(...basePos);
    const meshes: THREE.Mesh[] = [];
    const wireframes: THREE.LineSegments[] = [];
    const baseColors: number[] = [];

    const addMesh = (
      geo: THREE.BufferGeometry,
      hexColor: number,
      roughness = 0.38,
      metalness = 0.55
    ) => {
      const mat = new THREE.MeshStandardMaterial({
        color: hexColor,
        roughness,
        metalness,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.userData.subsystemId = subId;

      // Hologram / CAD structural edge overlay
      const edgeGeo = new THREE.EdgesGeometry(geo, 22);
      const edgeMat = new THREE.LineBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.55,
      });
      const wire = new THREE.LineSegments(edgeGeo, edgeMat);
      mesh.add(wire);

      meshes.push(mesh);
      wireframes.push(wire);
      baseColors.push(hexColor);
      interactables.push(mesh);
      return mesh;
    };

    builder(g, addMesh);
    root.add(g);
    partGroups.set(subId, {
      group: g,
      basePos: new THREE.Vector3(...basePos),
      explodeDir: new THREE.Vector3(...explodeDir),
      meshes,
      wireframes,
      baseColors,
    });
  };

  // Scale: 1.0 Three.js unit = 1,000 mm (1 metre)
  // Bounding box: X = 0.9585 m (-0.48 to +0.48), Z = 0.676 m (-0.338 to +0.338), Y = 0.715 m (-0.32 to +0.39)
  const frameX = 0.46;
  const frameZ = 0.32;
  const frameTopY = 0.25;
  const frameBotY = -0.22;
  const tubeRad = 0.017;

  // 1. TUBULAR EXOSKELETON FRAME CAGE (12 struts: FrameLong00..11, FrameCross00..11, FrameUpright00..11)
  registerSubsystem('sub-frame', [0, 0, 0], [0, 0.42, 0], (g, addMesh) => {
    const frameHex = 0x26353d;
    // 4 Longitudinal bars (FrameLong00, 01, 10, 11)
    [
      [frameBotY, -frameZ],
      [frameBotY, frameZ],
      [frameTopY, -frameZ],
      [frameTopY, frameZ],
    ].forEach(([y, z]) => {
      const bar = addMesh(
        new THREE.CylinderGeometry(tubeRad, tubeRad, frameX * 2, 12).rotateZ(Math.PI / 2),
        frameHex,
        0.45,
        0.75
      );
      bar.position.set(0, y, z);
      g.add(bar);
    });

    // 4 Crossbars (FrameCross00, 01, 10, 11)
    [
      [-frameX, frameBotY],
      [frameX, frameBotY],
      [-frameX, frameTopY],
      [frameX, frameTopY],
    ].forEach(([x, y]) => {
      const cross = addMesh(
        new THREE.CylinderGeometry(tubeRad, tubeRad, frameZ * 2, 12).rotateX(Math.PI / 2),
        frameHex,
        0.45,
        0.75
      );
      cross.position.set(x, y, 0);
      g.add(cross);
    });

    // 4 Corner Vertical Uprights (FrameUpright00, 01, 10, 11)
    const uprightH = frameTopY - frameBotY;
    [
      [-frameX, -frameZ],
      [-frameX, frameZ],
      [frameX, -frameZ],
      [frameX, frameZ],
    ].forEach(([x, z]) => {
      const post = addMesh(
        new THREE.CylinderGeometry(tubeRad * 1.05, tubeRad * 1.05, uprightH, 12),
        frameHex,
        0.45,
        0.75
      );
      post.position.set(x, (frameTopY + frameBotY) * 0.5, z);
      g.add(post);

      // Corner joint spheres
      const topCorner = addMesh(new THREE.SphereGeometry(tubeRad * 1.25, 10, 10), frameHex);
      topCorner.position.set(x, frameTopY, z);
      const botCorner = addMesh(new THREE.SphereGeometry(tubeRad * 1.25, 10, 10), frameHex);
      botCorner.position.set(x, frameBotY, z);
      g.add(topCorner, botCorner);
    });
  });

  // 2. TOP SYNTACTIC BUOYANCY FOAM BLOCK (BuoyancyFoam: 14,076,001 mm³)
  let buoyancyMesh!: THREE.Mesh;
  registerSubsystem('sub-buoyancy', [0, 0.21, 0], [0, 0.58, 0], (g, addMesh) => {
    const initialColor = initialVariant === 'restore-02' ? 0xc8681c : 0x0d7a8a;
    buoyancyMesh = addMesh(
      new THREE.BoxGeometry(0.56, 0.125, 0.42),
      initialColor,
      0.35,
      0.22
    );
    g.add(buoyancyMesh);
  });

  // 3. CENTRAL SILVER CYLINDRICAL PRESSURE HULL + ANTENNA & STATUS BEACON (PressureHull: 29,907,957 mm³)
  let beaconSphere!: THREE.Mesh;
  registerSubsystem('sub-hull-dvl', [0, 0.02, 0], [0, 0.15, 0], (g, addMesh) => {
    const hullColor = 0xb2bec3;
    const cyl = addMesh(
      new THREE.CylinderGeometry(0.145, 0.145, 0.54, 24).rotateZ(Math.PI / 2),
      hullColor,
      0.32,
      0.68
    );
    const fwdDome = addMesh(
      new THREE.SphereGeometry(0.145, 20, 16),
      hullColor,
      0.3,
      0.7
    );
    fwdDome.position.x = 0.27;
    const aftDome = addMesh(
      new THREE.SphereGeometry(0.145, 20, 16),
      hullColor,
      0.3,
      0.7
    );
    aftDome.position.x = -0.27;

    // Rear Antenna mast + Status sphere + IdentityBar
    const antennaMast = addMesh(
      new THREE.CylinderGeometry(0.012, 0.014, 0.22, 10),
      0x1e293b,
      0.4,
      0.8
    );
    antennaMast.position.set(-0.36, 0.29, -0.22);

    beaconSphere = addMesh(
      new THREE.SphereGeometry(0.028, 14, 12),
      initialVariant === 'restore-02' ? 0xc8681c : 0x0d7a8a,
      0.25,
      0.4
    );
    beaconSphere.position.set(-0.36, 0.41, -0.22);

    const idBar = addMesh(
      new THREE.BoxGeometry(0.18, 0.025, 0.04),
      0x334155,
      0.4,
      0.6
    );
    idBar.position.set(-0.28, 0.22, 0);

    g.add(cyl, fwdDome, aftDome, antennaMast, beaconSphere, idBar);
  });

  // 4. LOWER CYLINDRICAL BATTERY TUBES (Battery0 & Battery1: 2,888,255 mm³ each)
  registerSubsystem('sub-bat-a', [-0.04, -0.15, 0.24], [0, -0.35, 0.48], (g, addMesh) => {
    const tube = addMesh(
      new THREE.CylinderGeometry(0.068, 0.068, 0.48, 18).rotateZ(Math.PI / 2),
      0x141c24,
      0.42,
      0.75
    );
    const fwdRim = addMesh(
      new THREE.CylinderGeometry(0.082, 0.082, 0.07, 18).rotateZ(Math.PI / 2),
      0x22303c,
      0.35,
      0.85
    );
    fwdRim.position.x = 0.22;
    const aftRim = addMesh(
      new THREE.CylinderGeometry(0.082, 0.082, 0.07, 18).rotateZ(Math.PI / 2),
      0x22303c,
      0.35,
      0.85
    );
    aftRim.position.x = -0.22;
    g.add(tube, fwdRim, aftRim);
  });

  registerSubsystem('sub-bat-b', [-0.04, -0.15, -0.24], [0, -0.35, -0.48], (g, addMesh) => {
    const tube = addMesh(
      new THREE.CylinderGeometry(0.068, 0.068, 0.48, 18).rotateZ(Math.PI / 2),
      0x141c24,
      0.42,
      0.75
    );
    const fwdRim = addMesh(
      new THREE.CylinderGeometry(0.082, 0.082, 0.07, 18).rotateZ(Math.PI / 2),
      0x22303c,
      0.35,
      0.85
    );
    fwdRim.position.x = 0.22;
    const aftRim = addMesh(
      new THREE.CylinderGeometry(0.082, 0.082, 0.07, 18).rotateZ(Math.PI / 2),
      0x22303c,
      0.35,
      0.85
    );
    aftRim.position.x = -0.22;
    g.add(tube, fwdRim, aftRim);
  });

  // Helper for PELAGIC Shrouded Thrusters (Thruster + ThrusterRim + Motor)
  const buildShroudedThruster = (
    g: THREE.Group,
    addMesh: (geo: THREE.BufferGeometry, hexColor: number, r?: number, m?: number) => THREE.Mesh,
    pos: [number, number, number],
    yawAngle: number
  ) => {
    const tGroup = new THREE.Group();
    tGroup.position.set(...pos);
    tGroup.rotation.y = yawAngle;

    const shroud = addMesh(
      new THREE.CylinderGeometry(0.085, 0.085, 0.14, 18).rotateZ(Math.PI / 2),
      0x111921,
      0.38,
      0.72
    );
    const rim = addMesh(
      new THREE.CylinderGeometry(0.09, 0.09, 0.03, 18).rotateZ(Math.PI / 2),
      0x263846,
      0.3,
      0.82
    );
    rim.position.x = 0.06;
    const motor = addMesh(
      new THREE.CylinderGeometry(0.032, 0.032, 0.12, 12).rotateZ(Math.PI / 2),
      0x94a3b8,
      0.28,
      0.88
    );
    tGroup.add(shroud, rim, motor);
    g.add(tGroup);
  };

  // 5. PORT VECTORED THRUSTERS (Thruster0, Thruster1)
  registerSubsystem('sub-thruster-port', [0, 0.01, 0.22], [0, 0.12, 0.52], (g, addMesh) => {
    buildShroudedThruster(g, addMesh, [0.28, 0, 0], -0.28);
    buildShroudedThruster(g, addMesh, [-0.28, 0, 0], 0.28);
  });

  // 6. STARBOARD VECTORED THRUSTERS (Thruster2, Thruster3)
  registerSubsystem('sub-thruster-stbd', [0, 0.01, -0.22], [0, 0.12, -0.52], (g, addMesh) => {
    buildShroudedThruster(g, addMesh, [0.28, 0, 0], 0.28);
    buildShroudedThruster(g, addMesh, [-0.28, 0, 0], -0.28);
  });

  // 7. VERTICAL HEAVE THRUSTERS (VerticalThruster0, VerticalThruster1)
  registerSubsystem('sub-thruster-vert', [-0.32, 0.14, 0], [-0.42, 0.48, 0], (g, addMesh) => {
    const v0 = addMesh(
      new THREE.CylinderGeometry(0.068, 0.068, 0.16, 16),
      0x16222c,
      0.4,
      0.75
    );
    v0.position.set(0, 0, 0.18);
    const v1 = addMesh(
      new THREE.CylinderGeometry(0.068, 0.068, 0.16, 16),
      0x16222c,
      0.4,
      0.75
    );
    v1.position.set(0, 0, -0.18);
    g.add(v0, v1);
  });

  // 8. CAMERAS & HEADLAMPS (CameraPort, DownwardCamera, Headlamp0, Headlamp1)
  registerSubsystem('sub-cam-rgbd', [0.36, 0.04, 0], [0.55, 0.1, 0], (g, addMesh) => {
    const camPort = addMesh(
      new THREE.CylinderGeometry(0.072, 0.072, 0.11, 18).rotateZ(Math.PI / 2),
      0x182631,
      0.25,
      0.8
    );
    const camLens = addMesh(
      new THREE.SphereGeometry(0.058, 16, 14),
      0x7dd3fc,
      0.1,
      0.9
    );
    camLens.position.x = 0.05;

    const lampL = addMesh(
      new THREE.SphereGeometry(0.032, 12, 12),
      0xe2e8f0,
      0.15,
      0.4
    );
    lampL.position.set(0.02, 0.05, 0.16);
    const lampR = addMesh(
      new THREE.SphereGeometry(0.032, 12, 12),
      0xe2e8f0,
      0.15,
      0.4
    );
    lampR.position.set(0.02, 0.05, -0.16);

    const downCam = addMesh(
      new THREE.CylinderGeometry(0.042, 0.042, 0.08, 14),
      0x22323f,
      0.3,
      0.75
    );
    downCam.position.set(-0.22, -0.22, 0);

    g.add(camPort, camLens, lampL, lampR, downCam);
  });

  // 9. EXACT FRONT-RIGHT ARTICULATED MANIPULATOR ARM & GRIPPER ASSEMBLY
  // (Shoulder -> Colored ArmUpper -> Elbow at front-right corner -> Silver ArmFore folding back/down -> Gripper + MultispectralPod)
  const shoulderGroup = new THREE.Group();
  let upperArmMesh!: THREE.Mesh;
  const elbowGroup = new THREE.Group();
  const forearmGroup = new THREE.Group();
  const gripperGroup = new THREE.Group();
  let jawLeft!: THREE.Mesh;
  let jawRight!: THREE.Mesh;
  let heldCoralMesh!: THREE.Mesh;
  const multispectralPod = new THREE.Group();

  registerSubsystem('sub-arm-6dof', [0.16, -0.16, 0.06], [0.48, -0.45, 0.2], (g, addMesh) => {
    const shoulder = addMesh(
      new THREE.SphereGeometry(0.048, 14, 12),
      0x26353d,
      0.38,
      0.75
    );
    shoulderGroup.add(shoulder);

    // ArmUpper (Teal on SCOUT-01, Burnt Orange on RESTORE-02) reaching toward front corner
    const armAccent = initialVariant === 'restore-02' ? 0xc8681c : 0x0d7a8a;
    upperArmMesh = addMesh(
      new THREE.CylinderGeometry(0.034, 0.036, 0.34, 14).rotateZ(Math.PI / 2),
      armAccent,
      0.32,
      0.45
    );
    upperArmMesh.position.set(0.16, -0.02, 0.1);
    upperArmMesh.rotation.y = -0.52;
    shoulderGroup.add(upperArmMesh);

    // Spherical Elbow joint at front corner
    elbowGroup.position.set(0.31, -0.04, 0.19);
    const elbowBall = addMesh(
      new THREE.SphereGeometry(0.042, 14, 12),
      0x22323d,
      0.35,
      0.8
    );
    elbowGroup.add(elbowBall);
    shoulderGroup.add(elbowGroup);

    // Silver-white ArmFore folding back/down under the front crossbar
    forearmGroup.position.set(0, 0, 0);
    const forearmCyl = addMesh(
      new THREE.CylinderGeometry(0.028, 0.032, 0.32, 14).rotateZ(Math.PI / 2),
      0xdbe4e8,
      0.28,
      0.65
    );
    forearmCyl.position.set(-0.08, -0.11, -0.12);
    forearmCyl.rotation.y = 0.85;
    forearmCyl.rotation.z = 0.42;
    forearmGroup.add(forearmCyl);
    elbowGroup.add(forearmGroup);

    // Gripper Wrist, Palm, CameraBracket, ToolCamera, WorkLamp & Jaws
    gripperGroup.position.set(-0.16, -0.19, -0.22);
    const wrist = addMesh(
      new THREE.CylinderGeometry(0.026, 0.026, 0.05, 12),
      0xcbd5e1,
      0.3,
      0.75
    );
    const palm = addMesh(
      new THREE.BoxGeometry(0.095, 0.045, 0.085),
      0x111820,
      0.4,
      0.75
    );
    palm.position.set(0.04, -0.02, 0);

    const toolCam = addMesh(
      new THREE.CylinderGeometry(0.018, 0.018, 0.045, 10).rotateZ(Math.PI / 2),
      0x1e293b,
      0.3,
      0.8
    );
    toolCam.position.set(0.05, 0.02, 0);

    jawLeft = addMesh(
      new THREE.BoxGeometry(0.085, 0.018, 0.016),
      0x0f172a,
      0.35,
      0.8
    );
    jawLeft.position.set(0.11, -0.02, 0.034);

    jawRight = addMesh(
      new THREE.BoxGeometry(0.085, 0.018, 0.016),
      0x0f172a,
      0.35,
      0.8
    );
    jawRight.position.set(0.11, -0.02, -0.034);

    // RESTORE-02 Extra Solids: Gripper__MultispectralPod & Gripper__MultispectralLens
    const msPod = addMesh(
      new THREE.CylinderGeometry(0.026, 0.026, 0.065, 12),
      0x141c24,
      0.35,
      0.8
    );
    msPod.position.set(0.03, -0.055, 0);
    const msLens = addMesh(
      new THREE.SphereGeometry(0.018, 10, 10),
      0x38bdf8,
      0.15,
      0.9
    );
    msLens.position.set(0.05, -0.065, 0);
    multispectralPod.add(msPod, msLens);
    multispectralPod.visible = initialVariant === 'restore-02';

    heldCoralMesh = new THREE.Mesh(
      new THREE.DodecahedronGeometry(0.045, 1),
      new THREE.MeshStandardMaterial({
        color: 0x34d399,
        emissive: 0x10b981,
        emissiveIntensity: 0.65,
        roughness: 0.35,
      })
    );
    heldCoralMesh.position.set(0.13, -0.02, 0);
    heldCoralMesh.visible = false;

    gripperGroup.add(wrist, palm, toolCam, jawLeft, jawRight, multispectralPod, heldCoralMesh);
    forearmGroup.add(gripperGroup);
    g.add(shoulderGroup);
  });

  const setVariant = (variant: PelagicRobotId) => {
    const accentHex = variant === 'restore-02' ? 0xc8681c : 0x0d7a8a;
    (buoyancyMesh.material as THREE.MeshStandardMaterial).color.setHex(accentHex);
    (upperArmMesh.material as THREE.MeshStandardMaterial).color.setHex(accentHex);
    (beaconSphere.material as THREE.MeshStandardMaterial).color.setHex(accentHex);
    multispectralPod.visible = variant === 'restore-02';

    // Update cached baseColors so solid/hologram switches preserve variant color
    const buoyEntry = partGroups.get('sub-buoyancy');
    if (buoyEntry && buoyEntry.baseColors.length > 0) buoyEntry.baseColors[0] = accentHex;
    const armEntry = partGroups.get('sub-arm-6dof');
    if (armEntry && armEntry.baseColors.length > 1) armEntry.baseColors[1] = accentHex;
  };

  const setRenderStyle = (
    style: RobotRenderStyle,
    selectedSubsystemId?: string,
    warningSubsystemIds: string[] = []
  ) => {
    partGroups.forEach((entry, subId) => {
      const isSelected = subId === selectedSubsystemId;
      const isWarning = warningSubsystemIds.includes(subId);

      entry.meshes.forEach((m, idx) => {
        const mat = m.material as THREE.MeshStandardMaterial;
        const baseHex = entry.baseColors[idx] ?? 0x38bdf8;

        if (style === 'hologram') {
          mat.wireframe = false;
          mat.transparent = true;
          mat.opacity = isSelected ? 0.88 : isWarning ? 0.85 : 0.42;
          mat.color.setHex(
            isWarning ? 0xfbbf24 : isSelected ? 0x38bdf8 : baseHex
          );
          mat.emissive.setHex(
            isWarning ? 0xd97706 : isSelected ? 0x22d3ee : 0x0ea5e9
          );
          mat.emissiveIntensity = isWarning ? 0.65 : isSelected ? 0.55 : 0.22;
        } else if (style === 'wireframe') {
          mat.wireframe = true;
          mat.transparent = true;
          mat.opacity = isSelected || isWarning ? 0.95 : 0.55;
          mat.color.setHex(
            isWarning ? 0xfbbf24 : isSelected ? 0x34d399 : 0x38bdf8
          );
          mat.emissive.setHex(isWarning ? 0xf59e0b : 0x0284c7);
          mat.emissiveIntensity = 0.4;
        } else {
          // 'solid' Isaac Sim STEP CAD appearance
          mat.wireframe = false;
          mat.transparent = false;
          mat.opacity = 1.0;
          mat.color.setHex(baseHex);
          if (isWarning) {
            mat.emissive.setHex(0xf59e0b);
            mat.emissiveIntensity = 0.4;
          } else if (isSelected) {
            mat.emissive.setHex(0x22d3ee);
            mat.emissiveIntensity = 0.32;
          } else {
            mat.emissive.setHex(0x000000);
            mat.emissiveIntensity = 0;
          }
        }
      });

      entry.wireframes.forEach((w) => {
        const lMat = w.material as THREE.LineBasicMaterial;
        if (style === 'solid') {
          w.visible = isSelected || isWarning;
          lMat.color.setHex(isWarning ? 0xfbbf24 : 0x38bdf8);
          lMat.opacity = 0.75;
        } else {
          w.visible = true;
          lMat.color.setHex(
            isWarning ? 0xfbbf24 : isSelected ? 0x34d399 : 0x38bdf8
          );
          lMat.opacity = isSelected || isWarning ? 0.95 : 0.55;
        }
      });
    });
  };

  const setPose = (opts: {
    explodeFactor?: number;
    armExtensionPct?: number;
    wristPitchDeg?: number;
    holdingFragment?: boolean;
  }) => {
    if (opts.explodeFactor !== undefined) {
      partGroups.forEach((entry) => {
        const target = entry.basePos
          .clone()
          .addScaledVector(entry.explodeDir, opts.explodeFactor!);
        entry.group.position.copy(target);
      });
    }
    if (opts.armExtensionPct !== undefined) {
      const ratio = (opts.armExtensionPct - 50) / 100;
      elbowGroup.position.x = 0.31 + ratio * 0.14;
      gripperGroup.position.x = -0.16 + ratio * 0.18;
    }
    if (opts.wristPitchDeg !== undefined) {
      gripperGroup.rotation.z = (opts.wristPitchDeg * Math.PI) / 180;
    }
    if (opts.holdingFragment !== undefined) {
      heldCoralMesh.visible = opts.holdingFragment;
      jawLeft.position.z = opts.holdingFragment ? 0.022 : 0.038;
      jawRight.position.z = opts.holdingFragment ? -0.022 : -0.038;
    }
  };

  return {
    root,
    partGroups,
    interactables,
    armAssembly: {
      shoulderGroup,
      upperArmMesh,
      elbowGroup,
      forearmGroup,
      gripperGroup,
      jawLeft,
      jawRight,
      heldCoralMesh,
      multispectralPod,
    },
    buoyancyMesh,
    beaconSphere,
    setVariant,
    setRenderStyle,
    setPose,
  };
}
