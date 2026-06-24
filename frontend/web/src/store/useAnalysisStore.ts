import { create } from 'zustand';
import { SongAnalysis, InstrumentGuide, AnalyzeResponse } from '../types';
import { apiGet, openProgressStream, API_V1 } from '../lib/apiClient';
import { useToastStore } from './useToastStore';
import { usePlayerStore } from './usePlayerStore';

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

  // Load an already-analyzed song (by job_id) into the full interactive
  // player. Used by Library/Collections links (`/?job=<id>`) so saved songs
  // play back without re-running the pipeline. Fetches the cached analysis,
  // wires the player audio URL, and on failure toasts + leaves state untouched
  // (so the caller can fall back to the upload screen).
  loadExisting: (jobId: string) => Promise<void>;

  // Active instrument (guitar | piano | ukulele | bass). Lets the user switch
  // instruments in the player without re-running the whole analysis — the
  // backend recomputes just the instrument guide for the cached song.
  instrument: string;
  instrumentLoading: boolean;
  switchInstrument: (instrument: string) => Promise<void>;

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

  loadExisting: async (jobId) => {
    set({ jobId, jobStatus: 'processing', jobProgress: 0, jobMessage: 'Loading song…' });
    try {
      const resp = await apiGet<AnalyzeResponse>(
        `/analyze/${encodeURIComponent(jobId)}`
      );
      if (!resp.analysis) {
        throw new Error('No analysis available for this song.');
      }
      set({
        jobId,
        analysis: resp.analysis,
        instrumentGuide: resp.instrument_guide ?? null,
        instrument: resp.instrument_guide?.instrument || 'guitar',
        jobStatus: 'done',
        jobProgress: 100,
        jobMessage: 'Analysis Complete!',
      });
      // Wire the player to the backend-served audio (mirrors onDone).
      usePlayerStore
        .getState()
        .setAudioFileUrl(`${API_V1}/audio/${encodeURIComponent(jobId)}`);
    } catch (e) {
      // Leave analysis/jobId state effectively unloaded so the caller can fall
      // back to the upload screen — reset to idle and surface the error.
      set({ jobStatus: 'idle', jobProgress: 0, jobMessage: '' });
      useToastStore.getState().error(
        'Could not open song',
        e instanceof Error ? e.message : 'Please try again.'
      );
    }
  },

  instrument: 'guitar',
  instrumentLoading: false,
  switchInstrument: async (instrument) => {
    const jid = get().jobId;
    if (!jid || instrument === get().instrument) {
      set({ instrument });
      return;
    }
    set({ instrument, instrumentLoading: true }); // optimistic switch
    try {
      const resp = await apiGet<AnalyzeResponse>(
        `/analyze/${encodeURIComponent(jid)}?instrument=${encodeURIComponent(instrument)}`
      );
      set({
        instrumentGuide: resp.instrument_guide ?? null,
        instrument: resp.instrument_guide?.instrument || instrument,
        instrumentLoading: false,
      });
    } catch (e) {
      set({ instrumentLoading: false });
      useToastStore.getState().error(
        'Could not load instrument',
        e instanceof Error ? e.message : 'Please try again.'
      );
    }
  },

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
          instrument: d.instrument_guide?.instrument || 'guitar',
        });
        // Wire the player to the backend-served audio so YouTube/search
        // analyses actually play (the file lives at /audio/{jobId}). Uploads
        // already set a local blob URL in submitAnalyze — don't clobber it.
        const player = usePlayerStore.getState();
        const jid = get().jobId;
        if (!player.audioFileUrl && jid) {
          player.setAudioFileUrl(`${API_V1}/audio/${jid}`);
        }
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
