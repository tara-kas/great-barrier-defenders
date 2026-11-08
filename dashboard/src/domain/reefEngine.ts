export type CoralStatus = 'Living' | 'Bleached' | 'Dead' | 'Placed';
export type SubstrateType = 'hard_rock' | 'clean_skeleton' | 'sand' | 'rubble' | 'algae_rock';
export type AgentTool = 'scan' | 'goto' | 'inspect' | 'grasp' | 'carry' | 'place' | 'verify' | 'abort';
export type CoralMorphology = 'tabulate' | 'staghorn' | 'corymbose' | 'boulder' | 'fragment' | 'rubble';
export type ReviewerStatus = 'Confirmed' | 'Needs Review' | 'Uncertain' | 'Corrected';
export type DataProvenance =
  | 'Measured (Stereo RGB-D + DVL)'
  | 'Interpolated (Bathymetric Kriging)'
  | 'Coverage Gap (Close Pass Required)';

export interface SiteScoreBreakdown {
  totalScore: number;
  stabilityTerm: number;
  flowTerm: number;
  proximityTerm: number;
  algaePenalty: number;
  distancePenalty: number;
  uncertaintyPenalty: number;
  requiresVoIInspection: boolean;
  pcaUpwardValid: boolean;
  tiltAngleDeg: number;
}

export interface CoralCluster {
  id: string;
  status: CoralStatus;
  morphology: CoralMorphology;
  species: string;
  genetId: string;
  localX: number; // 0.1 to 10.1 m
  localY: number; // -0.1 to 9.8 m
  depthM: number; // 18.1 to 19.3 m
  boundsM: [number, number, number]; // [width, length, height] in metres
  substrate: SubstrateType;
  surfaceNormal: [number, number, number]; // PCA normal [nx, ny, nz]
  uncertainty: number; // 0.0 to 1.0
  confidence: number; // 0.0 to 1.0
  flowSpeedMs: number;
  stabilityScore: number; // 0.0 to 1.0
  algaeRisk: number; // 0.0 to 1.0
  frameId: string;
  detectedAt: string;
  reviewerStatus: ReviewerStatus;
  dataProvenance: DataProvenance;
  gfpIntensity: number; // 0.0 to 1.0
  chlIntensity: number; // 0.0 to 1.0
  fluorescence: {
    band: 'GFP-Cyan (508nm)' | 'RFP-Orange (585nm)' | 'Hyper-Neon Stress' | 'Carbonate (No Glow)';
    intensity: number; // 0 to 100%
    gfp508Peak: number; // 0 to 100
    rfp585Peak: number; // 0 to 100
    chl685Peak: number; // 0 to 100 (zooxanthellae symbiont density proxy)
  };
  placementShiftMm?: number;
  notes: string;
}

export interface DecisionTraceEvent {
  id: string;
  timestamp: string;
  actionType: string;
  toolCalled: AgentTool;
  headline: string;
  summary: string;
  clusterId: string;
  frameId?: string;
  modelVersion?: string;
  alternativesConsidered?: string[];
  humanReviewStatus?: 'Accepted' | 'Changed' | 'Rejected' | 'Pending Review';
  operatorReason?: string;
  surfaceNormal: [number, number, number];
  placementShiftMm: number;
  confidence: number;
  gripperForceN: number;
  uncertainty: number;
  outcome: string;
  statusTone: 'nominal' | 'warning' | 'critical';
  reasoning: string;
}

export interface LiveNotification {
  id: string;
  timestamp: string;
  title: string;
  detail: string;
  message?: string;
  clusterId: string;
  toolCalled?: AgentTool;
  tone: 'nominal' | 'warning' | 'critical';
  unread: boolean;
  read?: boolean;
}

export interface AuvSubsystem {
  id: string;
  name: string;
  category: 'Propulsion' | 'Power' | 'Perception' | 'Manipulation' | 'Hull & Nav';
  status: 'Nominal' | 'Warning' | 'Fault';
  healthPct: number;
  temperatureC: number;
  currentDrawA: number;
  voltageV: number;
  detail: string;
  telemetryLabel: string;
  telemetryValue: string;
  freshnessSec: number;
  suggestedAction?: string;
  position3D: [number, number, number];
}

export interface OptimiserWeights {
  wSub: number;
  wFlow: number;
  wProx: number;
  wAlgae: number;
  wDist: number;
  wUnc: number;
  uncertaintyThreshold: number;
}

export interface TemporalGrowthStage {
  day: number;
  label: string;
  phaseLabel: string;
  fusionPct: number;
  symbiontDensityPct: number;
  calcificationBondN: number;
  skeletalBondShearN: number;
  tissueBridgeMm: number;
  calcificationFactor: number;
  projectedBoundsM: [number, number, number];
  volumeCm3: number;
  biologicalStatus: string;
}

export interface PermitApprovalRecord {
  id: string;
  authority: string;
  referenceCode: string;
  title: string;
  validThrough: string;
  status: 'Permit Verified' | 'Permit Recorded (Pending Verification)';
  conditions: string[];
  verifiedBy?: string;
}

export interface MissionChecklistItem {
  id: string;
  category: 'Regulatory & Permit' | 'Geofence & No-Go' | 'Vehicle Pre-Dive' | 'Crew & Recovery';
  label: string;
  detail: string;
  completed: boolean;
  requiredForLaunch: boolean;
}

export interface NoGoZone {
  id: string;
  name: string;
  reason: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  maxDepthM: number;
}

export interface EcologicalSurveyVisit {
  id: string;
  visitCode: string;
  date: string;
  dayOffset: number;
  waterTempC: number;
  sampleSizeColonies: number;
  missingObservations: number;
  interventionSurvivalPct: number;
  referenceControlSurvivalPct: number;
  meanColonyAreaCm2: number;
  referenceAreaCm2: number;
  partialMortalityPct: number;
  shannonDiversityH: number;
  notes: string;
}

export interface CoralClumpSpreadLink {
  targetId: string;
  targetX: number;
  targetY: number;
  targetDepthM: number;
  distanceFromHubM: number;
  estimatedSpreadDays: number;
}

export interface CoralClumpPlan {
  clumpId: string;
  clumpName: string;
  donorClusterId: string;
  donorPos: [number, number, number];
  optimalHubId: string;
  hubPos: [number, number, number];
  waypoints: [number, number, number][];
  shortestTransitDistanceM: number;
  spreadLinks: CoralClumpSpreadLink[];
  totalClumpCoralsSaved: number;
  spreadEfficiencyScore: number;
  reasoning: string;
}

export const DEFAULT_OPTIMISER_WEIGHTS: OptimiserWeights = {
  wSub: 3.2,
  wFlow: 1.8,
  wProx: 1.4,
  wAlgae: 2.5,
  wDist: 0.25,
  wUnc: 2.8,
  uncertaintyThreshold: 0.4,
};

const SUBSTRATE_STABILITY_BONUS: Record<SubstrateType, number> = {
  hard_rock: 1.0,
  clean_skeleton: 0.92,
  rubble: 0.35,
  sand: 0.1,
  algae_rock: 0.25,
};

/**
 * Validates whether a local point-cloud PCA surface normal satisfies the upward-facing
 * sunlit seating constraint: n_k · [0, 0, 1] > cos(30°) ≈ 0.866025
 */
export function validatePcaSurfaceNormal(normal: [number, number, number]): {
  valid: boolean;
  dotZ: number;
  tiltAngleDeg: number;
} {
  const [nx, ny, nz] = normal;
  const mag = Math.hypot(nx, ny, nz) || 1;
  const unitZ = Math.max(-1, Math.min(1, nz / mag));
  const tiltRad = Math.acos(unitZ);
  const tiltAngleDeg = Number(((tiltRad * 180) / Math.PI).toFixed(1));
  const cos30 = Math.cos((30 * Math.PI) / 180);
  return {
    valid: unitZ >= cos30,
    dotZ: Number(unitZ.toFixed(3)),
    tiltAngleDeg,
  };
}

/**
 * Computes the classical inspectable site optimiser utility score S(i, j):
 * S(i, j) = w_sub * Stability_j + w_flow * FlowScore_j + w_prox * DonorProximity_j
 *           - w_algae * AlgaeRisk_j - w_dist * ||x_auv - x_j||_2 - w_unc * U_j
 */
export function calculateSiteScore(
  cluster: CoralCluster,
  vehiclePos: [number, number],
  weights: OptimiserWeights = DEFAULT_OPTIMISER_WEIGHTS,
  donorPos: [number, number] = [3.2, 4.1]
): SiteScoreBreakdown {
  const baseSub = SUBSTRATE_STABILITY_BONUS[cluster.substrate] * cluster.stabilityScore;
  const stabilityTerm = Number((weights.wSub * baseSub).toFixed(2));

  const flowIdealDelta = Math.abs(cluster.flowSpeedMs - 0.25);
  const flowNormalized = Math.max(0, 1 - flowIdealDelta * 2.2);
  const flowTerm = Number((weights.wFlow * flowNormalized).toFixed(2));

  const donorDist = Math.hypot(cluster.localX - donorPos[0], cluster.localY - donorPos[1]);
  const proximityNormalized = Math.max(0, 1 - donorDist / 10);
  const proximityTerm = Number((weights.wProx * proximityNormalized).toFixed(2));

  const algaePenalty = Number((weights.wAlgae * cluster.algaeRisk).toFixed(2));

  const auvDist = Math.hypot(cluster.localX - vehiclePos[0], cluster.localY - vehiclePos[1]);
  const distancePenalty = Number((weights.wDist * auvDist).toFixed(2));

  const uncertaintyPenalty = Number((weights.wUnc * cluster.uncertainty).toFixed(2));

  const totalScore = Number(
    (
      stabilityTerm +
      flowTerm +
      proximityTerm -
      algaePenalty -
      distancePenalty -
      uncertaintyPenalty
    ).toFixed(2)
  );

  const pcaCheck = validatePcaSurfaceNormal(cluster.surfaceNormal);

  return {
    totalScore,
    stabilityTerm,
    flowTerm,
    proximityTerm,
    algaePenalty,
    distancePenalty,
    uncertaintyPenalty,
    requiresVoIInspection: cluster.uncertainty > weights.uncertaintyThreshold,
    pcaUpwardValid: pcaCheck.valid,
    tiltAngleDeg: pcaCheck.tiltAngleDeg,
  };
}

/**
 * Evaluates clonal genet compatibility per Collins et al. (2026):
 * Same-genet pairings form gastrovascular tissue bridges in 3-5 days;
 * mixed-genet pairings trigger antagonistic mesenterial filament rejection.
 */
