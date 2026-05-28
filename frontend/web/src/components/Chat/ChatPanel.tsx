"use client";

import React, { useState, useRef, useEffect } from "react";
import { useChatStore } from "../../store/useChatStore";

export const ChatPanel: React.FC = () => {
  const { messages, isStreaming, sendMessage } = useChatStore();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim());
    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      {/* Chat Header */}
      <div className="p-4 border-b border-white/10 bg-white/5 shrink-0">
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
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-grow overflow-y-auto hide-scrollbar p-4 space-y-4"
      >
        {messages.map((msg) => (
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
                <div className="whitespace-pre-wrap">{msg.content}</div>
              )}
            </div>
          </div>
        ))}
      </div>

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
            className={`w-9 h-9 rounded-full flex items-center justify-center transition-all shrink-0 ${
              input.trim() && !isStreaming
                ? "primary-gradient hover:opacity-90"
                : "bg-white/10"
            }`}
            onClick={handleSend}
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
