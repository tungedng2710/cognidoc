import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import type { Revision } from "../types";
import { UploadDialog } from "./UploadDialog";

describe("UploadDialog", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("offers individual file and folder selection", async () => {
    const revision = {} as Revision;
    const uploadFiles = vi.spyOn(api, "uploadFiles").mockResolvedValue(revision);
    const onComplete = vi.fn();
    render(
      <UploadDialog
        dataset="plates"
        namespace="owner"
        onClose={vi.fn()}
        onComplete={onComplete}
        open
      />,
    );

    const fileInput = screen.getByLabelText("Choose files");
    const folderInput = screen.getByLabelText("Choose folder");
    expect(fileInput).not.toHaveAttribute("webkitdirectory");
    expect(folderInput).toHaveAttribute("webkitdirectory");

    const readme = new File(["# Dataset"], "README.md", {
      type: "text/markdown",
    });
    const parquet = new File(["PAR1"], "train.parquet");
    fireEvent.change(fileInput, {
      target: { files: [readme, parquet] },
    });

    expect(screen.getByText("2 files selected")).toBeInTheDocument();
    expect(screen.getByText(/· repository root$/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Upload and publish" }));

    await vi.waitFor(() => {
      expect(uploadFiles).toHaveBeenCalledWith(
        "owner",
        "plates",
        [readme, parquet],
        expect.any(Function),
        expect.any(AbortSignal),
      );
    });
    expect(onComplete).toHaveBeenCalledWith(revision);
  });
});
