import { create } from 'zustand';
import { ChatMessage } from '../types';
import { API_V1, consumeSse, ApiError } from '../lib/apiClient';

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;

  addMessage: (msg: ChatMessage) => void;
  updateLastMessage: (contentChunk: string) => void;
  clearChat: () => void;
  sendMessage: (content: string, analysisId?: string) => Promise<void>;
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

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  updateLastMessage: (contentChunk) =>
    set((state) => {
      const newMessages = [...state.messages];
      if (newMessages.length > 0) {
        newMessages[newMessages.length - 1].content += contentChunk;
      }
      return { messages: newMessages };
    }),

  clearChat: () => set({ messages: [{ ...WELCOME, timestamp: new Date() }] }),

  sendMessage: async (content: string) => {
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    };
    get().addMessage(userMsg);
    set({ isStreaming: true });

    const asstMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };
    get().addMessage(asstMsg);

    try {
      const allMessages = get().messages;
      const historyMessages = allMessages
        .filter((m) => m.id !== 'welcome' && m.id !== userMsg.id && m.id !== asstMsg.id)
        .map((m) => ({ role: m.role, content: m.content }));

      // POST + SSE: EventSource is GET-only, so we hand-consume the stream.
      // The apiClient's consumeSse handles the new D6 tagged-event format and
      // the legacy `data: {chunk}` / `data: [DONE]` shapes.
      const response = await fetch(`${API_V1}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ message: content, history: historyMessages }),
      });
      if (!response.ok) {
        let payload: unknown = undefined;
        try { payload = await response.json(); } catch { /* no body */ }
        throw new ApiError(response.status, (payload as { code: string; message: string }) || `HTTP ${response.status}`);
      }
      if (!response.body) throw new Error('No SSE body returned');

      await consumeSse<{ text: string }, { reply_length?: number }>(
        response.body,
        {
          onChunk: (data) => {
            const text = typeof data === 'string' ? data : data?.text;
            if (text) get().updateLastMessage(text);
          },
          onDone: () => { /* final flush handled by stream close */ },
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
      set({ isStreaming: false });
    }
  },
}));
