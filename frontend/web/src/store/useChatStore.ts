import { create } from 'zustand';
import { ChatMessage } from '../types';
import { API_V1, consumeSse, ApiError } from '../lib/apiClient';
import { getAuthToken } from './useAuthStore';

const SESSION_KEY = 'synesthesia.chat.session';

function readSession(): string | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw) as string; } catch { return null; }
}

function writeSession(id: string | null) {
  if (typeof window === 'undefined') return;
  if (id) window.localStorage.setItem(SESSION_KEY, JSON.stringify(id));
  else window.localStorage.removeItem(SESSION_KEY);
}

export interface ToolStatus { name: string; phase: 'start' | 'end'; }

export interface ChatContext {
  title?: string;
  artist?: string;
  key?: string;
  bpm?: number;
  status?: 'ok' | 'degraded' | 'failed';
}

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  sessionId: string | null;
  tutorMode: boolean;
  activeTool: ToolStatus | null;
  context: ChatContext | null;

  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (contentChunk: string) => void;
  setTutorMode: (on: boolean) => void;
  clearChat: () => void;
  sendMessage: (content: string, analysisJobId?: string) => Promise<void>;
}

const WELCOME: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hi! I'm your Synesthesia AI theory guide. Ask me anything about the song's progression, harmony, or arrangement!",
  timestamp: new Date(),
};

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [WELCOME],
  isStreaming: false,
  sessionId: typeof window === 'undefined' ? null : readSession(),
  tutorMode: false,
  activeTool: null,
  context: null,

  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  updateLastMessage: (contentChunk) =>
    set((state) => {
      const newMessages = [...state.messages];
      if (newMessages.length > 0) {
        newMessages[newMessages.length - 1].content += contentChunk;
      }
      return { messages: newMessages };
    }),

  setTutorMode: (on) => set({ tutorMode: on }),

  clearChat: () => set({ messages: [{ ...WELCOME, timestamp: new Date() }] }),

  sendMessage: async (content: string, analysisJobId?: string) => {
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    };
    get().addMessage(userMsg);
    set({ isStreaming: true, activeTool: null });

    const asstMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };
    get().addMessage(asstMsg);

    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      // Server owns identity (JWT) + history + session. We no longer send
      // history or a client-chosen user_id.
      const response = await fetch(`${API_V1}/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: content,
          analysis_job_id: analysisJobId ?? null,
          session_id: get().sessionId,
          tutor_mode: get().tutorMode,
        }),
      });
      if (!response.ok) {
        let payload: unknown = undefined;
        try { payload = await response.json(); } catch { /* no body */ }
        throw new ApiError(
          response.status,
          (payload as { status: 'error'; code: string; message: string }) || `HTTP ${response.status}`,
        );
      }
      if (!response.body) throw new Error('No SSE body returned');

      await consumeSse<{ text: string }, { session_id?: string }>(
        response.body,
        {
          onContext: (ctx) => set({ context: ctx as ChatContext }),
          onTool: (t) => set({ activeTool: t as ToolStatus }),
          onChunk: (data) => {
            const text = typeof data === 'string' ? data : data?.text;
            if (text) get().updateLastMessage(text);
          },
          onDone: (data) => {
            const sid = data && typeof data === 'object' ? (data as { session_id?: string }).session_id : undefined;
            if (sid) {
              writeSession(sid);
              set({ sessionId: sid });
            }
            set({ activeTool: null });
          },
          onError: (e) => {
            get().updateLastMessage(`\n\n*Error: ${e.message}*`);
          },
          onUnknown: (ev) => console.warn('chat SSE unknown event', ev),
        },
      );
    } catch (error) {
      console.error('Chat streaming error:', error);
      const msg = error instanceof ApiError ? error.message : 'Could not connect to AI assistant.';
      get().updateLastMessage(`\n\n*Error: ${msg}*`);
    } finally {
      set({ isStreaming: false, activeTool: null });
    }
  },
}));
