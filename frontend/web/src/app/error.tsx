"use client";

// Next.js App Router error segment (Plan 3 D0).
// Renders when a child route throws an unhandled exception during render
// or a Server Action. Gives the user a clear path back instead of a blank
// screen.

import React, { useEffect } from "react";
import Link from "next/link";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log to the browser console so devtools captures the original stack.
    // Server-side errors arrive here with a ``digest`` instead of a stack.
    console.error("App-segment error:", error);
  }, [error]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <div className="max-w-md w-full mx-4 glass-panel rounded-xl p-8 border border-error/30">
        <div className="flex items-center gap-3 mb-4">
          <span
            className="material-symbols-outlined text-3xl text-error"
            style={{ fontVariationSettings: "'FILL' 1" }}
          >
            error
          </span>
          <h1 className="font-headline text-2xl font-medium text-on-surface">
            Something went wrong
          </h1>
        </div>
        <p className="text-sm text-on-surface-variant mb-6">
          {error.message || "An unexpected error occurred while rendering this page."}
        </p>
        {error.digest && (
          <p className="text-xs text-outline-variant font-mono mb-6 break-all">
            digest: {error.digest}
          </p>
        )}
        <div className="flex gap-3">
          <button
            onClick={reset}
            className="px-4 py-2 rounded-full primary-gradient text-on-primary font-semibold text-sm"
          >
            Try again
          </button>
          <Link
            href="/"
            className="px-4 py-2 rounded-full glass-panel text-on-surface font-medium text-sm hover:border-primary/30"
          >
            Back home
          </Link>
        </div>
      </div>
    </div>
  );
}
