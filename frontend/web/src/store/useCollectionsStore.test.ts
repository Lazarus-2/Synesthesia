import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../lib/apiClient", () => ({
  apiGet: vi.fn(),
  apiPostJson: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
  ApiError: class ApiError extends Error {},
}));
vi.mock("./useToastStore", () => ({
  useToastStore: { getState: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) },
}));

import { useCollectionsStore } from "./useCollectionsStore";
import { apiGet, apiPostJson, apiPut, apiDelete } from "../lib/apiClient";

beforeEach(() => {
  useCollectionsStore.setState({ items: [], loading: false, loaded: false });
  vi.clearAllMocks();
});

describe("useCollectionsStore", () => {
  it("fetchAll loads items", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [{ id: "1", name: "A", kind: "collection", description: null, song_count: 0, created_at: "" }] });
    await useCollectionsStore.getState().fetchAll();
    expect(useCollectionsStore.getState().items).toHaveLength(1);
    expect(useCollectionsStore.getState().loaded).toBe(true);
  });
  it("create posts and refetches, returns id", async () => {
    (apiPostJson as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "new" });
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [] });
    const id = await useCollectionsStore.getState().create("My set", "setlist", ["j1"]);
    expect(id).toBe("new");
    expect(apiPostJson).toHaveBeenCalledWith("/collections", { name: "My set", kind: "setlist", song_ids: ["j1"] });
  });
  it("rename updates item in place", async () => {
    useCollectionsStore.setState({ items: [{ id: "1", name: "old", kind: "collection", description: null, song_count: 0, created_at: "" }] });
    (apiPut as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await useCollectionsStore.getState().rename("1", "new");
    expect(useCollectionsStore.getState().items[0].name).toBe("new");
  });
  it("remove deletes item", async () => {
    useCollectionsStore.setState({ items: [{ id: "1", name: "x", kind: "collection", description: null, song_count: 0, created_at: "" }] });
    (apiDelete as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await useCollectionsStore.getState().remove("1");
    expect(useCollectionsStore.getState().items).toHaveLength(0);
  });
  it("addSong increments song_count", async () => {
    useCollectionsStore.setState({ items: [{ id: "1", name: "x", kind: "collection", description: null, song_count: 0, created_at: "" }] });
    (apiPostJson as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await useCollectionsStore.getState().addSong("1", "j1");
    expect(useCollectionsStore.getState().items[0].song_count).toBe(1);
  });
  it("reorder returns true and PUTs song_ids", async () => {
    (apiPut as ReturnType<typeof vi.fn>).mockResolvedValue({});
    const ok = await useCollectionsStore.getState().reorder("1", ["j2", "j1"]);
    expect(ok).toBe(true);
    expect(apiPut).toHaveBeenCalledWith("/collections/1", { song_ids: ["j2", "j1"] });
  });
  it("removeSong returns true and decrements song_count", async () => {
    useCollectionsStore.setState({ items: [{ id: "1", name: "x", kind: "collection", description: null, song_count: 2, created_at: "" }] });
    (apiDelete as ReturnType<typeof vi.fn>).mockResolvedValue({});
    const ok = await useCollectionsStore.getState().removeSong("1", "j1");
    expect(ok).toBe(true);
    expect(useCollectionsStore.getState().items[0].song_count).toBe(1);
  });
  it("rename returns false and leaves name unchanged when the API rejects", async () => {
    useCollectionsStore.setState({ items: [{ id: "1", name: "old", kind: "collection", description: null, song_count: 0, created_at: "" }] });
    (apiPut as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    const ok = await useCollectionsStore.getState().rename("1", "new");
    expect(ok).toBe(false);
    expect(useCollectionsStore.getState().items[0].name).toBe("old");
  });
});
