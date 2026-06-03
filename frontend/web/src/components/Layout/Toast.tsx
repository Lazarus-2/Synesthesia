"use client";

import React, { useEffect } from "react";
import { useToastStore, ToastItem } from "../../store/useToastStore";

const LEVEL_STYLE: Record<ToastItem["level"], { border: string; bg: string; icon: string; iconColor: string }> = {
  error: {
    border: "border-error/40",
    bg: "bg-error/10",
    icon: "error",
    iconColor: "text-error",
  },
  info: {
    border: "border-primary-container/30",
    bg: "bg-primary-container/10",
    icon: "info",
    iconColor: "text-primary-container",
  },
  success: {
    border: "border-secondary-container/30",
    bg: "bg-secondary-container/10",
    icon: "check_circle",
    iconColor: "text-on-secondary-container",
  },
};

/**
 * Toast container (Plan 3 D0).
 *
 * Mounted once near the root of HomeClient. Each ToastEntry runs its own
 * auto-dismiss timer so calling code never has to manage cleanup.
 */
export const ToastContainer: React.FC = () => {
  const { toasts, dismiss } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-20 right-6 z-[60] flex flex-col gap-2 max-w-sm pointer-events-none"
      role="region"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <ToastEntry key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  );
};

interface EntryProps {
  toast: ToastItem;
  onDismiss: () => void;
}

const ToastEntry: React.FC<EntryProps> = ({ toast, onDismiss }) => {
  const style = LEVEL_STYLE[toast.level];

  useEffect(() => {
    if (toast.duration <= 0) return;
    const id = window.setTimeout(onDismiss, toast.duration);
    return () => window.clearTimeout(id);
  }, [toast.duration, onDismiss]);

  return (
    <div
      className={`pointer-events-auto rounded-xl p-3 backdrop-blur-xl glass-panel border ${style.border} ${style.bg} animate-pulse-glow shadow-lg`}
      role={toast.level === "error" ? "alert" : "status"}
    >
      <div className="flex items-start gap-3">
        <span
          className={`material-symbols-outlined text-xl ${style.iconColor} flex-shrink-0 mt-0.5`}
          style={{ fontVariationSettings: "'FILL' 1" }}
        >
          {style.icon}
        </span>
        <div className="flex-grow min-w-0">
          <p className="text-sm font-medium text-on-surface break-words">{toast.message}</p>
          {toast.detail && (
            <p className="text-xs text-on-surface-variant mt-1 break-words">
              {toast.detail}
            </p>
          )}
        </div>
        <button
          onClick={onDismiss}
          aria-label="Dismiss notification"
          className="text-on-surface-variant hover:text-on-surface shrink-0"
        >
          <span className="material-symbols-outlined text-sm">close</span>
        </button>
      </div>
    </div>
  );
};
