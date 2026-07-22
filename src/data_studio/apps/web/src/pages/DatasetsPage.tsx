import { ArrowRight, Database, LockKeyhole, Plus, Search, ShieldCheck, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { Brand } from "../components/Brand";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import type { Dataset, Visibility } from "../types";

function CreateDatasetDialog({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const [namespace, setNamespace] = useState("research");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const dataset = await api.createDataset({ namespace, slug, visibility, description });
      await navigate(`/datasets/${dataset.namespace}/${dataset.slug}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the dataset.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4 backdrop-blur-sm">
      <form
        className="w-full max-w-lg rounded-[2rem] bg-[#fffefa] p-7 shadow-2xl"
        onSubmit={(event) => void submit(event)}
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="eyebrow">Repository</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Create a dataset</h2>
          </div>
          <button className="icon-button" type="button" onClick={close} aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-4">
          <label className="field-label">
            Namespace
            <input
              className="field-input"
              required
              pattern="[a-z0-9][a-z0-9_-]*"
              value={namespace}
              onChange={(event) => setNamespace(event.target.value)}
            />
          </label>
          <label className="field-label">
            Dataset name
            <input
              className="field-input"
              required
              autoFocus
              pattern="[a-z0-9][a-z0-9._-]*"
              placeholder="support-tickets"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </label>
        </div>
        <label className="field-label mt-4">
          Description
          <textarea
            className="field-input min-h-24 resize-none"
            placeholder="What is this dataset used for?"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className="field-label mt-4">
          Visibility
          <select
            className="field-input"
            value={visibility}
            onChange={(event) => setVisibility(event.target.value as Visibility)}
          >
            <option value="private">Private — invited members only</option>
            <option value="internal">Internal — everyone in this Studio</option>
            <option value="public">Public — unauthenticated readers</option>
          </select>
        </label>
        {error ? <p className="mt-4 text-sm font-medium text-rose-700">{error}</p> : null}
        <div className="mt-6 flex justify-end gap-3">
          <button className="button-secondary" type="button" onClick={close}>Cancel</button>
          <button className="button-primary" type="submit" disabled={saving}>
            {saving ? "Creating…" : "Create dataset"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    setError("");
    void api.listDatasets().then(setDatasets).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load datasets.");
    });
  };
  useEffect(load, []);

  const filtered = datasets?.filter((dataset) =>
    `${dataset.namespace}/${dataset.slug} ${dataset.description}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200/80 bg-[#fffefa]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Brand />
          <button className="button-primary" type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> New dataset
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-12">
        <section className="grid gap-8 lg:grid-cols-[1.3fr_0.7fr] lg:items-end">
          <div>
            <p className="eyebrow">Private dataset hub</p>
            <h1 className="mt-3 max-w-3xl text-5xl font-semibold tracking-[-0.045em] text-slate-950">
              Your datasets, legible and versioned.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">
              Upload Hugging Face-compatible repositories without conversion. Browse cards, shards,
              schemas, and rows from one calm workspace.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <ShieldCheck className="size-5 text-teal-800" />
              <p className="mt-5 text-2xl font-semibold">{datasets?.length ?? "—"}</p>
              <p className="mt-1 text-xs font-medium text-slate-500">Dataset repositories</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <LockKeyhole className="size-5 text-teal-800" />
              <p className="mt-5 text-sm font-semibold">Source preserved</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">Immutable, content-addressed revisions</p>
            </div>
          </div>
        </section>

        <section className="mt-12">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-950">Datasets</h2>
              <p className="mt-1 text-sm text-slate-500">Repositories you can access in this Studio.</p>
            </div>
            <label className="relative block w-full max-w-xs">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
              <input
                className="field-input pl-9"
                type="search"
                placeholder="Search datasets"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>
          <div className="mt-5">
            {error ? <ErrorState message={error} retry={load} /> : null}
            {!error && datasets === null ? <LoadingState label="Loading repositories…" /> : null}
            {!error && datasets !== null && !filtered?.length ? (
              <EmptyState
                title={query ? "No matching datasets" : "Create your first dataset"}
                description={query ? "Try a different name or description." : "Start with a repository, then upload any Hugging Face-compatible folder."}
                action={!query ? <button className="button-primary" type="button" onClick={() => setCreating(true)}><Plus className="size-4" /> New dataset</button> : undefined}
              />
            ) : null}
            {filtered?.length ? (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {filtered.map((dataset) => (
                  <Link
                    className="group rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-800/30 hover:shadow-lg hover:shadow-slate-900/5"
                    to={`/datasets/${dataset.namespace}/${dataset.slug}`}
                    key={dataset.id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <span className="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-800">
                        <Database className="size-5" />
                      </span>
                      <span className="status-pill">{dataset.visibility}</span>
                    </div>
                    <p className="mt-5 text-xs font-medium text-slate-400">{dataset.namespace}</p>
                    <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-950">{dataset.slug}</h3>
                    <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
                      {dataset.description || "No description yet."}
                    </p>
                    <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
                      <span>{dataset.latest_revision ? `rev ${dataset.latest_revision.revision_id}` : "No revisions"}</span>
                      <ArrowRight className="size-4 transition group-hover:translate-x-1" />
                    </div>
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </main>
      {creating ? <CreateDatasetDialog close={() => setCreating(false)} /> : null}
    </div>
  );
}

