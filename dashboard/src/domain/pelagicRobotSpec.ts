/**
 * Exact STEP / Isaac Sim Robot Geometry & Topology Specification
 * Source: reefsim/isaac_scene.py (PELAGIC / ISAAC SIM ROBOT GEOMETRY)
 */

export type PelagicRobotId = 'scout-01' | 'restore-02';

export interface PelagicRobotPartSpec {
  name: string;
  volume_mm3: number;
  valid: boolean;
  subsystemId: string;
  groupLabel: string;
}

export interface PelagicRobotSpec {
  robot: PelagicRobotId;
  label: string;
  role: string;
  units: 'mm';
  size_mm: [number, number, number];
  solid_count: number;
  step_reimport_valid: boolean;
  round_trip_relative_volume_error: number;
  step_sha256: string;
  accentHex: string;
  parts: PelagicRobotPartSpec[];
}

function classifyPartSubsystem(name: string): { subsystemId: string; groupLabel: string } {
  if (name === 'PressureHull' || name === 'IdentityBar' || name === 'Antenna' || name === 'Status') {
    return { subsystemId: 'sub-hull-dvl', groupLabel: 'Pressure Hull & Beacon' };
  }
  if (name === 'BuoyancyFoam') {
    return { subsystemId: 'sub-buoyancy', groupLabel: 'Syntactic Buoyancy Foam' };
  }
  if (name.startsWith('Frame')) {
    return { subsystemId: 'sub-frame', groupLabel: 'Tubular Exoskeleton Frame (12)' };
  }
  if (name === 'Battery0') {
    return { subsystemId: 'sub-bat-a', groupLabel: 'Battery0 Tube (Port)' };
  }
  if (name === 'Battery1') {
    return { subsystemId: 'sub-bat-b', groupLabel: 'Battery1 Tube (Starboard)' };
  }
  if (
    name === 'Thruster0' ||
    name === 'ThrusterRim0' ||
    name === 'Motor0' ||
    name === 'Thruster1' ||
    name === 'ThrusterRim1' ||
    name === 'Motor1'
  ) {
    return { subsystemId: 'sub-thruster-port', groupLabel: 'Port Vectored Thrusters (T0/T1)' };
  }
  if (
    name === 'Thruster2' ||
    name === 'ThrusterRim2' ||
    name === 'Motor2' ||
    name === 'Thruster3' ||
    name === 'ThrusterRim3' ||
    name === 'Motor3'
  ) {
    return { subsystemId: 'sub-thruster-stbd', groupLabel: 'Stbd Vectored Thrusters (T2/T3)' };
  }
  if (name.startsWith('VerticalThruster')) {
    return { subsystemId: 'sub-thruster-vert', groupLabel: 'Vertical Heave Thrusters (V0/V1)' };
  }
  if (
    name === 'CameraPort' ||
    name === 'DownwardCamera' ||
    name === 'Headlamp0' ||
    name === 'Headlamp1'
  ) {
    return { subsystemId: 'sub-cam-rgbd', groupLabel: 'Cameras & Headlamps' };
  }
  return { subsystemId: 'sub-arm-6dof', groupLabel: 'Manipulator Arm & Gripper' };
}

const BASE_50_PARTS: Array<{ name: string; volume_mm3: number; valid: boolean }> = [
  { name: 'PressureHull', volume_mm3: 29907957.321448855, valid: true },
  { name: 'BuoyancyFoam', volume_mm3: 14076000.962734241, valid: true },
  { name: 'FrameLong00', volume_mm3: 653702.6253347702, valid: true },
  { name: 'FrameLong01', volume_mm3: 653702.6253347702, valid: true },
  { name: 'FrameCross00', volume_mm3: 435801.72316504805, valid: true },
  { name: 'FrameCross01', volume_mm3: 435801.72316504805, valid: true },
  { name: 'FrameLong10', volume_mm3: 653702.6253347701, valid: true },
  { name: 'FrameLong11', volume_mm3: 653702.6253347701, valid: true },
  { name: 'FrameCross10', volume_mm3: 435801.72316504805, valid: true },
  { name: 'FrameCross11', volume_mm3: 435801.72316504805, valid: true },
  { name: 'FrameUpright00', volume_mm3: 317772.091498981, valid: true },
  { name: 'FrameUpright01', volume_mm3: 317772.091498981, valid: true },
  { name: 'FrameUpright10', volume_mm3: 317772.091498981, valid: true },
  { name: 'FrameUpright11', volume_mm3: 317772.091498981, valid: true },
  { name: 'Battery0', volume_mm3: 2888254.6523843175, valid: true },
  { name: 'Battery1', volume_mm3: 2888254.6523843175, valid: true },
  { name: 'Thruster0', volume_mm3: 1841570.1876290604, valid: true },
  { name: 'ThrusterRim0', volume_mm3: 114680.69922348592, valid: true },
  { name: 'Motor0', volume_mm3: 43429.3664772426, valid: true },
  { name: 'Thruster1', volume_mm3: 1841570.1876290604, valid: true },
  { name: 'ThrusterRim1', volume_mm3: 114680.69922348592, valid: true },
  { name: 'Motor1', volume_mm3: 43429.366477242584, valid: true },
  { name: 'Thruster2', volume_mm3: 1841570.1876290604, valid: true },
  { name: 'ThrusterRim2', volume_mm3: 114680.69922348592, valid: true },
  { name: 'Motor2', volume_mm3: 43429.3664772426, valid: true },
  { name: 'Thruster3', volume_mm3: 1841570.1876290604, valid: true },
  { name: 'ThrusterRim3', volume_mm3: 114680.69922348592, valid: true },
  { name: 'Motor3', volume_mm3: 43429.366477242584, valid: true },
  { name: 'VerticalThruster0', volume_mm3: 1061858.2931789672, valid: true },
  { name: 'VerticalThruster1', volume_mm3: 1061858.2931789672, valid: true },
  { name: 'CameraPort', volume_mm3: 1327322.568762823, valid: true },
  { name: 'DownwardCamera', volume_mm3: 380132.6174912054, valid: true },
  { name: 'Headlamp0', volume_mm3: 91629.76933135462, valid: true },
  { name: 'Headlamp1', volume_mm3: 91629.76933135459, valid: true },
  { name: 'IdentityBar', volume_mm3: 81712.83366601427, valid: true },
  { name: 'Antenna', volume_mm3: 40715.03988047165, valid: true },
  { name: 'Status', volume_mm3: 44602.22787422381, valid: true },
  { name: 'Shoulder', volume_mm3: 696909.8105347465, valid: true },
  { name: 'ArmUpper', volume_mm3: 870283.9859768199, valid: true },
  { name: 'ArmFore', volume_mm3: 608212.3467980528, valid: true },
  { name: 'Elbow', volume_mm3: 195432.1289242176, valid: true },
  { name: 'Gripper__Palm', volume_mm3: 243000.0138804316, valid: true },
  { name: 'Gripper__Wrist', volume_mm3: 49857.07429807756, valid: true },
  { name: 'Gripper__WorkLamp', volume_mm3: 3053.6270144409027, valid: true },
  { name: 'Gripper__CameraBracket', volume_mm3: 18322.683798468446, valid: true },
  { name: 'Gripper__ToolCamera', volume_mm3: 20357.513850926276, valid: true },
  { name: 'Gripper__Jaw0__Finger', volume_mm3: 19594.11338043564, valid: true },
  { name: 'Gripper__Jaw0__SoftPad', volume_mm3: 4860.000059679148, valid: true },
  { name: 'Gripper__Jaw1__Finger', volume_mm3: 19594.11338043564, valid: true },
  { name: 'Gripper__Jaw1__SoftPad', volume_mm3: 4860.000059679148, valid: true },
];

