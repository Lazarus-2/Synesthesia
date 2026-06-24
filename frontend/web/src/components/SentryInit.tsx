"use client";
import { useEffect } from "react";

export function SentryInit() {
  useEffect(() => {
    const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
    if (!dsn) return;
    let cancelled = false;
    import("@sentry/browser").then((Sentry) => {
      if (cancelled) return;
      Sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
        tracesSampleRate: 0,
      });
    }).catch(() => { /* sentry optional — never break the app */ });
    return () => { cancelled = true; };
  }, []);
  return null;
}
