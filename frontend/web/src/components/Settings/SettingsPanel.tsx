"use client";

import React from "react";
import { useAppStore } from "../../store/useAppStore";

const LLM_PROVIDERS = [
  { id: "local", label: "Local (Ollama)", icon: "computer", desc: "Runs on your machine — fast, private" },
  { id: "openai", label: "OpenAI", icon: "cloud", desc: "GPT-4.1 / GPT-4.1 mini" },
  { id: "anthropic", label: "Anthropic", icon: "psychology", desc: "Claude Sonnet 4 / Claude Opus 4" },
];

export const SettingsPanel: React.FC = () => {
  const { llmProvider, setLlmProvider } = useAppStore();

  return (
    <div className="flex flex-col gap-6 p-6 overflow-y-auto hide-scrollbar flex-grow">
      <h2 className="font-headline text-2xl font-medium text-white">Settings</h2>

      {/* LLM Provider Selection */}
      <div>
        <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-4">
          AI Engine
        </h3>
        <div className="flex flex-col gap-3">
          {LLM_PROVIDERS.map((prov) => (
            <button
              key={prov.id}
              className={`w-full flex items-center gap-4 p-4 rounded-xl border transition-all text-left ${
                llmProvider === prov.id
                  ? "bg-secondary-container/15 border-secondary-container/40 glow-violet"
                  : "glass-panel hover:border-primary/30"
              }`}
              onClick={() => setLlmProvider(prov.id as "local" | "openai" | "anthropic")}
            >
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  llmProvider === prov.id
                    ? "bg-secondary-container/20"
                    : "bg-white/5"
                }`}
              >
                <span
                  className={`material-symbols-outlined text-xl ${
                    llmProvider === prov.id
                      ? "text-on-secondary-container"
                      : "text-on-surface-variant"
                  }`}
                >
                  {prov.icon}
                </span>
              </div>
              <div>
                <p className="text-sm font-semibold text-on-surface">{prov.label}</p>
                <p className="text-xs text-on-surface-variant mt-0.5">{prov.desc}</p>
              </div>
              {llmProvider === prov.id && (
                <span className="material-symbols-outlined text-secondary-container ml-auto" style={{ fontVariationSettings: "'FILL' 1" }}>
                  check_circle
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* System Info */}
      <div className="mt-6 glass-panel rounded-xl p-4">
        <h3 className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest mb-3">
          System Status
        </h3>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-sm text-on-surface">All Systems Normal</span>
        </div>
      </div>
    </div>
  );
};
