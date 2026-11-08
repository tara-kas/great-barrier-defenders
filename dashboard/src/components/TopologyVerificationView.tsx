import React, { useState } from 'react';
import {
  CoralCluster,
  OptimiserWeights,
  DEFAULT_OPTIMISER_WEIGHTS,
  INITIAL_ECOLOGICAL_VISITS,
  calculateSiteScore,
  evaluateGenetCompatibility,
  computeTemporalGrowthStage,
  computeSpectralCurve,
} from '../domain/reefEngine';
import {
  Sliders,
  RotateCcw,
  Dna,
  Clock,
  Sparkles,
  LineChart,
} from 'lucide-react';

interface TopologyVerificationViewProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  policyVersion: 'v1' | 'v2';
  onPromotePolicy: () => void;
  optimiserWeights: OptimiserWeights;
  onChangeOptimiserWeights: (weights: OptimiserWeights) => void;
  donorGenetId: string;
  onChangeDonorGenetId: (genetId: string) => void;
}

export const TopologyVerificationView: React.FC<TopologyVerificationViewProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  optimiserWeights,
  onChangeOptimiserWeights,
  donorGenetId,
  onChangeDonorGenetId,
}) => {
  const [growthDay, setGrowthDay] = useState<number>(14);
  const [selectedVisitId, setSelectedVisitId] = useState<string>(
    INITIAL_ECOLOGICAL_VISITS[3].id
  );

  const selectedCluster =
    clusters.find((c) => c.id === selectedClusterId) || clusters[2];

  const temporalStage = computeTemporalGrowthStage(selectedCluster, growthDay);
  const spectralPoints = computeSpectralCurve(selectedCluster);
  const genetEvaluation = evaluateGenetCompatibility(donorGenetId, selectedCluster);

  const rankedClusters = [...clusters]
    .map((c) => ({
      cluster: c,
      score: calculateSiteScore(c, [vehiclePos[0], vehiclePos[1]], optimiserWeights),
      compat: evaluateGenetCompatibility(donorGenetId, c),
    }))
    .sort((a, b) => b.score.totalScore - a.score.totalScore);

  const updateWeight = (key: keyof OptimiserWeights, val: number) => {
    onChangeOptimiserWeights({
      ...optimiserWeights,
      [key]: Number(val.toFixed(2)),
    });
  };

  const activeVisit =
    INITIAL_ECOLOGICAL_VISITS.find((v) => v.id === selectedVisitId) ||
    INITIAL_ECOLOGICAL_VISITS[3];

  const maxScore = Math.max(
    ...rankedClusters.map((r) => Math.max(0.1, r.score.totalScore)),
    2.5
  );

  return (
    <div className="space-y-4">
      {/* Compact Header */}
      <div className="bg-[#0D1A22] border border-[#1B313E] px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white tracking-tight">Coral Ecology</h1>
          <span className="px-2 py-0.5 text-xs font-mono bg-[#08131A] border border-[#1E3645] text-[#38BDF8]">
            {selectedCluster.id} · {selectedCluster.species}
          </span>
        </div>

        {/* Donor Genet Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#8BA6B8] flex items-center gap-1">
            <Dna className="w-3.5 h-3.5 text-[#34D399]" />
            Genet:
          </span>
          <div className="flex items-center bg-[#08131A] border border-[#1E3645] p-0.5">
            {(['GEN-AM-02', 'GEN-AH-01', 'GEN-AC-04'] as const).map((gid) => (
              <button
                key={gid}
                type="button"
                onClick={() => onChangeDonorGenetId(gid)}
                className={`px-2.5 py-1 text-xs font-mono transition-colors cursor-pointer ${
                  donorGenetId === gid
                    ? 'bg-[#12352E] text-[#6EE7B7] font-semibold'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {gid}
              </button>
            ))}
          </div>
          <span
            className={`px-2 py-1 text-xs font-mono border ${
              genetEvaluation.compatible
                ? 'bg-[#0E2E26] border-[#34D399]/40 text-[#34D399]'
                : 'bg-[#36161B] border-[#F87171]/40 text-[#F87171]'
            }`}
          >
            {genetEvaluation.interactionType}
          </span>
        </div>
      </div>

      {/* 3-Column Clean Visual Graphs Layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
        {/* GRAPH 1: Survival & Area Recovery (4 cols) */}
        <div className="xl:col-span-4 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#1B313E]">
              <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
                <LineChart className="w-4 h-4 text-[#34D399]" />
                Restored vs Control Survival
              </h2>
              <span className="text-xs font-mono text-[#34D399] font-semibold">
                +{(activeVisit.interventionSurvivalPct - activeVisit.referenceControlSurvivalPct).toFixed(1)}%
              </span>
            </div>

            {/* Day Visit Selector Buttons */}
            <div className="grid grid-cols-4 gap-1 font-mono text-xs">
              {INITIAL_ECOLOGICAL_VISITS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setSelectedVisitId(v.id)}
                  className={`py-1.5 border cursor-pointer transition-colors text-center ${
                    v.id === selectedVisitId
                      ? 'bg-[#123344] border-[#38BDF8] text-white font-semibold'
                      : 'bg-[#08131A] border-[#1E3645] text-[#8BA6B8] hover:text-white'
                  }`}
                >
                  Day {v.dayOffset}
                </button>
              ))}
            </div>

            {/* Visual SVG Survival Curve Across Visits */}
            <div className="bg-[#08131A] border border-[#172B36] p-3">
              <svg
                viewBox="0 0 280 115"
                className="w-full h-28"
                aria-label="Restored versus Control survival trend chart"
              >
                {[25, 55, 85].map((y) => (
                  <line
                    key={y}
                    x1="24"
                    y1={y}
                    x2="264"
                    y2={y}
                    stroke="#142632"
                    strokeDasharray="2 2"
                  />
                ))}
                {/* Control curve */}
                <polyline
                  fill="none"
                  stroke="#64748B"
                  strokeWidth="2"
                  strokeDasharray="4 3"
                  points={INITIAL_ECOLOGICAL_VISITS.map((v, i) => {
                    const x = 36 + i * 72;
                    const y = 96 - (v.referenceControlSurvivalPct / 100) * 76;
                    return `${x},${y}`;
                  }).join(' ')}
                />
                {/* Restored curve */}
                <polyline
                  fill="none"
                  stroke="#34D399"
                  strokeWidth="2.5"
                  points={INITIAL_ECOLOGICAL_VISITS.map((v, i) => {
                    const x = 36 + i * 72;
                    const y = 96 - (v.interventionSurvivalPct / 100) * 76;
                    return `${x},${y}`;
                  }).join(' ')}
                />
                {INITIAL_ECOLOGICAL_VISITS.map((v, i) => {
                  const x = 36 + i * 72;
                  const yRest = 96 - (v.interventionSurvivalPct / 100) * 76;
                  const yCtrl = 96 - (v.referenceControlSurvivalPct / 100) * 76;
                  const isSel = v.id === selectedVisitId;
                  return (
                    <g
                      key={v.id}
                      onClick={() => setSelectedVisitId(v.id)}
                      className="cursor-pointer"
                    >
                      <circle
                        cx={x}
                        cy={yCtrl}
                        r={isSel ? 4.5 : 3}
                        fill="#94A3B8"
                      />
                      <circle
                        cx={x}
                        cy={yRest}
                        r={isSel ? 5.5 : 3.5}
                        fill="#34D399"
                        stroke="#06141B"
                        strokeWidth="1.5"
                      />
                      <text
                        x={x}
                        y="110"
                        textAnchor="middle"
                        fill={isSel ? '#FFFFFF' : '#7FA0B5'}
                        fontSize="9"
                        fontFamily="JetBrains Mono"
                      >
                        D{v.dayOffset}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>

            {/* Clean Comparison Bars for Selected Visit */}
            <div className="space-y-2.5 text-xs font-mono tabular-nums">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-sans text-[#94B4C7]">Restored Survival</span>
                  <span className="text-[#34D399] font-semibold">
                    {activeVisit.interventionSurvivalPct.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-[#08131A] border border-[#172B36]">
                  <div
                    className="h-full bg-[#34D399]"
                    style={{ width: `${activeVisit.interventionSurvivalPct}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="font-sans text-[#94B4C7]">Control Survival</span>
                  <span className="text-[#94B4C7]">
                    {activeVisit.referenceControlSurvivalPct.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-[#08131A] border border-[#172B36]">
                  <div
                    className="h-full bg-[#64748B]"
                    style={{ width: `${activeVisit.referenceControlSurvivalPct}%` }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="p-2 bg-[#08131A] border border-[#172B36]">
                  <span className="text-[10px] font-sans text-[#8BA6B8] block">Restored Area</span>
                  <span className="text-sm font-bold text-[#38BDF8]">
                    {activeVisit.meanColonyAreaCm2.toFixed(1)} cm²
                  </span>
                </div>
                <div className="p-2 bg-[#08131A] border border-[#172B36]">
                  <span className="text-[10px] font-sans text-[#8BA6B8] block">Control Area</span>
                  <span className="text-sm font-bold text-[#94B4C7]">
                    {activeVisit.referenceAreaCm2.toFixed(1)} cm²
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* GRAPH 2: 4D Growth & UV Spectrum (4 cols) */}
        <div className="xl:col-span-4 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#1B313E]">
              <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-[#34D399]" />
                4D Colony Growth ({selectedCluster.id})
              </h2>
              <span className="text-xs font-mono text-[#6EE7B7]">
                Day {growthDay} · ×{temporalStage.calcificationFactor.toFixed(2)}
              </span>
            </div>

            {/* Day Scrubber */}
            <div className="space-y-1.5">
              <div className="grid grid-cols-4 gap-1 font-mono text-xs">
                {[0, 7, 14, 49].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setGrowthDay(d)}
                    className={`py-1 border cursor-pointer transition-colors ${
                      growthDay === d
                        ? 'bg-[#143545] border-[#38BDF8] text-white font-semibold'
                        : 'bg-[#08131A] border-[#1B313E] text-[#8BA6B8] hover:text-white'
                    }`}
                  >
                    Day {d}
                  </button>
                ))}
              </div>
              <input
                type="range"
                min="0"
                max="49"
                step="1"
                value={growthDay}
                onChange={(e) => setGrowthDay(parseInt(e.target.value, 10))}
                aria-label="Growth day timeline"
                className="w-full accent-[#34D399] cursor-pointer"
              />
            </div>

            {/* Visual Coral Fusion SVG */}
            <div className="bg-[#08131A] border border-[#172B36] p-3 flex items-center justify-between gap-3">
              <svg
                viewBox="0 0 170 105"
                className="w-36 h-24 shrink-0"
                aria-label="Coral fusion diagram"
              >
                <rect x="10" y="80" width="150" height="14" rx="3" fill="#1E3442" stroke="#33566B" />
                <ellipse
                  cx="85"
                  cy="80"
                  rx={16 + (growthDay / 49) * 32}
                  ry={4 + (growthDay / 49) * 4}
                  fill="rgba(56, 189, 248, 0.32)"
                  stroke="#38BDF8"
                  strokeWidth="1.2"
                />
                <path
                  d="M 32 80 Q 52 34 78 80 Z"
                  fill="rgba(52, 211, 153, 0.35)"
                  stroke="#34D399"
                  strokeWidth="1.5"
                />
                <path
                  d={`M 82 80 Q ${106 + (growthDay / 49) * 12} ${
                    42 - (growthDay / 49) * 16
                  } ${126 + (growthDay / 49) * 16} 80 Z`}
                  fill="rgba(34, 211, 238, 0.35)"
                  stroke="#22D3EE"
                  strokeWidth="1.5"
                />
                {growthDay >= 3 && (
                  <ellipse
                    cx="80"
                    cy="68"
                    rx={4 + Math.min(12, temporalStage.tissueBridgeMm * 0.8)}
                    ry={4 + Math.min(7, temporalStage.tissueBridgeMm * 0.4)}
                    fill="rgba(110, 231, 183, 0.6)"
                    stroke="#6EE7B7"
                  />
                )}
              </svg>

              <div className="flex-1 space-y-2 text-xs font-mono tabular-nums">
                <div className="flex justify-between">
                  <span className="font-sans text-[#8BA6B8]">Symbiont</span>
                  <span className="text-[#34D399] font-bold">{temporalStage.symbiontDensityPct}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-sans text-[#8BA6B8]">Bridge</span>
                  <span className="text-[#7DD3FC] font-bold">{temporalStage.tissueBridgeMm.toFixed(1)} mm</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-sans text-[#8BA6B8]">Bond Shear</span>
                  <span className="text-[#38BDF8] font-bold">{temporalStage.skeletalBondShearN.toFixed(1)} N</span>
                </div>
              </div>
            </div>

            {/* UV Fluorescence Bar Graph */}
            <div className="p-3 bg-[#08131A] border border-[#172B36] space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-[#E0F2FE] flex items-center gap-1">
                  <Sparkles className="w-3.5 h-3.5 text-[#34D399]" />
                  UV Emission ({selectedCluster.id})
                </span>
                <span className="font-mono text-[11px] text-[#34D399]">
                  GFP {Math.round(selectedCluster.gfpIntensity * 100)}%
                </span>
              </div>
              <div className="flex items-end gap-1.5 h-12 pt-1">
                {spectralPoints.map((pt) => (
                  <div key={pt.wavelengthNm} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-[#060E13] h-8 flex items-end overflow-hidden border border-[#162A36]">
                      <div
                        className="w-full transition-all"
                        style={{
                          height: `${Math.max(10, Math.round(pt.relativeIntensity * 100))}%`,
                          backgroundColor:
                            pt.wavelengthNm === 508
                              ? '#34D399'
                              : pt.wavelengthNm === 585
                              ? '#FBBF24'
                              : pt.wavelengthNm === 685
                              ? '#F87171'
                              : '#38BDF8',
                        }}
                      />
                    </div>
                    <span className="text-[9px] font-mono text-[#7FA0B5] tabular-nums">
                      {pt.wavelengthNm}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* GRAPH 3: Site Optimiser & Top Ranked Sites Bar Graph (4 cols) */}
        <div className="xl:col-span-4 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-3">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#1B313E]">
              <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
                <Sliders className="w-4 h-4 text-[#38BDF8]" />
                Site Optimiser Rankings
              </h2>
              <button
                type="button"
                onClick={() => onChangeOptimiserWeights(DEFAULT_OPTIMISER_WEIGHTS)}
                className="px-2 py-0.5 text-[11px] font-mono bg-[#08131A] hover:bg-[#122633] border border-[#1E3645] text-[#94B4C7] hover:text-white cursor-pointer inline-flex items-center gap-1"
              >
                <RotateCcw className="w-3 h-3" />
                Reset
              </button>
            </div>

            {/* 4 Clean Weight Sliders */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <label className="p-2 bg-[#08131A] border border-[#172B36] block">
                <div className="flex justify-between font-mono mb-1">
                  <span className="text-[#94B4C7]">Stability</span>
                  <span className="text-[#34D399]">{optimiserWeights.wSub.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.05"
                  value={optimiserWeights.wSub}
                  onChange={(e) => updateWeight('wSub', parseFloat(e.target.value))}
                  aria-label="Stability weight"
                  className="w-full accent-[#34D399] cursor-pointer"
                />
              </label>

              <label className="p-2 bg-[#08131A] border border-[#172B36] block">
                <div className="flex justify-between font-mono mb-1">
                  <span className="text-[#94B4C7]">Flow Fit</span>
                  <span className="text-[#38BDF8]">{optimiserWeights.wFlow.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.05"
                  value={optimiserWeights.wFlow}
                  onChange={(e) => updateWeight('wFlow', parseFloat(e.target.value))}
                  aria-label="Flow Fit weight"
                  className="w-full accent-[#38BDF8] cursor-pointer"
                />
              </label>

              <label className="p-2 bg-[#08131A] border border-[#172B36] block">
                <div className="flex justify-between font-mono mb-1">
                  <span className="text-[#94B4C7]">Clonal Prox</span>
                  <span className="text-[#7DD3FC]">{optimiserWeights.wProx.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.05"
                  value={optimiserWeights.wProx}
                  onChange={(e) => updateWeight('wProx', parseFloat(e.target.value))}
                  aria-label="Clonal proximity weight"
                  className="w-full accent-[#7DD3FC] cursor-pointer"
                />
              </label>

              <label className="p-2 bg-[#08131A] border border-[#172B36] block">
                <div className="flex justify-between font-mono mb-1">
                  <span className="text-[#94B4C7]">Uncertainty</span>
                  <span className="text-[#F87171]">{optimiserWeights.wUnc.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.05"
                  value={optimiserWeights.wUnc}
                  onChange={(e) => updateWeight('wUnc', parseFloat(e.target.value))}
                  aria-label="Uncertainty weight"
                  className="w-full accent-[#F87171] cursor-pointer"
                />
              </label>
            </div>

            {/* Interactive Ranked Coral Score Bars */}
            <div className="space-y-1.5 pt-1">
              {rankedClusters.slice(0, 7).map(({ cluster: c, score: sc }) => {
                const isSel = c.id === selectedClusterId;
                const pct = Math.max(8, Math.min(100, (sc.totalScore / maxScore) * 100));
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => onSelectCluster(c.id)}
                    className={`w-full text-left p-2 border transition-colors cursor-pointer ${
                      isSel
                        ? 'bg-[#123142] border-[#38BDF8]'
                        : 'bg-[#08131A] border-[#172B36] hover:border-[#2B4C5E]'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs font-mono mb-1">
                      <span className="font-bold text-white">
                        {c.id}{' '}
                        <span className="font-normal text-[#8BA6B8]">({c.status})</span>
                      </span>
                      <span className="text-[#34D399] font-semibold tabular-nums">
                        {sc.totalScore.toFixed(2)}
                      </span>
                    </div>
                    <div className="h-1.5 bg-[#060E14] overflow-hidden">
                      <div
                        className="h-full bg-[#38BDF8]"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
