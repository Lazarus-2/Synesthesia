"use client";
import React from "react";

interface Props { children: React.ReactNode; }
interface State { hasError: boolean; }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };
  static getDerivedStateFromError(): State { return { hasError: true }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
      import("@sentry/browser").then((S) => S.captureException(error, { extra: { componentStack: info.componentStack } })).catch(() => {});
    } else {
      console.error("Unhandled UI error:", error, info);
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6">
          <div className="glass-panel rounded-xl p-8 max-w-md text-center flex flex-col gap-4">
            <span className="material-symbols-outlined text-4xl text-primary">error</span>
            <h2 className="font-headline text-xl text-on-surface">Something went wrong</h2>
            <p className="text-sm text-on-surface-variant">An unexpected error occurred. Reloading usually fixes it.</p>
            <button onClick={() => window.location.reload()} className="px-4 py-2 rounded-full glass-panel text-primary hover:border-primary/30 self-center">Reload</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
