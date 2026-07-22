import { FolderUp, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Revision } from "../types";

interface UploadDialogProps {
  namespace: string;
  dataset: string;
  open: boolean;
  onClose: () => void;
  onComplete: (revision: Revision) => void;
}

export function UploadDialog({
  namespace,
  dataset,
  open,
  onClose,
  onComplete,
}: UploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    inputRef.current?.setAttribute("webkitdirectory", "");
    inputRef.current?.setAttribute("directory", "");
  }, [open]);

  if (!open) return null;

  const upload = async () => {
    if (!files.length) return;
    setError("");
    try {
      const revision = await api.uploadFolder(namespace, dataset, files, setStatus);
      setStatus("Dataset is ready");
      onComplete(revision);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The upload could not be completed.");
      setStatus("");
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4 backdrop-blur-sm">
      <section
        className="w-full max-w-xl rounded-[2rem] bg-[#fffefa] p-7 shadow-2xl shadow-slate-950/20"
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
              Keep your Hugging Face repository exactly as it is—README, data shards, and media paths
              are preserved.
            </p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close upload">
            <X className="size-4" />
          </button>
        </div>

        <label className="mt-6 flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-teal-800/30 bg-teal-50/60 px-6 text-center transition hover:border-teal-700 hover:bg-teal-50">
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
          <span className="grid size-12 place-items-center rounded-2xl bg-white text-teal-800 shadow-sm">
            <FolderUp className="size-6" />
          </span>
          <span className="mt-4 font-semibold text-slate-900">
            {files.length ? `${files.length.toLocaleString()} files selected` : "Choose repository folder"}
          </span>
          <span className="mt-1 text-xs text-slate-500">
            Parquet, CSV, TSV, JSON, JSONL, TXT, and ImageFolder
          </span>
        </label>

        {status ? (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-950">
            <LoaderCircle className="size-4 animate-spin" /> {status}
          </div>
        ) : null}
        {error ? <p className="mt-4 text-sm font-medium text-rose-700">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <button className="button-secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button-primary"
            type="button"
            disabled={!files.length || Boolean(status)}
            onClick={() => void upload()}
          >
            <UploadCloud className="size-4" /> Upload and publish
          </button>
        </div>
      </section>
    </div>
  );
}

