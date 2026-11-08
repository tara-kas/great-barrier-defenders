import React, { useState } from 'react';
import {
  PermitApprovalRecord,
  MissionChecklistItem,
  INITIAL_PERMIT_RECORDS,
  INITIAL_MISSION_CHECKLIST,
  evaluateMissionReadiness,
} from '../domain/reefEngine';
import {
  ShieldCheck,
  AlertTriangle,
  FileCheck2,
  Users,
  CheckSquare,
  Square,
} from 'lucide-react';

interface MissionPlanningPermitViewProps {
  currentSpeedMs: number;
  turbidity: number;
}

export const MissionPlanningPermitView: React.FC<MissionPlanningPermitViewProps> = ({
  currentSpeedMs,
  turbidity,
}) => {
  const [permits, setPermits] = useState<PermitApprovalRecord[]>(INITIAL_PERMIT_RECORDS);
  const [checklist, setChecklist] = useState<MissionChecklistItem[]>(INITIAL_MISSION_CHECKLIST);
  const [maxAllowedCurrentMs, setMaxAllowedCurrentMs] = useState<number>(0.75);
  const [minAllowedVisibilityM, setMinAllowedVisibilityM] = useState<number>(2.5);

  const estimatedVisibilityM = Number(Math.max(1.2, 8.5 - turbidity * 11.5).toFixed(1));

  const readiness = evaluateMissionReadiness({
    permits,
    checklist,
    currentSpeedMs,
    maxAllowedCurrentMs,
    visibilityM: estimatedVisibilityM,
    minAllowedVisibilityM,
  });

  const togglePermitVerification = (id: string) => {
    setPermits((prev) =>
      prev.map((p) =>
        p.id === id
          ? {
              ...p,
              status:
                p.status === 'Permit Verified'
                  ? 'Permit Recorded (Pending Verification)'
                  : 'Permit Verified',
            }
          : p
      )
    );
  };

  const toggleChecklist = (id: string) => {
    setChecklist((prev) =>
      prev.map((c) => (c.id === id ? { ...c, completed: !c.completed } : c))
    );
  };

  return (
    <div className="space-y-4">
      {/* Compact Single-Row Launch Readiness Banner */}
      <div
        className={`px-4 py-3 border flex flex-wrap items-center justify-between gap-3 ${
          readiness.ready
            ? 'bg-[#0C2420] border-[#34D399]'
            : 'bg-[#261910] border-[#FBBF24]'
        }`}
      >
        <div className="flex items-center gap-2.5">
          {readiness.ready ? (
            <ShieldCheck className="w-5 h-5 text-[#34D399]" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-[#FBBF24]" />
          )}
          <span className="text-base font-bold text-white tracking-tight">
            {readiness.ready ? 'READY FOR OPERATION' : `HOLD LAUNCH — ${readiness.blockers[0] || 'Check Permits'}`}
          </span>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono tabular-nums">
          <span className={readiness.allPermitsVerified ? 'text-[#34D399]' : 'text-[#FBBF24]'}>
            Permits Verified: {permits.filter((p) => p.status === 'Permit Verified').length}/{permits.length}
          </span>
          <span className="text-[#527082]">·</span>
          <span className={readiness.requiredChecklistComplete ? 'text-[#34D399]' : 'text-[#FBBF24]'}>
            Checklist: {checklist.filter((c) => c.completed).length}/{checklist.length}
          </span>
        </div>
      </div>

      {/* Clean 2-Column Layout: Permits (7 cols) + Operating Limits & Pre-Dive Checklist (5 cols) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
        {/* Left: Regulatory Permits */}
        <div className="xl:col-span-7 bg-[#0D1A22] border border-[#1B313E] p-4 space-y-3">
          <div className="pb-2.5 border-b border-[#1B313E] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <FileCheck2 className="w-4 h-4 text-[#38BDF8]" />
              Permits & Approvals
            </h2>
            <span className="text-xs font-mono text-[#8BA6B8]">
              Click badge to toggle Verified / Recorded
            </span>
          </div>

          <div className="space-y-2.5">
            {permits.map((perm) => {
              const isVerified = perm.status === 'Permit Verified';
              return (
                <div
                  key={perm.id}
                  className="p-3.5 bg-[#09141B] border border-[#19303E] space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-[11px] font-mono text-[#7DD3FC]">
                        {perm.referenceCode} · Valid {perm.validThrough}
                      </div>
                      <h3 className="text-sm font-semibold text-white">{perm.title}</h3>
                    </div>

                    <button
                      type="button"
                      onClick={() => togglePermitVerification(perm.id)}
                      className={`px-2.5 py-1 text-xs font-mono font-semibold border cursor-pointer transition-colors ${
                        isVerified
                          ? 'bg-[#10332C] border-[#34D399] text-[#6EE7B7]'
                          : 'bg-[#2B1F12] border-[#FBBF24] text-[#FDE68A]'
                      }`}
                    >
                      {isVerified ? '✓ Permit Verified' : 'Permit Recorded'}
                    </button>
                  </div>

                  <div className="text-xs text-[#94B4C7]">
                    {perm.conditions[0]}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Operating Limits Graph & Pre-Dive Checklist */}
        <div className="xl:col-span-5 bg-[#0D1A22] border border-[#1B313E] p-4 flex flex-col justify-between space-y-4">
          {/* Operating Limits Bar Graph */}
          <div className="space-y-3">
            <div className="pb-2.5 border-b border-[#1B313E] flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Users className="w-4 h-4 text-[#34D399]" />
                Operating Limits & Team
              </h2>
              <span className="text-xs font-mono text-[#94B4C7]">
                Lead: Dr. E. Vance
              </span>
            </div>

            <div className="p-3 bg-[#09141B] border border-[#19303E] space-y-3 text-xs">
              {/* Current Limit Bar */}
              <div className="space-y-1">
                <div className="flex justify-between font-mono">
                  <span className="text-[#94B4C7]">Water Current</span>
                  <span
                    className={
                      currentSpeedMs <= maxAllowedCurrentMs
                        ? 'text-[#34D399]'
                        : 'text-[#F87171]'
                    }
                  >
                    {currentSpeedMs.toFixed(2)} / {maxAllowedCurrentMs.toFixed(2)} m/s max
                  </span>
                </div>
                <div className="h-2 bg-[#060E14]">
                  <div
                    style={{
                      width: `${Math.min(100, (currentSpeedMs / maxAllowedCurrentMs) * 100)}%`,
                    }}
                    className={`h-full ${
                      currentSpeedMs <= maxAllowedCurrentMs
                        ? 'bg-[#34D399]'
                        : 'bg-[#F87171]'
                    }`}
                  />
                </div>
                <input
                  type="range"
                  min="0.35"
                  max="1.0"
                  step="0.05"
                  value={maxAllowedCurrentMs}
                  onChange={(e) => setMaxAllowedCurrentMs(parseFloat(e.target.value))}
                  aria-label="Maximum allowed current speed"
                  className="w-full accent-[#38BDF8] cursor-pointer"
                />
              </div>

              {/* Visibility Limit Bar */}
              <div className="space-y-1">
                <div className="flex justify-between font-mono">
                  <span className="text-[#94B4C7]">Water Visibility</span>
                  <span
                    className={
                      estimatedVisibilityM >= minAllowedVisibilityM
                        ? 'text-[#34D399]'
                        : 'text-[#F87171]'
                    }
                  >
                    {estimatedVisibilityM}m (Min {minAllowedVisibilityM}m)
                  </span>
                </div>
                <div className="h-2 bg-[#060E14]">
                  <div
                    style={{
                      width: `${Math.min(100, (estimatedVisibilityM / 10) * 100)}%`,
                    }}
                    className={`h-full ${
                      estimatedVisibilityM >= minAllowedVisibilityM
                        ? 'bg-[#38BDF8]'
                        : 'bg-[#F87171]'
                    }`}
                  />
                </div>
                <input
                  type="range"
                  min="1.5"
                  max="6.0"
                  step="0.5"
                  value={minAllowedVisibilityM}
                  onChange={(e) => setMinAllowedVisibilityM(parseFloat(e.target.value))}
                  aria-label="Minimum allowed visibility"
                  className="w-full accent-[#38BDF8] cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* Pre-Dive Checklist */}
          <div className="space-y-2">
            <div className="text-xs font-semibold text-white">Pre-Dive Checklist</div>
            {checklist.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => toggleChecklist(item.id)}
                className="w-full text-left p-2.5 bg-[#09141B] hover:bg-[#10222E] border border-[#19303E] flex items-center gap-2.5 cursor-pointer text-xs"
              >
                {item.completed ? (
                  <CheckSquare className="w-4 h-4 text-[#34D399] shrink-0" />
                ) : (
                  <Square className="w-4 h-4 text-[#FBBF24] shrink-0" />
                )}
                <span className="font-medium text-white truncate">{item.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
