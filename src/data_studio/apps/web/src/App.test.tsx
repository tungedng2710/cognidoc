import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ items: [] }),
      }),
    );
  });

  it("renders the empty dataset hub state", async () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByText("Your datasets, legible and versioned.")).toBeInTheDocument();
    expect(await screen.findByText("Create your first dataset")).toBeInTheDocument();
  });
});
