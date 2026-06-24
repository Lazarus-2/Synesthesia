import { describe, it, expect, beforeEach } from "vitest";
import { useSavedLoopsStore } from "./useSavedLoopsStore";

beforeEach(() => {
  localStorage.clear();
  useSavedLoopsStore.setState({ loops: {} });
});

describe("useSavedLoopsStore", () => {
  it("saves and lists loops for a jobId", () => {
    useSavedLoopsStore.getState().save("job1", "Solo", 10, 20);
    const list = useSavedLoopsStore.getState().list("job1");
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ name: "Solo", start: 10, end: 20 });
    expect(list[0].id).toBeTruthy();
  });

  it("removes a loop by id", () => {
    useSavedLoopsStore.getState().save("job1", "Solo", 10, 20);
    const id = useSavedLoopsStore.getState().list("job1")[0].id;
    useSavedLoopsStore.getState().remove("job1", id);
    expect(useSavedLoopsStore.getState().list("job1")).toHaveLength(0);
  });

  it("persists to localStorage under the synesthesia.savedLoops key", () => {
    useSavedLoopsStore.getState().save("job1", "Solo", 10, 20);
    expect(localStorage.getItem("synesthesia.savedLoops")).toContain("Solo");
  });
});
