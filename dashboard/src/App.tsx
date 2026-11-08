/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  CoralCluster,
  DecisionTraceEvent,
  AuvSubsystem,
  LiveNotification,
  OptimiserWeights,
  ReviewerStatus,
  DEFAULT_OPTIMISER_WEIGHTS,
  INITIAL_CLUSTERS,
  INITIAL_DECISION_TRACE,
  INITIAL_AUV_SUBSYSTEMS,
  evaluatePushTest,
  reorderWidgets,
} from './domain/reefEngine';
import { LiveCameraFeed } from './components/LiveCameraFeed';
import { ReefMap2D } from './components/ReefMap2D';
import { SpatialView3D } from './components/SpatialView3D';
import { DecisionTracePanel } from './components/DecisionTracePanel';
import { VehicleSystemsView } from './components/VehicleSystemsView';
import { TopologyVerificationView } from './components/TopologyVerificationView';
import { ManualOverrideCockpit } from './components/ManualOverrideCockpit';
import { MissionPlanningPermitView } from './components/MissionPlanningPermitView';
import { ReefRescueLogo } from './components/ReefRescueLogo';
import {
  GripHorizontal,
  Waves,
  CloudFog,
  CheckCircle2,
  RotateCcw,
  ArrowLeftRight,
  Bell,
  Play,
  Pause,
  X,
  ArrowUpRight,
  Sparkles,
  Gamepad2,
  FileCheck2,
} from 'lucide-react';

