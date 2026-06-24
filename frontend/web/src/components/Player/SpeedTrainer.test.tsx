import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SpeedTrainer } from "./SpeedTrainer";
import { useSpeedTrainerStore } from "../../store/useSpeedTrainerStore";
import { usePracticeStore } from "../../store/usePracticeStore";

beforeEach(() => {
  useSpeedTrainerStore.setState({
    enabled: false,
    startPct: 60,
    targetPct: 100,
    stepPct: 5,
    loopsPerStep: 2,
    currentPass: 0,
    currentPct: 60,
  });
  usePracticeStore.setState({ loopStart: null, loopEnd: null });
});

describe("SpeedTrainer", () => {
  it("disables the On/Off toggle when no loop is set", () => {
    usePracticeStore.setState({ loopStart: null, loopEnd: null });
    render(<SpeedTrainer />);
    const toggle = screen.getByRole("button", { name: "Off" });
    expect(toggle).toBeDisabled();
  });

  it("enables the toggle with a valid loop; clicking flips enabled and shows the pass readout", async () => {
    const user = userEvent.setup();
    usePracticeStore.setState({ loopStart: 10, loopEnd: 20 });
    render(<SpeedTrainer />);

    const toggle = screen.getByRole("button", { name: "Off" });
    expect(toggle).toBeEnabled();

    await user.click(toggle);

    expect(useSpeedTrainerStore.getState().enabled).toBe(true);
    // The "Pass …%→…%" readout (currentPct → targetPct) now renders.
    expect(screen.getByText(/60% → 100%/)).toBeInTheDocument();
    expect(screen.getByText(/Pass 0/)).toBeInTheDocument();
  });

  it("updates startPct in the store when the Start % input changes", async () => {
    const user = userEvent.setup();
    usePracticeStore.setState({ loopStart: 10, loopEnd: 20 });
    render(<SpeedTrainer />);

    const startInput = screen.getByLabelText("Start %");
    await user.clear(startInput);
    await user.type(startInput, "75");

    expect(useSpeedTrainerStore.getState().startPct).toBe(75);
  });
});
