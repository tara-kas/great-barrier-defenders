import React, { useState, useRef } from 'react';
import {
  CoralCluster,
  CoralStatus,
  OptimiserWeights,
  DEFAULT_OPTIMISER_WEIGHTS,
  INITIAL_NOGO_ZONES,
  calculateSiteScore,
  evaluateGenetCompatibility,
  computeOptimalClumpHubAndPath,
} from '../domain/reefEngine';
import {
  Compass,
  Navigation,
  Ruler,
  RotateCcw,
  RotateCw,
  ZoomIn,
  ZoomOut,
  Move,
  Maximize2,
  Crosshair,
} from 'lucide-react';

interface ReefMap2DProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  vehicleTrail?: [number, number][];
  onCommandGoto: (cluster: CoralCluster) => void;
  currentVec?: [number, number];
  optimiserWeights?: OptimiserWeights;
  donorGenetId?: string;
  rescuePhase?: string;
  holdingFragment?: boolean;
  patrolPhaseLabel?: string;
  clumpSpreadProgress?: number;
}

type MapOverlayMode = 'clump_spread' | 'bathymetry' | 'provenance' | 'optimiser' | 'clonal';

/**
 * Deterministic per-colony PRNG so every coral colony has a unique, organic branching silhouette
 */
function createColonyRng(id: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h = (h * 1664525 + 1013904223) >>> 0;
    return (h & 0xfffffff) / 0xfffffff;
  };
}