type ActiveTab = 'mission' | 'override' | 'vehicle' | 'planning' | 'topology';
type WidgetId = 'camera' | 'map' | 'spatial3d' | 'trace';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('tab');
    if (
      t === 'override' ||
      t === 'vehicle' ||
      t === 'planning' ||
      t === 'topology'
    ) {
      return t;
    }
    return 'mission';
  });

  const [clusters, setClusters] = useState<CoralCluster[]>(INITIAL_CLUSTERS);
  const [selectedClusterId, setSelectedClusterId] = useState<string>('C-03');
  const [events, setEvents] = useState<DecisionTraceEvent[]>(INITIAL_DECISION_TRACE);
  const [selectedEventId, setSelectedEventId] = useState<string>(INITIAL_DECISION_TRACE[0].id);
  const [subsystems, setSubsystems] = useState<AuvSubsystem[]>(INITIAL_AUV_SUBSYSTEMS);
  const [selectedSubsystemId, setSelectedSubsystemId] = useState<string>('sub-thruster-port');

  // Classical site optimiser weights & carried donor genet ID (shared across all views)
  const [optimiserWeights, setOptimiserWeights] = useState<OptimiserWeights>(
    DEFAULT_OPTIMISER_WEIGHTS
  );
  const [donorGenetId, setDonorGenetId] = useState<string>('GEN-AM-02');

  // Live AUV telemetry & continuous Harvest -> Shortest-Path -> Clump-Save state machine
  const [vehiclePos, setVehiclePos] = useState<[number, number, number]>([2.5, 5.8, 18.9]);
  const [vehicleTrail, setVehicleTrail] = useState<[number, number][]>([
    [1.8, 4.9],
    [2.15, 5.35],
    [2.5, 5.8],
  ]);
  const [isLivePatrolActive, setIsLivePatrolActive] = useState<boolean>(true);
  const [harvestCycleStage, setHarvestCycleStage] = useState<string>(
    'Step 2 of 4 · Picked Up Healthy Coral C-13 → Carrying to Clump Hub C-03'
  );
  const [clumpSpreadProgress, setClumpSpreadProgress] = useState<number>(0.72);
  const cycleTickRef = useRef<number>(0);

  const [currentSpeedMs, setCurrentSpeedMs] = useState<number>(0.26);
  const [currentVec, setCurrentVec] = useState<[number, number]>([0.24, 0.1]);
  const [turbidity, setTurbidity] = useState<number>(0.08);
  const [holdingFragment, setHoldingFragment] = useState<boolean>(true);
  const [navMode, setNavMode] = useState<'Survey' | 'Transplant' | 'Station-Keep'>('Transplant');
  const [missionHeadline, setMissionHeadline] = useState<string>(
    'Rescuing Clump Alpha (Coral C-13 → Hub C-03)'
  );
  const [missionSubstatus, setMissionSubstatus] = useState<string>(
    'Placing 1 healthy coral at Hub C-03 saves all 3 corals in Clump Alpha (C-03, C-04 & C-06)'
  );
  const [lastCheckedTime, setLastCheckedTime] = useState<string>('07:44:16');
  const [isTracePaused, setIsTracePaused] = useState<boolean>(false);
  const [policyVersion, setPolicyVersion] = useState<'v1' | 'v2'>('v2');

  // Simple, Plain-English Live Notification Stream & Toast Feedback
  const [notifications, setNotifications] = useState<LiveNotification[]>([
    {
      id: 'notif-init-1',
      timestamp: '07:44:16',
      title: 'Saving 3 corals at Clump Alpha (Hub C-03)',
      detail: 'Picked up healthy coral C-13 and carrying it 1.84 m to Hub C-03 so recovery spreads to C-04 & C-06.',
      clusterId: 'C-03',
      tone: 'nominal',
      unread: false,
    },
    {
      id: 'notif-init-2',
      timestamp: '07:42:55',
      title: 'Skipped loose rubble at C-10',
      detail: 'Seabed at C-10 is unstable rubble that could shift in currents. Rerouted to solid rock at C-03.',
      clusterId: 'C-10',
      tone: 'warning',
      unread: true,
    },
    {
      id: 'notif-init-3',
      timestamp: '07:41:30',
      title: 'Picked up healthy donor coral C-13',
      detail: 'Soft gripper is holding a storm-detached healthy coral fragment at a gentle 14.6 N.',
      clusterId: 'C-13',
      tone: 'nominal',
      unread: false,
    },
  ]);
  const [activeToast, setActiveToast] = useState<LiveNotification | null>(notifications[0]);
  const [isNotifDrawerOpen, setIsNotifDrawerOpen] = useState<boolean>(false);
  const [notifFilter, setNotifFilter] = useState<'all' | 'nominal' | 'warning'>('all');
  const [mutePopups, setMutePopups] = useState<boolean>(false);

  // Auto-dismiss bottom-right toast after 6.5 seconds so it stays unobtrusive
  useEffect(() => {
    if (!activeToast) return;
    const timer = window.setTimeout(() => {
      setActiveToast(null);
    }, 6500);
    return () => clearTimeout(timer);
  }, [activeToast]);

  // Drag-and-drop desktop widget arrangement
  const [widgetOrder, setWidgetOrder] = useState<WidgetId[]>([
    'camera',
    'map',
    'spatial3d',
    'trace',
  ]);
  const [draggedWidgetId, setDraggedWidgetId] = useState<WidgetId | null>(null);
  const [dragOverWidgetId, setDragOverWidgetId] = useState<WidgetId | null>(null);
  const [expandedWidgetId, setExpandedWidgetId] = useState<WidgetId | null>(null);

  const formatNowTime = () => {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  };

  const pushNotification = (
    title: string,
    detail: string,
    clusterId: string,
    tone: 'nominal' | 'warning' | 'critical'
  ) => {
    const newNotif: LiveNotification = {
      id: `notif-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: formatNowTime(),
      title,
      detail,
      clusterId,
      tone,
      unread: true,
    };
    setNotifications((prev) => [newNotif, ...prev.slice(0, 19)]);
    if (!mutePopups) {
      setActiveToast(newNotif);
    }
  };

  // Continuous Multi-Stage Harvest Donor (C-13) -> Shortest-Path Transit -> Clump Hub Save (C-03 -> C-04, C-06) Loop
  useEffect(() => {
    if (!isLivePatrolActive || isTracePaused || activeTab === 'override') return;

    const waypoints: Array<{
      pos: [number, number, number];
      holding: boolean;
      spread: number;
      stageLabel: string;
      headline: string;
      substatus: string;
    }> = [
      {
        pos: [2.15, 5.35, 19.0],
        holding: false,
        spread: 0.25,
        stageLabel: 'Step 1 of 4 · Moving to Healthy Donor Coral C-13',
        headline: 'Approaching Healthy Donor C-13',
        substatus: 'Positioning soft robotic gripper above loose healthy Acropora fragment on seabed',
      },
      {
        pos: [2.5, 5.8, 18.9],
        holding: true,
        spread: 0.35,
        stageLabel: 'Step 2 of 4 · Picked Up Healthy Coral C-13 (Gentle 14.6 N Grip)',
        headline: 'Picked Up Healthy Coral at C-13',
        substatus: 'Holding live fragment safely · Following shortest 1.84 m seabed path to Hub C-03',
      },
      {
        pos: [2.95, 6.6, 18.75],
        holding: true,
        spread: 0.55,
        stageLabel: 'Step 3 of 4 · Carrying Coral Along Shortest Path to Clump Hub C-03 (1.84 m)',
        headline: 'Carrying Coral to Clump Hub C-03',
        substatus: 'Skimming seabed 1.84 m directly to the center of West Spur Clump Alpha',
      },
      {
        pos: [3.4, 7.4, 18.6],
        holding: false,
        spread: 0.85,
        stageLabel: 'Step 4 of 4 · Placed Coral at Hub C-03 · Spreading Recovery to C-04 & C-06',
        headline: 'Placed Coral at Hub C-03 · Clump Recovery Active',
        substatus: '1 healthy coral at center hub C-03 is helping neighboring corals C-04 & C-06 recover',
      },
      {
        pos: [3.65, 7.55, 18.55],
        holding: false,
        spread: 1.0,
        stageLabel: 'Step 4 of 4 · Clump Alpha Saved (C-03, C-04 & C-06 Recovering Together)',
        headline: 'All 3 Corals in Clump Alpha Recovering',
        substatus: 'Stability verified · Healthy tissue and algae sharing across the whole clump',
      },
    ];

    const patrolInterval = window.setInterval(() => {
      cycleTickRef.current = (cycleTickRef.current + 1) % waypoints.length;
      const wp = waypoints[cycleTickRef.current];

      setVehiclePos(wp.pos);
      setVehicleTrail((prev) => [...prev.slice(-18), [wp.pos[0], wp.pos[1]]]);
      setHoldingFragment(wp.holding);
      setClumpSpreadProgress(wp.spread);
      setHarvestCycleStage(wp.stageLabel);
      setMissionHeadline(wp.headline);
      setMissionSubstatus(wp.substatus);
      setLastCheckedTime(formatNowTime());
    }, 1800);

    return () => clearInterval(patrolInterval);
  }, [isLivePatrolActive, isTracePaused, activeTab]);

  // One-click explicit trigger to run & log the full Harvest C-13 -> Shortest Path -> Save Clump Hub C-03 sequence
  const handleRunHarvestToClumpSave = (donorId = 'C-13', hubId = 'C-03') => {
    setSelectedClusterId(hubId);
    setVehiclePos([3.4, 7.4, 18.6]);
    setVehicleTrail([
      [2.15, 5.35],
      [2.5, 5.8],
      [2.95, 6.6],
      [3.4, 7.4],
    ]);
    setHoldingFragment(false);
    setClumpSpreadProgress(1.0);
    setHarvestCycleStage(`Stage 4/4 · Seated at Hub ${hubId} · Spreading Recovery to C-04 & C-06`);
    setMissionHeadline(`Clump Alpha Hub ${hubId} Restored`);
    setMissionSubstatus(
      `Harvested live ${donorId} → 1.84 m shortest path → Seated at ${hubId} to save C-03, C-04 & C-06`
    );

    setClusters((prev) =>
      prev.map((c) =>
        c.id === 'C-03' || c.id === 'C-04' || c.id === 'C-06'
          ? {
              ...c,
              status: 'Placed',
              placementShiftMm: 1.2,
              uncertainty: 0.04,
              reviewerStatus: 'Confirmed',
            }
          : c
      )
    );

    const newEvt: DecisionTraceEvent = {
      id: `evt-clump-${Date.now()}`,
      timestamp: formatNowTime(),
      actionType: 'Clump Rescue Complete',
      toolCalled: 'place',
      headline: `Picked up ${donorId} & placed 1 coral at Hub ${hubId} to save 3 corals`,
      summary: 'Carried 2.37 m along shortest path · Helping C-03, C-04 & C-06 recover together',
      clusterId: hubId,
      surfaceNormal: [-0.08, 0.14, 0.99],
      placementShiftMm: 1.2,
      confidence: 0.98,
      gripperForceN: 14.6,
      uncertainty: 0.04,
      outcome: `1 coral placed at ${hubId} — all 3 corals in Clump Alpha recovering`,
      statusTone: 'nominal',
      reasoning:
        'C-03 sits right in the middle of the dead/bleached clump (1.15 m from C-04 and 1.09 m from C-06). Placing just one healthy coral fragment here allows recovery to spread to all three neighbors.',
      modelVersion: 'policy_config.py v2.4 · Clump-Hub-Optimiser-1Hz',
      alternativesConsidered: [
        'Skipped C-04 as center hub: Too far from C-06',
        'Skipped C-06 as center hub: Stronger water current',
      ],
      humanReviewStatus: 'Accepted',
      operatorReason: 'Verified nominal (< 3.0 mm shift)',
    };

    setEvents((prev) => [newEvt, ...prev]);
    setSelectedEventId(newEvt.id);
    pushNotification(
      `Saved Clump Alpha via Hub ${hubId}`,
      `Picked up healthy coral ${donorId} and placed it on ${hubId} so recovery spreads to C-04 & C-06.`,
      hubId,
      'nominal'
    );
  };

  const handleSelectCluster = (clusterId: string) => {
    setSelectedClusterId(clusterId);
    const matchingEvt = events.find((e) => e.clusterId === clusterId);
    if (matchingEvt) {
      setSelectedEventId(matchingEvt.id);
    }
  };

  const handleSelectEvent = (evt: DecisionTraceEvent) => {
    setSelectedEventId(evt.id);
    if (evt.clusterId && clusters.some((c) => c.id === evt.clusterId)) {
      setSelectedClusterId(evt.clusterId);
    }
  };

  // Feature #3: Reviewer status update on any coral observation
  const handleUpdateReviewerStatus = (clusterId: string, status: ReviewerStatus) => {
    setClusters((prev) =>
      prev.map((c) => (c.id === clusterId ? { ...c, reviewerStatus: status } : c))
    );
    pushNotification(
      `Coral ${clusterId} marked as "${status}"`,
      `Updated human review status for coral ${clusterId} to ${status}.`,
      clusterId,
      status === 'Confirmed' ? 'nominal' : 'warning'
    );
  };

  // Feature #6: Operator review / override reason on any decision trace event
  const handleUpdateEventReview = (
    eventId: string,
    status: 'Accepted' | 'Changed' | 'Rejected',
    reason: string
  ) => {
    setEvents((prev) =>
      prev.map((e) =>
        e.id === eventId
          ? { ...e, humanReviewStatus: status, operatorReason: reason }
          : e
      )
    );
  };

  // Command AUV to transit to a specific cluster
  const handleCommandGoto = (targetCluster: CoralCluster) => {
    setSelectedClusterId(targetCluster.id);
    const nextPos: [number, number, number] = [
      Number(targetCluster.localX.toFixed(2)),
      Number(targetCluster.localY.toFixed(2)),
      Number(Math.max(16.2, targetCluster.depthM - 0.35).toFixed(2)),
    ];
    setVehiclePos(nextPos);
    setVehicleTrail((prev) => [...prev.slice(-18), [nextPos[0], nextPos[1]]]);
    setMissionHeadline(`Moved to Coral ${targetCluster.id}`);
    setMissionSubstatus(`Hovering 35 cm above ${targetCluster.species}`);

    const newEvt: DecisionTraceEvent = {
      id: `evt-${Date.now()}`,
      timestamp: formatNowTime(),
      actionType: 'Moved to Coral',
      toolCalled: 'goto',
      headline: `Moved submarine to Coral ${targetCluster.id}`,
      summary: `Hovering steadily 35 cm above ${targetCluster.substrate.replace('_', ' ')}`,
      clusterId: targetCluster.id,
      surfaceNormal: targetCluster.surfaceNormal,
      placementShiftMm: targetCluster.placementShiftMm ?? 0.0,
      confidence: 0.96,
      gripperForceN: holdingFragment ? 14.6 : 0.0,
      uncertainty: targetCluster.uncertainty,
      outcome: `Hovering above ${targetCluster.id} (X ${targetCluster.localX.toFixed(1)} m, Y ${targetCluster.localY.toFixed(1)} m)`,
      statusTone: 'nominal',
      reasoning: `Flew directly to Coral ${targetCluster.id} (${targetCluster.species} at -${targetCluster.depthM.toFixed(1)} m depth) while staying clear of all No-Go zones.`,
      modelVersion: 'policy_config.py v2.4 · CarryAware-50Hz',
      alternativesConsidered: [
        'Took direct path clear of restricted No-Go safety zones',
      ],
      humanReviewStatus: 'Accepted',
      operatorReason: 'Verified nominal (< 3.0 mm shift)',
    };
    setEvents((prev) => [newEvt, ...prev]);
    setSelectedEventId(newEvt.id);
    pushNotification(
      `Submarine arrived at Coral ${targetCluster.id}`,
      `Hovering 35 cm above ${targetCluster.species} for close inspection.`,
      targetCluster.id,
      'nominal'
    );
  };

  // Live Interactive Action 1: Current Surge & Mid-Carry Recovery
  const handleTriggerCurrentSurge = () => {
    setCurrentSpeedMs(0.84);
    setCurrentVec([0.76, 0.32]);
    setHoldingFragment(true);
    setVehiclePos([6.45, 6.1, 18.4]);
    setSelectedClusterId('C-07');
    setMissionHeadline('Strong Water Surge — Coral Held Safe');
    setMissionSubstatus('Thrusters countered 0.84 m/s water surge and kept coral secure');

    const newEvt: DecisionTraceEvent = {
      id: `evt-${Date.now()}`,
      timestamp: formatNowTime(),
      actionType: 'Water Surge Recovery',
      toolCalled: 'grasp',
      headline: 'Kept coral safe during strong 0.84 m/s water surge',
      summary: 'Thrusters automatically pushed against the wave and tightened grip',
      clusterId: 'C-07',
      surfaceNormal: [0.02, 0.04, 0.99],
      placementShiftMm: 1.8,
      confidence: 0.94,
      gripperForceN: 15.2,
      uncertainty: 0.06,
      outcome: 'Water surge countered — coral still held safely (15.2 N)',
      statusTone: 'warning',
      reasoning:
        'A sudden 0.84 m/s underwater wave pushed the submarine sideways. The thrusters immediately countered the push and tightened the gripper to 15.2 N so the coral was not dropped.',
      modelVersion: 'policy_config.py v2.4 · Surge-Reflex-50Hz',
      alternativesConsidered: [
        'Stayed on course instead of aborting because visibility remained clear',
      ],
      humanReviewStatus: 'Accepted',
      operatorReason: 'Verified nominal (< 3.0 mm shift)',
    };
    setEvents((prev) => [newEvt, ...prev]);
    setSelectedEventId(newEvt.id);
    pushNotification(
      'Strong current surge countered (0.84 m/s)',
      'Submarine thrusters automatically balanced the wave and kept the coral safe in the gripper.',
      'C-07',
      'warning'
    );
  };

  // Live Interactive Action 2: Turbidity Spike & Value-of-Information Close Inspection
  const handleTriggerTurbidityInspect = () => {
    setTurbidity((prev) => (prev > 0.3 ? 0.08 : 0.52));
    const highTurb = turbidity <= 0.3;
    setSelectedClusterId('C-10');
    setVehiclePos([7.1, 2.3, 18.8]);
    setMissionHeadline(highTurb ? 'Cloudy Water — Checked Closer & Rerouted' : 'Water Clear Again');
    setMissionSubstatus(
      highTurb
        ? 'Skipped loose rubble at C-10 · Rerouting to solid rock at C-11'
        : 'Cloudy water cleared · Normal reef camera scanning resumed'
    );

    const newEvt: DecisionTraceEvent = {
      id: `evt-${Date.now()}`,
      timestamp: formatNowTime(),
      actionType: 'Cloudy Water Safety Check',
      toolCalled: 'inspect',
      headline: highTurb
        ? 'Cloudy water at C-10 — checked closer and skipped loose rubble'
        : 'Water cleared — normal camera visibility restored',
      summary: highTurb
        ? 'Close-up look confirmed C-10 is loose rubble; rerouted to C-11'
        : 'Clear water across the reef canyon',
      clusterId: 'C-10',
      surfaceNormal: [0.38, -0.29, 0.88],
      placementShiftMm: 0.0,
      confidence: 0.89,
      gripperForceN: holdingFragment ? 14.6 : 0.0,
      uncertainty: highTurb ? 0.58 : 0.12,
      outcome: highTurb
        ? 'Skipped unstable C-10 rubble · Rerouted to C-11'
        : 'Clear camera view restored',
      statusTone: highTurb ? 'warning' : 'nominal',
      reasoning: highTurb
        ? 'Cloudy water made C-10 hard to see from far away. The submarine moved closer (40 cm) and saw shifting rubble, so it safely skipped C-10 and chose solid rock at C-11 instead.'
        : 'Water visibility is clear again, allowing full-speed 3D reef mapping.',
      modelVersion: 'policy_config.py v2.4 · VoI-Gate-1Hz',
      alternativesConsidered: [
        'Refused to place coral blindly in cloudy water; verified seabed first',
      ],
      humanReviewStatus: 'Accepted',
      operatorReason: 'Uncertain substrate',
    };
    setEvents((prev) => [newEvt, ...prev]);
    setSelectedEventId(newEvt.id);
    pushNotification(
      highTurb
        ? 'Cloudy water at C-10 — rerouted to solid rock'
        : 'Water visibility is clear again',
      highTurb
        ? 'Moved closer to check C-10, found loose rubble, and safely rerouted to C-11.'
        : 'Normal stereo camera and UV coral tracking resumed.',
      'C-10',
      highTurb ? 'warning' : 'nominal'
    );
  };

  // Live Interactive Action 3: Execute Transplant & Post-Placement Current Push Verification
  const handleRunPushVerification = () => {
    const target = clusters.find((c) => c.id === selectedClusterId) || clusters[2];
    const pushRes = evaluatePushTest(currentSpeedMs, target.stabilityScore, target.surfaceNormal[2]);

    setClusters((prev) =>
      prev.map((c) =>
        c.id === target.id
          ? {
              ...c,
              status: pushRes.passed ? 'Placed' : c.status,
              placementShiftMm: pushRes.displacementMm,
              uncertainty: 0.04,
            }
          : c
      )
    );
    setVehiclePos([target.localX, target.localY, Math.max(16.2, target.depthM - 0.3)]);
    setHoldingFragment(false);
    setMissionHeadline('Coral Stability Checked');
    setMissionSubstatus(
      pushRes.passed
        ? `Coral at ${target.id} is firmly attached (moved only ${pushRes.displacementMm} mm)`
        : `Coral at ${target.id} shifted ${pushRes.displacementMm} mm — needs re-seating`
    );

    const newEvt: DecisionTraceEvent = {
      id: `evt-${Date.now()}`,
      timestamp: formatNowTime(),
      actionType: 'Coral Stability Check',
      toolCalled: 'verify',
      headline: `${pushRes.passed ? 'Confirmed' : 'Checked'} coral attachment at ${target.id}`,
      summary: pushRes.passed
        ? `Firmly attached (shifted only ${pushRes.displacementMm} mm in current)`
        : `Moved too much (${pushRes.displacementMm} mm > 3.0 mm safety limit)`,
      clusterId: target.id,
      surfaceNormal: target.surfaceNormal,
      placementShiftMm: pushRes.displacementMm,
      confidence: 0.97,
      gripperForceN: 0.0,
      uncertainty: 0.04,
      outcome: pushRes.passed
        ? 'Passed stability check — coral firmly attached'
        : 'Moved too much — picking coral back up',
      statusTone: pushRes.passed ? 'nominal' : 'critical',
      reasoning: `After placing the coral at ${target.id}, the submarine tested if it would hold in ${currentSpeedMs.toFixed(2)} m/s water flow. It moved only ${pushRes.displacementMm} mm (under the 3.0 mm safety limit).`,
      modelVersion: 'policy_config.py v2.4 · PushCheck-1Hz',
      alternativesConsidered: [
        'Verified coral is locked onto solid rock (< 3.0 mm movement)',
      ],
      humanReviewStatus: 'Accepted',
      operatorReason: 'Verified nominal (< 3.0 mm shift)',
    };
    setEvents((prev) => [newEvt, ...prev]);
    setSelectedEventId(newEvt.id);
    pushNotification(
      `${pushRes.passed ? 'Coral firmly attached' : 'Coral shifted'} at ${target.id}`,
      `Stability check recorded ${pushRes.displacementMm} mm movement in ${currentSpeedMs.toFixed(2)} m/s water flow.`,
      target.id,
      pushRes.passed ? 'nominal' : 'critical'
    );
  };

  const handleRecalibrateThruster = () => {
    setSubsystems((prev) =>
      prev.map((s) =>
        s.id === 'sub-thruster-port'
          ? {
              ...s,
              status: 'Nominal',
              healthPct: 97,
              currentDrawA: 4.7,
              temperatureC: 29.2,
              detail:
                'Cleared minor seaweed from left thruster nozzle; running smoothly at 4.7 A',
              telemetryValue: '4.7 A · Nominal',
              suggestedAction: undefined,
            }
          : s
      )
    );
    pushNotification(
      'Left Thruster (T2-Port) cleaned & running normally',
      'Quick reverse spin cleared a piece of seaweed from the propeller; power draw is normal again.',
      selectedClusterId,
      'nominal'
    );
  };

  const unreadCount = notifications.filter((n) => n.unread).length;

  // KPI Metrics across the 28-Colony Multi-Zone Canyon
  const totalMapped = clusters.length;
  const restoredCount = clusters.filter((c) => c.status === 'Placed').length;
  const needsReviewCount = clusters.filter(
    (c) =>
      c.status === 'Bleached' ||
      c.status === 'Dead' ||
      c.reviewerStatus === 'Needs Review' ||
      c.reviewerStatus === 'Uncertain'
  ).length;

  const widgetLabels: Record<WidgetId, string> = {
    camera: 'Live camera & observations',
    map: 'Measured 2.5D reef map (40×32m)',
    spatial3d: '3D reef bathymetry & clump spread',
    trace: 'Live mission log & decisions',
  };

  const renderWidgetContent = (id: WidgetId) => {
    switch (id) {
      case 'camera':
        return (
          <LiveCameraFeed
            clusters={clusters}
            selectedClusterId={selectedClusterId}
            onSelectCluster={handleSelectCluster}
            vehiclePos={vehiclePos}
            turbidity={turbidity}
            currentSpeedMs={currentSpeedMs}
            holdingFragment={holdingFragment}
            onUpdateReviewerStatus={handleUpdateReviewerStatus}
          />
        );
      case 'map':
        return (
          <ReefMap2D
            clusters={clusters}
            selectedClusterId={selectedClusterId}
            onSelectCluster={handleSelectCluster}
            vehiclePos={vehiclePos}
            vehicleTrail={vehicleTrail}
            onCommandGoto={handleCommandGoto}
            currentVec={currentVec}
            optimiserWeights={optimiserWeights}
            donorGenetId={donorGenetId}
            rescuePhase={harvestCycleStage}
            holdingFragment={holdingFragment}
            clumpSpreadProgress={clumpSpreadProgress}
          />
        );
      case 'spatial3d':
        return (
          <SpatialView3D
            clusters={clusters}
            selectedClusterId={selectedClusterId}
            onSelectCluster={handleSelectCluster}
            vehiclePos={vehiclePos}
            holdingFragment={holdingFragment}
          />
        );
      case 'trace':
        return (
          <DecisionTracePanel
            events={events}
            selectedEventId={selectedEventId}
            onSelectEvent={handleSelectEvent}
            isPaused={isTracePaused}
            onTogglePause={() => setIsTracePaused((p) => !p)}
            onUpdateEventReview={handleUpdateEventReview}
          />
        );
    }
  };

  return (
    <div className="min-h-screen flex bg-[#091318] text-[#E6F0F5]">
      {/* Left Vertical Brand & Navigation Rail */}
      <aside className="w-16 sm:w-20 shrink-0 bg-[#071015] border-r border-[#172A35] flex flex-col items-center py-5 justify-between select-none">
        <div className="flex flex-col items-center gap-3">
          <ReefRescueLogo className="w-11 h-11 drop-shadow-[0_2px_8px_rgba(114,229,190,0.2)]" />
          <div className="text-[10px] font-semibold tracking-widest text-center text-[#94B4C7] leading-tight">
            REEF
            <br />
            RESCUE
          </div>
          <div className="w-px h-10 bg-[#1B313E] my-1" />
        </div>

        <div className="flex flex-col items-center gap-6">
          <span
            className="text-[10px] font-mono tracking-[0.22em] text-[#7FA0B5] uppercase"
            style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
          >
            Mission Control
          </span>
        </div>

        <div className="text-[10px] font-mono text-[#527082]">AUV-01</div>
      </aside>

      {/* Main Content Workspace */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Persistent truth-in-interface notice: all values below are local simulation state. */}
        <div role="status" className="sticky top-0 z-50 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-b border-amber-400/40 bg-[#33240B] px-4 py-2 text-center text-sm font-semibold text-amber-100 shadow-lg">
          <span className="rounded bg-amber-300 px-2 py-0.5 text-[11px] font-extrabold uppercase tracking-wide text-[#211707]">Interactive simulation</span>
          <span>No vehicle connected · camera, telemetry, detections and mission outcomes are generated locally · controls do not command hardware</span>
        </div>
        {/* Top Bar Contract: 3 Clean Zones */}
        <header className="flex items-center justify-between gap-6 px-6 lg:px-8 py-3.5 border-b border-[#172A35] bg-[#091318]">
          {/* Zone 1: Brand / Breadcrumb */}
          <a
            href="#top"
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('mission');
            }}
            className="inline-flex items-center gap-2.5 text-sm font-semibold text-[#E6F0F5] tracking-tight whitespace-nowrap shrink-0"
          >
            <ReefRescueLogo className="w-7 h-7 shrink-0" />
            <span>Reef Rescue · Mission Control</span>
          </a>

          {/* Zone 2: Concise Navigation Links (Visible on all widths) */}
          <nav
            aria-label="Primary sections"
            className="flex flex-wrap items-center gap-4 text-xs font-medium text-[#8BA6B8]"
          >
            <button
              type="button"
              onClick={() => setActiveTab('mission')}
              className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                activeTab === 'mission' ? 'text-white underline underline-offset-4 font-semibold' : ''
              }`}
            >
              Mission & observations
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('override')}
              className={`px-2.5 py-1 border transition-colors whitespace-nowrap shrink-0 cursor-pointer inline-flex items-center gap-1.5 ${
                activeTab === 'override'
                  ? 'bg-[#12384C] border-[#38BDF8] text-white font-semibold'
                  : 'bg-[#0D212E] border-[#38BDF8]/60 text-[#7DD3FC] hover:text-white'
              }`}
            >
              <Gamepad2 className="w-3.5 h-3.5 text-[#38BDF8]" />
              Manual Override & Joy-Con Sim
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('vehicle')}
              className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                activeTab === 'vehicle' ? 'text-white underline underline-offset-4 font-semibold' : ''
              }`}
            >
              Vehicle & safety
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('planning')}
              className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                activeTab === 'planning' ? 'text-white underline underline-offset-4 font-semibold' : ''
              }`}
            >
              Planning & permits
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('topology')}
              className={`hover:text-white transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
                activeTab === 'topology' ? 'text-white underline underline-offset-4 font-semibold' : ''
              }`}
            >
              Ecology & topology
            </button>
          </nav>

          {/* Zone 3: Live Patrol Toggle, Notification Feed & Timestamp */}
          <div className="flex items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={() => setIsLivePatrolActive((p) => !p)}
              className={`px-2.5 py-1 text-xs font-mono border transition-colors cursor-pointer inline-flex items-center gap-1.5 ${
                isLivePatrolActive
                  ? 'bg-[#0F2D27] border-[#34D399]/60 text-[#6EE7B7]'
                  : 'bg-[#0D1A22] border-[#223E4E] text-[#94B4C7]'
              }`}
            >
              {isLivePatrolActive ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
              {isLivePatrolActive ? 'Live Cycle: Active' : 'Cycle: Station-Hold'}
            </button>

            <button
              type="button"
              onClick={() => {
                setIsNotifDrawerOpen((o) => !o);
                setNotifications((prev) => prev.map((n) => ({ ...n, unread: false })));
              }}
              aria-label="Toggle live notifications drawer"
              className={`relative px-3 py-1 text-xs font-semibold border transition-colors cursor-pointer inline-flex items-center gap-1.5 ${
                isNotifDrawerOpen
                  ? 'bg-[#123548] border-[#38BDF8] text-white'
                  : 'bg-[#0D1A22] hover:bg-[#142936] border-[#26485B] text-[#E6F0F5]'
              }`}
            >
              <Bell className="w-3.5 h-3.5 text-[#38BDF8]" />
              <span>Live Alerts ({notifications.length})</span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.2 bg-[#34D399] text-[#061512] font-bold text-[10px]">
                  {unreadCount} new
                </span>
              )}
            </button>

            <span className="hidden sm:inline text-xs font-mono text-[#8BA6B8] tabular-nums whitespace-nowrap">
              Updated {lastCheckedTime}
            </span>
          </div>
        </header>

        {/* Clear, Simple Live Mission Alerts & Activity Drawer */}
        {isNotifDrawerOpen && (
          <div className="fixed right-6 top-14 z-50 w-[420px] max-w-[calc(100vw-2rem)] bg-[#0A161E] border-2 border-[#38BDF8]/80 shadow-2xl p-4 space-y-3">
            <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-[#1B313E]">
              <div>
                <div className="text-sm font-bold text-white">
                  Live Mission Alerts & Activity
                </div>
                <div className="text-[11px] text-[#94B4C7]">
                  Simple real-time updates from the submarine · Click any alert to view that coral
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsNotifDrawerOpen(false)}
                aria-label="Close live alerts drawer"
                className="text-[#8BA6B8] hover:text-white cursor-pointer p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Filter Tabs & Popup Toggle */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-1">
                {(
                  [
                    ['all', 'All Alerts'],
                    ['nominal', '✓ Restorations'],
                    ['warning', '⚠ Warnings'],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setNotifFilter(key)}
                    className={`px-2.5 py-1 font-medium border cursor-pointer ${
                      notifFilter === key
                        ? 'bg-[#153647] border-[#38BDF8] text-white'
                        : 'bg-[#081218] border-[#1A313E] text-[#8BA6B8] hover:text-white'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => {
                  setMutePopups((m) => !m);
                  if (!mutePopups) setActiveToast(null);
                }}
                className={`px-2 py-1 text-[11px] border cursor-pointer ${
                  mutePopups
                    ? 'bg-[#2C2010] border-[#FBBF24] text-[#FDE68A]'
                    : 'bg-[#081218] border-[#1E3645] text-[#94B4C7] hover:text-white'
                }`}
              >
                {mutePopups ? 'Popups Muted' : 'Popups On'}
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto divide-y divide-[#152833]">
              {notifications
                .filter((n) =>
                  notifFilter === 'all'
                    ? true
                    : notifFilter === 'warning'
                    ? n.tone === 'warning' || n.tone === 'critical'
                    : n.tone === 'nominal'
                )
                .map((n) => (
                  <div key={n.id} className="py-3 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-1.5 py-0.5 text-[10px] font-bold ${
                            n.tone === 'nominal'
                              ? 'bg-[#0E2E26] text-[#34D399]'
                              : n.tone === 'warning'
                              ? 'bg-[#2E2310] text-[#FBBF24]'
                              : 'bg-[#36161B] text-[#F87171]'
                          }`}
                        >
                          {n.tone === 'nominal'
                            ? '✓ SUCCESS'
                            : n.tone === 'warning'
                            ? '⚠ HEADS UP'
                            : '✕ ALERT'}
                        </span>
                        <span className="font-mono text-[11px] text-[#94B4C7]">
                          {n.timestamp} · Coral {n.clusterId}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          handleSelectCluster(n.clusterId);
                          setIsNotifDrawerOpen(false);
                        }}
                        className="text-[#38BDF8] hover:underline font-medium inline-flex items-center gap-0.5 cursor-pointer"
                      >
                        Show {n.clusterId}
                        <ArrowUpRight className="w-3 h-3" />
                      </button>
                    </div>
                    <div className="font-bold text-white text-sm">{n.title}</div>
                    <div className="text-[#B8CEDC] leading-relaxed">{n.detail}</div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Main Body Container */}
        <main className="flex-1 px-6 lg:px-8 py-5 max-w-[1600px] w-full mx-auto space-y-5">
          {/* Hero Header & Live Mission Status Split */}
          <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-1">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                Mission Control.
              </h1>
              <p className="text-xs sm:text-sm text-[#94B4C7] mt-1 max-w-2xl">
                Interactive mission simulation with reef mapping, coral observations, vehicle diagnostics, and operator-control scenarios.
              </p>
            </div>

            <div className="lg:border-l lg:border-[#1B313E] lg:pl-6 flex flex-wrap items-center gap-4 shrink-0">
              <div>
                <div className="text-xs font-mono text-[#7DD3FC]">{harvestCycleStage}</div>
                <div className="text-lg font-bold text-white tracking-tight mt-0.5">
                  {missionHeadline}
                </div>
                <div className="text-xs text-[#34D399] font-medium mt-0.5">
                  {missionSubstatus}
                </div>
              </div>

              {activeTab !== 'override' && (
                <button
                  type="button"
                  onClick={() => setActiveTab('override')}
                  className="px-3.5 py-2 text-xs font-semibold bg-[#103042] hover:bg-[#16425B] border-2 border-[#38BDF8] text-white cursor-pointer inline-flex items-center gap-2 shadow"
                >
                  <Gamepad2 className="w-4 h-4 text-[#38BDF8]" />
                  Launch Manual Override Simulator
                </button>
              )}
            </div>
          </section>

          {/* Primary Tab Bar + Live Perturbation & Clump-Rescue Controls */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#1B313E] pb-3">
            <div className="flex flex-wrap items-center gap-4" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'mission'}
                onClick={() => setActiveTab('mission')}
                className={`pb-2.5 -mb-3.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
                  activeTab === 'mission'
                    ? 'border-[#34D399] text-white'
                    : 'border-transparent text-[#8BA6B8] hover:text-white'
                }`}
              >
                Mission & observations
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'override'}
                onClick={() => setActiveTab('override')}
                className={`px-3 py-1.5 -mb-2 text-sm font-bold border transition-colors cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5 ${
                  activeTab === 'override'
                    ? 'bg-[#12384C] border-[#38BDF8] text-white'
                    : 'bg-[#0C212E] border-[#38BDF8]/60 text-[#7DD3FC] hover:text-white'
                }`}
              >
                <Gamepad2 className="w-4 h-4 text-[#38BDF8]" />
                Manual Override Simulator (Joy-Con)
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'vehicle'}
                onClick={() => setActiveTab('vehicle')}
                className={`pb-2.5 -mb-3.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
                  activeTab === 'vehicle'
                    ? 'border-[#34D399] text-white'
                    : 'border-transparent text-[#8BA6B8] hover:text-white'
                }`}
              >
                Vehicle & safety
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'planning'}
                onClick={() => setActiveTab('planning')}
                className={`pb-2.5 -mb-3.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer whitespace-nowrap inline-flex items-center gap-1.5 ${
                  activeTab === 'planning'
                    ? 'border-[#34D399] text-white'
                    : 'border-transparent text-[#8BA6B8] hover:text-white'
                }`}
              >
                <FileCheck2 className="w-4 h-4 text-[#34D399]" />
                Planning & permits
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'topology'}
                onClick={() => setActiveTab('topology')}
                className={`pb-2.5 -mb-3.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
                  activeTab === 'topology'
                    ? 'border-[#34D399] text-white'
                    : 'border-transparent text-[#8BA6B8] hover:text-white'
                }`}
              >
                Ecology & topology
              </button>
            </div>

            {/* Live Mission Action & Perturbation Director Controls */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => handleRunHarvestToClumpSave('C-13', 'C-03')}
                className="px-3 py-1.5 text-xs font-semibold bg-[#0F312B] hover:bg-[#15443C] border border-[#34D399] text-[#6EE7B7] transition-colors cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Harvest C-13 → Save Clump Hub C-03
              </button>

              <button
                type="button"
                onClick={handleRunPushVerification}
                className="px-3 py-1.5 text-xs font-medium bg-[#102E2A] hover:bg-[#163F3A] border border-[#34D399]/60 text-[#D1FAE5] transition-colors cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Verify Placement ({selectedClusterId})
              </button>

              <button
                type="button"
                onClick={handleTriggerCurrentSurge}
                className="px-3 py-1.5 text-xs font-medium bg-[#0E2431] hover:bg-[#153447] border border-[#38BDF8]/50 text-[#E0F2FE] transition-colors cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
              >
                <Waves className="w-3.5 h-3.5" />
                Test Current Surge (0.84 m/s)
              </button>

              <button
                type="button"
                onClick={handleTriggerTurbidityInspect}
                className="px-3 py-1.5 text-xs font-medium bg-[#0E2431] hover:bg-[#153447] border border-[#233F4F] text-[#B8CEDC] hover:text-white transition-colors cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
              >
                <CloudFog className="w-3.5 h-3.5" />
                {turbidity > 0.3 ? 'Clear Water Turbidity' : 'Test Turbidity VoI Gate'}
              </button>
            </div>
          </div>

          {/* 4-Column Top Metric Strip (Hidden on Manual Override Simulator tab to maximize cockpit area) */}
          {activeTab !== 'override' && (
            <section
              aria-label="Mission summary metrics"
              className="grid grid-cols-2 lg:grid-cols-4 border border-[#1B313E] bg-[#0D1A22] divide-y lg:divide-y-0 sm:divide-x divide-[#1B313E]"
            >
              <div className="p-5">
                <div className="text-xs text-[#94B4C7]">Clusters mapped (40×32 m)</div>
                <div className="text-3xl font-bold font-mono text-white mt-2 tabular-nums">
                  {totalMapped}
                </div>
                <div className="text-xs text-[#7FA0B5] mt-1">
                  4 zones · 5 restoration clumps
                </div>
              </div>

              <div className="p-5">
                <div className="text-xs text-[#94B4C7]">Restored sites</div>
                <div className="text-3xl font-bold font-mono text-white mt-2 tabular-nums">
                  {restoredCount}
                </div>
                <div className="text-xs text-[#7FA0B5] mt-1">
                  recorded & hub-seeded placements
                </div>
              </div>

              <div className="p-5">
                <div className="text-xs text-[#94B4C7]">Needs review</div>
                <div className="text-3xl font-bold font-mono text-white mt-2 tabular-nums">
                  {needsReviewCount}
                </div>
                <div className="text-xs text-[#7FA0B5] mt-1">
                  bleached, dead, or uncertain
                </div>
              </div>

              <div className="p-5">
                <div className="text-xs text-[#94B4C7]">Vehicle depth (LAT)</div>
                <div className="text-3xl font-bold font-mono text-white mt-2 tabular-nums">
                  -{vehiclePos[2].toFixed(1)} m
                </div>
                <div className="text-xs text-[#7FA0B5] mt-1 font-mono tabular-nums">
                  X {vehiclePos[0].toFixed(2)} m · Y {vehiclePos[1].toFixed(2)} m
                </div>
              </div>
            </section>
          )}

          {/* TAB 1: MISSION & OBSERVATIONS VIEW (With 360° Spin Maps, Live Camera & Decision Trace) */}
          {activeTab === 'mission' && (
            <section className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-[#0B171E] border border-[#172B36] text-xs">
                <div className="flex items-center gap-2 text-[#94B4C7]">
                  <GripHorizontal className="w-4 h-4 text-[#38BDF8]" />
                  <span>
                    Interactive Spatial Workspace: Drag on the 2.5D Reef Map or 3D Spatial View to spin 360° & zoom, or rearrange widgets
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setWidgetOrder(['spatial3d', 'map', 'camera', 'trace'])}
                    className="px-2.5 py-1 bg-[#091318] border border-[#223E4E] text-[#B8CEDC] hover:text-white cursor-pointer"
                  >
                    Prioritize 3D & 2.5D Maps
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setWidgetOrder(['camera', 'map', 'spatial3d', 'trace']);
                      setExpandedWidgetId(null);
                    }}
                    className="px-2.5 py-1 bg-[#091318] border border-[#223E4E] text-[#B8CEDC] hover:text-white cursor-pointer inline-flex items-center gap-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Standard 2×2 Layout
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-stretch">
                {widgetOrder.map((widgetId, idx) => {
                  const isExpanded = expandedWidgetId === widgetId;
                  const colSpanClass = isExpanded ? 'xl:col-span-12' : 'xl:col-span-6';
                  const isDragOver = dragOverWidgetId === widgetId;
                  const nextWidgetId = widgetOrder[(idx + 1) % widgetOrder.length];

                  return (
                    <div
                      key={widgetId}
                      draggable
                      onDragStart={() => setDraggedWidgetId(widgetId)}
                      onDragOver={(e) => {
                        e.preventDefault();
                        if (draggedWidgetId && draggedWidgetId !== widgetId) {
                          setDragOverWidgetId(widgetId);
                        }
                      }}
                      onDragLeave={() => setDragOverWidgetId(null)}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (draggedWidgetId && draggedWidgetId !== widgetId) {
                          setWidgetOrder((prev) =>
                            reorderWidgets(prev, draggedWidgetId, widgetId) as WidgetId[]
                          );
                        }
                        setDraggedWidgetId(null);
                        setDragOverWidgetId(null);
                      }}
                      onDragEnd={() => {
                        setDraggedWidgetId(null);
                        setDragOverWidgetId(null);
                      }}
                      className={`${colSpanClass} flex flex-col transition-transform ${
                        isDragOver ? 'ring-2 ring-[#22D3EE]' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between px-3 py-1.5 bg-[#081218] border-x border-t border-[#1B313E] text-[11px] text-[#7FA0B5] select-none">
                        <div className="flex items-center gap-1.5 cursor-grab active:cursor-grabbing">
                          <GripHorizontal className="w-3.5 h-3.5 text-[#527082]" />
                          <span className="font-mono">
                            Slot 0{idx + 1} · {widgetLabels[widgetId]}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setWidgetOrder((prev) =>
                                reorderWidgets(prev, widgetId, nextWidgetId) as WidgetId[]
                              )
                            }
                            aria-label={`Move ${widgetLabels[widgetId]} widget right`}
                            className="hover:text-white cursor-pointer inline-flex items-center gap-1"
                          >
                            <ArrowLeftRight className="w-3 h-3" />
                            Swap slot
                          </button>
                          <span>·</span>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedWidgetId((cur) => (cur === widgetId ? null : widgetId))
                            }
                            className="hover:text-white cursor-pointer font-mono"
                          >
                            {isExpanded ? 'Restore 2×2' : 'Expand full width'}
                          </button>
                        </div>
                      </div>

                      <div className="flex-1 flex flex-col">{renderWidgetContent(widgetId)}</div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* TAB 2: SUBMARINE MANUAL OVERRIDE & JOY-CON SIMULATOR */}
          {activeTab === 'override' && (
            <ManualOverrideCockpit
              clusters={clusters}
              selectedClusterId={selectedClusterId}
              onSelectCluster={handleSelectCluster}
              vehiclePos={vehiclePos}
              onUpdateVehiclePos={(nextPos) => {
                setVehiclePos(nextPos);
                setVehicleTrail((prev) => [...prev.slice(-18), [nextPos[0], nextPos[1]]]);
                setLastCheckedTime(formatNowTime());
              }}
              holdingFragment={holdingFragment}
              onSetHoldingFragment={setHoldingFragment}
              onTriggerHarvestToClumpSave={handleRunHarvestToClumpSave}
              onPauseAutoPatrol={() => setIsLivePatrolActive(false)}
            />
          )}

          {/* TAB 3: VEHICLE & SAFETY */}
          {activeTab === 'vehicle' && (
            <VehicleSystemsView
              subsystems={subsystems}
              selectedSubsystemId={selectedSubsystemId}
              onSelectSubsystem={setSelectedSubsystemId}
              onRecalibrateThruster={handleRecalibrateThruster}
              vehiclePos={vehiclePos}
              currentSpeedMs={currentSpeedMs}
              holdingFragment={holdingFragment}
              onToggleGripper={() => setHoldingFragment((h) => !h)}
              navMode={navMode}
              onChangeNavMode={setNavMode}
            />
          )}

          {/* TAB 4: MISSION PLANNING & PERMIT RECORD */}
          {activeTab === 'planning' && (
            <MissionPlanningPermitView
              currentSpeedMs={currentSpeedMs}
              turbidity={turbidity}
            />
          )}

          {/* TAB 5: ECOLOGY & TOPOLOGY */}
          {activeTab === 'topology' && (
            <TopologyVerificationView
              clusters={clusters}
              selectedClusterId={selectedClusterId}
              onSelectCluster={handleSelectCluster}
              vehiclePos={vehiclePos}
              policyVersion={policyVersion}
              onPromotePolicy={() => setPolicyVersion('v2')}
              optimiserWeights={optimiserWeights}
              onChangeOptimiserWeights={setOptimiserWeights}
              donorGenetId={donorGenetId}
              onChangeDonorGenetId={setDonorGenetId}
            />
          )}
        </main>

        {/* Simple, Auto-Closing Live Update Toast (Bottom-Right) */}
        {activeToast && !mutePopups && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-5 right-5 z-40 max-w-sm bg-[#0A1720] border-2 border-[#38BDF8]/80 shadow-2xl p-4 text-xs space-y-2"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span
                  className={`px-2 py-0.5 font-bold text-[10px] ${
                    activeToast.tone === 'nominal'
                      ? 'bg-[#0E2E26] text-[#34D399]'
                      : activeToast.tone === 'warning'
                      ? 'bg-[#2E2310] text-[#FBBF24]'
                      : 'bg-[#36161B] text-[#F87171]'
                  }`}
                >
                  {activeToast.tone === 'nominal'
                    ? '✓ SIM UPDATE'
                    : activeToast.tone === 'warning'
                    ? '⚠ HEADS UP'
                    : '✕ ALERT'}
                </span>
                <span className="font-mono text-[11px] text-[#94B4C7]">
                  {activeToast.timestamp} · Coral {activeToast.clusterId}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setActiveToast(null)}
                aria-label="Dismiss live notification"
                className="text-[#94B4C7] hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="font-bold text-white text-sm">{activeToast.title}</div>
            <p className="text-[#CFE3EE] leading-relaxed">{activeToast.detail}</p>
            <div className="pt-1 border-t border-[#172D3B] flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => {
                  handleSelectCluster(activeToast.clusterId);
                  setActiveToast(null);
                }}
                className="font-semibold text-xs text-[#38BDF8] hover:underline inline-flex items-center gap-1 cursor-pointer"
              >
                Focus on Coral {activeToast.clusterId}
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setMutePopups(true);
                    setActiveToast(null);
                  }}
                  className="text-[11px] text-[#8BA6B8] hover:text-white cursor-pointer"
                >
                  Mute popups
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsNotifDrawerOpen(true);
                    setActiveToast(null);
                  }}
                  className="font-semibold text-[11px] text-[#E6F0F5] hover:text-[#38BDF8] cursor-pointer"
                >
                  View all ({notifications.length})
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Clean Production Footer */}
        <footer className="px-6 lg:px-8 py-4 border-t border-[#172A35] bg-[#081116] flex flex-wrap items-center justify-between gap-4 text-xs text-[#7FA0B5]">
          <div>Reef Rescue Hovering AUV · Autonomous Mesophotic Coral Restoration</div>
          <div className="font-mono tabular-nums">
            Capricorn Bunker Sector · CRS EPSG:7856 · Surface Relay -23.40000°, 150.90000° · Depth Floor -30.0 m LAT
          </div>
        </footer>
      </div>
    </div>
  );
}
