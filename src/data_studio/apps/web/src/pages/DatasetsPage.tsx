import {
  ArrowRight,
  Database,
  HardDrive,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import type { Dataset, Visibility } from "../types";

function CreateDatasetDialog({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [namespace, setNamespace] = useState(user?.username ?? "research");
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
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/65 p-4 backdrop-blur-sm">
      <form
        className="modal-panel max-h-[calc(100vh-2rem)] max-w-lg overflow-y-auto"
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
  const { user, openAuth } = useAuth();
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
  useEffect(load, [user?.id]);

  const filtered = datasets?.filter((dataset) =>
    `${dataset.namespace}/${dataset.slug} ${dataset.description}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="min-h-screen">
      <header className="app-header sticky top-0 z-30">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
          <Brand />
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 text-xs font-medium text-slate-400 sm:flex">
              <span className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgb(52_211_153)]" />
              {user ? "Private workspace" : "Public catalog"}
            </span>
            <AccountControls />
            <button className="button-primary" type="button" onClick={() => user ? setCreating(true) : openAuth("register")}>
              <Plus className="size-4" /> <span className="hidden sm:inline">New dataset</span><span className="sm:hidden">New</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-10 lg:py-14">
        <section className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-7 py-9 text-white shadow-2xl shadow-slate-950/15 sm:px-10 lg:px-12 lg:py-12">
          <div className="pointer-events-none absolute -top-36 -right-28 size-96 rounded-full bg-indigo-500/25 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-40 left-1/3 size-80 rounded-full bg-cyan-400/15 blur-3xl" />
          <div className="relative grid gap-10 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
          <div>
            <p className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] text-cyan-300 uppercase">
              <Sparkles className="size-3.5" /> Private dataset hub
            </p>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.045em] text-white sm:text-5xl">
              Your datasets, legible and versioned.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              Upload Hugging Face-compatible repositories without conversion. Browse cards, shards,
              schemas, and rows from one focused workspace.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="metric-card">
              <Database className="size-5 text-cyan-300" />
              <p className="mt-5 text-2xl font-semibold text-white">{datasets?.length ?? "—"}</p>
              <p className="mt-1 text-xs font-medium text-slate-400">Repositories</p>
            </div>
            <div className="metric-card">
              <ShieldCheck className="size-5 text-indigo-300" />
              <p className="mt-5 text-sm font-semibold text-white">Source preserved</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">Immutable revisions</p>
            </div>
          </div>
          </div>
        </section>

        <section className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-950">Your repositories</h2>
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
                description={query ? "Try a different name or description." : user ? "Start with a repository, then upload any Hugging Face-compatible folder." : "Sign in to create a dataset, or browse public repositories here."}
                action={!query ? <button className="button-primary" type="button" onClick={() => user ? setCreating(true) : openAuth("register")}><Plus className="size-4" /> {user ? "New dataset" : "Create account"}</button> : undefined}
              />
            ) : null}
            {filtered?.length ? (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {filtered.map((dataset) => (
                  <Link
                    className="group relative overflow-hidden rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/5 transition hover:-translate-y-1 hover:border-indigo-200 hover:shadow-xl hover:shadow-indigo-950/8"
                    to={`/datasets/${dataset.namespace}/${dataset.slug}`}
                    key={dataset.id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-50 to-cyan-50 text-indigo-600 ring-1 ring-indigo-100">
                        <Database className="size-5" />
                      </span>
                      <span className="status-pill">{dataset.visibility}</span>
                    </div>
                    <p className="mt-5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                      <HardDrive className="size-3" /> {dataset.owner ?? dataset.namespace}
                    </p>
                    <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-950">{dataset.slug}</h3>
                    <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
                      {dataset.description || "No description yet."}
                    </p>
                    <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
                      <span>{dataset.latest_revision ? `rev ${dataset.latest_revision.revision_id}` : "No revisions"}</span>
                      <span className="grid size-7 place-items-center rounded-lg bg-slate-50 text-slate-500 transition group-hover:bg-indigo-50 group-hover:text-indigo-600">
                        <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        </section>
      </main>
      {creating && user ? <CreateDatasetDialog close={() => setCreating(false)} /> : null}
    </div>
  );
}
