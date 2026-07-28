import { CheckCircle2, FolderUp, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { UploadProgress } from "../api";
import type { Revision } from "../types";

interface UploadDialogProps {
  namespace: string;
  dataset: string;
  open: boolean;
  onClose: () => void;
  onComplete: (revision: Revision) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = "B";
  for (const candidate of units) {
    value /= 1024;
    unit = candidate;
    if (value < 1024) break;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
}

export function UploadDialog({
  namespace,
  dataset,
  open,
  onClose,
  onComplete,
}: UploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState("");
  const totalBytes = useMemo(() => files.reduce((total, file) => total + file.size, 0), [files]);

  useEffect(() => {
    if (!open) return;
    setFiles([]);
    setProgress(null);
    setError("");
    inputRef.current?.setAttribute("webkitdirectory", "");
    inputRef.current?.setAttribute("directory", "");
  }, [open]);

  if (!open) return null;

  const close = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    onClose();
  };

  const upload = async () => {
    if (!files.length || progress) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setError("");
    try {
      const nextRevision = await api.uploadFolder(
        namespace,
        dataset,
        files,
        setProgress,
        controller.signal,
      );
      setProgress((current) => current ? { ...current, message: "Dataset is ready" } : current);
      abortRef.current = null;
      onComplete(nextRevision);
    } catch (caught) {
      abortRef.current = null;
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "The upload could not be completed.");
      setProgress(null);
    }
  };

  const percent = progress
    ? progress.phase === "publishing"
      ? 100
      : progress.totalBytes > 0
        ? Math.round((progress.uploadedBytes / progress.totalBytes) * 100)
        : Math.round((progress.uploadedFiles / Math.max(progress.totalFiles, 1)) * 100)
    : 0;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/65 p-4 backdrop-blur-sm">
      <section
        className="modal-panel max-h-[calc(100vh-2rem)] max-w-xl overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-title"
      >
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="eyebrow">New immutable revision</p>
            <h2 id="upload-title" className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
              Upload a dataset folder
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Source paths, cards, data shards, and media are preserved. Large repositories upload in
              safe batches with no dataset-size limit in the Studio.
            </p>
          </div>
          <button className="icon-button" type="button" onClick={close} aria-label="Close upload">
            <X className="size-4" />
          </button>
        </div>

        <label className={`mt-5 flex min-h-40 flex-col items-center justify-center rounded-2xl border border-dashed px-5 text-center transition ${progress ? "cursor-not-allowed border-slate-200 bg-slate-50" : "cursor-pointer border-indigo-300 bg-gradient-to-br from-indigo-50/80 to-cyan-50/70 hover:border-indigo-400 hover:from-indigo-50"}`}>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            multiple
            disabled={Boolean(progress)}
            onChange={(event) => {
              setFiles(Array.from(event.target.files ?? []));
              setError("");
            }}
          />
          <span className="grid size-12 place-items-center rounded-2xl bg-white text-indigo-600 shadow-sm ring-1 ring-indigo-100">
            {files.length ? <CheckCircle2 className="size-6" /> : <FolderUp className="size-6" />}
          </span>
          <span className="mt-4 font-semibold text-slate-900">
            {files.length ? `${files.length.toLocaleString()} files selected` : "Choose repository folder"}
          </span>
          <span className="mt-1 text-xs text-slate-500">
            {files.length ? formatBytes(totalBytes) : "Parquet, CSV, TSV, JSON, JSONL, TXT, and ImageFolder"}
          </span>
        </label>

        {progress ? (
          <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4">
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="flex min-w-0 items-center gap-2 font-medium text-indigo-950">
                <LoaderCircle className="size-4 shrink-0 animate-spin text-indigo-600" />
                <span className="truncate">{progress.message}</span>
              </span>
              <span className="font-mono text-xs font-semibold text-indigo-700">{percent}%</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-indigo-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-cyan-500 transition-[width] duration-300"
                style={{ width: `${Math.max(percent, progress.phase === "preparing" ? 3 : 0)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-indigo-700/80">
              {progress.uploadedFiles.toLocaleString()} / {progress.totalFiles.toLocaleString()} files
              {progress.totalBytes ? ` · ${formatBytes(progress.uploadedBytes)} / ${formatBytes(progress.totalBytes)}` : ""}
            </p>
          </div>
        ) : null}
        {error ? <p className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <button className="button-secondary" type="button" onClick={close}>
            {progress ? "Cancel upload" : "Cancel"}
          </button>
          <button
            className="button-primary"
            type="button"
            disabled={!files.length || Boolean(progress)}
            onClick={() => void upload()}
          >
            <UploadCloud className="size-4" /> Upload and publish
          </button>
        </div>
      </section>
    </div>
  );
}