export const ReefMap2D: React.FC<ReefMap2DProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  vehicleTrail = [],
  onCommandGoto,
  optimiserWeights = DEFAULT_OPTIMISER_WEIGHTS,
  holdingFragment = false,
  rescuePhase,
  patrolPhaseLabel = 'Step 1 of 4 · Moving to Healthy Donor Coral C-13',
  clumpSpreadProgress = 0.65,
}) => {
  void rescuePhase;
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [statusFilter, setStatusFilter] = useState<'All' | CoralStatus>('All');
  const [overlayMode, setOverlayMode] = useState<MapOverlayMode>('clump_spread');
  const [measureMode, setMeasureMode] = useState<boolean>(false);
  const [measureStartId, setMeasureStartId] = useState<string>('C-13');
  const [measureEndId, setMeasureEndId] = useState<string>('C-03');

  // Navigation & Camera state — Default drag is 'pan' for intuitive map dragging!
  const [activeClusterPreset, setActiveClusterPreset] = useState<string>('all');
  const [yawDeg, setYawDeg] = useState<number>(0);
  const [pitchDeg, setPitchDeg] = useState<number>(10);
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<[number, number]>([0, 0]);
  const [dragMode, setDragMode] = useState<'pan' | 'spin'>('pan');
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{
    x: number;
    y: number;
    yaw: number;
    pitch: number;
    panX: number;
    panY: number;
  }>({ x: 0, y: 0, yaw: 0, pitch: 10, panX: 0, panY: 0 });

  const filteredClusters =
    statusFilter === 'All'
      ? clusters
      : clusters.filter((c) => c.status === statusFilter);

  const selectedCluster =
    clusters.find((c) => c.id === selectedClusterId) || clusters[0];

  const donorGenetId = 'GEN-AM-02';

  const counts = {
    All: clusters.length,
    Living: clusters.filter((c) => c.status === 'Living').length,
    Bleached: clusters.filter((c) => c.status === 'Bleached').length,
    Dead: clusters.filter((c) => c.status === 'Dead').length,
    Placed: clusters.filter((c) => c.status === 'Placed').length,
  };

  // Multi-clump shortest-path and radial spread plans across the reef
  const clumpPlans = [
    computeOptimalClumpHubAndPath(
      clusters,
      'C-13',
      ['C-03', 'C-04', 'C-06'],
      'CLUMP-ALPHA',
      'West Spur Thicket'
    ),
    computeOptimalClumpHubAndPath(
      clusters,
      'C-16',
      ['C-11', 'C-09', 'C-12'],
      'CLUMP-BETA',
      'Central Crest Staghorn Bank'
    ),
    computeOptimalClumpHubAndPath(
      clusters,
      'C-17',
      ['C-18', 'C-19', 'C-20'],
      'CLUMP-GAMMA',
      'North Pinnacle Amphitheatre'
    ),
    computeOptimalClumpHubAndPath(
      clusters,
      'C-21',
      ['C-22', 'C-23', 'C-24'],
      'CLUMP-DELTA',
      'Channel Patch Bommie'
    ),
    computeOptimalClumpHubAndPath(
      clusters,
      'C-25',
      ['C-26', 'C-27', 'C-28'],
      'CLUMP-EPSILON',
      'East Drop-Off Wall'
    ),
  ];

  const measureA = clusters.find((c) => c.id === measureStartId) || clusters[12];
  const measureB = clusters.find((c) => c.id === measureEndId) || clusters[2];
  const measuredDist3DM = Math.hypot(
    measureB.localX - measureA.localX,
    measureB.localY - measureA.localY,
    measureB.depthM - measureA.depthM
  );

  const getColorForStatus = (status: CoralStatus) => {
    switch (status) {
      case 'Living':
        return '#34D399';
      case 'Bleached':
        return '#FBBF24';
      case 'Dead':
        return '#F87171';
      case 'Placed':
        return '#38BDF8';
    }
  };

  // Map 0..36.0m X and 0..24.0m Y into SVG 680x360 viewBox
  const baseToSvgX = (xM: number) => 42 + (xM / 36.0) * 596;
  const baseToSvgY = (yM: number) => 324 - (yM / 23.5) * 288;

  const toSvgPt = (xM: number, yM: number): [number, number] => {
    const bx = baseToSvgX(xM) - 340;
    const by = baseToSvgY(yM) - 180;
    const rad = (yawDeg * Math.PI) / 180;
    const cosR = Math.cos(rad);
    const sinR = Math.sin(rad);
    const rx = bx * cosR - by * sinR;
    const ry = (bx * sinR + by * cosR) * Math.cos((pitchDeg * Math.PI) / 180);
    return [340 + rx * zoom + pan[0], 180 + ry * zoom + pan[1]];
  };

  // Smoothly center & zoom onto any world coordinate (xM, yM)
  const zoomToWorldCoord = (xM: number, yM: number, targetZoom: number = 2.2, presetId: string = 'custom') => {
    setActiveClusterPreset(presetId);
    setYawDeg(0);
    setPitchDeg(10);
    const bx = baseToSvgX(xM) - 340;
    const by = (baseToSvgY(yM) - 180) * Math.cos((10 * Math.PI) / 180);
    setZoom(targetZoom);
    setPan([-bx * targetZoom, -by * targetZoom]);
  };

  const resetFullMap = () => {
    setActiveClusterPreset('all');
    setYawDeg(0);
    setPitchDeg(10);
    setZoom(1.0);
    setPan([0, 0]);
  };

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as HTMLElement).closest('[data-interactive-node="true"]')) return;
    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      yaw: yawDeg,
      pitch: pitchDeg,
      panX: pan[0],
      panY: pan[1],
    });
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    const rect = svgRef.current?.getBoundingClientRect();
    const scaleX = rect ? 680 / rect.width : 1.0;
    const scaleY = rect ? 360 / rect.height : 1.0;
    const dx = (e.clientX - dragStart.x) * scaleX;
    const dy = (e.clientY - dragStart.y) * scaleY;

    if (dragMode === 'spin' || e.shiftKey) {
      setYawDeg(Number(((dragStart.yaw + dx * 0.45) % 360).toFixed(1)));
      setPitchDeg(Math.max(0, Math.min(48, Number((dragStart.pitch + dy * 0.22).toFixed(1)))));
    } else {
      setPan([dragStart.panX + dx, dragStart.panY + dy]);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.22 : -0.22;
    setZoom((z) => Math.max(0.75, Math.min(4.0, Number((z + delta).toFixed(2)))));
  };

  const [vehSvgX, vehSvgY] = toSvgPt(vehiclePos[0], vehiclePos[1]);
  const [selSvgX, selSvgY] = toSvgPt(selectedCluster.localX, selectedCluster.localY);

  const handleClusterClick = (cluster: CoralCluster) => {
    if (measureMode) {
      setMeasureStartId(measureEndId);
      setMeasureEndId(cluster.id);
    }
    onSelectCluster(cluster.id);
  };

  // 10 Large, Distinctly Shaped Reef Cluster Formations Distributed Across the Entire Reef
  const reefClusterFormations: Array<{
    id: string;
    shortName: string;
    depthLabel: string;
    centerX: number;
    centerY: number;
    repClusterId: string;
    stroke: string;
    fill: string;
    points: [number, number][];
    innerPoints: [number, number][];
  }> = [
    {
      id: 'west-spur',
      shortName: '1 · West Spur Thicket',
      depthLabel: '-18.5m',
      centerX: 3.9,
      centerY: 7.4,
      repClusterId: 'C-03',
      stroke: '#22D3EE',
      fill: 'rgba(14, 116, 144, 0.28)',
      points: [
        [1.4, 5.2],
        [2.0, 9.6],
        [4.2, 9.8],
        [5.8, 8.2],
        [5.5, 6.0],
        [3.6, 5.0],
      ],
      innerPoints: [
        [2.4, 6.2],
        [2.8, 8.8],
        [4.6, 8.6],
        [4.9, 6.6],
      ],
    },
    {
      id: 'sw-garden',
      shortName: '2 · SW Staghorn & Table',
      depthLabel: '-18.3m',
      centerX: 5.6,
      centerY: 3.4,
      repClusterId: 'C-01',
      stroke: '#34D399',
      fill: 'rgba(16, 185, 129, 0.22)',
      points: [
        [3.8, 1.8],
        [4.2, 4.9],
        [6.2, 5.1],
        [7.6, 3.8],
        [7.2, 1.9],
        [5.4, 1.5],
      ],
      innerPoints: [
        [4.5, 2.5],
        [4.8, 4.3],
        [6.6, 4.0],
        [6.4, 2.3],
      ],
    },
    {
      id: 'nw-ridge',
      shortName: '3 · NW Sunlit Acropora',
      depthLabel: '-16.8m',
      centerX: 7.7,
      centerY: 18.6,
      repClusterId: 'C-29',
      stroke: '#2DD4BF',
      fill: 'rgba(20, 184, 166, 0.24)',
      points: [
        [5.6, 16.8],
        [5.9, 20.6],
        [8.4, 20.9],
        [10.2, 19.2],
        [9.6, 16.9],
        [7.4, 16.4],
      ],
      innerPoints: [
        [6.5, 17.6],
        [6.8, 19.8],
        [9.0, 19.4],
        [8.6, 17.4],
      ],
    },
    {
      id: 'central-bank',
      shortName: '4 · East Crest Bank',
      depthLabel: '-18.8m',
      centerX: 12.6,
      centerY: 7.6,
      repClusterId: 'C-11',
      stroke: '#FBBF24',
      fill: 'rgba(245, 158, 11, 0.20)',
      points: [
        [9.8, 5.2],
        [10.4, 9.4],
        [13.4, 9.7],
        [15.2, 8.4],
        [14.8, 6.0],
        [12.2, 5.0],
      ],
      innerPoints: [
        [10.9, 6.4],
        [11.4, 8.7],
        [13.9, 8.4],
        [13.7, 6.4],
      ],
    },
    {
      id: 'central-forest',
      shortName: '5 · Central Reef Forest',
      depthLabel: '-17.8m',
      centerX: 14.5,
      centerY: 13.5,
      repClusterId: 'C-32',
      stroke: '#38BDF8',
      fill: 'rgba(56, 189, 248, 0.24)',
      points: [
        [12.2, 11.8],
        [12.6, 15.4],
        [15.4, 15.8],
        [16.8, 13.9],
        [16.2, 11.6],
        [13.8, 11.3],
      ],
      innerPoints: [
        [13.1, 12.6],
        [13.5, 14.7],
        [15.6, 14.2],
        [15.2, 12.3],
      ],
    },
    {
      id: 'north-pinnacle',
      shortName: '6 · North Pinnacle',
      depthLabel: '-15.8m',
      centerX: 17.2,
      centerY: 19.6,
      repClusterId: 'C-18',
      stroke: '#2DD4BF',
      fill: 'rgba(13, 148, 136, 0.30)',
      points: [
        [14.6, 17.4],
        [14.9, 21.6],
        [17.8, 22.0],
        [19.9, 20.4],
        [19.4, 17.6],
        [16.8, 17.0],
      ],
      innerPoints: [
        [15.6, 18.4],
        [16.0, 20.8],
        [18.6, 20.4],
        [18.2, 18.2],
      ],
    },
    {
      id: 'south-meadow',
      shortName: '7 · South Staghorn Meadow',
      depthLabel: '-19.4m',
      centerX: 17.6,
      centerY: 2.9,
      repClusterId: 'C-35',
      stroke: '#34D399',
      fill: 'rgba(16, 185, 129, 0.22)',
      points: [
        [15.4, 1.4],
        [15.8, 4.4],
        [18.8, 4.6],
        [19.8, 3.0],
        [19.2, 1.3],
      ],
      innerPoints: [
        [16.3, 2.1],
        [16.6, 3.7],
        [18.7, 3.5],
        [18.4, 2.0],
      ],
    },
    {
      id: 'channel-bommie',
      shortName: '8 · Channel Patch Bommie',
      depthLabel: '-19.6m',
      centerX: 21.8,
      centerY: 8.2,
      repClusterId: 'C-22',
      stroke: '#38BDF8',
      fill: 'rgba(14, 165, 233, 0.24)',
      points: [
        [19.2, 6.4],
        [19.8, 10.2],
        [22.8, 10.6],
        [24.4, 8.8],
        [23.8, 6.2],
        [21.2, 5.9],
      ],
      innerPoints: [
        [20.2, 7.2],
        [20.8, 9.4],
        [23.2, 9.0],
        [22.8, 6.9],
      ],
    },
    {
      id: 'ne-crest',
      shortName: '9 · NE Spur Table Crest',
      depthLabel: '-18.9m',
      centerX: 26.2,
      centerY: 20.6,
      repClusterId: 'C-37',
      stroke: '#34D399',
      fill: 'rgba(16, 185, 129, 0.24)',
      points: [
        [24.0, 18.4],
        [24.4, 22.4],
        [27.4, 22.8],
        [28.6, 20.8],
        [27.8, 18.2],
      ],
      innerPoints: [
        [24.9, 19.3],
        [25.3, 21.6],
        [27.5, 21.2],
        [27.0, 19.0],
      ],
    },
    {
      id: 'se-terrace',
      shortName: '10 · SE Terrace & Wall',
      depthLabel: '-22.8m',
      centerX: 31.2,
      centerY: 12.2,
      repClusterId: 'C-26',
      stroke: '#818CF8',
      fill: 'rgba(79, 70, 229, 0.22)',
      points: [
        [27.2, 4.2],
        [29.8, 20.4],
        [34.6, 20.8],
        [35.2, 16.4],
        [32.8, 4.4],
      ],
      innerPoints: [
        [28.4, 5.6],
        [30.8, 19.2],
        [33.8, 18.8],
        [31.6, 5.8],
      ],
    },
  ];

  // Defined, realistic multi-branch Acropora & scalloped table coral SVG renderer
  const renderDefinedCoralShape = (
    cluster: CoralCluster,
    cx: number,
    cy: number,
    color: string,
    isSelected: boolean
  ) => {
    const rng = createColonyRng(cluster.id);
    const rotDeg = Math.round(rng() * 360);
    const baseR = Math.max(8.5, cluster.boundsM[0] * 6.2 * Math.min(2.1, Math.sqrt(zoom)));
    const strokeCol = isSelected ? '#FFFFFF' : '#051017';
    const strokeW = isSelected ? 1.8 : 1.0;
    // Pale growing tip color (just like real Acropora axial corallite tips!)
    const tipColor =
      cluster.status === 'Living'
        ? '#ECFDF5'
        : cluster.status === 'Placed'
        ? '#E0F2FE'
        : cluster.status === 'Bleached'
        ? '#FFFFFF'
        : '#FDA4AF';

    if (
      cluster.morphology === 'staghorn' ||
      cluster.morphology === 'corymbose' ||
      cluster.morphology === 'fragment'
    ) {
      // Multi-forked Y-branching Acropora thicket with pale axial corallite tip dots
      const armCount =
        cluster.morphology === 'fragment'
          ? 4
          : cluster.morphology === 'corymbose'
          ? 8
          : 7;
      const arms = Array.from({ length: armCount }, (_, i) => {
        const angle = (i * Math.PI * 2) / armCount + (rng() - 0.5) * 0.35;
        const len = baseR * (0.8 + rng() * 0.48);
        const mx = Math.cos(angle) * (len * 0.52);
        const my = Math.sin(angle) * (len * 0.52);
        const tx = Math.cos(angle) * len;
        const ty = Math.sin(angle) * len;
        const f1Angle = angle + 0.44;
        const f2Angle = angle - 0.44;
        const fLen = len * 0.52;
        return {
          mx,
          my,
          tx,
          ty,
          f1x: mx + Math.cos(f1Angle) * fLen,
          f1y: my + Math.sin(f1Angle) * fLen,
          f2x: mx + Math.cos(f2Angle) * fLen,
          f2y: my + Math.sin(f2Angle) * fLen,
        };
      });

      return (
        <g transform={`translate(${cx}, ${cy}) rotate(${rotDeg})`}>
          {/* Carbonate holdfast shadow */}
          <circle
            cx="0"
            cy="0"
            r={baseR * 0.72}
            fill={color}
            fillOpacity="0.22"
            stroke={color}
            strokeOpacity="0.45"
            strokeWidth="0.9"
          />
          {arms.map((a, idx) => (
            <g key={idx}>
              <path
                d={`M 0 0 L ${a.tx.toFixed(1)} ${a.ty.toFixed(1)} M ${a.mx.toFixed(1)} ${a.my.toFixed(
                  1
                )} L ${a.f1x.toFixed(1)} ${a.f1y.toFixed(1)} M ${a.mx.toFixed(1)} ${a.my.toFixed(
                  1
                )} L ${a.f2x.toFixed(1)} ${a.f2y.toFixed(1)}`}
                stroke={color}
                strokeWidth={isSelected ? 2.5 : 1.9}
                strokeLinecap="round"
              />
              {/* Bright Axial Corallite Tips */}
              <circle cx={a.tx} cy={a.ty} r={1.8} fill={tipColor} />
              <circle cx={a.f1x} cy={a.f1y} r={1.5} fill={tipColor} />
              <circle cx={a.f2x} cy={a.f2y} r={1.5} fill={tipColor} />
            </g>
          ))}
          <circle cx="0" cy="0" r={baseR * 0.24} fill={color} stroke={strokeCol} strokeWidth={strokeW} />
        </g>
      );
    }

    if (cluster.morphology === 'tabulate') {
      // Multi-tiered scalloped Acropora hyacinthus table coral plates
      const rx = baseR * 1.18;
      const ry = baseR * 0.85;
      return (
        <g transform={`translate(${cx}, ${cy}) rotate(${rotDeg})`}>
          <ellipse
            cx={-1.5}
            cy={1.2}
            rx={rx}
            ry={ry}
            fill={color}
            fillOpacity="0.48"
            stroke={tipColor}
            strokeWidth={strokeW}
          />
          <ellipse
            cx={1.5}
            cy={-1.2}
            rx={rx * 0.76}
            ry={ry * 0.76}
            fill={color}
            fillOpacity="0.82"
            stroke={tipColor}
            strokeWidth={strokeW}
          />
          <ellipse
            cx={0}
            cy={0}
            rx={rx * 0.44}
            ry={ry * 0.44}
            fill={color}
            stroke={strokeCol}
            strokeWidth={strokeW}
          />
        </g>
      );
    }

    // Boulder / Brain coral or Rubble
    const pts: string[] = [];
    const verts = 10;
    for (let i = 0; i < verts; i++) {
      const ang = (i * Math.PI * 2) / verts;
      const rad = baseR * (0.78 + rng() * 0.34);
      pts.push(`${(Math.cos(ang) * rad).toFixed(1)},${(Math.sin(ang) * rad).toFixed(1)}`);
    }
    return (
      <g transform={`translate(${cx}, ${cy}) rotate(${rotDeg})`}>
        <polygon
          points={pts.join(' ')}
          fill={color}
          fillOpacity="0.88"
          stroke={strokeCol}
          strokeWidth={strokeW}
          strokeLinejoin="round"
        />
        <path
          d={`M ${(-baseR * 0.45).toFixed(1)} 0 Q 0 ${(-baseR * 0.35).toFixed(1)} ${(
            baseR * 0.45
          ).toFixed(1)} 0`}
          fill="none"
          stroke="#051017"
          strokeWidth="1.1"
          opacity="0.65"
        />
      </g>
    );
  };

  // Key IDs to label even at 1.0x overview zoom so there is zero text clutter
  const priorityLabelIds = new Set([
    selectedClusterId,
    'C-01',
    'C-03',
    'C-04',
    'C-11',
    'C-13',
    'C-18',
    'C-22',
    'C-26',
    'C-29',
    'C-32',
    'C-35',
    'C-37',
    'C-40',
  ]);

  return (
    <div className="flex flex-col h-full bg-[#0D1A22] border border-[#1B313E]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-[#1B313E]">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-[#F0F7FA] tracking-tight">
              2.5D reef cluster navigation map (80 × 64 m)
            </h2>
            <span className="px-2 py-0.5 text-[11px] font-mono bg-[#112633] text-[#7DD3FC] border border-[#1E3F52]">
              10 Reef Clusters · 42 Colonies
            </span>
          </div>
          <p className="text-xs text-[#8BA6B8] mt-0.5">
            Drag anywhere to pan · Scroll or click any cluster below to zoom right in · Shift+Drag to spin 360°
          </p>
        </div>

        {/* Layer Mode Switcher */}
        <div
          role="group"
          aria-label="Map analytical layer"
          className="flex flex-wrap items-center bg-[#091318] border border-[#1E3645] p-0.5 text-xs"
        >
          {(
            [
              { id: 'clump_spread', label: 'Clump Spread' },
              { id: 'bathymetry', label: 'Bathymetry' },
              { id: 'provenance', label: 'Confidence' },
              { id: 'optimiser', label: 'Site Score' },
              { id: 'clonal', label: 'Genets' },
            ] as const
          ).map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => setOverlayMode(mode.id)}
              className={`px-2.5 py-1 font-medium transition-colors cursor-pointer whitespace-nowrap ${
                overlayMode === mode.id
                  ? 'bg-[#15394A] text-white'
                  : 'text-[#8BA6B8] hover:text-white'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      {/* Instant Cluster Quick-Zoom Navigation Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b border-[#1B313E] bg-[#081218] text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[#8BA6B8] font-medium mr-1 inline-flex items-center gap-1">
            <Crosshair className="w-3.5 h-3.5 text-[#38BDF8]" />
            Zoom to Cluster:
          </span>
          <button
            type="button"
            onClick={resetFullMap}
            className={`px-2 py-0.5 font-mono border cursor-pointer transition-colors ${
              activeClusterPreset === 'all'
                ? 'bg-[#15394A] border-[#38BDF8] text-white font-semibold'
                : 'bg-[#0D1F2B] border-[#1E3A4A] text-[#B8CEDC] hover:text-white'
            }`}
          >
            All Reef (1.0×)
          </button>
          {reefClusterFormations.slice(0, 6).map((fmt) => (
            <button
              key={fmt.id}
              type="button"
              onClick={() => {
                onSelectCluster(fmt.repClusterId);
                zoomToWorldCoord(fmt.centerX, fmt.centerY, 2.35, fmt.id);
              }}
              className={`px-2 py-0.5 font-mono border cursor-pointer transition-colors ${
                activeClusterPreset === fmt.id
                  ? 'bg-[#15394A] border-[#38BDF8] text-white font-semibold'
                  : 'bg-[#0D1F2B] border-[#1E3A4A] text-[#B8CEDC] hover:text-white'
              }`}
            >
              {fmt.shortName}
            </button>
          ))}
        </div>

        <div className="font-mono text-[11px] text-[#34D399] truncate">
          {patrolPhaseLabel}
        </div>
      </div>

      {/* Main Interactive Drag-to-Pan, Spin & Zoom SVG Map Viewport */}
      <div className="relative flex-1 min-h-[385px] bg-[#061017] overflow-hidden select-none">
        <svg
          ref={svgRef}
          viewBox="0 0 680 360"
          className={`w-full h-full block ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
          aria-label="Interactive 80 by 64 metre 2.5D reef cluster map"
        >
          <defs>
            <radialGradient id="zonePinnacle2" cx="48%" cy="22%" r="38%">
              <stop offset="0%" stopColor="#0D9488" stopOpacity="0.34" />
              <stop offset="65%" stopColor="#115E59" stopOpacity="0.14" />
              <stop offset="100%" stopColor="#061017" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="zoneCrest2" cx="18%" cy="68%" r="34%">
              <stop offset="0%" stopColor="#0284C7" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#061017" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="zoneDeepWall2" cx="85%" cy="45%" r="38%">
              <stop offset="0%" stopColor="#1E3A8A" stopOpacity="0.36" />
              <stop offset="100%" stopColor="#061017" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect x="0" y="0" width="680" height="360" fill="url(#zonePinnacle2)" />
          <rect x="0" y="0" width="680" height="360" fill="url(#zoneCrest2)" />
          <rect x="0" y="0" width="680" height="360" fill="url(#zoneDeepWall2)" />

          {/* Clean 5m Bathymetric Coordinate Grid */}
          {[0, 5, 10, 15, 20, 25, 30, 35].map((i) => {
            const [x1, y1] = toSvgPt(i, 0);
            const [x2, y2] = toSvgPt(i, 23.5);
            return (
              <g key={`gx-${i}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#0F212C" strokeWidth="1" />
                <text
                  x={x1}
                  y={y1 + 12}
                  textAnchor="middle"
                  fill="#4A687A"
                  fontSize="8.5"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {i * 2}m
                </text>
              </g>
            );
          })}

          {[0, 5, 10, 15, 20].map((j) => {
            const [x1, y1] = toSvgPt(0, j);
            const [x2, y2] = toSvgPt(36, j);
            return (
              <g key={`gy-${j}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#0F212C" strokeWidth="1" />
                <text
                  x={x1 - 7}
                  y={y1 + 3}
                  textAnchor="end"
                  fill="#4A687A"
                  fontSize="8.5"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {j * 2.5}m
                </text>
              </g>
            );
          })}

          {/* 10 Clickable Organic Reef Cluster Formations (Click any cluster rock bed to zoom into it!) */}
          {reefClusterFormations.map((fmt) => {
            const outerPts = fmt.points
              .map(([px, py]) => {
                const [sx, sy] = toSvgPt(px, py);
                return `${sx.toFixed(1)},${sy.toFixed(1)}`;
              })
              .join(' ');
            const innerPts = fmt.innerPoints
              .map(([px, py]) => {
                const [sx, sy] = toSvgPt(px, py);
                return `${sx.toFixed(1)},${sy.toFixed(1)}`;
              })
              .join(' ');
            const [lx, ly] = toSvgPt(fmt.centerX, fmt.centerY + 2.1);

            return (
              <g
                key={fmt.id}
                data-interactive-node="true"
                onClick={() => {
                  onSelectCluster(fmt.repClusterId);
                  zoomToWorldCoord(fmt.centerX, fmt.centerY, 2.35, fmt.id);
                }}
                className="cursor-pointer group"
              >
                <polygon
                  points={outerPts}
                  fill={fmt.fill}
                  stroke={fmt.stroke}
                  strokeWidth={activeClusterPreset === fmt.id ? '2.0' : '1.2'}
                  strokeLinejoin="round"
                />
                <polygon
                  points={innerPts}
                  fill={fmt.fill}
                  stroke={fmt.stroke}
                  strokeWidth="0.8"
                  strokeDasharray="3 2"
                  strokeLinejoin="round"
                />
                {/* Clean Cluster Header Pill */}
                <g transform={`translate(${lx}, ${ly})`}>
                  <rect
                    x="-54"
                    y="-9"
                    width="108"
                    height="14"
                    rx="2"
                    fill="#07131B"
                    fillOpacity="0.88"
                    stroke={fmt.stroke}
                    strokeWidth="0.8"
                  />
                  <text
                    x="0"
                    y="1"
                    textAnchor="middle"
                    fill="#E6F0F5"
                    fontSize="7.8"
                    fontWeight="600"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {fmt.shortName}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Regulatory No-Go Exclusion Zones */}
          {INITIAL_NOGO_ZONES.map((zone) => {
            const [p1x, p1y] = toSvgPt(zone.xMin, zone.yMin);
            const [p2x, p2y] = toSvgPt(zone.xMax, zone.yMin);
            const [p3x, p3y] = toSvgPt(zone.xMax, zone.yMax);
            const [p4x, p4y] = toSvgPt(zone.xMin, zone.yMax);
            return (
              <g key={zone.id} opacity="0.65">
                <polygon
                  points={`${p1x},${p1y} ${p2x},${p2y} ${p3x},${p3y} ${p4x},${p4y}`}
                  fill="rgba(248, 113, 113, 0.1)"
                  stroke="#F87171"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
              </g>
            );
          })}

          {/* Coral Clump Shortest-Path Harvest & Radial Spread Networks */}
          {(overlayMode === 'clump_spread' || overlayMode === 'bathymetry') &&
            clumpPlans.map((plan) => {
              const [dx, dy] = toSvgPt(plan.donorPos[0], plan.donorPos[1]);
              const [hx, hy] = toSvgPt(plan.hubPos[0], plan.hubPos[1]);
              const spreadRadiusPx = (16 + clumpSpreadProgress * 22) * Math.min(1.8, zoom);
              return (
                <g key={plan.clumpId}>
                  <circle
                    cx={hx}
                    cy={hy}
                    r={spreadRadiusPx}
                    fill="rgba(52, 211, 153, 0.08)"
                    stroke="#34D399"
                    strokeWidth="1.2"
                    strokeDasharray="4 3"
                  />
                  <line
                    x1={dx}
                    y1={dy}
                    x2={hx}
                    y2={hy}
                    stroke="#38BDF8"
                    strokeWidth="2.0"
                    strokeDasharray="5 3"
                  />
                  {plan.spreadLinks.map((link) => {
                    const [tx, ty] = toSvgPt(link.targetX, link.targetY);
                    const mx = (hx + tx) / 2;
                    const my = (hy + ty) / 2 - 8;
                    const pulseX = hx + (tx - hx) * clumpSpreadProgress;
                    const pulseY = hy + (ty - hy) * clumpSpreadProgress;
                    return (
                      <g key={`${plan.clumpId}-${link.targetId}`}>
                        <path
                          d={`M ${hx} ${hy} Q ${mx} ${my} ${tx} ${ty}`}
                          fill="none"
                          stroke="#34D399"
                          strokeWidth="1.7"
                        />
                        <circle cx={pulseX} cy={pulseY} r="3.0" fill="#6EE7B7" />
                      </g>
                    );
                  })}
                </g>
              );
            })}

          {/* Point-to-Point Distance Measurement Ruler */}
          {measureMode && (
            <g>
              {(() => {
                const [ax, ay] = toSvgPt(measureA.localX, measureA.localY);
                const [bx, by] = toSvgPt(measureB.localX, measureB.localY);
                return (
                  <>
                    <line
                      x1={ax}
                      y1={ay}
                      x2={bx}
                      y2={by}
                      stroke="#FBBF24"
                      strokeWidth="2"
                      strokeDasharray="4 2"
                    />
                    <rect
                      x={(ax + bx) / 2 - 58}
                      y={(ay + by) / 2 - 11}
                      width="116"
                      height="18"
                      fill="#091318"
                      stroke="#FBBF24"
                      strokeWidth="1"
                    />
                    <text
                      x={(ax + bx) / 2}
                      y={(ay + by) / 2 + 1}
                      textAnchor="middle"
                      fill="#FDE68A"
                      fontSize="9.5"
                      fontWeight="600"
                      fontFamily="JetBrains Mono, monospace"
                    >
                      {measureA.id}↔{measureB.id}: {measuredDist3DM.toFixed(2)} m
                    </text>
                  </>
                );
              })()}
            </g>
          )}

          {/* Live AUV Patrol Breadcrumb Trail */}
          {vehicleTrail.length > 1 && (
            <polyline
              fill="none"
              stroke="#38BDF8"
              strokeWidth="1.8"
              strokeOpacity="0.65"
              points={vehicleTrail
                .map(([tx, ty]) => {
                  const [sx, sy] = toSvgPt(tx, ty);
                  return `${sx.toFixed(1)},${sy.toFixed(1)}`;
                })
                .join(' ')}
            />
          )}

          {/* Planned AUV Trajectory to Selected Cluster */}
          <line
            x1={vehSvgX}
            y1={vehSvgY}
            x2={selSvgX}
            y2={selSvgY}
            stroke="#22D3EE"
            strokeWidth="1.5"
            strokeDasharray="5 4"
            opacity="0.75"
          />

          {/* 42 Realistic Multi-Branch Coral Colonies with Smart Level-of-Detail Labels */}
          {filteredClusters.map((cluster, idx) => {
            const [cx, cy] = toSvgPt(cluster.localX, cluster.localY);
            const isSelected = cluster.id === selectedClusterId;
            const color = getColorForStatus(cluster.status);
            const cScore = calculateSiteScore(
              cluster,
              [vehiclePos[0], vehiclePos[1]],
              optimiserWeights
            );
            const compat = evaluateGenetCompatibility(donorGenetId, cluster);

            const bwPx = Math.max(20, cluster.boundsM[0] * 18 * Math.min(2.2, zoom));
            const bhPx = Math.max(20, cluster.boundsM[1] * 18 * Math.min(2.2, zoom));
            const showLabel = zoom >= 1.45 || priorityLabelIds.has(cluster.id);
            const labelOffsetX = idx % 2 === 0 ? 11 : -24;
            const labelOffsetY = idx % 3 === 0 ? -8 : 11;

            return (
              <g
                key={cluster.id}
                data-interactive-node="true"
                onClick={() => handleClusterClick(cluster)}
                onDoubleClick={() => zoomToWorldCoord(cluster.localX, cluster.localY, 2.5, 'custom')}
                className="cursor-pointer"
              >
                {overlayMode === 'provenance' && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={14}
                    fill={
                      cluster.dataProvenance.startsWith('Measured')
                        ? 'rgba(52, 211, 153, 0.14)'
                        : cluster.dataProvenance.startsWith('Interpolated')
                        ? 'rgba(56, 189, 248, 0.14)'
                        : 'rgba(248, 113, 113, 0.2)'
                    }
                    stroke={
                      cluster.dataProvenance.startsWith('Measured')
                        ? '#34D399'
                        : cluster.dataProvenance.startsWith('Interpolated')
                        ? '#38BDF8'
                        : '#F87171'
                    }
                    strokeWidth="1"
                  />
                )}

                {overlayMode === 'optimiser' && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={Math.max(10, cScore.totalScore * 3.6)}
                    fill="rgba(56, 189, 248, 0.12)"
                    stroke="#38BDF8"
                    strokeWidth="0.8"
                  />
                )}

                {overlayMode === 'clonal' && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={14}
                    fill={
                      compat.interactionType === 'Clonal Tissue Fusion'
                        ? 'rgba(52, 211, 153, 0.22)'
                        : compat.interactionType === 'Mixed-Genet Antagonism'
                        ? 'rgba(248, 113, 113, 0.18)'
                        : 'rgba(56, 189, 248, 0.12)'
                    }
                    stroke={
                      compat.interactionType === 'Clonal Tissue Fusion'
                        ? '#34D399'
                        : compat.interactionType === 'Mixed-Genet Antagonism'
                        ? '#F87171'
                        : '#38BDF8'
                    }
                    strokeWidth="1.2"
                  />
                )}

                {isSelected && (
                  <rect
                    x={cx - bwPx / 2}
                    y={cy - bhPx / 2}
                    width={bwPx}
                    height={bhPx}
                    fill="rgba(34, 211, 238, 0.14)"
                    stroke="#22D3EE"
                    strokeWidth="1.6"
                    strokeDasharray="3 2"
                  />
                )}

                {renderDefinedCoralShape(cluster, cx, cy, color, isSelected)}

                {showLabel && (
                  <text
                    x={cx + labelOffsetX}
                    y={cy + labelOffsetY}
                    fill={isSelected ? '#FFFFFF' : '#D9E8F2'}
                    fontSize={isSelected ? '10' : '8.2'}
                    fontWeight={isSelected ? '700' : '600'}
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {cluster.id}
                  </text>
                )}
              </g>
            );
          })}

          {/* Hovering AUV Submarine Marker */}
          <g transform={`translate(${vehSvgX}, ${vehSvgY})`}>
            <circle
              cx="0"
              cy="0"
              r="15"
              fill={holdingFragment ? 'rgba(52, 211, 153, 0.28)' : 'rgba(56, 189, 248, 0.22)'}
              stroke={holdingFragment ? '#34D399' : '#38BDF8'}
              strokeWidth="1.8"
            />
            <polygon points="0,-9 6.5,6.5 0,3.5 -6.5,6.5" fill="#FBBF24" stroke="#FFFFFF" strokeWidth="0.8" />
            {holdingFragment && (
              <circle cx="0" cy="-11" r="4" fill="#34D399" stroke="#FFFFFF" strokeWidth="1" />
            )}
            <rect
              x="16"
              y="-8"
              width="76"
              height="16"
              rx="2"
              fill="#07131B"
              fillOpacity="0.9"
              stroke="#38BDF8"
              strokeWidth="0.8"
            />
            <text
              x="54"
              y="3"
              textAnchor="middle"
              fill="#FFFFFF"
              fontSize="8.8"
              fontWeight="600"
              fontFamily="JetBrains Mono, monospace"
            >
              AUV (-{vehiclePos[2].toFixed(1)}m)
            </text>
          </g>
        </svg>

        {/* Top-Left Compass & Drag Mode Indicator */}
        <div className="absolute top-2.5 left-3 flex items-center gap-2 bg-[#071520]/92 border border-[#1E3645] px-2.5 py-1 text-xs font-mono text-[#CFE3EE] tabular-nums">
          <Compass
            className="w-4 h-4 text-[#38BDF8] transition-transform"
            style={{ transform: `rotate(${yawDeg}deg)` }}
          />
          <span>
            N · Zoom {zoom.toFixed(1)}× {yawDeg !== 0 ? `· Spin ${Math.round(yawDeg)}°` : ''}
          </span>
        </div>

        {/* Top-Right Compact Selected Coral Pill with 1-Click Zoom & Transit */}
        <div className="absolute top-2.5 right-3 flex items-center gap-2 bg-[#071520]/94 border border-[#1E3A4A] px-2.5 py-1.5 text-xs">
          <span className="font-mono font-bold text-white">{selectedCluster.id}</span>
          <span className="text-[#94B4C7] hidden sm:inline">
            {selectedCluster.status} · {selectedCluster.morphology}
          </span>
          <button
            type="button"
            onClick={() => zoomToWorldCoord(selectedCluster.localX, selectedCluster.localY, 2.4, 'custom')}
            className="px-2 py-0.5 font-mono text-[11px] bg-[#133243] hover:bg-[#1A4359] text-[#7DD3FC] border border-[#38BDF8]/50 cursor-pointer inline-flex items-center gap-1"
          >
            <Maximize2 className="w-3 h-3" />
            Zoom In
          </button>
        </div>

        {/* Bottom-Left Navigation & Zoom Controls Bar */}
        <div className="absolute bottom-2.5 left-3 flex flex-wrap items-center gap-1.5 bg-[#071520]/94 border border-[#1E3645] px-2.5 py-1 text-xs">
          <button
            type="button"
            onClick={() => setDragMode((m) => (m === 'pan' ? 'spin' : 'pan'))}
            className={`px-2 py-0.5 font-mono text-[11px] border cursor-pointer inline-flex items-center gap-1 ${
              dragMode === 'pan'
                ? 'bg-[#143342] border-[#38BDF8] text-white'
                : 'bg-[#1F2D3A] border-[#34D399] text-[#6EE7B7]'
            }`}
          >
            <Move className="w-3 h-3" />
            Drag: {dragMode === 'pan' ? 'Pan Map' : '3D Spin'}
          </button>

          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(4.0, Number((z + 0.35).toFixed(2))))}
            aria-label="Zoom in reef map"
            className="px-1.5 py-0.5 bg-[#0E222E] border border-[#1E3645] text-[#CFE3EE] hover:text-white cursor-pointer inline-flex items-center gap-1"
          >
            <ZoomIn className="w-3.5 h-3.5 text-[#38BDF8]" />
            +
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.75, Number((z - 0.35).toFixed(2))))}
            aria-label="Zoom out reef map"
            className="px-1.5 py-0.5 bg-[#0E222E] border border-[#1E3645] text-[#CFE3EE] hover:text-white cursor-pointer inline-flex items-center gap-1"
          >
            <ZoomOut className="w-3.5 h-3.5 text-[#38BDF8]" />
            -
          </button>

          <button
            type="button"
            onClick={() => setYawDeg((y) => (y - 30) % 360)}
            aria-label="Spin map counter-clockwise"
            className="p-1 text-[#94B4C7] hover:text-white cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setYawDeg((y) => (y + 30) % 360)}
            aria-label="Spin map clockwise"
            className="p-1 text-[#94B4C7] hover:text-white cursor-pointer"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={() => zoomToWorldCoord(vehiclePos[0], vehiclePos[1], 2.2, 'auv')}
            className="px-2 py-0.5 font-mono text-[11px] bg-[#0E222E] border border-[#1E3645] text-[#7DD3FC] hover:text-white cursor-pointer"
          >
            Center AUV
          </button>

          <button
            type="button"
            onClick={resetFullMap}
            className="px-2 py-0.5 font-mono text-[11px] text-[#B8CEDC] hover:text-white cursor-pointer"
          >
            Reset View
          </button>

          <button
            type="button"
            onClick={() => setMeasureMode((m) => !m)}
            className={`px-2 py-0.5 font-mono text-[11px] border inline-flex items-center gap-1 cursor-pointer ${
              measureMode
                ? 'bg-[#2E2410] border-[#FBBF24] text-[#FDE68A]'
                : 'bg-[#081218] border-[#1E3645] text-[#94B4C7] hover:text-white'
            }`}
          >
            <Ruler className="w-3 h-3" />
            Ruler
          </button>
        </div>
      </div>

      {/* Clean Single Filter & Transit Action Bar (Bottom depth/score bar removed as requested) */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5 border-t border-[#1B313E] bg-[#0A151C]">
        <div className="flex flex-wrap items-center gap-1.5">
          {(['All', 'Living', 'Bleached', 'Dead', 'Placed'] as const).map((st) => {
            const active = statusFilter === st;
            return (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer whitespace-nowrap tabular-nums ${
                  active
                    ? 'bg-[#163140] border border-[#38BDF8]/60 text-white'
                    : 'text-[#8BA6B8] hover:text-white border border-transparent'
                }`}
              >
                {st} <span className="font-mono ml-1 text-[#B8CEDC]">{counts[st]}</span>
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => onCommandGoto(selectedCluster)}
          className="px-3 py-1 text-xs font-medium bg-[#123546] hover:bg-[#19465C] border border-[#38BDF8]/60 text-[#E0F2FE] transition-colors cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap"
        >
          <Navigation className="w-3 h-3" />
          Transit AUV to {selectedCluster.id}
        </button>
      </div>
    </div>
  );
};
