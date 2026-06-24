import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SavedLoops } from "./SavedLoops";
import { useSavedLoopsStore } from "../../store/useSavedLoopsStore";
import { useAnalysisStore } from "../../store/useAnalysisStore";
import { usePracticeStore } from "../../store/usePracticeStore";

beforeEach(() => {
  localStorage.clear();
  useSavedLoopsStore.setState({ loops: {} });
  useAnalysisStore.setState({ jobId: null });
  usePracticeStore.setState({ loopStart: null, loopEnd: null });
});

describe("SavedLoops", () => {
  it("renders nothing when there is no jobId", () => {
    useAnalysisStore.setState({ jobId: null });
    const { container } = render(<SavedLoops />);
    expect(container).toBeEmptyDOMElement();
  });

  it("saves a named loop and renders it as a chip", async () => {
    const user = userEvent.setup();
    useAnalysisStore.setState({ jobId: "job-1" });
    usePracticeStore.setState({ loopStart: 10, loopEnd: 20 });
    render(<SavedLoops />);

    const input = screen.getByLabelText("Loop name");
    await user.type(input, "Chorus");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(useSavedLoopsStore.getState().list("job-1")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Chorus" })).toBeInTheDocument();
  });

  it("applies a saved loop to the practice store when its chip is clicked", async () => {
    const user = userEvent.setup();
    useAnalysisStore.setState({ jobId: "job-1" });
    usePracticeStore.setState({ loopStart: 10, loopEnd: 20 });
    useSavedLoopsStore.getState().save("job-1", "Verse", 5, 15);

    // Clear the active loop so we can observe the chip click setting it.
    usePracticeStore.setState({ loopStart: null, loopEnd: null });
    render(<SavedLoops />);

    await user.click(screen.getByRole("button", { name: "Verse" }));

    expect(usePracticeStore.getState().loopStart).toBe(5);
    expect(usePracticeStore.getState().loopEnd).toBe(15);
  });
});