export function evaluateGenetCompatibility(
  donorGenetId: string,
  targetCluster: CoralCluster
): {
  compatible: boolean;
  interactionType: 'Clonal Tissue Fusion' | 'Inert Carbonate Substrate' | 'Mixed-Genet Antagonism';
  expectedRecoveryDays: number;
  symbiontDoublingDays: number;
  summary: string;
  recommendation: string;
} {
  if (targetCluster.genetId === donorGenetId) {
    const msg = `Same-genet match (${donorGenetId}): rapid gastrovascular bridge in 3–5 days, ~4.0-day symbiont doubling.`;
    return {
      compatible: true,
      interactionType: 'Clonal Tissue Fusion',
      expectedRecoveryDays: 7,
      symbiontDoublingDays: 4.0,
      summary: msg,
      recommendation: msg,
    };
  }
  if (targetCluster.genetId.startsWith('SUBSTRATE-CARB')) {
    const msg =
      'Clean carbonate skeleton with zero foreign tissue antagonism; suitable for primary basal seating.';
    return {
      compatible: true,
      interactionType: 'Inert Carbonate Substrate',
      expectedRecoveryDays: 14,
      symbiontDoublingDays: 9.5,
      summary: msg,
      recommendation: msg,
    };
  }
  const msg = `Genotype mismatch (${donorGenetId} vs ${targetCluster.genetId}): triggers mesenterial filament warfare; keep >= 18 cm clearance.`;
  return {
    compatible: false,
    interactionType: 'Mixed-Genet Antagonism',
    expectedRecoveryDays: 0,
    symbiontDoublingDays: 28.0,
    summary: msg,
    recommendation: msg,
  };
}

/**
 * Computes 4D temporal restoration projection for Day 0 through Day 49
 */
export function computeTemporalGrowthStage(
  cluster: CoralCluster,
  day: number
): TemporalGrowthStage {
  const baseVolCm3 = Math.round(
    cluster.boundsM[0] * cluster.boundsM[1] * cluster.boundsM[2] * 420000
  );
  const clampedDay = Math.max(0, Math.min(49, day));
  const progress = clampedDay / 49;
  const calcificationFactor = Number((1.0 + progress * 0.26).toFixed(2));
  const projectedBoundsM: [number, number, number] = [
    Number((cluster.boundsM[0] * calcificationFactor).toFixed(2)),
    Number((cluster.boundsM[1] * calcificationFactor).toFixed(2)),
    Number((cluster.boundsM[2] * (1 + progress * 0.22)).toFixed(2)),
  ];

  if (clampedDay <= 1) {
    return {
      day: clampedDay,
      label: 'Robotic Seating',
      phaseLabel: 'Phase 1 · Robotic Seating & Push Verification',
      fusionPct: 8,
      symbiontDensityPct: cluster.status === 'Bleached' ? 28 : 76,
      calcificationBondN: 16.5,
      skeletalBondShearN: 16.5,
      tissueBridgeMm: 0.4,
      calcificationFactor,
      projectedBoundsM,
      volumeCm3: baseVolCm3,
      biologicalStatus:
        'Seated along upward PCA normal; marine adhesive cured and passed 0.30 m/s current push check (< 2.1 mm shift).',
    };
  }
  if (clampedDay <= 6) {
    return {
      day: clampedDay,
      label: 'Tissue Bridge',
      phaseLabel: 'Phase 2 · Clonal Tissue Bridge & Rapid Symbiont Replication (Days 3–5)',
      fusionPct: 58,
      symbiontDensityPct: cluster.status === 'Bleached' ? 68 : 88,
      calcificationBondN: 24.2,
      skeletalBondShearN: 24.2,
      tissueBridgeMm: 4.8,
      calcificationFactor,
      projectedBoundsM,
      volumeCm3: Math.round(baseVolCm3 * 1.03),
      biologicalStatus:
        'Direct gastrovascular connection established across clonal contact boundary; symbiont doubling time accelerated to ~4.0 days.',
    };
  }
  if (clampedDay <= 21) {
    return {
      day: clampedDay,
      label: 'Basal Calcification',
      phaseLabel: 'Phase 3 · Self-Sustained Recovery & Basal Calcification (Days 7–21)',
      fusionPct: 89,
      symbiontDensityPct: 95,
      calcificationBondN: 38.6,
      skeletalBondShearN: 38.6,
      tissueBridgeMm: 9.6,
      calcificationFactor,
      projectedBoundsM,
      volumeCm3: Math.round(baseVolCm3 * 1.11),
      biologicalStatus:
        'Complete fragment-wide zooxanthellae repopulation; calcium carbonate skeleton actively welding to basalt/carbonate substrate.',
    };
  }
  return {
    day: clampedDay,
    label: 'Full Integration',
    phaseLabel: 'Phase 4 · Full Reef Structural Integration (Week 7 / Day 49)',
    fusionPct: 100,
    symbiontDensityPct: 99,
    calcificationBondN: 54.0,
    skeletalBondShearN: 54.0,
    tissueBridgeMm: 16.2,
    calcificationFactor,
    projectedBoundsM,
    volumeCm3: Math.round(baseVolCm3 * 1.26),
    biologicalStatus:
      'Complete skeletal and tissue integration across the reef patch; axial corallite branching expanding into local flow.',
  };
}

/**
 * Generates a 7-point spectral fluorescence emission curve from 450nm to 685nm
 */
export function computeSpectralCurve(cluster: CoralCluster): Array<{
  wavelengthNm: number;
  label: string;
  intensityPct: number;
  relativeIntensity: number;
}> {
  const { gfp508Peak, rfp585Peak, chl685Peak } = cluster.fluorescence;
  const raw = [
    { wavelengthNm: 450, label: '450nm (Excitation Tail)', intensityPct: 18 },
    { wavelengthNm: 485, label: '485nm (Cyan)', intensityPct: Math.round(gfp508Peak * 0.68) },
    { wavelengthNm: 508, label: '508nm (GFP Peak)', intensityPct: gfp508Peak },
    { wavelengthNm: 545, label: '545nm (Green)', intensityPct: Math.round((gfp508Peak + rfp585Peak) * 0.42) },
    { wavelengthNm: 585, label: '585nm (RFP Peak)', intensityPct: rfp585Peak },
    { wavelengthNm: 630, label: '630nm (Orange-Red)', intensityPct: Math.round(rfp585Peak * 0.45) },
    { wavelengthNm: 685, label: '685nm (Chl-a Symbiont)', intensityPct: chl685Peak },
  ];
  return raw.map((pt) => ({
    ...pt,
    relativeIntensity: Number((pt.intensityPct / 100).toFixed(2)),
  }));
}

/**
 * Evaluates pre-mission regulatory permit verification and operational readiness gate.
 * Distinguishes "Permit Recorded" from "Permit Verified" so unverified permits block launch.
 */
export function evaluateMissionReadiness(params: {
  permits: PermitApprovalRecord[];
  checklist: MissionChecklistItem[];
  currentSpeedMs: number;
  maxAllowedCurrentMs: number;
  visibilityM: number;
  minAllowedVisibilityM: number;
}): {
  ready: boolean;
  allPermitsVerified: boolean;
  requiredChecklistComplete: boolean;
  withinEnvironmentalLimits: boolean;
  blockers: string[];
} {
  const blockers: string[] = [];
  const unverified = params.permits.filter((p) => p.status !== 'Permit Verified');
  if (unverified.length > 0) {
    blockers.push(
      `${unverified.length} permit(s) recorded but not yet verified (${unverified
        .map((u) => u.referenceCode)
        .join(', ')})`
    );
  }

  const incompleteReq = params.checklist.filter((c) => c.requiredForLaunch && !c.completed);
  if (incompleteReq.length > 0) {
    blockers.push(`${incompleteReq.length} mandatory pre-dive checklist item(s) incomplete`);
  }

  const withinEnvironmentalLimits =
    params.currentSpeedMs <= params.maxAllowedCurrentMs &&
    params.visibilityM >= params.minAllowedVisibilityM;

  if (!withinEnvironmentalLimits) {
    blockers.push('Environmental sea-state or current exceeds operating permit limits');
  }

  return {
    ready: blockers.length === 0,
    allPermitsVerified: unverified.length === 0,
    requiredChecklistComplete: incompleteReq.length === 0,
    withinEnvironmentalLimits,
    blockers,
  };
}

/**
 * Computes the optimal single-fragment placement hub inside a coral clump and the shortest
 * obstacle-free trajectory from a live donor fragment so one transplanted fragment
 * spreads gastrovascular & symbiont recovery across the entire clump fastest.
 */
export function computeOptimalClumpHubAndPath(
  clusters: CoralCluster[],
  donorClusterId: string = 'C-13',
  clumpMemberIds: string[] = ['C-03', 'C-04', 'C-06'],
  clumpId: string = 'CLUMP-ALPHA',
  clumpName: string = 'Central Ridge Clump (C-03 · C-04 · C-06)'
): CoralClumpPlan {
  const donor = clusters.find((c) => c.id === donorClusterId) || clusters[0];
  const members = clumpMemberIds
    .map((id) => clusters.find((c) => c.id === id))
    .filter((c): c is CoralCluster => Boolean(c));

  const fallbackMembers = members.length > 0 ? members : clusters.slice(0, 3);

  let bestHub = fallbackMembers[0];
  let bestScore = -Infinity;

  for (const candidate of fallbackMembers) {
    const transitDist = Math.hypot(
      candidate.localX - donor.localX,
      candidate.localY - donor.localY
    );
    const radialSpreadSum = fallbackMembers.reduce((acc, other) => {
      if (other.id === candidate.id) return acc;
      return acc + Math.hypot(other.localX - candidate.localX, other.localY - candidate.localY);
    }, 0);
    const pca = validatePcaSurfaceNormal(candidate.surfaceNormal);
    // Higher stability & upward normal, shorter radial spread to neighbors, shorter transit from donor
    const score =
      candidate.stabilityScore * 4.5 +
      (pca.valid ? 2.0 : -2.0) -
      radialSpreadSum * 0.85 -
      transitDist * 0.35;

    if (score > bestScore) {
      bestScore = score;
      bestHub = candidate;
    }
  }

  const donorPos: [number, number, number] = [donor.localX, donor.localY, donor.depthM];
  const hubPos: [number, number, number] = [bestHub.localX, bestHub.localY, bestHub.depthM];
  const midPos: [number, number, number] = [
    Number(((donor.localX + bestHub.localX) / 2).toFixed(2)),
    Number(((donor.localY + bestHub.localY) / 2).toFixed(2)),
    Number((Math.min(donor.depthM, bestHub.depthM) - 0.35).toFixed(2)),
  ];

  const shortestTransitDistanceM = Number(
    Math.hypot(
      bestHub.localX - donor.localX,
      bestHub.localY - donor.localY,
      bestHub.depthM - donor.depthM
    ).toFixed(2)
  );

  const spreadLinks: CoralClumpSpreadLink[] = fallbackMembers
    .filter((m) => m.id !== bestHub.id)
    .map((m) => {
      const dist = Number(
        Math.hypot(m.localX - bestHub.localX, m.localY - bestHub.localY).toFixed(2)
      );
      return {
        targetId: m.id,
        targetX: m.localX,
        targetY: m.localY,
        targetDepthM: m.depthM,
        distanceFromHubM: dist,
        estimatedSpreadDays: Number(Math.max(3.5, dist * 2.8).toFixed(1)),
      };
    });

  return {
    clumpId,
    clumpName,
    donorClusterId: donor.id,
    donorPos,
    optimalHubId: bestHub.id,
    hubPos,
    waypoints: [donorPos, midPos, hubPos],
    shortestTransitDistanceM,
    spreadLinks,
    totalClumpCoralsSaved: fallbackMembers.length,
    spreadEfficiencyScore: Number(bestScore.toFixed(2)),
    reasoning: `Selected ${bestHub.id} (${bestHub.substrate}, stability ${(
      bestHub.stabilityScore * 100
    ).toFixed(0)}%) as central clump hub: shortest ${shortestTransitDistanceM} m transit from live donor ${
      donor.id
    } enables 1 fragment to propagate symbionts across all ${
      fallbackMembers.length
    } clump colonies (${fallbackMembers.map((m) => m.id).join(', ')}).`,
  };
}

