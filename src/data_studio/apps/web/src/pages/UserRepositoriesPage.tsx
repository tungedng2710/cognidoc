import { ArrowLeft, ArrowRight, Database, HardDrive, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { ApiGuideLink } from "../components/ApiGuideLink";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import type { Dataset } from "../types";

export function UserRepositoriesPage() {
  const { username = "" } = useParams();
  const { user, loading: authLoading } = useAuth();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const load = () => {
    setDatasets(null);
    setError("");
    void api.listDatasets(username)
      .then(setDatasets)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load repositories.");
      });
  };

  useEffect(load, [username]);

  if (authLoading) {
    return <div className="page-shell py-16"><LoadingState label="Loading repositories…" /></div>;
  }
  if (!user) return <Navigate to="/" replace />;

  const filtered = datasets?.filter((dataset) =>
    `${dataset.namespace}/${dataset.slug} ${dataset.description}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const isCurrentUser = username === user.username;
  const ownerLabel = isCurrentUser ? user.display_name || user.username : username;

  return (
    <div className="min-h-screen">
      <header className="app-header">
        <div className="app-header-bar page-shell">
          <Brand />
          <div className="flex items-center gap-2">
            <Link className="header-action" to="/">
              <ArrowLeft className="size-4" />
              <span className="hidden sm:inline">All datasets</span>
            </Link>
            <ApiGuideLink />
            <AccountControls />
          </div>
        </div>
      </header>
      <main className="page-shell py-5 lg:py-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">{isCurrentUser ? "Your workspace" : `@${username}`}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
              {ownerLabel}&apos;s repositories
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Repositories created by @{username}.
            </p>
          </div>
          <label className="relative block w-full max-w-xs">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <input
              className="field-input pl-9"
              type="search"
              placeholder="Search repositories"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>

        <section className="mt-5">
          {error ? <ErrorState message={error} retry={load} /> : null}
          {!error && datasets === null ? <LoadingState label="Loading repositories…" /> : null}
          {!error && datasets !== null && !filtered?.length ? (
            <EmptyState
              title={query ? "No matching repositories" : "No repositories yet"}
              description={query ? "Try a different name or description." : `@${username} has not created a visible repository.`}
            />
          ) : null}
          {filtered?.length ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {filtered.map((dataset) => (
                <Link
                  className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-4 shadow-xs shadow-slate-900/5 transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md"
                  to={`/datasets/${dataset.namespace}/${dataset.slug}`}
                  key={dataset.id}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-indigo-50 to-cyan-50 text-indigo-600 ring-1 ring-indigo-100">
                      <Database className="size-5" />
                    </span>
                    <span className="status-pill">{dataset.visibility}</span>
                  </div>
                  <p className="mt-4 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                    <HardDrive className="size-3" /> {dataset.namespace}
                  </p>
                  <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-950">
                    {dataset.slug}
                  </h2>
                  <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
                    {dataset.description || "No description yet."}
                  </p>
                  <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
                    <span>
                      {dataset.latest_revision
                        ? `rev ${dataset.latest_revision.revision_id}`
                        : "No revisions"}
                    </span>
                    <ArrowRight className="size-4 transition group-hover:translate-x-0.5 group-hover:text-indigo-600" />
                  </div>
                </Link>
              ))}
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
