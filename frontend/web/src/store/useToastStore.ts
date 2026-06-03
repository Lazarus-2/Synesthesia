import { create } from 'zustand';

/**
 * Toast notifications (Plan 3 D0).
 *
 * Tiny pub/sub for transient error / info messages. The Toast component
 * subscribes and renders the queue; consumers call ``error()`` / ``info()``
 * to push. Auto-dismiss is handled in the component via setTimeout because
 * doing it in the store would create a cleanup race on rapid pushes.
 */
export type ToastLevel = 'error' | 'info' | 'success';

export interface ToastItem {
  id: number;
  level: ToastLevel;
  message: string;
  detail?: string;
  /** Milliseconds before auto-dismissal; 0 keeps it pinned. */
  duration: number;
}

interface ToastState {
  toasts: ToastItem[];
  push: (level: ToastLevel, message: string, detail?: string, duration?: number) => number;
  dismiss: (id: number) => void;
  clear: () => void;
  // Convenience wrappers
  error: (message: string, detail?: string) => number;
  info: (message: string, detail?: string) => number;
  success: (message: string, detail?: string) => number;
}

let _nextId = 1;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  push: (level, message, detail, duration = 5000) => {
    const id = _nextId++;
    set((s) => ({
      toasts: [...s.toasts, { id, level, message, detail, duration }],
    }));
    return id;
  },

  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  clear: () => set({ toasts: [] }),

  error: (message, detail) => get().push('error', message, detail, 8000),
  info: (message, detail) => get().push('info', message, detail, 4000),
  success: (message, detail) => get().push('success', message, detail, 4000),
}));