/**
 * Projects 2D normalized camera pixel (u, v in [0, 1]) at range depth d into 3D local world frame
 */
export function projectPixelToWorld(
  uNorm: number,
  vNorm: number,
  depthFromCamM: number,
  vehiclePose: { x: number; y: number; depthM: number; yawRad: number }
): [number, number, number] {
  const fovH = 1.1;
  const fovV = 0.85;
  const camX = (uNorm - 0.5) * depthFromCamM * Math.tan(fovH / 2) * 2;
  const camY = (0.5 - vNorm) * depthFromCamM * Math.tan(fovV / 2) * 2;

  const cosY = Math.cos(vehiclePose.yawRad);
  const sinY = Math.sin(vehiclePose.yawRad);

  const worldX = Number((vehiclePose.x + camX * cosY - camY * sinY).toFixed(2));
  const worldY = Number((vehiclePose.y + camX * sinY + camY * cosY).toFixed(2));
  const worldDepth = Number((vehiclePose.depthM + depthFromCamM * 0.45).toFixed(2));

  return [worldX, worldY, worldDepth];
}

/**
 * Computes carry-aware thruster efforts (%) and drag/mass compensation
 */
export function computeCarryAwareThrusters(params: {
  surgeSpeedMs: number;
  currentSpeedMs: number;
  holdingFragment: boolean;
  fragmentMassKg: number;
  portThrusterDegraded?: boolean;
}): {
  portForwardPct: number;
  starboardForwardPct: number;
  portAftPct: number;
  starboardAftPct: number;
  verticalBowPct: number;
  verticalSternPct: number;
  massDeltaKg: number;
  dragCompensationN: number;
} {
  const {
    surgeSpeedMs,
    currentSpeedMs,
    holdingFragment,
    fragmentMassKg,
    portThrusterDegraded = true,
  } = params;

  const relVel = surgeSpeedMs + currentSpeedMs;
  const linearDrag = 14.5 * relVel;
  const quadDrag = 22.0 * relVel * Math.abs(relVel);
  const carryDragDelta = holdingFragment ? 6.8 * relVel + fragmentMassKg * 9.81 * 0.35 : 0;
  const dragCompensationN = Number((linearDrag + quadDrag + carryDragDelta).toFixed(2));

  const baseHorizontal = Math.min(92, Math.max(18, 28 + relVel * 48 + (holdingFragment ? 14 : 0)));
  const baseVertical = Math.min(95, Math.max(22, 34 + (holdingFragment ? fragmentMassKg * 28 : 0)));

  return {
    portForwardPct: Number(Math.min(99, baseHorizontal * (portThrusterDegraded ? 1.18 : 1.0)).toFixed(1)),
    starboardForwardPct: Number(baseHorizontal.toFixed(1)),
    portAftPct: Number((baseHorizontal * 0.94).toFixed(1)),
    starboardAftPct: Number((baseHorizontal * 0.96).toFixed(1)),
    verticalBowPct: Number((baseVertical * 1.06).toFixed(1)),
    verticalSternPct: Number((baseVertical * 0.95).toFixed(1)),
    massDeltaKg: holdingFragment ? fragmentMassKg : 0,
    dragCompensationN,
  };
}

/**
 * Evaluates post-placement current push verification test
 */
export function evaluatePushTest(
  currentSpeedMs: number,
  stabilityScore: number,
  pcaDotZ: number
): {
  passed: boolean;
  displacementMm: number;
  shearForceN: number;
  holdMarginN: number;
} {
  const shearForceN = Number((12.4 * currentSpeedMs * currentSpeedMs + 3.1 * currentSpeedMs).toFixed(2));
  const bondStrengthN = Number((18.0 * stabilityScore * Math.max(0.5, pcaDotZ)).toFixed(2));
  const holdMarginN = Number((bondStrengthN - shearForceN).toFixed(2));
  const displacementMm = Number(
    Math.max(0.4, (shearForceN / Math.max(2, bondStrengthN)) * 3.8).toFixed(1)
  );
  return {
    passed: displacementMm <= 3.0 && holdMarginN > 0,
    displacementMm,
    shearForceN,
    holdMarginN,
  };
}

/**
 * Pure helper to reorder desktop widgets via drag-and-drop
 */
export function reorderWidgets(order: string[], sourceId: string, targetId: string): string[] {
  if (sourceId === targetId) return [...order];
  const srcIdx = order.indexOf(sourceId);
  const tgtIdx = order.indexOf(targetId);
  if (srcIdx === -1 || tgtIdx === -1) return [...order];
  const next = [...order];
  const [moved] = next.splice(srcIdx, 1);
  next.splice(tgtIdx, 0, moved);
  return next;
}