const RESTORE_02_EXTRA_PARTS: Array<{ name: string; volume_mm3: number; valid: boolean }> = [
  { name: 'Gripper__MultispectralPod', volume_mm3: 99714.14859615504, valid: true },
  { name: 'Gripper__MultispectralLens', volume_mm3: 10585.07023863003, valid: true },
];

export const PELAGIC_ROBOT_SPECS: Record<PelagicRobotId, PelagicRobotSpec> = {
  'scout-01': {
    robot: 'scout-01',
    label: 'SCOUT-01',
    role: 'Reef Survey & Optical Mapping AUV',
    units: 'mm',
    size_mm: [958.51947374424, 676.0, 715.0000004941901],
    solid_count: 50,
    step_reimport_valid: true,
    round_trip_relative_volume_error: 3.3650859876388495e-13,
    step_sha256: '28666c4650e4513e6eb0ba90b8ecbc6eac621101f1f96aa48f02c6299bce3fe7',
    accentHex: '#0E7C8B',
    parts: BASE_50_PARTS.map((p) => ({
      ...p,
      ...classifyPartSubsystem(p.name),
    })),
  },
  'restore-02': {
    robot: 'restore-02',
    label: 'RESTORE-02',
    role: 'Coral Transplant & Multispectral Gripper AUV',
    units: 'mm',
    size_mm: [958.51947374424, 676.0, 715.0000004941901],
    solid_count: 52,
    step_reimport_valid: true,
    round_trip_relative_volume_error: 3.3595348725157237e-13,
    step_sha256: '65f0283a19a685db61acaedb20046e2a9af7524f6ba541f27c24a3a2e49c7994',
    accentHex: '#C8681C',
    parts: [...BASE_50_PARTS, ...RESTORE_02_EXTRA_PARTS].map((p) => ({
      ...p,
      ...classifyPartSubsystem(p.name),
    })),
  },
};

export function summarizeRobotVolumeByGroup(robotId: PelagicRobotId): Array<{
  subsystemId: string;
  groupLabel: string;
  partCount: number;
  totalVolumeCm3: number;
  sharePct: number;
}> {
  const spec = PELAGIC_ROBOT_SPECS[robotId];
  const totalMm3 = spec.parts.reduce((acc, p) => acc + p.volume_mm3, 0);
  const map = new Map<
    string,
    { subsystemId: string; groupLabel: string; partCount: number; volumeMm3: number }
  >();

  for (const p of spec.parts) {
    const existing = map.get(p.subsystemId);
    if (existing) {
      existing.partCount += 1;
      existing.volumeMm3 += p.volume_mm3;
    } else {
      map.set(p.subsystemId, {
        subsystemId: p.subsystemId,
        groupLabel: p.groupLabel,
        partCount: 1,
        volumeMm3: p.volume_mm3,
      });
    }
  }

  return Array.from(map.values())
    .map((g) => ({
      subsystemId: g.subsystemId,
      groupLabel: g.groupLabel,
      partCount: g.partCount,
      totalVolumeCm3: Math.round(g.volumeMm3 / 1000),
      sharePct: Number(((g.volumeMm3 / totalMm3) * 100).toFixed(1)),
    }))
    .sort((a, b) => b.totalVolumeCm3 - a.totalVolumeCm3);
}
