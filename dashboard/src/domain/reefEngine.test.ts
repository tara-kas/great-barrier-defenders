import test from 'node:test';
import assert from 'node:assert/strict';
import {
  validatePcaSurfaceNormal,
  calculateSiteScore,
  projectPixelToWorld,
  computeCarryAwareThrusters,
  evaluatePushTest,
  reorderWidgets,
  evaluateGenetCompatibility,
  computeTemporalGrowthStage,
  computeSpectralCurve,
  evaluateMissionReadiness,
  computeOptimalClumpHubAndPath,
  INITIAL_CLUSTERS,
  INITIAL_PERMIT_RECORDS,
  INITIAL_MISSION_CHECKLIST,
} from './reefEngine';

test('validatePcaSurfaceNormal accepts upward-facing normals within 30 degrees of vertical', () => {
  const flatUp = validatePcaSurfaceNormal([0.02, 0.04, 0.99]);
  assert.equal(flatUp.valid, true);
  assert.ok(flatUp.dotZ > 0.866);
  assert.ok(flatUp.tiltAngleDeg < 30);

  const steepWall = validatePcaSurfaceNormal([0.75, 0.2, 0.5]);
  assert.equal(steepWall.valid, false);
  assert.ok(steepWall.tiltAngleDeg > 30);
});

test('calculateSiteScore ranks stable hard rock higher than high-uncertainty rubble and flags VoI', () => {
  const c07 = INITIAL_CLUSTERS.find((c) => c.id === 'C-07')!;
  const c10 = INITIAL_CLUSTERS.find((c) => c.id === 'C-10')!;

  const scoreC07 = calculateSiteScore(c07, [4.0, 4.0]);
  const scoreC10 = calculateSiteScore(c10, [4.0, 4.0]);

  assert.ok(scoreC07.totalScore > scoreC10.totalScore);
  assert.equal(scoreC07.requiresVoIInspection, false);
  assert.equal(scoreC10.requiresVoIInspection, true);
});

test('evaluateGenetCompatibility identifies same-genet fusion vs mixed-genet antagonism', () => {
  const c04 = INITIAL_CLUSTERS.find((c) => c.id === 'C-04')!; // GEN-AC-04
  const c01 = INITIAL_CLUSTERS.find((c) => c.id === 'C-01')!; // GEN-AH-01
  const c03 = INITIAL_CLUSTERS.find((c) => c.id === 'C-03')!; // SUBSTRATE-CARB

  const sameMatch = evaluateGenetCompatibility('GEN-AC-04', c04);
  assert.equal(sameMatch.compatible, true);
  assert.equal(sameMatch.interactionType, 'Clonal Tissue Fusion');

  const mixedMismatch = evaluateGenetCompatibility('GEN-AC-04', c01);
  assert.equal(mixedMismatch.compatible, false);
  assert.equal(mixedMismatch.interactionType, 'Mixed-Genet Antagonism');

  const carbSubstrate = evaluateGenetCompatibility('GEN-AC-04', c03);
  assert.equal(carbSubstrate.compatible, true);
  assert.equal(carbSubstrate.interactionType, 'Inert Carbonate Substrate');
});

test('computeTemporalGrowthStage progresses fusion and calcification from Day 0 to Day 49', () => {
  const c07 = INITIAL_CLUSTERS.find((c) => c.id === 'C-07')!;
  const day0 = computeTemporalGrowthStage(c07, 0);
  const day4 = computeTemporalGrowthStage(c07, 4);
  const day49 = computeTemporalGrowthStage(c07, 49);

  assert.ok(day4.fusionPct > day0.fusionPct);
  assert.ok(day49.fusionPct === 100);
  assert.ok(day49.calcificationBondN > day4.calcificationBondN);
});