export const INITIAL_CLUSTERS: CoralCluster[] = [
  // CLUSTER 1: West Spur Staghorn Thicket (Primary Restoration Clump Alpha)
  {
    id: 'C-01',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Arborescent Thicket)',
    genetId: 'GEN-AH-01',
    localX: 4.8,
    localY: 3.2,
    depthM: 18.2,
    boundsM: [1.85, 1.68, 1.12],
    substrate: 'hard_rock',
    surfaceNormal: [0.03, -0.02, 0.99],
    uncertainty: 0.08,
    confidence: 0.97,
    flowSpeedMs: 0.24,
    stabilityScore: 0.94,
    algaeRisk: 0.08,
    frameId: 'FRM-018401',
    detectedAt: '07:43:52.1',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.94,
    chlIntensity: 0.89,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 92,
      gfp508Peak: 94,
      rfp585Peak: 28,
      chl685Peak: 89,
    },
    notes: 'Large arborescent staghorn donor colony on primary basalt ridge; strong GFP 508nm emission.',
  },
  {
    id: 'C-02',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora millepora (Branching Bush)',
    genetId: 'GEN-AM-02',
    localX: 6.1,
    localY: 2.6,
    depthM: 18.4,
    boundsM: [1.54, 1.42, 0.96],
    substrate: 'hard_rock',
    surfaceNormal: [-0.04, 0.05, 0.99],
    uncertainty: 0.11,
    confidence: 0.95,
    flowSpeedMs: 0.26,
    stabilityScore: 0.91,
    algaeRisk: 0.1,
    frameId: 'FRM-018404',
    detectedAt: '07:43:56.8',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.88,
    chlIntensity: 0.86,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 88,
      gfp508Peak: 88,
      rfp585Peak: 34,
      chl685Peak: 86,
    },
    notes: 'Dense branching Acropora colony; verified clonal match for loose fragment F-03 / C-13.',
  },
  {
    id: 'C-03',
    status: 'Dead',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Carbonate Thicket Hub)',
    genetId: 'SUBSTRATE-CARB',
    localX: 3.4,
    localY: 7.4,
    depthM: 18.6,
    boundsM: [1.92, 1.74, 1.18],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.05, 0.08, 0.99],
    uncertainty: 0.14,
    confidence: 0.92,
    flowSpeedMs: 0.28,
    stabilityScore: 0.89,
    algaeRisk: 0.12,
    frameId: 'FRM-018408',
    detectedAt: '07:44:01.2',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.08,
    chlIntensity: 0.05,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 6,
      gfp508Peak: 8,
      rfp585Peak: 6,
      chl685Peak: 5,
    },
    notes: 'Large intact branching carbonate framework; prime central clump hub for seating.',
  },
  {
    id: 'C-04',
    status: 'Bleached',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Staghorn Canopy)',
    genetId: 'GEN-AC-04',
    localX: 4.6,
    localY: 8.1,
    depthM: 18.5,
    boundsM: [1.78, 1.62, 1.14],
    substrate: 'hard_rock',
    surfaceNormal: [0.04, -0.06, 0.99],
    uncertainty: 0.12,
    confidence: 0.94,
    flowSpeedMs: 0.29,
    stabilityScore: 0.88,
    algaeRisk: 0.18,
    frameId: 'FRM-018412',
    detectedAt: '07:44:05.0',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.62,
    chlIntensity: 0.24,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 96,
      gfp508Peak: 62,
      rfp585Peak: 96,
      chl685Peak: 24,
    },
    notes: 'Thermally stressed large staghorn thicket exhibiting colorful bleaching photoprotective surge.',
  },
  {
    id: 'C-05',
    status: 'Living',
    morphology: 'corymbose',
    species: 'Acropora millepora',
    genetId: 'GEN-PD-05',
    localX: 6.8,
    localY: 3.5,
    depthM: 18.4,
    boundsM: [1.48, 1.36, 0.88],
    substrate: 'hard_rock',
    surfaceNormal: [0.01, 0.03, 0.99],
    uncertainty: 0.09,
    confidence: 0.96,
    flowSpeedMs: 0.22,
    stabilityScore: 0.93,
    algaeRisk: 0.07,
    frameId: 'FRM-018415',
    detectedAt: '07:44:07.6',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.85,
    chlIntensity: 0.84,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 85,
      gfp508Peak: 85,
      rfp585Peak: 22,
      chl685Peak: 84,
    },
    notes: 'Dense corymbose branching coral dome with stable basal attachment.',
  },
  {
    id: 'C-06',
    status: 'Dead',
    morphology: 'tabulate',
    species: 'Acropora palmata (Elkhorn/Table Skeleton)',
    genetId: 'SUBSTRATE-CARB',
    localX: 3.8,
    localY: 8.8,
    depthM: 18.8,
    boundsM: [1.96, 1.78, 1.08],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.06, -0.04, 0.99],
    uncertainty: 0.16,
    confidence: 0.91,
    flowSpeedMs: 0.31,
    stabilityScore: 0.92,
    algaeRisk: 0.14,
    frameId: 'FRM-018418',
    detectedAt: '07:44:09.3',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.06,
    chlIntensity: 0.04,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 4,
      gfp508Peak: 6,
      rfp585Peak: 5,
      chl685Peak: 4,
    },
    notes: 'High-relief structural crest skeleton; zero turf algae overgrowth.',
  },
  {
    id: 'C-07',
    status: 'Placed',
    morphology: 'staghorn',
    species: 'Acropora millepora (Transplanted Thicket)',
    genetId: 'GEN-AM-02',
    localX: 4.8,
    localY: 6.9,
    depthM: 18.3,
    boundsM: [1.46, 1.34, 0.92],
    substrate: 'hard_rock',
    surfaceNormal: [0.02, 0.04, 0.99],
    uncertainty: 0.05,
    confidence: 0.98,
    flowSpeedMs: 0.27,
    stabilityScore: 0.96,
    algaeRisk: 0.05,
    frameId: 'FRM-018421',
    detectedAt: '07:44:12.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.91,
    chlIntensity: 0.87,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 91,
      gfp508Peak: 91,
      rfp585Peak: 31,
      chl685Peak: 87,
    },
    placementShiftMm: 2.1,
    notes: 'Seated fragment F-03 onto clean basalt crest; passed post-placement current push check.',
  },
  {
    id: 'C-08',
    status: 'Placed',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (Transplanted Table)',
    genetId: 'GEN-AH-01',
    localX: 5.7,
    localY: 4.1,
    depthM: 18.3,
    boundsM: [1.52, 1.38, 0.84],
    substrate: 'clean_skeleton',
    surfaceNormal: [-0.02, 0.03, 0.99],
    uncertainty: 0.06,
    confidence: 0.97,
    flowSpeedMs: 0.25,
    stabilityScore: 0.95,
    algaeRisk: 0.06,
    frameId: 'FRM-018422',
    detectedAt: '07:44:13.1',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.89,
    chlIntensity: 0.86,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 89,
      gfp508Peak: 89,
      rfp585Peak: 25,
      chl685Peak: 86,
    },
    placementShiftMm: 1.4,
    notes: 'Same-genet contact transplant placed near GEN-AH-01 for gastrovascular tissue fusion.',
  },
  // CLUSTER 3: Central Crest Staghorn Bank
  {
    id: 'C-09',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (East Crest Thicket)',
    genetId: 'GEN-MC-09',
    localX: 11.4,
    localY: 8.6,
    depthM: 18.9,
    boundsM: [1.82, 1.66, 1.15],
    substrate: 'hard_rock',
    surfaceNormal: [0.07, 0.05, 0.99],
    uncertainty: 0.19,
    confidence: 0.9,
    flowSpeedMs: 0.33,
    stabilityScore: 0.87,
    algaeRisk: 0.11,
    frameId: 'FRM-018424',
    detectedAt: '07:44:14.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.42,
    chlIntensity: 0.82,
    fluorescence: {
      band: 'RFP-Orange (585nm)',
      intensity: 84,
      gfp508Peak: 42,
      rfp585Peak: 88,
      chl685Peak: 82,
    },
    notes: 'Sprawling branching colony expressing 585nm red-orange fluorescent proteins.',
  },
  {
    id: 'C-10',
    status: 'Dead',
    morphology: 'rubble',
    species: 'Rubble Bed (Unstable)',
    genetId: 'SUBSTRATE-RUBBLE',
    localX: 10.8,
    localY: 5.8,
    depthM: 19.2,
    boundsM: [1.18, 1.06, 0.48],
    substrate: 'rubble',
    surfaceNormal: [0.38, -0.29, 0.88],
    uncertainty: 0.58,
    confidence: 0.74,
    flowSpeedMs: 0.36,
    stabilityScore: 0.32,
    algaeRisk: 0.45,
    frameId: 'FRM-018425',
    detectedAt: '07:44:14.6',
    reviewerStatus: 'Uncertain',
    dataProvenance: 'Coverage Gap (Close Pass Required)',
    gfpIntensity: 0.09,
    chlIntensity: 0.12,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 8,
      gfp508Peak: 9,
      rfp585Peak: 8,
      chl685Peak: 12,
    },
    notes: 'Rejected by site optimiser: loose post-storm unconsolidated rubble over shifting sand.',
  },
  {
    id: 'C-11',
    status: 'Bleached',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Giant Staghorn)',
    genetId: 'GEN-AC-04',
    localX: 12.6,
    localY: 7.8,
    depthM: 18.7,
    boundsM: [1.94, 1.76, 1.24],
    substrate: 'clean_skeleton',
    surfaceNormal: [-0.03, 0.04, 0.99],
    uncertainty: 0.15,
    confidence: 0.92,
    flowSpeedMs: 0.28,
    stabilityScore: 0.9,
    algaeRisk: 0.15,
    frameId: 'FRM-018426',
    detectedAt: '07:44:15.1',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.58,
    chlIntensity: 0.29,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 94,
      gfp508Peak: 58,
      rfp585Peak: 94,
      chl685Peak: 29,
    },
    notes: 'Target recipient colony for GEN-AC-04 clonal symbiont bridge seating (Collins et al., 2026).',
  },
  {
    id: 'C-12',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora prolifera (Fused Staghorn)',
    genetId: 'GEN-PC-12',
    localX: 13.5,
    localY: 6.9,
    depthM: 18.6,
    boundsM: [1.86, 1.72, 1.16],
    substrate: 'hard_rock',
    surfaceNormal: [0.02, -0.05, 0.99],
    uncertainty: 0.12,
    confidence: 0.95,
    flowSpeedMs: 0.25,
    stabilityScore: 0.93,
    algaeRisk: 0.09,
    frameId: 'FRM-018427',
    detectedAt: '07:44:15.4',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.82,
    chlIntensity: 0.85,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 81,
      gfp508Peak: 82,
      rfp585Peak: 29,
      chl685Peak: 85,
    },
    notes: 'Dense fused staghorn thicket with high structural integrity.',
  },
  {
    id: 'C-13',
    status: 'Living',
    morphology: 'fragment',
    species: 'Acropora millepora (Loose Branching Donor)',
    genetId: 'GEN-AM-02',
    localX: 2.5,
    localY: 5.8,
    depthM: 18.9,
    boundsM: [1.05, 0.92, 0.68],
    substrate: 'sand',
    surfaceNormal: [0.22, 0.19, 0.95],
    uncertainty: 0.1,
    confidence: 0.95,
    flowSpeedMs: 0.34,
    stabilityScore: 0.2,
    algaeRisk: 0.3,
    frameId: 'FRM-018428',
    detectedAt: '07:44:15.7',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.9,
    chlIntensity: 0.84,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 90,
      gfp508Peak: 90,
      rfp585Peak: 32,
      chl685Peak: 84,
    },
    notes: 'Viable storm-detached branching cluster resting on sand trough; priority rescue.',
  },
  {
    id: 'C-14',
    status: 'Living',
    morphology: 'corymbose',
    species: 'Stylophora pistillata (Branching Cluster)',
    genetId: 'GEN-SP-14',
    localX: 14.2,
    localY: 8.3,
    depthM: 19.1,
    boundsM: [1.56, 1.44, 0.94],
    substrate: 'hard_rock',
    surfaceNormal: [-0.05, 0.02, 0.99],
    uncertainty: 0.21,
    confidence: 0.89,
    flowSpeedMs: 0.29,
    stabilityScore: 0.89,
    algaeRisk: 0.12,
    frameId: 'FRM-018429',
    detectedAt: '07:44:15.9',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.46,
    chlIntensity: 0.81,
    fluorescence: {
      band: 'RFP-Orange (585nm)',
      intensity: 87,
      gfp508Peak: 46,
      rfp585Peak: 87,
      chl685Peak: 81,
    },
    notes: 'Large branching hood coral on central ridge ledge.',
  },
  {
    id: 'C-15',
    status: 'Dead',
    morphology: 'rubble',
    species: 'Algae-Covered Ledge',
    genetId: 'SUBSTRATE-ALGAE',
    localX: 1.8,
    localY: 10.4,
    depthM: 19.1,
    boundsM: [1.24, 1.12, 0.62],
    substrate: 'algae_rock',
    surfaceNormal: [0.18, -0.24, 0.95],
    uncertainty: 0.48,
    confidence: 0.79,
    flowSpeedMs: 0.21,
    stabilityScore: 0.45,
    algaeRisk: 0.82,
    frameId: 'FRM-018430',
    detectedAt: '07:44:16.0',
    reviewerStatus: 'Uncertain',
    dataProvenance: 'Coverage Gap (Close Pass Required)',
    gfpIntensity: 0.11,
    chlIntensity: 0.48,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 12,
      gfp508Peak: 11,
      rfp585Peak: 14,
      chl685Peak: 48,
    },
    notes: 'High macroalgae competition risk; rejected by classical site optimiser.',
  },
  {
    id: 'C-16',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Donor Branch Thicket)',
    genetId: 'GEN-AC-04',
    localX: 5.2,
    localY: 4.9,
    depthM: 18.7,
    boundsM: [1.32, 1.18, 0.84],
    substrate: 'rubble',
    surfaceNormal: [0.12, 0.09, 0.98],
    uncertainty: 0.09,
    confidence: 0.96,
    flowSpeedMs: 0.3,
    stabilityScore: 0.28,
    algaeRisk: 0.22,
    frameId: 'FRM-018431',
    detectedAt: '07:44:16.2',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.93,
    chlIntensity: 0.88,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 93,
      gfp508Peak: 93,
      rfp585Peak: 36,
      chl685Peak: 88,
    },
    notes: 'Healthy clonal staghorn cluster matching C-04 and C-11; queued for next transplant cycle.',
  },
  // CLUSTER 4: Northern Acropora Amphitheatre & Pinnacle Ridge
  {
    id: 'C-17',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Pinnacle Staghorn Donor)',
    genetId: 'GEN-AH-01',
    localX: 15.8,
    localY: 18.2,
    depthM: 16.4,
    boundsM: [1.74, 1.58, 1.12],
    substrate: 'sand',
    surfaceNormal: [0.14, 0.11, 0.98],
    uncertainty: 0.09,
    confidence: 0.96,
    flowSpeedMs: 0.27,
    stabilityScore: 0.34,
    algaeRisk: 0.14,
    frameId: 'FRM-018435',
    detectedAt: '07:44:18.1',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.95,
    chlIntensity: 0.91,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 95,
      gfp508Peak: 95,
      rfp585Peak: 30,
      chl685Peak: 91,
    },
    notes: 'High-vitality shallow pinnacle staghorn thicket; primary donor for Northern Amphitheatre.',
  },
  {
    id: 'C-18',
    status: 'Dead',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (Crest Hub Canopy)',
    genetId: 'SUBSTRATE-CARB',
    localX: 17.2,
    localY: 19.6,
    depthM: 15.8,
    boundsM: [2.25, 2.04, 1.18],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.02, 0.03, 0.99],
    uncertainty: 0.07,
    confidence: 0.98,
    flowSpeedMs: 0.25,
    stabilityScore: 0.97,
    algaeRisk: 0.05,
    frameId: 'FRM-018438',
    detectedAt: '07:44:19.4',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.08,
    chlIntensity: 0.06,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 7,
      gfp508Peak: 8,
      rfp585Peak: 6,
      chl685Peak: 6,
    },
    notes: 'Massive sunlit pinnacle hub (15.8m shallow crest); 1 seated fragment spreads across C-18, C-19, and C-20.',
  },
  {
    id: 'C-19',
    status: 'Bleached',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Pinnacle Staghorn)',
    genetId: 'GEN-AH-01',
    localX: 18.6,
    localY: 20.4,
    depthM: 16.2,
    boundsM: [1.98, 1.82, 1.22],
    substrate: 'hard_rock',
    surfaceNormal: [-0.03, 0.04, 0.99],
    uncertainty: 0.11,
    confidence: 0.94,
    flowSpeedMs: 0.26,
    stabilityScore: 0.94,
    algaeRisk: 0.09,
    frameId: 'FRM-018440',
    detectedAt: '07:44:20.2',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.64,
    chlIntensity: 0.28,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 93,
      gfp508Peak: 64,
      rfp585Peak: 93,
      chl685Peak: 28,
    },
    notes: 'Northern Amphitheatre neighbor staghorn thicket receiving radial symbiont transfer from C-18 hub.',
  },
  {
    id: 'C-20',
    status: 'Dead',
    morphology: 'staghorn',
    species: 'Acropora millepora (Branching Framework)',
    genetId: 'SUBSTRATE-CARB',
    localX: 15.9,
    localY: 20.8,
    depthM: 16.7,
    boundsM: [1.76, 1.62, 1.08],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.04, -0.03, 0.99],
    uncertainty: 0.12,
    confidence: 0.93,
    flowSpeedMs: 0.24,
    stabilityScore: 0.92,
    algaeRisk: 0.08,
    frameId: 'FRM-018442',
    detectedAt: '07:44:21.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.07,
    chlIntensity: 0.05,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 6,
      gfp508Peak: 7,
      rfp585Peak: 5,
      chl685Peak: 5,
    },
    notes: 'Secondary receptor in Clump Gamma within radial propagation envelope of C-18.',
  },
  // CLUSTER 5: Central Sand Channel & Carbonate Patch Reefs
  {
    id: 'C-21',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Channel Staghorn Donor)',
    genetId: 'GEN-AM-02',
    localX: 20.2,
    localY: 7.4,
    depthM: 20.1,
    boundsM: [1.68, 1.52, 1.06],
    substrate: 'sand',
    surfaceNormal: [0.16, -0.12, 0.98],
    uncertainty: 0.11,
    confidence: 0.95,
    flowSpeedMs: 0.32,
    stabilityScore: 0.25,
    algaeRisk: 0.19,
    frameId: 'FRM-018445',
    detectedAt: '07:44:22.4',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.91,
    chlIntensity: 0.87,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 91,
      gfp508Peak: 91,
      rfp585Peak: 33,
      chl685Peak: 87,
    },
    notes: 'Large branching thicket in central channel; shortest-path donor for Patch Reef Clump Delta (C-22).',
  },
  {
    id: 'C-22',
    status: 'Placed',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Patch Hub Outplant)',
    genetId: 'GEN-AM-02',
    localX: 21.8,
    localY: 8.6,
    depthM: 19.6,
    boundsM: [2.08, 1.92, 1.26],
    substrate: 'hard_rock',
    surfaceNormal: [0.01, 0.02, 0.99],
    uncertainty: 0.06,
    confidence: 0.97,
    flowSpeedMs: 0.26,
    stabilityScore: 0.96,
    algaeRisk: 0.06,
    frameId: 'FRM-018448',
    detectedAt: '07:44:23.8',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.89,
    chlIntensity: 0.85,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 89,
      gfp508Peak: 89,
      rfp585Peak: 28,
      chl685Peak: 85,
    },
    placementShiftMm: 1.7,
    notes: 'Central patch reef hub bommie; seated GEN-AM-02 branching coral actively spreading to C-23 and C-24.',
  },
  {
    id: 'C-23',
    status: 'Bleached',
    morphology: 'corymbose',
    species: 'Acropora millepora',
    genetId: 'GEN-AM-02',
    localX: 23.1,
    localY: 9.4,
    depthM: 19.9,
    boundsM: [1.74, 1.58, 1.04],
    substrate: 'hard_rock',
    surfaceNormal: [-0.02, 0.05, 0.99],
    uncertainty: 0.13,
    confidence: 0.92,
    flowSpeedMs: 0.27,
    stabilityScore: 0.91,
    algaeRisk: 0.11,
    frameId: 'FRM-018450',
    detectedAt: '07:44:24.5',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.61,
    chlIntensity: 0.34,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 90,
      gfp508Peak: 61,
      rfp585Peak: 90,
      chl685Peak: 34,
    },
    notes: 'Clonal GEN-AM-02 colony receiving symbiont plume down-current from C-22 hub.',
  },
  {
    id: 'C-24',
    status: 'Dead',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Skeleton Thicket)',
    genetId: 'SUBSTRATE-CARB',
    localX: 22.8,
    localY: 7.2,
    depthM: 20.5,
    boundsM: [1.88, 1.72, 1.18],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.05, -0.04, 0.99],
    uncertainty: 0.15,
    confidence: 0.91,
    flowSpeedMs: 0.29,
    stabilityScore: 0.89,
    algaeRisk: 0.12,
    frameId: 'FRM-018452',
    detectedAt: '07:44:25.2',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.09,
    chlIntensity: 0.06,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 8,
      gfp508Peak: 9,
      rfp585Peak: 7,
      chl685Peak: 6,
    },
    notes: 'Large branching carbonate framework on eastern edge of Clump Delta.',
  },
  // CLUSTER 10: Eastern Mesophotic Drop-Off Wall & Outcrop
  {
    id: 'C-25',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora tenuis (Mesophotic Branching Donor)',
    genetId: 'GEN-MC-09',
    localX: 31.4,
    localY: 17.8,
    depthM: 22.4,
    boundsM: [1.96, 1.82, 1.24],
    substrate: 'hard_rock',
    surfaceNormal: [0.04, 0.03, 0.99],
    uncertainty: 0.14,
    confidence: 0.94,
    flowSpeedMs: 0.23,
    stabilityScore: 0.95,
    algaeRisk: 0.07,
    frameId: 'FRM-018455',
    detectedAt: '07:44:26.8',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.48,
    chlIntensity: 0.89,
    fluorescence: {
      band: 'RFP-Orange (585nm)',
      intensity: 91,
      gfp508Peak: 48,
      rfp585Peak: 92,
      chl685Peak: 89,
    },
    notes: 'Deep mesophotic RFP-585nm branching donor colony on upper drop-off terrace.',
  },
  {
    id: 'C-26',
    status: 'Dead',
    morphology: 'boulder',
    species: 'Porites lobata (Deep Wall Hub)',
    genetId: 'SUBSTRATE-CARB',
    localX: 32.8,
    localY: 18.8,
    depthM: 23.4,
    boundsM: [2.18, 1.98, 1.32],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.06, 0.04, 0.99],
    uncertainty: 0.16,
    confidence: 0.92,
    flowSpeedMs: 0.24,
    stabilityScore: 0.94,
    algaeRisk: 0.08,
    frameId: 'FRM-018458',
    detectedAt: '07:44:28.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.06,
    chlIntensity: 0.04,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 5,
      gfp508Peak: 6,
      rfp585Peak: 5,
      chl685Peak: 4,
    },
    notes: 'Massive mesophotic carbonate buttress at -23.4m; optimal hub for Deep Wall Clump Epsilon.',
  },
  {
    id: 'C-27',
    status: 'Bleached',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (Mesophotic Canopy)',
    genetId: 'GEN-AH-01',
    localX: 34.1,
    localY: 19.6,
    depthM: 24.1,
    boundsM: [2.12, 1.94, 1.08],
    substrate: 'hard_rock',
    surfaceNormal: [0.05, -0.05, 0.99],
    uncertainty: 0.18,
    confidence: 0.9,
    flowSpeedMs: 0.22,
    stabilityScore: 0.91,
    algaeRisk: 0.09,
    frameId: 'FRM-018460',
    detectedAt: '07:44:29.1',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.59,
    chlIntensity: 0.31,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 88,
      gfp508Peak: 59,
      rfp585Peak: 88,
      chl685Peak: 31,
    },
    notes: 'Deep terrace table coral canopy in Clump Epsilon.',
  },
  {
    id: 'C-28',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Deep Wall Thicket)',
    genetId: 'GEN-SP-14',
    localX: 33.8,
    localY: 17.2,
    depthM: 24.6,
    boundsM: [1.84, 1.68, 1.18],
    substrate: 'hard_rock',
    surfaceNormal: [-0.04, 0.06, 0.99],
    uncertainty: 0.22,
    confidence: 0.89,
    flowSpeedMs: 0.25,
    stabilityScore: 0.9,
    algaeRisk: 0.1,
    frameId: 'FRM-018462',
    detectedAt: '07:44:30.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Coverage Gap (Close Pass Required)',
    gfpIntensity: 0.49,
    chlIntensity: 0.83,
    fluorescence: {
      band: 'RFP-Orange (585nm)',
      intensity: 86,
      gfp508Peak: 49,
      rfp585Peak: 86,
      chl685Peak: 83,
    },
    notes: 'Deepest mapped mesophotic branching colony on eastern drop-off ledge (-24.6m).',
  },
  // ADDITIONAL SPRAWLING CLUSTERS ACROSS THE ENTIRE REEF CANYON (C-29 to C-42)
  // CLUSTER 6: Northwest Sunlit Acropora Ridge (X=6..10, Y=16..20)
  {
    id: 'C-29',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (NW Crest Thicket)',
    genetId: 'GEN-AH-01',
    localX: 7.4,
    localY: 17.8,
    depthM: 16.9,
    boundsM: [2.04, 1.88, 1.28],
    substrate: 'hard_rock',
    surfaceNormal: [0.02, 0.03, 0.99],
    uncertainty: 0.08,
    confidence: 0.97,
    flowSpeedMs: 0.25,
    stabilityScore: 0.95,
    algaeRisk: 0.06,
    frameId: 'FRM-018464',
    detectedAt: '07:44:31.2',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.94,
    chlIntensity: 0.9,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 94,
      gfp508Peak: 94,
      rfp585Peak: 30,
      chl685Peak: 90,
    },
    notes: 'Massive northwest sunlit staghorn reef garden with dense bifurcating antlers.',
  },
  {
    id: 'C-30',
    status: 'Living',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (NW Canopy Plate)',
    genetId: 'GEN-AH-01',
    localX: 8.9,
    localY: 18.9,
    depthM: 16.6,
    boundsM: [2.16, 1.94, 1.04],
    substrate: 'hard_rock',
    surfaceNormal: [-0.02, 0.04, 0.99],
    uncertainty: 0.09,
    confidence: 0.96,
    flowSpeedMs: 0.24,
    stabilityScore: 0.96,
    algaeRisk: 0.05,
    frameId: 'FRM-018466',
    detectedAt: '07:44:32.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.92,
    chlIntensity: 0.89,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 92,
      gfp508Peak: 92,
      rfp585Peak: 27,
      chl685Peak: 89,
    },
    notes: 'Wide cantilevered table coral interlocking with NW staghorn thicket.',
  },
  {
    id: 'C-31',
    status: 'Bleached',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (NW Spur)',
    genetId: 'GEN-AC-04',
    localX: 6.8,
    localY: 19.6,
    depthM: 17.1,
    boundsM: [1.82, 1.66, 1.16],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.03, -0.03, 0.99],
    uncertainty: 0.11,
    confidence: 0.94,
    flowSpeedMs: 0.27,
    stabilityScore: 0.92,
    algaeRisk: 0.1,
    frameId: 'FRM-018468',
    detectedAt: '07:44:32.8',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.63,
    chlIntensity: 0.3,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 92,
      gfp508Peak: 63,
      rfp585Peak: 92,
      chl685Peak: 30,
    },
    notes: 'Bleached staghorn thicket adjacent to healthy C-29 donor garden.',
  },
  // CLUSTER 7: Mid-Reef Acropora Garden (X=12..16, Y=12..15)
  {
    id: 'C-32',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (Central Reef Forest)',
    genetId: 'GEN-AM-02',
    localX: 13.6,
    localY: 13.4,
    depthM: 17.8,
    boundsM: [2.18, 1.96, 1.34],
    substrate: 'hard_rock',
    surfaceNormal: [0.01, 0.02, 0.99],
    uncertainty: 0.07,
    confidence: 0.98,
    flowSpeedMs: 0.26,
    stabilityScore: 0.96,
    algaeRisk: 0.06,
    frameId: 'FRM-018470',
    detectedAt: '07:44:33.5',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.95,
    chlIntensity: 0.91,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 95,
      gfp508Peak: 95,
      rfp585Peak: 31,
      chl685Peak: 91,
    },
    notes: 'Towering central staghorn coral forest with bright axial corallite tips.',
  },
  {
    id: 'C-33',
    status: 'Placed',
    morphology: 'staghorn',
    species: 'Acropora millepora (Central Outplant Hub)',
    genetId: 'GEN-AM-02',
    localX: 15.2,
    localY: 12.6,
    depthM: 18.0,
    boundsM: [1.76, 1.62, 1.12],
    substrate: 'hard_rock',
    surfaceNormal: [0.03, 0.01, 0.99],
    uncertainty: 0.06,
    confidence: 0.97,
    flowSpeedMs: 0.25,
    stabilityScore: 0.95,
    algaeRisk: 0.06,
    frameId: 'FRM-018472',
    detectedAt: '07:44:34.1',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.91,
    chlIntensity: 0.88,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 91,
      gfp508Peak: 91,
      rfp585Peak: 29,
      chl685Peak: 88,
    },
    placementShiftMm: 1.5,
    notes: 'Verified outplant hub connecting central staghorn ridge.',
  },
  {
    id: 'C-34',
    status: 'Living',
    morphology: 'corymbose',
    species: 'Acropora humilis (Digitform Cluster)',
    genetId: 'GEN-AM-02',
    localX: 14.8,
    localY: 14.5,
    depthM: 17.6,
    boundsM: [1.68, 1.54, 0.98],
    substrate: 'hard_rock',
    surfaceNormal: [-0.02, 0.03, 0.99],
    uncertainty: 0.08,
    confidence: 0.96,
    flowSpeedMs: 0.24,
    stabilityScore: 0.94,
    algaeRisk: 0.07,
    frameId: 'FRM-018474',
    detectedAt: '07:44:34.9',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.9,
    chlIntensity: 0.87,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 90,
      gfp508Peak: 90,
      rfp585Peak: 28,
      chl685Peak: 87,
    },
    notes: 'Thick finger-branching corymbose cluster on central bommie crest.',
  },
  // CLUSTER 8: South Channel Staghorn Meadow (X=16..20, Y=2..5)
  {
    id: 'C-35',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (South Meadow Thicket)',
    genetId: 'GEN-AC-04',
    localX: 16.8,
    localY: 3.2,
    depthM: 19.3,
    boundsM: [2.06, 1.88, 1.24],
    substrate: 'hard_rock',
    surfaceNormal: [0.02, -0.02, 0.99],
    uncertainty: 0.09,
    confidence: 0.96,
    flowSpeedMs: 0.28,
    stabilityScore: 0.93,
    algaeRisk: 0.08,
    frameId: 'FRM-018476',
    detectedAt: '07:44:35.6',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.92,
    chlIntensity: 0.88,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 92,
      gfp508Peak: 92,
      rfp585Peak: 31,
      chl685Peak: 88,
    },
    notes: 'Expansive southern staghorn coral meadow thriving in laminar channel flow.',
  },
  {
    id: 'C-36',
    status: 'Bleached',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (South Spur)',
    genetId: 'GEN-AC-04',
    localX: 18.4,
    localY: 2.6,
    depthM: 19.5,
    boundsM: [1.84, 1.68, 1.15],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.04, 0.03, 0.99],
    uncertainty: 0.12,
    confidence: 0.93,
    flowSpeedMs: 0.29,
    stabilityScore: 0.9,
    algaeRisk: 0.11,
    frameId: 'FRM-018478',
    detectedAt: '07:44:36.2',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.6,
    chlIntensity: 0.31,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 91,
      gfp508Peak: 60,
      rfp585Peak: 91,
      chl685Peak: 31,
    },
    notes: 'Southern staghorn colony scheduled for clonal symbiont bridge seeding.',
  },
  // CLUSTER 9: Northeast Spur Table & Staghorn Crest (X=24..28, Y=19..23)
  {
    id: 'C-37',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (NE Outer Ridge)',
    genetId: 'GEN-AH-01',
    localX: 25.4,
    localY: 20.8,
    depthM: 18.9,
    boundsM: [2.14, 1.94, 1.32],
    substrate: 'hard_rock',
    surfaceNormal: [0.03, 0.02, 0.99],
    uncertainty: 0.1,
    confidence: 0.95,
    flowSpeedMs: 0.27,
    stabilityScore: 0.95,
    algaeRisk: 0.07,
    frameId: 'FRM-018480',
    detectedAt: '07:44:37.0',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.93,
    chlIntensity: 0.89,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 93,
      gfp508Peak: 93,
      rfp585Peak: 29,
      chl685Peak: 89,
    },
    notes: 'Large northeast ridge arborescent staghorn thicket overlooking the outer wall.',
  },
  {
    id: 'C-38',
    status: 'Living',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (NE Table Canopy)',
    genetId: 'GEN-AH-01',
    localX: 27.1,
    localY: 21.8,
    depthM: 19.2,
    boundsM: [2.28, 2.06, 1.12],
    substrate: 'hard_rock',
    surfaceNormal: [-0.02, 0.04, 0.99],
    uncertainty: 0.11,
    confidence: 0.95,
    flowSpeedMs: 0.26,
    stabilityScore: 0.94,
    algaeRisk: 0.07,
    frameId: 'FRM-018482',
    detectedAt: '07:44:37.8',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.91,
    chlIntensity: 0.88,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 91,
      gfp508Peak: 91,
      rfp585Peak: 28,
      chl685Peak: 88,
    },
    notes: 'Multi-tiered table coral sheltering juvenile reef fish on NE crest.',
  },
  {
    id: 'C-39',
    status: 'Dead',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (NE Crest Hub)',
    genetId: 'SUBSTRATE-CARB',
    localX: 26.2,
    localY: 19.4,
    depthM: 19.4,
    boundsM: [1.92, 1.76, 1.18],
    substrate: 'clean_skeleton',
    surfaceNormal: [0.03, -0.02, 0.99],
    uncertainty: 0.13,
    confidence: 0.93,
    flowSpeedMs: 0.28,
    stabilityScore: 0.92,
    algaeRisk: 0.09,
    frameId: 'FRM-018484',
    detectedAt: '07:44:38.4',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.08,
    chlIntensity: 0.05,
    fluorescence: {
      band: 'Carbonate (No Glow)',
      intensity: 6,
      gfp508Peak: 8,
      rfp585Peak: 6,
      chl685Peak: 5,
    },
    notes: 'Clean carbonate staghorn framework ready for outplanting.',
  },
  // CLUSTER 10B: Southeast Outer Terrace Outcrop (X=27..33, Y=4..9)
  {
    id: 'C-40',
    status: 'Living',
    morphology: 'staghorn',
    species: 'Acropora cervicornis (SE Terrace Thicket)',
    genetId: 'GEN-MC-09',
    localX: 28.4,
    localY: 5.8,
    depthM: 21.2,
    boundsM: [2.08, 1.92, 1.28],
    substrate: 'hard_rock',
    surfaceNormal: [0.04, 0.02, 0.99],
    uncertainty: 0.12,
    confidence: 0.94,
    flowSpeedMs: 0.25,
    stabilityScore: 0.94,
    algaeRisk: 0.08,
    frameId: 'FRM-018486',
    detectedAt: '07:44:39.1',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.89,
    chlIntensity: 0.87,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 89,
      gfp508Peak: 89,
      rfp585Peak: 34,
      chl685Peak: 87,
    },
    notes: 'Large southeast terrace staghorn colony with dense upward antler branches.',
  },
  {
    id: 'C-41',
    status: 'Placed',
    morphology: 'staghorn',
    species: 'Acropora millepora (SE Terrace Outplant)',
    genetId: 'GEN-AM-02',
    localX: 30.2,
    localY: 6.9,
    depthM: 21.6,
    boundsM: [1.78, 1.64, 1.14],
    substrate: 'hard_rock',
    surfaceNormal: [0.02, 0.03, 0.99],
    uncertainty: 0.07,
    confidence: 0.96,
    flowSpeedMs: 0.24,
    stabilityScore: 0.95,
    algaeRisk: 0.07,
    frameId: 'FRM-018488',
    detectedAt: '07:44:39.8',
    reviewerStatus: 'Confirmed',
    dataProvenance: 'Measured (Stereo RGB-D + DVL)',
    gfpIntensity: 0.9,
    chlIntensity: 0.86,
    fluorescence: {
      band: 'GFP-Cyan (508nm)',
      intensity: 90,
      gfp508Peak: 90,
      rfp585Peak: 30,
      chl685Peak: 86,
    },
    placementShiftMm: 1.8,
    notes: 'Restored southeast terrace hub colony with strong tissue attachment.',
  },
  {
    id: 'C-42',
    status: 'Bleached',
    morphology: 'tabulate',
    species: 'Acropora hyacinthus (SE Outer Plate)',
    genetId: 'GEN-AH-01',
    localX: 31.6,
    localY: 5.2,
    depthM: 22.1,
    boundsM: [2.16, 1.98, 1.06],
    substrate: 'hard_rock',
    surfaceNormal: [-0.03, 0.04, 0.99],
    uncertainty: 0.14,
    confidence: 0.92,
    flowSpeedMs: 0.26,
    stabilityScore: 0.91,
    algaeRisk: 0.09,
    frameId: 'FRM-018490',
    detectedAt: '07:44:40.5',
    reviewerStatus: 'Needs Review',
    dataProvenance: 'Interpolated (Bathymetric Kriging)',
    gfpIntensity: 0.61,
    chlIntensity: 0.32,
    fluorescence: {
      band: 'Hyper-Neon Stress',
      intensity: 90,
      gfp508Peak: 61,
      rfp585Peak: 90,
      chl685Peak: 32,
    },
    notes: 'Large tiered table coral on southeast outer terrace receiving symbiont plume from C-41.',
  },
];

