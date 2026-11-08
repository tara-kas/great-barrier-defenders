import React, { useState } from 'react';
import {
  CoralCluster,
  OptimiserWeights,
  calculateSiteScore,
  computeTemporalGrowthStage,
} from '../domain/reefEngine';

interface LiveMissionGraphsStripProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  currentSpeedMs: number;
  turbidity: number;
  holdingFragment: boolean;
  optimiserWeights: OptimiserWeights;
  telemetryHistory: Array<{
    tick: number;
    depthM: number;
    currentMs: number;
    powerW: number;
  }>;
}

export const LiveMissionGraphsStrip: React.FC<LiveMissionGraphsStripProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  currentSpeedMs,
  holdingFragment,
  optimiserWeights,
  telemetryHistory,
}) => {
  const [hoveredDay, setHoveredDay] = useState<number>(35);
  const [hoveredTelemetryIdx, setHoveredTelemetryIdx] = useState<number | null>(null);

  // 1. Coral Status Breakdown
  const counts = {
    Living: clusters.filter((c) => c.status === 'Living').length,
    Placed: clusters.filter((c) => c.status === 'Placed').length,
    Bleached: clusters.filter((c) => c.status === 'Bleached').length,
    Dead: clusters.filter((c) => c.status === 'Dead').length,
  };
  const total = clusters.length || 1;

  // 2. Top Candidate Coral Scores (Interactive Bar Chart)
  const candidateClusters = clusters
    .filter((c) => c.status !== 'Living' || c.id === 'C-13')
    .slice(0, 7)
    .map((c) => {
      const score = calculateSiteScore(c, [vehiclePos[0], vehiclePos[1]], optimiserWeights);
      return {
        cluster: c,
        score: score.totalScore,
      };
    });

  // 3. Recovery & Clump Spread Growth Curve (Days 0..49)
  const selectedCluster =
    clusters.find((c) => c.id === selectedClusterId) || clusters[0];
  const sampleDays = [0, 7, 14, 21, 28, 35, 42, 49];
  const growthPoints = sampleDays.map((day) => {
    const st = computeTemporalGrowthStage(selectedCluster, day);
    const untreated = Math.max(12, Math.round(48 - day * 0.55));
    return {
      day,
      fusionPct: st.fusionPct,
      calcificationMm: st.tissueBridgeMm,
      untreatedPct: untreated,
    };
  });
  const activeGrowth =
    growthPoints.find((g) => g.day === hoveredDay) || growthPoints[5];

  // 4. Live AUV Depth & Power Telemetry Sparkline
  const history =
    telemetryHistory.length > 1
      ? telemetryHistory
      : [
          { tick: 1, depthM: 18.1, currentMs: 0.24, powerW: 142 },
          { tick: 2, depthM: 18.3, currentMs: 0.26, powerW: 148 },
          { tick: 3, depthM: 18.5, currentMs: 0.25, powerW: 151 },
          { tick: 4, depthM: 18.4, currentMs: 0.28, powerW: 156 },
          { tick: 5, depthM: 18.6, currentMs: 0.27, powerW: 152 },
          { tick: 6, depthM: vehiclePos[2], currentMs: currentSpeedMs, powerW: holdingFragment ? 174 : 146 },
        ];

  const activeTelem =
    hoveredTelemetryIdx !== null && history[hoveredTelemetryIdx]
      ? history[hoveredTelemetryIdx]
      : history[history.length - 1];

  return (
    <section
      aria-label="Live interactive mission graphs"
      className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 bg-[#0B161E] border border-[#172B36] divide-y md:divide-y-0 md:divide-x divide-[#172B36]"
    >
      {/* GRAPH 1: Reef Health Distribution (Donut + Interactive Bars) */}
      <div className="p-4 flex flex-col justify-between">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-[#8BA6B8]">Reef Colony Health</span>
          <span className="text-xl font-bold font-mono text-white tabular-nums">
            {clusters.length} <span className="text-xs font-normal text-[#7FA0B5]">corals</span>
          </span>
        </div>

        {/* Stacked Segmented Bar */}
        <div className="h-2.5 w-full bg-[#071016] flex overflow-hidden my-3 border border-[#162934]">
          <div
            style={{ width: `${(counts.Living / total) * 100}%` }}
            className="bg-[#34D399] transition-all"
            title={`Living: ${counts.Living}`}
          />
          <div
            style={{ width: `${(counts.Placed / total) * 100}%` }}
            className="bg-[#38BDF8] transition-all"
            title={`Placed: ${counts.Placed}`}
          />
          <div
            style={{ width: `${(counts.Bleached / total) * 100}%` }}
            className="bg-[#FBBF24] transition-all"
            title={`Bleached: ${counts.Bleached}`}
          />
          <div
            style={{ width: `${(counts.Dead / total) * 100}%` }}
            className="bg-[#F87171] transition-all"
            title={`Dead: ${counts.Dead}`}
          />
        </div>

        {/* Interactive Status Legend Bars (Click to jump to representative coral) */}
        <div className="grid grid-cols-4 gap-1.5 text-[11px] font-mono tabular-nums">
          {(
            [
              { label: 'Living', count: counts.Living, color: '#34D399', target: 'C-13' },
              { label: 'Placed', count: counts.Placed, color: '#38BDF8', target: 'C-07' },
              { label: 'Bleach', count: counts.Bleached, color: '#FBBF24', target: 'C-04' },
              { label: 'Dead', count: counts.Dead, color: '#F87171', target: 'C-03' },
            ] as const
          ).map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => onSelectCluster(item.target)}
              className="px-2 py-1 bg-[#081117] hover:bg-[#112430] border border-[#152834] text-left cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between">
                <span style={{ color: item.color }} className="font-bold">
                  {item.count}
                </span>
                <span className="text-[9px] text-[#648296]">
                  {Math.round((item.count / total) * 100)}%
                </span>
              </div>
              <div className="text-[10px] text-[#94B4C7] truncate">{item.label}</div>
            </button>
          ))}
        </div>
      </div>

      {/* GRAPH 2: Site Suitability Score S(i,j) Interactive Bar Chart */}
      <div className="p-4 flex flex-col justify-between">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-[#8BA6B8]">Site Suitability Score</span>
          <span className="text-xs font-mono text-[#38BDF8] tabular-nums">
            Selected: {selectedClusterId}
          </span>
        </div>

        <div className="h-20 flex items-end gap-2 pt-3 pb-1">
          {candidateClusters.map(({ cluster, score }) => {
            const isSel = cluster.id === selectedClusterId;
            const normH = Math.max(18, Math.min(100, Math.round(((score + 1) / 6.5) * 100)));
            const barColor = isSel
              ? '#38BDF8'
              : score >= 3.8
              ? '#34D399'
              : score >= 2.2
              ? '#FBBF24'
              : '#F87171';

            return (
              <button
                key={cluster.id}
                type="button"
                onClick={() => onSelectCluster(cluster.id)}
                title={`${cluster.id}: Score ${score.toFixed(2)}`}
                className="flex-1 flex flex-col items-center gap-1 h-full justify-end group cursor-pointer"
              >
                <span className="text-[9.5px] font-mono tabular-nums text-[#8BA6B8] group-hover:text-white">
                  {score.toFixed(1)}
                </span>
                <div className="w-full bg-[#071016] h-12 flex items-end border border-[#152834] p-0.5">
                  <div
                    style={{ height: `${normH}%`, backgroundColor: barColor }}
                    className="w-full transition-all"
                  />
                </div>
                <span
                  className={`text-[10px] font-mono ${
                    isSel ? 'text-white font-bold' : 'text-[#7FA0B5]'
                  }`}
                >
                  {cluster.id}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* GRAPH 3: Clump Recovery & Fusion Curve (Interactive SVG Area Chart) */}
      <div className="p-4 flex flex-col justify-between">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-[#8BA6B8]">Clump Recovery Curve</span>
          <span className="text-sm font-bold font-mono text-[#34D399] tabular-nums">
            Day {activeGrowth.day}: {activeGrowth.fusionPct}%{' '}
            <span className="text-[11px] font-normal text-[#8BA6B8]">
              (+{activeGrowth.calcificationMm}mm)
            </span>
          </span>
        </div>

        <svg
          viewBox="0 0 240 68"
          className="w-full h-16 my-1 overflow-visible select-none"
          aria-label="Clump recovery growth curve"
        >
          <defs>
            <linearGradient id="growthGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34D399" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#34D399" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1="0" y1="14" x2="240" y2="14" stroke="#142632" strokeWidth="1" />
          <line x1="0" y1="36" x2="240" y2="36" stroke="#142632" strokeWidth="1" />
          <line x1="0" y1="58" x2="240" y2="58" stroke="#142632" strokeWidth="1" />

          {/* Untreated Baseline Dashed Line */}
          <polyline
            fill="none"
            stroke="#F87171"
            strokeWidth="1.3"
            strokeDasharray="3 3"
            points={growthPoints
              .map((pt, i) => {
                const x = 8 + (i / (growthPoints.length - 1)) * 224;
                const y = 60 - (pt.untreatedPct / 100) * 50;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ')}
          />

          {/* Restored Area + Line */}
          <polygon
            fill="url(#growthGrad)"
            points={`8,60 ${growthPoints
              .map((pt, i) => {
                const x = 8 + (i / (growthPoints.length - 1)) * 224;
                const y = 60 - (pt.fusionPct / 100) * 50;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ')} 232,60`}
          />
          <polyline
            fill="none"
            stroke="#34D399"
            strokeWidth="2"
            points={growthPoints
              .map((pt, i) => {
                const x = 8 + (i / (growthPoints.length - 1)) * 224;
                const y = 60 - (pt.fusionPct / 100) * 50;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ')}
          />

          {/* Interactive Hover/Click Nodes */}
          {growthPoints.map((pt, i) => {
            const x = 8 + (i / (growthPoints.length - 1)) * 224;
            const y = 60 - (pt.fusionPct / 100) * 50;
            const isAct = pt.day === activeGrowth.day;
            return (
              <g
                key={pt.day}
                onMouseEnter={() => setHoveredDay(pt.day)}
                onClick={() => setHoveredDay(pt.day)}
                className="cursor-pointer"
              >
                <rect x={x - 12} y="0" width="24" height="68" fill="transparent" />
                {isAct && (
                  <line
                    x1={x}
                    y1="6"
                    x2={x}
                    y2="60"
                    stroke="#34D399"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={isAct ? 4 : 2.3}
                  fill={isAct ? '#FFFFFF' : '#34D399'}
                  stroke="#071219"
                  strokeWidth="1.2"
                />
              </g>
            );
          })}
        </svg>

        <div className="flex items-center justify-between text-[10.5px] font-mono text-[#7FA0B5]">
          <span className="text-[#34D399]">― Seeded Clump</span>
          <span className="text-[#F87171]">-- Untreated ({activeGrowth.untreatedPct}%)</span>
        </div>
      </div>

      {/* GRAPH 4: Live AUV Depth & Power Telemetry Sparkline */}
      <div className="p-4 flex flex-col justify-between">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-[#8BA6B8]">AUV Depth & Power</span>
          <span className="text-sm font-bold font-mono text-[#38BDF8] tabular-nums">
            -{activeTelem.depthM.toFixed(1)}m · {activeTelem.powerW}W
          </span>
        </div>

        <svg
          viewBox="0 0 240 68"
          className="w-full h-16 my-1 overflow-visible select-none"
          aria-label="Live AUV depth and thruster power chart"
        >
          <line x1="0" y1="14" x2="240" y2="14" stroke="#142632" strokeWidth="1" />
          <line x1="0" y1="36" x2="240" y2="36" stroke="#142632" strokeWidth="1" />
          <line x1="0" y1="58" x2="240" y2="58" stroke="#142632" strokeWidth="1" />

          {/* Power W curve (Amber) */}
          <polyline
            fill="none"
            stroke="#FBBF24"
            strokeWidth="1.4"
            strokeOpacity="0.85"
            points={history
              .map((h, i) => {
                const x = 8 + (i / Math.max(1, history.length - 1)) * 224;
                const y = 58 - ((h.powerW - 110) / 110) * 44;
                return `${x.toFixed(1)},${Math.max(8, Math.min(60, y)).toFixed(1)}`;
              })
              .join(' ')}
          />

          {/* Depth m curve (Cyan) */}
          <polyline
            fill="none"
            stroke="#38BDF8"
            strokeWidth="2"
            points={history
              .map((h, i) => {
                const x = 8 + (i / Math.max(1, history.length - 1)) * 224;
                const y = 12 + ((h.depthM - 15) / 10) * 44;
                return `${x.toFixed(1)},${Math.max(8, Math.min(60, y)).toFixed(1)}`;
              })
              .join(' ')}
          />

          {history.map((h, i) => {
            const x = 8 + (i / Math.max(1, history.length - 1)) * 224;
            const y = 12 + ((h.depthM - 15) / 10) * 44;
            const isAct =
              hoveredTelemetryIdx === i ||
              (hoveredTelemetryIdx === null && i === history.length - 1);
            return (
              <g
                key={h.tick}
                onMouseEnter={() => setHoveredTelemetryIdx(i)}
                onMouseLeave={() => setHoveredTelemetryIdx(null)}
                className="cursor-pointer"
              >
                <rect x={x - 10} y="0" width="20" height="68" fill="transparent" />
                <circle
                  cx={x}
                  cy={Math.max(8, Math.min(60, y))}
                  r={isAct ? 3.8 : 2}
                  fill={isAct ? '#FFFFFF' : '#38BDF8'}
                />
              </g>
            );
          })}
        </svg>

        <div className="flex items-center justify-between text-[10.5px] font-mono text-[#7FA0B5] tabular-nums">
          <span className="text-[#38BDF8]">― Depth (-{activeTelem.depthM.toFixed(1)}m)</span>
          <span className="text-[#FBBF24]">― Load ({activeTelem.powerW}W · {activeTelem.currentMs.toFixed(2)}m/s)</span>
        </div>
      </div>
    </section>
  );
};
