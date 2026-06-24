"use client";

import React from "react";
import { useSpeedTrainerStore } from "../../store/useSpeedTrainerStore";
import { usePracticeStore } from "../../store/usePracticeStore";

/** Tempo-ramp practice control. Shown inside the practice tray when a loop is
 *  set. Reads/writes the SpeedTrainer store; the actual rate bumps happen in
 *  BottomBar's loop-wrap effect via registerLoopWrap(). */
export const SpeedTrainer: React.FC = () => {
  const { enabled, startPct, targetPct, stepPct, loopsPerStep, currentPct, currentPass, toggle, setConfig } =
    useSpeedTrainerStore();
  const loopStart = usePracticeStore((s) => s.loopStart);
  const loopEnd = usePracticeStore((s) => s.loopEnd);
  const hasLoop = loopStart !== null && loopEnd !== null && loopEnd > loopStart;

  const pctRange = Math.max(1, targetPct - startPct);
  const progress = Math.min(100, Math.max(0, ((currentPct - startPct) / pctRange) * 100));

  return (
    <div className="glass-panel rounded-lg p-3 flex flex-col gap-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-on-surface flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">trending_up</span>
          Speed Trainer
        </span>
        <button
          onClick={toggle}
          disabled={!hasLoop}
          aria-pressed={enabled}
          title={hasLoop ? "Auto speed-up each loop pass" : "Set an A/B loop first"}
          className={`px-2 py-1 rounded-full text-xs font-medium transition-all ${
            enabled
              ? "bg-primary-container/20 text-primary border border-primary-container/40"
              : "text-on-surface-variant hover:text-primary border border-white/10"
          } disabled:opacity-40`}
        >
          {enabled ? "On" : "Off"}
        </button>
      </div>

      {enabled && (
        <>
          <div className="flex items-center justify-between text-on-surface-variant tabular-nums">
            <span>Pass {currentPass}</span>
            <span>
              {currentPct}% → {targetPct}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-2 mt-1">
        <label className="flex flex-col gap-0.5 text-on-surface-variant">
          Start %
          <input
            type="number" min={20} max={100} value={startPct}
            onChange={(e) => setConfig({ startPct: Number(e.target.value) })}
            className="bg-white/5 rounded px-1.5 py-0.5 text-on-surface tabular-nums"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-on-surface-variant">
          Target %
          <input
            type="number" min={20} max={150} value={targetPct}
            onChange={(e) => setConfig({ targetPct: Number(e.target.value) })}
            className="bg-white/5 rounded px-1.5 py-0.5 text-on-surface tabular-nums"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-on-surface-variant">
          Step %
          <input
            type="number" min={1} max={50} value={stepPct}
            onChange={(e) => setConfig({ stepPct: Number(e.target.value) })}
            className="bg-white/5 rounded px-1.5 py-0.5 text-on-surface tabular-nums"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-on-surface-variant">
          Loops / step
          <input
            type="number" min={1} max={8} value={loopsPerStep}
            onChange={(e) => setConfig({ loopsPerStep: Number(e.target.value) })}
            className="bg-white/5 rounded px-1.5 py-0.5 text-on-surface tabular-nums"
          />
        </label>
      </div>
    </div>
  );
};