export const INITIAL_DECISION_TRACE: DecisionTraceEvent[] = [
  {
    id: 'evt-6',
    timestamp: '16:33:16',
    actionType: 'Coral Placement Verified',
    toolCalled: 'verify',
    headline: 'Secured new coral at C-07 & verified stability',
    summary: 'Coral is firmly attached on flat rock (moved only 2.1 mm in current)',
    clusterId: 'C-07',
    frameId: 'FRM-018421',
    modelVersion: 'Gemma-4-Edge + SiteOptimiser v2.4',
    alternativesConsidered: [
      'Skipped C-10: Loose rubble slope could shift in strong water',
      'Skipped C-15: Too much seaweed nearby (82% algae risk)',
      'Kept C-03 as backup: Clean rock hub for next placement',
    ],
    humanReviewStatus: 'Accepted',
    operatorReason: 'Verified nominal (< 3.0 mm shift)',
    surfaceNormal: [0.02, 0.04, 0.99],
    placementShiftMm: 2.1,
    confidence: 0.96,
    gripperForceN: 0.0,
    uncertainty: 0.05,
    outcome: 'Passed stability test — coral firmly attached',
    statusTone: 'nominal',
    reasoning:
      'Rock surface at C-07 is flat, sunlit, and stable. After seating the coral, a gentle water-push check confirmed it shifted only 2.1 mm (well within the 3.0 mm safety limit).',
  },
  {
    id: 'evt-5',
    timestamp: '16:33:02',
    actionType: 'Carrying Coral to Target',
    toolCalled: 'carry',
    headline: 'Carrying healthy coral fragment to C-07',
    summary: 'Cruising smoothly while compensating for coral weight',
    clusterId: 'C-07',
    frameId: 'FRM-018419',
    modelVersion: 'Gemma-4-Edge + CarryPID v2.0',
    alternativesConsidered: ['Steered around C-10 rubble to keep a safe 0.5 m clearance above the reef'],
    humanReviewStatus: 'Accepted',
    surfaceNormal: [0.02, 0.04, 0.99],
    placementShiftMm: 0.0,
    confidence: 0.94,
    gripperForceN: 14.2,
    uncertainty: 0.08,
    outcome: 'Steady flight with coral held safely',
    statusTone: 'nominal',
    reasoning:
      'Chose C-07 because it has solid rock and matches the donor coral type. Thrusters automatically adjusted for the extra 0.45 kg weight of the carried coral.',
  },
  {
    id: 'evt-4',
    timestamp: '16:32:44',
    actionType: 'Picked Up Donor Coral',
    toolCalled: 'grasp',
    headline: 'Gently picked up loose live coral at C-13',
    summary: 'Soft gripper holding coral at a safe 14.6 N grip force',
    clusterId: 'C-13',
    frameId: 'FRM-018414',
    modelVersion: 'YOLO11n-Reef-Seg + ForceJaw v2.1',
    alternativesConsidered: ['Left C-16 for later because C-13 is closer to the restoration clump'],
    humanReviewStatus: 'Accepted',
    surfaceNormal: [0.22, 0.19, 0.95],
    placementShiftMm: 0.8,
    confidence: 0.95,
    gripperForceN: 14.6,
    uncertainty: 0.1,
    outcome: 'Coral held securely in soft gripper (14.6 N)',
    statusTone: 'nominal',
    reasoning:
      'Found a healthy, storm-detached coral fragment (Acropora millepora) resting on sand where it would otherwise die. Aligned the soft robotic fingers and closed with a gentle 14.6 N grip.',
  },
  {
    id: 'evt-3',
    timestamp: '16:32:31',
    actionType: 'Moved to Donor Coral',
    toolCalled: 'goto',
    headline: 'Arrived above healthy donor coral C-13',
    summary: 'Hovering steadily 38 cm above the seabed',
    clusterId: 'C-13',
    frameId: 'FRM-018410',
    modelVersion: 'Gemma-4-Edge + DVL-Lock v2.4',
    alternativesConsidered: ['Lowered from 1.0 m to 0.38 m for a clearer camera view before pickup'],
    humanReviewStatus: 'Accepted',
    surfaceNormal: [0.22, 0.19, 0.95],
    placementShiftMm: 0.0,
    confidence: 0.92,
    gripperForceN: 0.0,
    uncertainty: 0.1,
    outcome: 'Hovering in position within 1.2 cm accuracy',
    statusTone: 'nominal',
    reasoning:
      'Guided the submarine to donor coral C-13 (X 3.35 m, Y 3.85 m, depth 19.0 m) and locked hover position before extending the robotic arm.',
  },
  {
    id: 'evt-2',
    timestamp: '16:32:19',
    actionType: 'Site Safety Check',
    toolCalled: 'inspect',
    headline: 'Skipped loose rubble at C-10; chose solid rock at C-07',
    summary: 'Avoided unstable seabed that could wash away',
    clusterId: 'C-10',
    frameId: 'FRM-018406',
    modelVersion: 'SiteOptimiser v2.4 + VoI-Gate',
    alternativesConsidered: [
      'Skipped C-10: Seabed is loose rubble on a steep slope',
      'Selected C-07: Solid rock with matching coral family',
    ],
    humanReviewStatus: 'Accepted',
    operatorReason: 'Uncertain substrate',
    surfaceNormal: [0.38, -0.29, 0.88],
    placementShiftMm: 0.0,
    confidence: 0.91,
    gripperForceN: 0.0,
    uncertainty: 0.58,
    outcome: 'Rerouted away from loose rubble at C-10',
    statusTone: 'warning',
    reasoning:
      'Camera and depth sensors showed that C-10 is loose, shifting rubble. Placing a coral there would risk it washing away, so the robot automatically picked C-07 instead.',
  },
  {
    id: 'evt-1',
    timestamp: '16:31:58',
    actionType: 'Reef Area Scan',
    toolCalled: 'scan',
    headline: 'Mapped 28 coral colonies across the reef canyon',
    summary: 'Identified healthy donors, bleached corals, and best rescue hubs',
    clusterId: 'C-01',
    frameId: 'FRM-018401',
    modelVersion: 'YOLO11n-Reef-Seg + UV-GFP v2.4',
    alternativesConsidered: ['Combined normal camera + UV light to spot glowing healthy corals'],
    humanReviewStatus: 'Accepted',
    surfaceNormal: [0.03, -0.02, 0.99],
    placementShiftMm: 0.0,
    confidence: 0.97,
    gripperForceN: 0.0,
    uncertainty: 0.08,
    outcome: 'All 28 coral locations mapped in 3D',
    statusTone: 'nominal',
    reasoning:
      'Scanned the reef using stereo cameras and UV light to separate glowing healthy corals from dead or bleached clumps that need rescue.',
  },
];