test('computeSpectralCurve returns 7 spectral bands including 508nm GFP and 585nm RFP', () => {
  const c01 = INITIAL_CLUSTERS.find((c) => c.id === 'C-01')!;
  const curve = computeSpectralCurve(c01);
  assert.equal(curve.length, 7);
  const gfpBand = curve.find((b) => b.wavelengthNm === 508)!;
  assert.equal(gfpBand.intensityPct, c01.fluorescence.gfp508Peak);
});

test('evaluateMissionReadiness distinguishes Permit Recorded from Permit Verified', () => {
  const readyState = evaluateMissionReadiness({
    permits: INITIAL_PERMIT_RECORDS,
    checklist: INITIAL_MISSION_CHECKLIST,
    currentSpeedMs: 0.28,
    maxAllowedCurrentMs: 0.75,
    visibilityM: 6.5,
    minAllowedVisibilityM: 2.5,
  });
  assert.equal(readyState.ready, true);
  assert.equal(readyState.allPermitsVerified, true);

  const unverifiedPermits = INITIAL_PERMIT_RECORDS.map((p, idx) =>
    idx === 0 ? { ...p, status: 'Permit Recorded (Pending Verification)' as const } : p
  );
  const blockedState = evaluateMissionReadiness({
    permits: unverifiedPermits,
    checklist: INITIAL_MISSION_CHECKLIST,
    currentSpeedMs: 0.28,
    maxAllowedCurrentMs: 0.75,
    visibilityM: 6.5,
    minAllowedVisibilityM: 2.5,
  });
  assert.equal(blockedState.ready, false);
  assert.equal(blockedState.allPermitsVerified, false);
  assert.ok(blockedState.blockers.length > 0);
});

test('projectPixelToWorld, computeCarryAwareThrusters, evaluatePushTest, and reorderWidgets work accurately', () => {
  const worldPos = projectPixelToWorld(0.5, 0.5, 2.0, {
    x: 4.0,
    y: 4.0,
    depthM: 18.1,
    yawRad: 0,
  });
  assert.equal(worldPos[0], 4.0);

  const loaded = computeCarryAwareThrusters({
    surgeSpeedMs: 0.3,
    currentSpeedMs: 0.2,
    holdingFragment: true,
    fragmentMassKg: 0.45,
  });
  assert.equal(loaded.massDeltaKg, 0.45);

  const push = evaluatePushTest(0.28, 0.95, 0.99);
  assert.equal(push.passed, true);

  const reordered = reorderWidgets(['camera', 'map', 'spatial3d', 'trace'], 'trace', 'camera');
  assert.deepEqual(reordered, ['trace', 'camera', 'map', 'spatial3d']);

  const clumpPlan = computeOptimalClumpHubAndPath(INITIAL_CLUSTERS, 'C-13', ['C-03', 'C-04', 'C-06']);
  assert.equal(clumpPlan.donorClusterId, 'C-13');
  assert.equal(clumpPlan.totalClumpCoralsSaved, 3);
  assert.equal(clumpPlan.spreadLinks.length, 2);
  assert.ok(clumpPlan.shortestTransitDistanceM > 0);
});

import {
  PELAGIC_ROBOT_SPECS,
  summarizeRobotVolumeByGroup,
} from './pelagicRobotSpec';

test('PELAGIC_ROBOT_SPECS matches exact SCOUT-01 (50 solids) and RESTORE-02 (52 solids) STEP specifications', () => {
  const scout = PELAGIC_ROBOT_SPECS['scout-01'];
  const restore = PELAGIC_ROBOT_SPECS['restore-02'];

  assert.equal(scout.solid_count, 50);
  assert.equal(scout.parts.length, 50);
  assert.equal(restore.solid_count, 52);
  assert.equal(restore.parts.length, 52);
  assert.deepEqual(scout.size_mm.map((n: number) => Math.round(n)), [959, 676, 715]);

  const groups = summarizeRobotVolumeByGroup('restore-02');
  assert.ok(groups.length >= 6);
  const totalCount = groups.reduce((acc, g) => acc + g.partCount, 0);
  assert.equal(totalCount, 52);
});
