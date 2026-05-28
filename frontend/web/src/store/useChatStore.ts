import { create } from 'zustand';
import { ChatMessage } from '../types';

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  
  // Appends a new message
  addMessage: (msg: ChatMessage) => void;
  
  // Updates the last message (used during streaming)
  updateLastMessage: (contentChunk: string) => void;
  
  // Clear chat
  clearChat: () => void;
  
  // Send message and handle SSE streaming
  sendMessage: (content: string, analysisId?: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [
    {
      id: "welcome",
      role: "assistant",
      content: "Hi! I'm your Synesthesia AI theory guide. Ask me anything about the song's progression, harmony, or arrangement!",
      timestamp: new Date()
    }
  ],
  isStreaming: false,
  
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  
  updateLastMessage: (contentChunk) => set((state) => {
    const newMessages = [...state.messages];
    if (newMessages.length > 0) {
      newMessages[newMessages.length - 1].content += contentChunk;
    }
    return { messages: newMessages };
  }),
  
  clearChat: () => set({ 
    messages: [{
      id: "welcome",
      role: "assistant",
      content: "Hi! I'm your Synesthesia AI theory guide. Ask me anything about the song's progression, harmony, or arrangement!",
      timestamp: new Date()
    }] 
  }),
  
  sendMessage: async (content: string, analysisId?: string) => {
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date()
    };
    
    get().addMessage(userMsg);
    set({ isStreaming: true });
    
    // Create empty assistant message placeholder
    const asstMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };
    get().addMessage(asstMsg);
    
    try {
      // Build history from existing messages (exclude welcome + current user msg)
      const allMessages = get().messages;
      const historyMessages = allMessages
        .filter(m => m.id !== 'welcome' && m.id !== userMsg.id && m.id !== asstMsg.id)
        .map(m => ({ role: m.role, content: m.content }));

      // Backend expects: { message: str, history: list[dict] }
      const payload = {
        message: content,
        history: historyMessages
      };
      
      const response = await fetch('http://localhost:8000/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error("Failed to start chat stream");
      
      // Read the SSE stream manually via body reader since fetch doesn't natively support EventSource for POST
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) throw new Error("No reader available");
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        // SSE messages look like: "data: Hello\n\n"
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') break;
            try {
              // Backend sends: data: {"chunk": "text token"}
              const parsed = JSON.parse(data);
              if (parsed.chunk) {
                get().updateLastMessage(parsed.chunk);
              }
            } catch {
              // Raw text fallback
              get().updateLastMessage(data);
            }
          }
        }
      }
    } catch (error) {
      console.error("Chat streaming error:", error);
      get().updateLastMessage("\n\n*Error: Could not connect to AI assistant.*");
    } finally {
      set({ isStreaming: false });
    }
  }
}));
