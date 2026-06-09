"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useChatStore } from "../../store/useChatStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { useAuthStore } from "../../store/useAuthStore";

const SUGGESTED_PROMPTS = [
  "Why does this progression feel sad?",
  "How do I play the hardest chord?",
  "Suggest a capo position.",
  "What songs sound similar?",
];

/** Split an assistant message into rendered text + the source citations it
 *  carries ([analysis], [theory:<id>]). Citations render as dismissible chips. */
function extractSources(content: string): { text: string; sources: string[] } {
  const sources = new Set<string>();
  const re = /\[(analysis|theory:[a-z0-9_-]+)\]/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) sources.add(m[1].toLowerCase());
  return { text: content.replace(re, "").replace(/\s{2,}/g, " ").trim(), sources: [...sources] };
}

export const ChatPanel: React.FC = () => {
  const { messages, isStreaming, sendMessage, tutorMode, setTutorMode, activeTool, context } =
    useChatStore();
  const { analysis, jobId } = useAnalysisStore();
  const token = useAuthStore((s) => s.token);
  const [input, setInput] = useState("");
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, activeTool]);

  const handleSend = (text?: string) => {
    const value = (text ?? input).trim();
    if (!value || isStreaming) return;
    sendMessage(value, jobId ?? undefined);
    setInput("");
  };

  // ---- Login gate -----------------------------------------------------------
  if (!token) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 p-6 text-center">
        <span
          className="material-symbols-outlined text-3xl text-secondary-container"
          style={{ fontVariationSettings: "'FILL' 1" }}
        >
          lock
        </span>
        <p className="text-sm text-on-surface font-semibold">Sign in to chat</p>
        <p className="text-xs text-on-surface-variant max-w-[28ch]">
          AURA keeps your conversation history private to your account. Sign in to ask about this song.
        </p>
        <Link
          href="/login"
          className="primary-gradient text-on-primary text-sm font-semibold px-5 py-2 rounded-full hover:opacity-90"
        >
          Sign in
        </Link>
      </div>
    );
  }

  // Prefer the server-authoritative `context` frame (emitted at the start of
  // every chat stream) so the chip reflects the song the CHAT SESSION is
  // grounded on. Fall back to the client-local analysis store before context
  // has arrived. Show a caveat marker when the analysis is degraded/failed.
  const contextStatus = context?.status;
  const isDegraded =
    contextStatus === "degraded" || contextStatus === "failed";

  let discussing: string | null = null;
  if (context?.loaded !== false && (context?.title || context?.key)) {
    // Server context is available — use it.
    const parts: string[] = [];
    if (context.key) parts.push(context.key);
    if (context.tempo != null) parts.push(`${Math.round(context.tempo)} BPM`);
    const detail = parts.length ? ` (${parts.join(", ")})` : "";
    discussing = `Discussing: ${context.title ?? "this song"}${detail}`;
  } else if (analysis) {
    // Context hasn't arrived yet — fall back to the analysis store.
    discussing = `Discussing: ${analysis.title} (${analysis.key}, ${Math.round(analysis.tempo)} BPM)`;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-white/10 bg-white/5 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              className="material-symbols-outlined text-secondary-container"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              auto_awesome
            </span>
            <h3 className="text-sm font-semibold text-on-surface uppercase tracking-wider">
              AI Theory Guide
            </h3>
          </div>
          {/* Tutor-mode toggle */}
          <button
            role="switch"
            aria-checked={tutorMode}
            aria-label="Tutor mode"
            onClick={() => setTutorMode(!tutorMode)}
            className={`flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-colors ${
              tutorMode
                ? "bg-secondary-container/40 text-on-secondary-container border-secondary-container/40"
                : "text-on-surface-variant border-white/10 hover:text-on-surface"
            }`}
          >
            <span className="material-symbols-outlined text-[14px]">school</span>
            Tutor
          </button>
        </div>
        {discussing && (
          <div
            className={`mt-2 inline-flex items-center gap-1 text-[11px] rounded-full px-2.5 py-1 border ${
              isDegraded
                ? "text-warning bg-warning/10 border-warning/30"
                : "text-on-surface-variant bg-white/5 border-white/10"
            }`}
            title={isDegraded ? `Analysis is ${contextStatus} — some facts may be unreliable` : undefined}
          >
            <span className="material-symbols-outlined text-[13px]">graphic_eq</span>
            {isDegraded && <span aria-label="partial analysis">⚠</span>}
            {discussing}
          </div>
        )}
      </div>

      {/* Messages (a11y: live log region) */}
      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        className="flex-grow overflow-y-auto hide-scrollbar p-4 space-y-4"
      >
        {messages.map((msg) => {
          const { text, sources } =
            msg.role === "assistant" ? extractSources(msg.content) : { text: msg.content, sources: [] };
          return (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-secondary-container/30 text-on-secondary-container border border-secondary-container/20"
                    : "bg-white/5 text-on-surface border border-white/5"
                }`}
              >
                {msg.role === "assistant" && msg.content === "" && isStreaming ? (
                  <div className="flex items-center gap-2 text-on-surface-variant">
                    <span className="material-symbols-outlined text-sm animate-spin">refresh</span>
                    Thinking...
                  </div>
                ) : (
                  <>
                    <div className="whitespace-pre-wrap">{text}</div>
                    {sources.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {sources
                          .filter((s) => !dismissed.has(`${msg.id}:${s}`))
                          .map((s) => (
                            <button
                              key={s}
                              aria-label={`Dismiss source ${s}`}
                              onClick={() =>
                                setDismissed((d) => new Set(d).add(`${msg.id}:${s}`))
                              }
                              className="inline-flex items-center gap-1 text-[10px] text-on-surface-variant bg-white/5 border border-white/10 rounded-full px-2 py-0.5 hover:bg-white/10"
                            >
                              {s.startsWith("theory:") ? `theory · ${s.slice(7)}` : s}
                              <span className="material-symbols-outlined text-[11px]">close</span>
                            </button>
                          ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}

        {/* Transient tool-status pill */}
        {isStreaming && activeTool && activeTool.phase === "start" && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-1.5 text-[11px] text-on-surface-variant bg-white/5 border border-white/10 rounded-full px-3 py-1">
              <span className="material-symbols-outlined text-[13px] animate-spin">progress_activity</span>
              Using {activeTool.name}…
            </div>
          </div>
        )}
      </div>

      {/* Suggested-prompt pills (only before the first user turn) */}
      {messages.filter((m) => m.role === "user").length === 0 && (
        <div className="px-4 pb-2 flex flex-wrap gap-2 shrink-0">
          {SUGGESTED_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => handleSend(p)}
              disabled={isStreaming}
              className="text-[11px] text-on-surface-variant bg-white/5 border border-white/10 rounded-full px-3 py-1.5 hover:bg-white/10 disabled:opacity-50"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Input Bar */}
      <div className="p-3 border-t border-white/10 shrink-0">
        <div className="flex items-center gap-2 glass-panel rounded-xl px-4 py-2 glow-focus">
          <input
            className="flex-grow bg-transparent border-none text-sm text-on-surface focus:ring-0 focus:outline-none placeholder:text-outline-variant"
            placeholder="Ask about chords, theory, techniques..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={isStreaming}
          />
          <button
            aria-label="send"
            className={`w-9 h-9 rounded-full flex items-center justify-center transition-all shrink-0 ${
              input.trim() && !isStreaming ? "primary-gradient hover:opacity-90" : "bg-white/10"
            }`}
            onClick={() => handleSend()}
            disabled={!input.trim() || isStreaming}
          >
            <span className="material-symbols-outlined text-[18px] text-on-primary-container">
              send
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};
