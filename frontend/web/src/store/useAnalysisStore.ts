import { create } from 'zustand';
import { SongAnalysis, InstrumentGuide } from '../types';
import { openProgressStream } from '../lib/apiClient';
import { useToastStore } from './useToastStore';

export type JobStatus = 'idle' | 'queued' | 'processing' | 'done' | 'error';

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

  // Open and close the SSE progress stream
  startProgressStream: (jobId: string) => void;
  stopProgressStream: () => void;
}

// Hold a reference to the active EventSource so we can close it on demand
// or when the next stream starts.
let activeEventSource: EventSource | null = null;

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  jobId: null,
  setJobId: (id) => set({ jobId: id }),

  jobStatus: 'idle',
  jobProgress: 0,
  jobMessage: '',
  setJobStatus: (status, progress = 0, message = '') =>
    set({ jobStatus: status, jobProgress: progress, jobMessage: message }),

  analysis: null,
  instrumentGuide: null,
  setAnalysis: (analysis) => set({ analysis }),

  startProgressStream: (jobId) => {
    get().stopProgressStream();
    set({ jobId, jobStatus: 'queued', jobProgress: 0, jobMessage: 'Connecting…' });

    activeEventSource = openProgressStream(jobId, {
      onChunk: (data) => {
        const d = data as {
          status?: JobStatus;
          progress?: number;
          message?: string;
        };
        set({
          jobStatus: (d.status as JobStatus) ?? 'processing',
          jobProgress: d.progress ?? 0,
          jobMessage: d.message ?? '',
        });
      },
      onDone: (data) => {
        const d = data as {
          analysis?: SongAnalysis;
          instrument_guide?: InstrumentGuide | null;
        };
        set({
          jobStatus: 'done',
          jobProgress: 100,
          jobMessage: 'Analysis Complete!',
          analysis: d.analysis ?? null,
          instrumentGuide: d.instrument_guide ?? null,
        });
        get().stopProgressStream();
      },
      onError: (data) => {
        const message = data.message || 'An error occurred during analysis.';
        set({ jobStatus: 'error', jobMessage: message });
        useToastStore.getState().error('Analysis failed', message);
        get().stopProgressStream();
      },
      onUnknown: (ev) => {
        // Diagnostic only — shouldn't fire against the new backend.
        console.warn('SSE unknown event', ev);
      },
    });
  },

  stopProgressStream: () => {
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }
  },
}));