export const INITIAL_AUV_SUBSYSTEMS: AuvSubsystem[] = [
  {
    id: 'sub-bat-a',
    name: 'Primary LiFePO4 Battery Pack A',
    category: 'Power',
    status: 'Nominal',
    healthPct: 96,
    temperatureC: 28.2,
    currentDrawA: 8.4,
    voltageV: 48.2,
    detail: 'Starboard titanium pod · 84.2% charge · Est. return reserve 18.0% · 2h 48m remaining',
    telemetryLabel: 'State of Charge / Reserve',
    telemetryValue: '84.2% (Reserve 18%)',
    freshnessSec: 0.4,
    position3D: [0.55, -0.15, 0.25],
  },
  {
    id: 'sub-bat-b',
    name: 'Avionics & Compute Battery Pack B',
    category: 'Power',
    status: 'Nominal',
    healthPct: 99,
    temperatureC: 27.6,
    currentDrawA: 3.1,
    voltageV: 24.4,
    detail: 'Isolated rail for Jetson Orin Nano 8GB + stereo optical array · 91.6% charge',
    telemetryLabel: 'State of Charge',
    telemetryValue: '91.6% (24.4 V)',
    freshnessSec: 0.4,
    position3D: [0.55, -0.15, -0.25],
  },
  {
    id: 'sub-thruster-port',
    name: 'Port Vectored Thruster (T-01)',
    category: 'Propulsion',
    status: 'Warning',
    healthPct: 78,
    temperatureC: 34.8,
    currentDrawA: 5.9,
    voltageV: 48.0,
    detail: 'High current draw (+18% above nominal curve) from minor filament drag on nozzle shroud; compensated in PID mixer',
    telemetryLabel: 'Current Draw',
    telemetryValue: '5.9 A · Warning',
    freshnessSec: 0.2,
    suggestedAction: 'Run reverse cavitation nozzle purge or cap forward surge to 0.35 m/s',
    position3D: [-0.65, 0.05, 0.62],
  },
  {
    id: 'sub-thruster-stbd',
    name: 'Starboard Vectored Thruster (T-02)',
    category: 'Propulsion',
    status: 'Nominal',
    healthPct: 98,
    temperatureC: 29.1,
    currentDrawA: 4.6,
    voltageV: 48.1,
    detail: 'Brushless magnetically coupled thruster operating at 1,420 RPM nominal station-keeping load',
    telemetryLabel: 'Current Draw',
    telemetryValue: '4.6 A · Nominal',
    freshnessSec: 0.2,
    position3D: [-0.65, 0.05, -0.62],
  },
  {
    id: 'sub-thruster-vert',
    name: 'Vertical Heave & Pitch Thrusters (T-03 / T-04)',
    category: 'Propulsion',
    status: 'Nominal',
    healthPct: 97,
    temperatureC: 28.9,
    currentDrawA: 5.2,
    voltageV: 48.1,
    detail: 'Active carry-aware heave feedforward compensating for held coral fragment mass and negative buoyancy trim',
    telemetryLabel: 'Heave Effort',
    telemetryValue: '46.8% Duty',
    freshnessSec: 0.2,
    position3D: [0.0, 0.32, 0.0],
  },
  {
    id: 'sub-cam-rgbd',
    name: 'Stereo RGB-D & UV Fluorescence Array',
    category: 'Perception',
    status: 'Nominal',
    healthPct: 100,
    temperatureC: 26.8,
    currentDrawA: 1.4,
    voltageV: 24.4,
    detail: 'Optical sapphire dome · 10 Hz 3D pinhole projection + 470nm blue/UV excitation for GFP/RFP coral classification',
    telemetryLabel: 'Optical Frame Rate',
    telemetryValue: '29.97 FPS / 38 ms delay',
    freshnessSec: 0.1,
    position3D: [0.95, -0.05, 0.0],
  },
  {
    id: 'sub-arm-6dof',
    name: '6-DoF Coral Micro-Manipulator & Force Jaw',
    category: 'Manipulation',
    status: 'Nominal',
    healthPct: 95,
    temperatureC: 27.4,
    currentDrawA: 2.3,
    voltageV: 24.2,
    detail: 'Compliant silicone micro-gripper with strain-gauge force feedback (0–25 N) and marine adhesive dispenser',
    telemetryLabel: 'Jaw Force / State',
    telemetryValue: 'Open · 0.0 N',
    freshnessSec: 0.2,
    position3D: [0.85, -0.45, 0.0],
  },
  {
    id: 'sub-hull-dvl',
    name: 'Titanium Pressure Hull, DVL & Leak Sensors',
    category: 'Hull & Nav',
    status: 'Nominal',
    healthPct: 100,
    temperatureC: 26.4,
    currentDrawA: 0.9,
    voltageV: 24.4,
    detail: 'Dual vacuum & conductivity moisture probes: Clear (0.0% humidity rise) · 600 kHz phased-array DVL bottom lock (98.4% confidence)',
    telemetryLabel: 'Chamber Vacuum / DVL',
    telemetryValue: 'Clear · -35 kPa · Lock 98%',
    freshnessSec: 0.5,
    position3D: [-0.1, -0.25, 0.0],
  },
];

