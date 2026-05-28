import { create } from 'zustand';
import { SongAnalysis, InstrumentGuide } from '../types';

export type JobStatus = 'idle' | 'queued' | 'processing' | 'done' | 'error';

interface ProgressData {
  status: JobStatus;
  progress?: number;
  message?: string;
}

interface AnalysisState {
  jobId: string | null;
  setJobId: (id: string | null) => void;
  
  jobStatus: JobStatus;
  jobProgress: number;
  jobMessage: string;
  setJobStatus: (status: JobStatus, progress?: number, message?: string) => void;
  
  analysis: SongAnalysis | null;
  instrumentGuide: InstrumentGuide | null;
  setAnalysis: (analysis: SongAnalysis | null) => void;
  
  // Method to start listening to SSE
  startProgressStream: (jobId: string) => void;
  stopProgressStream: () => void;
}

// Keep a reference to the active EventSource so we can close it
let activeEventSource: EventSource | null = null;

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  jobId: null,
  setJobId: (id) => set({ jobId: id }),
  
  jobStatus: 'idle',
  jobProgress: 0,
  jobMessage: '',
  setJobStatus: (status, progress = 0, message = '') => set({ jobStatus: status, jobProgress: progress, jobMessage: message }),
  
  analysis: null,
  instrumentGuide: null,
  setAnalysis: (analysis) => set({ analysis }),
  
  startProgressStream: (jobId) => {
    // Stop any existing stream
    get().stopProgressStream();
    
    set({ jobId, jobStatus: 'queued', jobProgress: 0, jobMessage: 'Connecting...' });
    
    // Create new SSE connection
    activeEventSource = new EventSource(`http://localhost:8000/jobs/${jobId}/progress`);
    
    activeEventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.status === 'done') {
          set({ 
            jobStatus: 'done', 
            jobProgress: 100, 
            jobMessage: 'Analysis Complete!',
            analysis: data.analysis,
            instrumentGuide: data.instrument_guide || null
          });
          get().stopProgressStream();
        } else if (data.status === 'error') {
          set({ 
            jobStatus: 'error', 
            jobMessage: data.error || 'An error occurred during analysis.' 
          });
          get().stopProgressStream();
        } else {
          set({
            jobStatus: data.status,
            jobProgress: data.progress || 0,
            jobMessage: data.message || `Status: ${data.status}`
          });
        }
      } catch (e) {
        console.error("Failed to parse SSE message", e);
      }
    };
    
    activeEventSource.onerror = (error) => {
      console.error("SSE connection error", error);
      set({ jobStatus: 'error', jobMessage: 'Lost connection to analysis server.' });
      get().stopProgressStream();
    };
  },
  
  stopProgressStream: () => {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }
  }
}));
