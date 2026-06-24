import { create } from "zustand";
import { apiGet, apiPostJson, apiPut, apiDelete, ApiError } from "../lib/apiClient";
import { useToastStore } from "./useToastStore";
import type { CollectionSummary, CollectionKind } from "../types";

interface CollectionsState {
  items: CollectionSummary[];
  loading: boolean;
  loaded: boolean;
  fetchAll: () => Promise<void>;
  create: (name: string, kind: CollectionKind, songIds?: string[]) => Promise<string | null>;
  rename: (id: string, name: string) => Promise<boolean>;
  remove: (id: string) => Promise<void>;
  addSong: (id: string, jobId: string) => Promise<void>;
  removeSong: (id: string, jobId: string) => Promise<boolean>;
  reorder: (id: string, songIds: string[]) => Promise<boolean>;
}

function msg(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

export const useCollectionsStore = create<CollectionsState>((set, get) => ({
  items: [],
  loading: false,
  loaded: false,
  fetchAll: async () => {
    set({ loading: true });
    try {
      const r = await apiGet<{ items: CollectionSummary[] }>("/collections?limit=100");
      set({ items: r.items, loading: false, loaded: true });
    } catch (e) {
      set({ loading: false });
      useToastStore.getState().error("Could not load collections", msg(e, "Please try again."));
    }
  },
  create: async (name, kind, songIds) => {
    try {
      const r = await apiPostJson<{ id: string }>("/collections", { name, kind, song_ids: songIds ?? [] });
      await get().fetchAll();
      useToastStore.getState().success(kind === "setlist" ? "Setlist created" : "Collection created", name);
      return r.id;
    } catch (e) {
      useToastStore.getState().error("Could not create", msg(e, "Please try again."));
      return null;
    }
  },
  rename: async (id, name) => {
    try {
      await apiPut(`/collections/${encodeURIComponent(id)}`, { name });
      set({ items: get().items.map((c) => (c.id === id ? { ...c, name } : c)) });
      return true;
    } catch (e) {
      useToastStore.getState().error("Could not rename", msg(e, "Please try again."));
      return false;
    }
  },
  remove: async (id) => {
    try {
      await apiDelete(`/collections/${encodeURIComponent(id)}`);
      set({ items: get().items.filter((c) => c.id !== id) });
      useToastStore.getState().success("Deleted", "");
    } catch (e) {
      useToastStore.getState().error("Could not delete", msg(e, "Please try again."));
    }
  },
  addSong: async (id, jobId) => {
    try {
      await apiPostJson(`/collections/${encodeURIComponent(id)}/songs`, { job_id: jobId });
      set({ items: get().items.map((c) => (c.id === id ? { ...c, song_count: c.song_count + 1 } : c)) });
      useToastStore.getState().success("Added to collection", "");
    } catch (e) {
      useToastStore.getState().error("Could not add", msg(e, "Please try again."));
    }
  },
  removeSong: async (id, jobId) => {
    try {
      await apiDelete(`/collections/${encodeURIComponent(id)}/songs/${encodeURIComponent(jobId)}`);
      set({ items: get().items.map((c) => (c.id === id ? { ...c, song_count: Math.max(0, c.song_count - 1) } : c)) });
      return true;
    } catch (e) {
      useToastStore.getState().error("Could not remove", msg(e, "Please try again."));
      return false;
    }
  },
  reorder: async (id, songIds) => {
    try {
      await apiPut(`/collections/${encodeURIComponent(id)}`, { song_ids: songIds });
      return true;
    } catch (e) {
      useToastStore.getState().error("Could not reorder", msg(e, "Please try again."));
      return false;
    }
  },
}));
