import { create } from 'zustand';
import type WaveSurfer from 'wavesurfer.js';

interface PlayerState {
  wavesurfer: WaveSurfer | null;
  setWavesurfer: (ws: WaveSurfer | null) => void;
  
  isPlaying: boolean;
  setIsPlaying: (playing: boolean) => void;
  
  currentTime: number;
  setCurrentTime: (time: number) => void;
  
  duration: number;
  setDuration: (duration: number) => void;
  
  volume: number; // 0 to 1
  setVolume: (volume: number) => void;
  
  // Track currently playing audio file URL / object
  audioFileUrl: string | null;
  setAudioFileUrl: (url: string | null) => void;
}

export const usePlayerStore = create<PlayerState>((set, get) => ({
  wavesurfer: null,
  setWavesurfer: (ws) => set({ wavesurfer: ws }),
  
  isPlaying: false,
  setIsPlaying: (playing) => {
    const ws = get().wavesurfer;
    if (ws) {
      if (playing) ws.play(); else ws.pause();
    }
    set({ isPlaying: playing });
  },
  
  currentTime: 0,
  setCurrentTime: (time) => set({ currentTime: time }),
  
  duration: 0,
  setDuration: (duration) => set({ duration }),
  
  volume: 1,
  setVolume: (volume) => {
    const ws = get().wavesurfer;
    if (ws) {
      ws.setVolume(volume);
    }
    set({ volume });
  },
  
  audioFileUrl: null,
  setAudioFileUrl: (url) => set({ audioFileUrl: url }),
}));
