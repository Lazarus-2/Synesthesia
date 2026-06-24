import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlayAlongPresets } from "./PlayAlongPresets";
import { usePlayAlongStore } from "../../store/usePlayAlongStore";
import { useAppStore } from "../../store/useAppStore";
import type { StemId } from "../../lib/practice";

const ALL_STEMS: StemId[] = ["vocals", "drums", "bass", "other"];

beforeEach(() => {
  usePlayAlongStore.setState({ engaged: false, mutedStem: null });
  useAppStore.setState({ instrument: "guitar" });
});

describe("PlayAlongPresets", () => {
  it("renders nothing when there are no available stems", () => {
    const { container } = render(<PlayAlongPresets availableStems={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a Mute button per stem and highlights the suggested stem", () => {
    render(<PlayAlongPresets availableStems={ALL_STEMS} />);

    for (const label of ["Vocals", "Drums", "Bass", "Melodics"]) {
      expect(screen.getByRole("button", { name: `Mute ${label}` })).toBeInTheDocument();
    }

    // guitar -> "other" -> "Melodics" gets the ring highlight when not engaged.
    const suggested = screen.getByRole("button", { name: "Mute Melodics" });
    expect(suggested.className).toMatch(/ring-1/);

    // A non-suggested stem should not carry the ring.
    const vocals = screen.getByRole("button", { name: "Mute Vocals" });
    expect(vocals.className).not.toMatch(/ring-1/);
  });

  it("engages play-along on click and disengages on a second click", async () => {
    const user = userEvent.setup();
    render(<PlayAlongPresets availableStems={ALL_STEMS} />);

    const vocals = screen.getByRole("button", { name: "Mute Vocals" });
    await user.click(vocals);

    expect(usePlayAlongStore.getState().engaged).toBe(true);
    expect(usePlayAlongStore.getState().mutedStem).toBe("vocals");

    await user.click(screen.getByRole("button", { name: "Mute Vocals" }));
    expect(usePlayAlongStore.getState().engaged).toBe(false);
    expect(usePlayAlongStore.getState().mutedStem).toBeNull();
  });
});