export const INITIAL_PERMIT_RECORDS: PermitApprovalRecord[] = [
  {
    id: 'perm-gbrmpa',
    authority: 'Great Barrier Reef Marine Park Authority (Reef Authority)',
    referenceCode: 'G26/48912.1',
    title: 'Marine Park Restoration & Loose Fragment Re-Attachment Permit',
    validThrough: '2027-06-30',
    status: 'Permit Verified',
    verifiedBy: 'Dr. E. Vance (Chief Scientist) · 2026-11-07',
    conditions: [
      'Only storm-detached fragments of opportunity resting on sand/rubble may be harvested; zero cutting of intact living colonies.',
      'All outplants must remain within Capricorn Bunker Sector Plot CB-04 (10.0 × 9.9 m georeferenced boundary).',
      'Operations must suspend immediately if lateral current exceeds 0.75 m/s or optical visibility drops below 2.5 m.',
    ],
  },
  {
    id: 'perm-aims-sop',
    authority: 'AIMS / Restoration Research Partner Protocol',
    referenceCode: 'SOP-CORAL-2026-V4',
    title: 'Clonal Genet Compatibility & Biosecure Adhesive Protocol',
    validThrough: '2027-12-31',
    status: 'Permit Verified',
    verifiedBy: 'M. Tan (Marine Operations Lead) · 2026-11-07',
    conditions: [
      'Enforce same-genet pairing or clean carbonate seating; prohibit mixed-genet contact within 15 cm.',
      'Execute post-placement hydrodynamic push verification (< 3.0 mm displacement) on 100% of seated fragments.',
    ],
  },
  {
    id: 'perm-indigenous-tumu',
    authority: 'Traditional Owner Sea Country & Ranger Co-Management',
    referenceCode: 'TUMRA-CB-2026-09',
    title: 'Capricorn Bunker Sea Country Operational Notice & Cultural Exclusion Zone',
    validThrough: '2027-03-31',
    status: 'Permit Verified',
    verifiedBy: 'Ranger Coordinator K. Bonner · 2026-11-06',
    conditions: [
      'Maintain strict No-Go Buffer Zone NGZ-01 around North-West Spawning Crest (X 0.0–2.2 m, Y 7.5–9.9 m).',
      'Provide post-dive georeferenced orthomosaic and colony survival log to Sea Country Ranger Registry.',
    ],
  },
];

