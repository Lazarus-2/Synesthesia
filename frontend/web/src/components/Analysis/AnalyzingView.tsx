"use client";

import React, { useEffect, useState } from "react";
import { useAnalysisStore } from "../../store/useAnalysisStore";

const STEPS = [
  { label: "Listening", threshold: 5 },
  { label: "Detecting chords", threshold: 30 },
  { label: "Analyzing theory", threshold: 60 },
  { label: "Generating your guide", threshold: 90 },
];

// Constellation positions are rolled once at module load — the visual is
// pure decoration, and computing them at render time tripped
// ``react-hooks/purity``. A static array also avoids the re-mount jitter
// you'd get from a per-mount useMemo.
const CONSTELLATION = Array.from({ length: 30 }, () => ({
  size: Math.random() * 2 + 2,
  left: Math.random() * 100,
  top: Math.random() * 100,
  duration: Math.random() * 4 + 3,
  delay: Math.random() * 5,
}));

function getActiveStep(progress: number): number {
  for (let i = STEPS.length - 1; i >= 0; i--) {
    if (progress >= STEPS[i].threshold) return i;
  }
  return 0;
}

export const AnalyzingView: React.FC = () => {
  const { jobStatus, jobProgress, jobMessage } = useAnalysisStore();

  // Trickle: backend milestones are coarse and some stages (the local-model
  // LLM) take a minute+, so the raw % can sit still. A timer eases a
  // *displayed* value toward the next milestone (capped at 95) so the bar
  // keeps visibly moving and never looks frozen. All updates happen inside
  // the interval callback (no synchronous setState in an effect body): it
  // snaps up to a real milestone, trickles between them, and resets when a
  // new job starts (progress jumps back down).
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (jobStatus !== "queued" && jobStatus !== "processing") return;
    const id = setInterval(() => {
      setShown((s) => {
        if (jobProgress < s - 5) return jobProgress; // new job → reset
        if (jobProgress > s) return jobProgress; // real milestone → snap up
        const ceiling = Math.min(jobProgress + 12, 95);
        return s >= ceiling ? s : Math.min(ceiling, s + 0.4);
      });
    }, 350);
    return () => clearInterval(id);
  }, [jobStatus, jobProgress]);

  // Only show when actively processing
  if (jobStatus === "idle" || jobStatus === "done") return null;

  const activeStep = getActiveStep(jobProgress);
  const isError = jobStatus === "error";

  return (
    <div className="fixed inset-0 z-40 bg-background flex items-center justify-center relative overflow-hidden">
      {/* Background constellation dots */}
      <div className="absolute inset-0 pointer-events-none z-0">
        {CONSTELLATION.map((p, i) => (
          <div
            key={i}
            className="absolute rounded-full bg-white/10 animate-pulse-glow"
            style={{
              width: `${p.size}px`,
              height: `${p.size}px`,
              left: `${p.left}%`,
              top: `${p.top}%`,
              animationDuration: `${p.duration}s`,
              animationDelay: `${p.delay}s`,
            }}
          />
        ))}
      </div>

      <div className="max-w-[600px] w-full flex flex-col items-center px-5 relative z-10">
        {/* Animated Waveform Icon */}
        <div className="relative w-48 h-48 mb-12 flex items-center justify-center">
          {/* Glowing aura */}
          <div className="absolute inset-0 bg-primary-container rounded-full blur-[60px] opacity-20 animate-pulse-glow mix-blend-screen" />
          {/* Inner glass container with wave bars */}
          <div className="relative z-10 w-32 h-32 rounded-full border border-white/10 bg-white/[0.03] backdrop-blur-xl flex items-center justify-center gap-[3px] shadow-[inset_0_0_0_1px_rgba(255,181,71,0.1)]">
            {[6, 10, 16, 20, 24, 20, 16, 10, 6].map((h, i) => (
              <div
                key={i}
                className="w-1.5 bg-gradient-to-t from-primary to-tertiary-container rounded-full wave-bar"
                style={{ height: `${h}px`, opacity: 0.7 + i * 0.03 }}
              />
            ))}
          </div>
        </div>

        {/* Pipeline Step Indicator */}
        {!isError && (
          <div className="w-full bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.4)] mb-8">
            <div className="flex flex-col gap-6">
              {STEPS.map((step, i) => {
                const isDone = i < activeStep || (i === activeStep && jobProgress >= STEPS[i].threshold + 10);
                const isActive = i === activeStep && !isDone;

                return (
                  <React.Fragment key={step.label}>
                    {i > 0 && (
                      <div
                        className={`w-0.5 h-4 ml-[15px] -my-4 rounded-full ${
                          isDone ? "bg-secondary-container/30" : isActive ? "bg-primary-container/30" : "bg-white/10"
                        }`}
                      />
                    )}
                    <div className="flex items-center gap-4">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                          isDone
                            ? "bg-secondary-container/20 border border-secondary-container glow-violet"
                            : isActive
                            ? "border border-primary-container bg-primary-container/10 inner-glow-focus"
                            : "border border-white/20 bg-white/5"
                        }`}
                      >
                        {isDone ? (
                          <span className="material-symbols-outlined text-[16px] text-on-secondary-container" style={{ fontVariationSettings: "'FILL' 1" }}>
                            check
                          </span>
                        ) : isActive ? (
                          <span className="material-symbols-outlined text-[16px] text-primary-container animate-spin">
                            refresh
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-on-surface-variant">{i + 1}</span>
                        )}
                      </div>
                      <p
                        className={`${
                          isDone
                            ? "text-on-surface"
                            : isActive
                            ? "text-primary font-medium"
                            : "text-on-surface-variant"
                        }`}
                      >
                        {isActive ? `${step.label}...` : step.label}
                      </p>
                    </div>
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        )}

        {/* Status Text */}
        <div className="text-center">
          {isError ? (
            <>
              <h2 className="font-headline text-2xl font-medium text-error mb-2">Analysis Failed</h2>
              <p className="text-on-surface-variant">{jobMessage}</p>
            </>
          ) : (
            <>
              <h2 className="font-headline text-2xl font-medium text-on-surface mb-2">
                {jobMessage || "Processing..."}
              </h2>
              {/* Visible progress bar — determinate fill (jobProgress%) with a
                  shimmer sweep so it reads as "working" even while the backend
                  percentage is static (e.g. during a long YouTube download). */}
              <div
                className="w-full h-2.5 rounded-full bg-white/10 overflow-hidden mt-4 mb-3"
                role="progressbar"
                aria-valuenow={Math.round(shown)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Analysis progress"
              >
                <div
                  className="progress-fill progress-shimmer relative h-full rounded-full bg-gradient-to-r from-primary to-tertiary-container"
                  style={{ width: `${Math.max(4, Math.min(100, shown))}%` }}
                />
              </div>
              <p className="text-on-surface-variant flex items-center justify-center gap-2 tabular-nums">
                <span className="w-2 h-2 rounded-full bg-primary-container animate-pulse" />
                {shown > 0 ? `${Math.round(shown)}% complete` : "Starting analysis…"}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
