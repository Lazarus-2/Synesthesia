import { create } from 'zustand';

type Tab = "play" | "theory" | "stems" | "lyrics" | "chat" | "settings";
type Theme = "light" | "dark";
type LlmProvider = "local" | "openai" | "anthropic";

interface AppState {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  
  // Settings
  instrument: string;
  setInstrument: (inst: string) => void;
  difficulty: string;
  setDifficulty: (diff: string) => void;
  
  // LLM Provider
  llmProvider: LlmProvider;
  setLlmProvider: (provider: LlmProvider) => void;
  
  // App-wide error handling
  error: string | null;
  setError: (error: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activeTab: "play",
  setActiveTab: (tab) => set({ activeTab: tab }),
  theme: "dark",
  setTheme: (theme) => set({ theme }),
  
  instrument: "guitar",
  setInstrument: (instrument) => set({ instrument }),
  difficulty: "beginner",
  setDifficulty: (difficulty) => set({ difficulty }),
  
  llmProvider: "local",
  setLlmProvider: (llmProvider) => set({ llmProvider }),
  
  error: null,
  setError: (error) => set({ error }),
}));