export const INITIAL_MISSION_CHECKLIST: MissionChecklistItem[] = [
  {
    id: 'chk-1',
    category: 'Regulatory & Permit',
    label: 'Verify GBRMPA Marine Park Permit G26/48912.1 & TUMRA No-Go Zones',
    detail: 'Confirm site-specific conditions are loaded into hardware geofence and verified by Responsible Person.',
    completed: true,
    requiredForLaunch: true,
  },
  {
    id: 'chk-2',
    category: 'Geofence & No-Go',
    label: 'Lock 10.0 × 9.9 m Survey Box & 30.0 m Hard Depth Floor',
    detail: 'Hardware depth pressure switch and DVL boundary keep-out zones active on Orin Nano.',
    completed: true,
    requiredForLaunch: true,
  },
  {
    id: 'chk-3',
    category: 'Vehicle Pre-Dive',
    label: 'Dual Vacuum Chamber Seal (-35 kPa) & Return Reserve Check (≥ 18%)',
    detail: 'Primary LiFePO4 Pack A at 84.2% (Est. return reserve 18.0% verified).',
    completed: true,
    requiredForLaunch: true,
  },
  {
    id: 'chk-4',
    category: 'Crew & Recovery',
    label: 'Surface Acoustic Relay Buoy & Emergency Recovery Line Ready',
    detail: 'Fail-safe comms timeout set to: Hold Station 15 s → Autonomous Surface Return.',
    completed: true,
    requiredForLaunch: true,
  },
];

export const INITIAL_NOGO_ZONES: NoGoZone[] = [
  {
    id: 'NGZ-01',
    name: 'NW Spawning Crest & Cultural Buffer',
    reason: 'Fragile gravid Acropora spawning table & TUMRA exclusion zone',
    xMin: 0.2,
    xMax: 2.3,
    yMin: 7.4,
    yMax: 9.7,
    maxDepthM: 19.5,
  },
  {
    id: 'NGZ-02',
    name: 'SE Unstable Rubble Chute',
    reason: 'Steep unconsolidated rubble slope (tilt > 30° · entanglement hazard)',
    xMin: 6.7,
    xMax: 8.1,
    yMin: 1.6,
    yMax: 3.1,
    maxDepthM: 20.0,
  },
];

export const INITIAL_ECOLOGICAL_VISITS: EcologicalSurveyVisit[] = [
  {
    id: 'visit-baseline',
    visitCode: 'SV-01 · Baseline',
    date: '2026-09-20',
    dayOffset: 0,
    waterTempC: 26.1,
    sampleSizeColonies: 16,
    missingObservations: 0,
    interventionSurvivalPct: 100,
    referenceControlSurvivalPct: 100,
    meanColonyAreaCm2: 310,
    referenceAreaCm2: 305,
    partialMortalityPct: 14.2,
    shannonDiversityH: 1.68,
    notes: 'Initial georeferenced baseline across Plot CB-04 (n=16) and untreated reference control Plot REF-01 (n=14).',
  },
  {
    id: 'visit-day4',
    visitCode: 'SV-02 · Day 4 Follow-Up',
    date: '2026-09-24',
    dayOffset: 4,
    waterTempC: 26.3,
    sampleSizeColonies: 16,
    missingObservations: 0,
    interventionSurvivalPct: 100,
    referenceControlSurvivalPct: 92.8,
    meanColonyAreaCm2: 322,
    referenceAreaCm2: 302,
    partialMortalityPct: 9.8,
    shannonDiversityH: 1.71,
    notes: 'Clonal tissue fusion bridges observed on same-genet transplants C-07 and C-08; rapid symbiont recovery.',
  },
  {
    id: 'visit-day14',
    visitCode: 'SV-03 · Day 14 Follow-Up',
    date: '2026-10-04',
    dayOffset: 14,
    waterTempC: 26.5,
    sampleSizeColonies: 15,
    missingObservations: 1,
    interventionSurvivalPct: 93.8,
    referenceControlSurvivalPct: 78.6,
    meanColonyAreaCm2: 348,
    referenceAreaCm2: 294,
    partialMortalityPct: 6.4,
    shannonDiversityH: 1.74,
    notes: 'Basal carbonate welding confirmed (>38 N shear). 1 peripheral colony (C-14) partially occluded by surge plume (recorded as missing observation).',
  },
  {
    id: 'visit-day49',
    visitCode: 'SV-04 · Day 49 Current',
    date: '2026-11-08',
    dayOffset: 49,
    waterTempC: 26.4,
    sampleSizeColonies: 16,
    missingObservations: 0,
    interventionSurvivalPct: 93.8,
    referenceControlSurvivalPct: 71.4,
    meanColonyAreaCm2: 392,
    referenceAreaCm2: 288,
    partialMortalityPct: 4.1,
    shannonDiversityH: 1.79,
    notes: 'Week 7 follow-up: +26.4% colony area expansion in restored plot vs -5.6% decline in untreated reference plot.',
  },
];
