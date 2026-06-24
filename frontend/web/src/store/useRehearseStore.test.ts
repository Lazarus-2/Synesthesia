import { describe, it, expect, beforeEach } from "vitest";
import { useRehearseStore } from "./useRehearseStore";

beforeEach(() => {
  useRehearseStore.setState({ active: false, queue: [], index: 0 });
});

describe("useRehearseStore", () => {
  it("start sets active + queue and seeds index to 0", () => {
    useRehearseStore.getState().start(["a", "b", "c"]);
    const s = useRehearseStore.getState();
    expect(s.active).toBe(true);
    expect(s.queue).toEqual(["a", "b", "c"]);
    expect(s.index).toBe(0);
    expect(useRehearseStore.getState().current()).toBe("a");
  });

  it("start is a no-op on an empty list", () => {
    useRehearseStore.getState().start([]);
    expect(useRehearseStore.getState().active).toBe(false);
    expect(useRehearseStore.getState().queue).toEqual([]);
  });

  it("next advances and returns the new current id", () => {
    useRehearseStore.getState().start(["a", "b", "c"]);
    expect(useRehearseStore.getState().next()).toBe("b");
    expect(useRehearseStore.getState().index).toBe(1);
    expect(useRehearseStore.getState().current()).toBe("b");
    expect(useRehearseStore.getState().next()).toBe("c");
    expect(useRehearseStore.getState().index).toBe(2);
  });

  it("next past the end returns null and deactivates", () => {
    useRehearseStore.getState().start(["a", "b"]);
    expect(useRehearseStore.getState().next()).toBe("b");
    expect(useRehearseStore.getState().next()).toBeNull();
    const s = useRehearseStore.getState();
    expect(s.active).toBe(false);
    expect(s.queue).toEqual([]);
    expect(s.index).toBe(0);
  });

  it("stop resets active, queue and index", () => {
    useRehearseStore.getState().start(["a", "b"]);
    useRehearseStore.getState().next();
    useRehearseStore.getState().stop();
    const s = useRehearseStore.getState();
    expect(s.active).toBe(false);
    expect(s.queue).toEqual([]);
    expect(s.index).toBe(0);
    expect(useRehearseStore.getState().current()).toBeNull();
  });

  it("current is null when inactive", () => {
    expect(useRehearseStore.getState().current()).toBeNull();
  });
});
