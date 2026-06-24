import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../lib/apiClient", () => ({
  apiGet: vi.fn(),
  openProgressStream: vi.fn(),
  API_V1: "http://api.test/api/v1",
  ApiError: class ApiError extends Error {},
}));

// usePlayerStore is imported at module scope by useAnalysisStore; mock it so we
// can observe setAudioFileUrl and read back the resulting url.
let _audioFileUrl: string | null = null;
vi.mock("./usePlayerStore", () => ({
  usePlayerStore: {
    getState: () => ({
      audioFileUrl: _audioFileUrl,
      setAudioFileUrl: (url: string | null) => {
        _audioFileUrl = url;
      },
    }),
  },
}));

const errorMock = vi.fn();
vi.mock("./useToastStore", () => ({
  useToastStore: {
    getState: () => ({ success: vi.fn(), error: errorMock, info: vi.fn() }),
  },
}));

import { useAnalysisStore } from "./useAnalysisStore";
import { apiGet } from "../lib/apiClient";

beforeEach(() => {
  _audioFileUrl = null;
  useAnalysisStore.setState({
    jobId: null,
    analysis: null,
    instrumentGuide: null,
    instrument: "guitar",
    jobStatus: "idle",
    jobProgress: 0,
    jobMessage: "",
  });
  vi.clearAllMocks();
});

describe("useAnalysisStore.loadExisting", () => {
  it("loads analysis + audio on success", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "job1",
      status: "done",
      analysis: { key: "C major", tempo: 120 },
      instrument_guide: { instrument: "piano" },
    });

    await useAnalysisStore.getState().loadExisting("job1");

    const s = useAnalysisStore.getState();
    expect(s.analysis).toEqual({ key: "C major", tempo: 120 });
    expect(s.jobId).toBe("job1");
    expect(s.jobStatus).toBe("done");
    expect(s.instrument).toBe("piano");
    expect(s.instrumentGuide).toEqual({ instrument: "piano" });
    expect(_audioFileUrl).toMatch(/\/audio\/job1$/);
    expect(errorMock).not.toHaveBeenCalled();
  });

  it("defaults instrument to guitar when no guide present", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "job2",
      status: "done",
      analysis: { key: "A minor", tempo: 90 },
    });

    await useAnalysisStore.getState().loadExisting("job2");

    const s = useAnalysisStore.getState();
    expect(s.instrument).toBe("guitar");
    expect(s.instrumentGuide).toBeNull();
    expect(_audioFileUrl).toMatch(/\/audio\/job2$/);
  });

  it("leaves state unchanged and toasts on failure", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));

    await useAnalysisStore.getState().loadExisting("job3");

    const s = useAnalysisStore.getState();
    expect(s.analysis).toBeNull();
    expect(s.jobStatus).toBe("idle");
    expect(_audioFileUrl).toBeNull();
    expect(errorMock).toHaveBeenCalledTimes(1);
  });

  it("treats a missing analysis in the response as a failure", async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue({
      job_id: "job4",
      status: "done",
    });

    await useAnalysisStore.getState().loadExisting("job4");

    const s = useAnalysisStore.getState();
    expect(s.analysis).toBeNull();
    expect(s.jobStatus).toBe("idle");
    expect(errorMock).toHaveBeenCalledTimes(1);
  });
});
