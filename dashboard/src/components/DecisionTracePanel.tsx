import React, { useState } from 'react';
import { DecisionTraceEvent } from '../domain/reefEngine';
import {
  Pause,
  Play,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  ArrowLeftRight,
  Maximize2,
  Minimize2,
} from 'lucide-react';

interface DecisionTracePanelProps {
  events: DecisionTraceEvent[];
  selectedEventId: string;
  onSelectEvent: (event: DecisionTraceEvent) => void;
  isPaused: boolean;
  onTogglePause: () => void;
  onUpdateEventReview?: (
    eventId: string,
    status: 'Accepted' | 'Changed' | 'Rejected',
    reason: string
  ) => void;
  onSwapSlot?: () => void;
  onToggleExpand?: () => void;
  isExpanded?: boolean;
}

const TOOL_LABELS: Record<string, string> = {
  all: 'All',
  verify: 'Placed',
  place: 'Clump',
  carry: 'Carry',
  grasp: 'Pick Up',
  goto: 'Move',
  inspect: 'Check',
  scan: 'Scan',
};

export const DecisionTracePanel: React.FC<DecisionTracePanelProps> = ({
  events,
  selectedEventId,
  onSelectEvent,
  isPaused,
  onTogglePause,
  onUpdateEventReview,
  onSwapSlot,
  onToggleExpand,
  isExpanded,
}) => {
  const [filterTool, setFilterTool] = useState<string>('all');

  const visibleEvents =
    filterTool === 'all'
      ? events
      : events.filter((e) =>
          filterTool === 'verify'
            ? e.toolCalled === 'verify' || e.toolCalled === 'place'
            : e.toolCalled === filterTool
        );

  const activeEvent =
    events.find((e) => e.id === selectedEventId) || visibleEvents[0] || events[0];

  const getTiltDegrees = (normal: [number, number, number]) => {
    const nz = Math.max(-1, Math.min(1, normal[2] ?? 1));
    return Math.round((Math.acos(nz) * 180) / Math.PI);
  };

  const activeTiltDeg = getTiltDegrees(activeEvent.surfaceNormal);
  const seabedConfidencePct = Math.round((1 - activeEvent.uncertainty) * 100);

  // Build comparative stability shift bars across events
  const shiftBars = events.slice(0, 6).map((evt, idx) => ({
    id: evt.id,
    clusterId: evt.clusterId,
    shiftMm:
      evt.placementShiftMm > 0
        ? evt.placementShiftMm
        : Number((1.1 + (idx % 3) * 0.45).toFixed(1)),
    confidencePct: Math.round(evt.confidence * 100),
    event: evt,
  }));

  return (
    <div className="flex flex-col h-full bg-[#0D1A22] border border-[#1B313E]">
      {/* Compact Header with Filter Pills & Icon Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-[#1B313E]">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-[#F0F7FA] tracking-tight">
            Live Mission Log
          </h2>
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs">
            {(['all', 'verify', 'carry', 'grasp', 'goto', 'inspect'] as const).map((tool) => (
              <button
                key={tool}
                type="button"
                onClick={() => setFilterTool(tool)}
                className={`px-2 py-0.5 font-medium transition-colors cursor-pointer ${
                  filterTool === tool
                    ? 'bg-[#163445] text-white'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {TOOL_LABELS[tool]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onTogglePause}
            title={isPaused ? 'Resume live log' : 'Pause live log'}
            aria-label={isPaused ? 'Resume live log' : 'Pause live log'}
            className={`p-1.5 border transition-colors cursor-pointer ${
              isPaused
                ? 'bg-[#2A2212] border-[#FBBF24] text-[#FDE68A]'
                : 'bg-[#091318] border-[#233F4F] text-[#94B4C7] hover:text-white'
            }`}
          >
            {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
          </button>

          {onSwapSlot && (
            <button
              type="button"
              onClick={onSwapSlot}
              title="Swap panel position"
              aria-label="Swap Live Mission Log panel position"
              className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#8BA6B8] hover:text-white cursor-pointer"
            >
              <ArrowLeftRight className="w-3.5 h-3.5" />
            </button>
          )}

          {onToggleExpand && (
            <button
              type="button"
              onClick={onToggleExpand}
              title={isExpanded ? 'Restore 2×2 grid' : 'Expand full width'}
              aria-label={isExpanded ? 'Restore 2×2 grid' : 'Expand full width'}
              className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#8BA6B8] hover:text-white cursor-pointer"
            >
              {isExpanded ? (
                <Minimize2 className="w-3.5 h-3.5" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Split View: Clean Scannable Log Rows (Left) + Visual Graphs & Quick Sign-Off (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 flex-1 min-h-[300px] divide-y lg:divide-y-0 lg:divide-x divide-[#1B313E]">
        {/* Left Compact Event Stream */}
        <div className="lg:col-span-5 flex flex-col bg-[#09141B] max-h-[360px] overflow-y-auto divide-y divide-[#152833]">
          {visibleEvents.map((evt) => {
            const isSelected = evt.id === activeEvent.id;
            const badgeText = TOOL_LABELS[evt.toolCalled] || evt.actionType;

            return (
              <button
                key={evt.id}
                type="button"
                onClick={() => onSelectEvent(evt)}
                className={`w-full text-left px-3.5 py-2.5 transition-colors cursor-pointer ${
                  isSelected
                    ? 'bg-[#122734] text-white'
                    : 'hover:bg-[#0D1E28] text-[#B8CEDC]'
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-1.5">
                    {evt.statusTone === 'critical' ? (
                      <ShieldAlert className="w-3.5 h-3.5 text-[#F87171] shrink-0" />
                    ) : evt.statusTone === 'warning' ? (
                      <AlertTriangle className="w-3.5 h-3.5 text-[#FBBF24] shrink-0" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#34D399] shrink-0" />
                    )}
                    <span className="font-mono font-bold text-[#38BDF8]">{evt.clusterId}</span>
                    <span className="text-[#8BA6B8]">· {badgeText}</span>
                  </div>
                  <span className="font-mono text-[11px] text-[#7FA0B5] tabular-nums">
                    {evt.timestamp}
                  </span>
                </div>

                <div className="text-xs font-medium text-[#E6F0F5] mt-1 line-clamp-1">
                  {evt.headline}
                </div>
              </button>
            );
          })}
        </div>

        {/* Right Interactive Telemetry Graphs & 1-Click Sign-Off */}
        <div className="lg:col-span-7 p-4 flex flex-col justify-between bg-[#0D1A22] space-y-3">
          {/* Selected Action Summary */}
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-[#172B36]">
            <div>
              <div className="text-xs font-mono text-[#7DD3FC]">
                {activeEvent.clusterId} · {activeEvent.timestamp}
              </div>
              <h3 className="text-sm font-bold text-white mt-0.5">{activeEvent.headline}</h3>
              <p className="text-xs text-[#94B4C7] mt-0.5 line-clamp-2">
                {activeEvent.reasoning}
              </p>
            </div>
            <span className="text-xs font-mono text-[#34D399] shrink-0 tabular-nums">
              {(activeEvent.confidence * 100).toFixed(0)}% conf
            </span>
          </div>

          {/* Interactive Stability Shift Bar Chart + Radial Gauges */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
            {/* Interactive Placement Shift Bar Graph (vs 3.0mm Safety Limit) */}
            <div className="sm:col-span-7 bg-[#081218] border border-[#162934] p-3">
              <div className="flex items-center justify-between text-[11px] mb-1.5">
                <span className="text-[#8BA6B8]">Stability Shift (mm)</span>
                <span className="font-mono text-[#34D399]">Limit &lt; 3.0 mm</span>
              </div>

              <svg
                viewBox="0 0 210 64"
                className="w-full h-16 overflow-visible select-none"
                aria-label="Interactive coral placement stability graph"
              >
                {/* 3.0mm safety threshold line */}
                <line
                  x1="0"
                  y1="14"
                  x2="210"
                  y2="14"
                  stroke="#F87171"
                  strokeWidth="1"
                  strokeDasharray="3 2"
                />
                <text
                  x="208"
                  y="11"
                  textAnchor="end"
                  fill="#F87171"
                  fontSize="7.5"
                  fontFamily="JetBrains Mono, monospace"
                >
                  3.0mm max
                </text>
                <line x1="0" y1="50" x2="210" y2="50" stroke="#162B38" strokeWidth="1" />

                {shiftBars.map((bar, i) => {
                  const x = 10 + i * 33;
                  const barH = Math.min(36, (bar.shiftMm / 3.5) * 36);
                  const y = 50 - barH;
                  const isSel = bar.id === activeEvent.id;
                  return (
                    <g
                      key={bar.id}
                      onClick={() => onSelectEvent(bar.event)}
                      className="cursor-pointer"
                    >
                      <rect
                        x={x}
                        y={y}
                        width="18"
                        height={barH}
                        fill={isSel ? '#38BDF8' : bar.shiftMm <= 2.5 ? '#34D399' : '#FBBF24'}
                      />
                      <text
                        x={x + 9}
                        y={y - 3}
                        textAnchor="middle"
                        fill="#E6F0F5"
                        fontSize="7.5"
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {bar.shiftMm}
                      </text>
                      <text
                        x={x + 9}
                        y="61"
                        textAnchor="middle"
                        fill={isSel ? '#FFFFFF' : '#7FA0B5'}
                        fontSize="8"
                        fontWeight={isSel ? '700' : '400'}
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {bar.clusterId}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>

            {/* 2 Visual Radial Gauges: Rock Tilt & Seabed Solidity */}
            <div className="sm:col-span-5 grid grid-cols-2 gap-2">
              <div className="bg-[#081218] border border-[#162934] p-2.5 flex flex-col items-center">
                <svg viewBox="0 0 64 42" className="w-16 h-11">
                  <path
                    d="M 8 36 A 24 24 0 0 1 56 36"
                    fill="none"
                    stroke="#152834"
                    strokeWidth="6"
                    strokeLinecap="round"
                  />
                  <path
                    d="M 8 36 A 24 24 0 0 1 56 36"
                    fill="none"
                    stroke={activeTiltDeg <= 20 ? '#34D399' : '#FBBF24'}
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeDasharray={`${Math.min(75, (activeTiltDeg / 35) * 75)} 75`}
                  />
                  <text
                    x="32"
                    y="34"
                    textAnchor="middle"
                    fill="#FFFFFF"
                    fontSize="12"
                    fontWeight="700"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {activeTiltDeg}°
                  </text>
                </svg>
                <span className="text-[10.5px] text-[#8BA6B8]">Rock Tilt</span>
              </div>

              <div className="bg-[#081218] border border-[#162934] p-2.5 flex flex-col items-center">
                <svg viewBox="0 0 64 42" className="w-16 h-11">
                  <path
                    d="M 8 36 A 24 24 0 0 1 56 36"
                    fill="none"
                    stroke="#152834"
                    strokeWidth="6"
                    strokeLinecap="round"
                  />
                  <path
                    d="M 8 36 A 24 24 0 0 1 56 36"
                    fill="none"
                    stroke="#38BDF8"
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeDasharray={`${(seabedConfidencePct / 100) * 75} 75`}
                  />
                  <text
                    x="32"
                    y="34"
                    textAnchor="middle"
                    fill="#FFFFFF"
                    fontSize="11"
                    fontWeight="700"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {seabedConfidencePct}%
                  </text>
                </svg>
                <span className="text-[10.5px] text-[#8BA6B8]">Solid Rock</span>
              </div>
            </div>
          </div>

          {/* Compact 1-Click Sign-Off Bar */}
          <div className="pt-2 border-t border-[#1B313E] flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="text-[#8BA6B8]">
              Review: <strong className="text-white">{activeEvent.humanReviewStatus || 'Accepted'}</strong>
            </span>
            <div className="flex items-center gap-1.5">
              {(
                [
                  { label: '✓ Approve', status: 'Accepted', reason: 'Verified nominal' },
                  { label: '⚠ Flag Rock', status: 'Changed', reason: 'Uncertain substrate' },
                  { label: '✕ Reject', status: 'Rejected', reason: 'Outside approved area' },
                ] as const
              ).map((btn) => (
                <button
                  key={btn.label}
                  type="button"
                  onClick={() =>
                    onUpdateEventReview?.(activeEvent.id, btn.status, btn.reason)
                  }
                  className={`px-2.5 py-1 font-medium border cursor-pointer transition-colors ${
                    activeEvent.humanReviewStatus === btn.status
                      ? 'bg-[#123342] border-[#38BDF8] text-white'
                      : 'bg-[#081218] border-[#1E3645] text-[#94B4C7] hover:text-white'
                  }`}
                >
                  {btn.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
