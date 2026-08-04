import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Database,
  Search,
  Settings,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { ApiGuideLink } from "../components/ApiGuideLink";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { DatasetTags } from "../components/DatasetTags";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { UserAvatar } from "../components/UserAvatar";
import { UserSearch } from "../components/UserSearch";
import type { Dataset, PublicUser } from "../types";

function formatJoined(date: string): string {
  const joined = new Date(date);
  if (Number.isNaN(joined.getTime())) return "recently";
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(joined);
}

function RepositoryOverviewCard({ dataset }: { dataset: Dataset }) {
  return (
    <Link
      className="group flex min-h-44 flex-col rounded-xl border border-slate-200 bg-white p-4 transition hover:border-indigo-200 hover:shadow-sm"
      to={`/datasets/${dataset.namespace}/${dataset.slug}`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 truncate text-sm font-semibold text-indigo-700 group-hover:text-indigo-600">
          {dataset.slug}
        </h3>
        <span className="status-pill shrink-0">{dataset.visibility}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">
        {dataset.description || "No description yet."}
      </p>
      <DatasetTags
        className="mt-auto pt-3"
        dataStage={dataset.data_stage}
        maxTags={3}
        tags={dataset.tags}
      />
    </Link>
  );
}

function RepositoryRow({ dataset }: { dataset: Dataset }) {
  return (
    <article className="border-b border-slate-200 py-6 first:pt-0 last:border-0 last:pb-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3>
              <Link
                className="text-xl font-semibold text-indigo-700 hover:text-indigo-600 hover:underline"
                to={`/datasets/${dataset.namespace}/${dataset.slug}`}
              >
                {dataset.slug}
              </Link>
            </h3>
            <span className="status-pill">{dataset.visibility}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            {dataset.description || "No description yet."}
          </p>
          <DatasetTags
            className="mt-3"
            dataStage={dataset.data_stage}
            maxTags={6}
            tags={dataset.tags}
          />
          <p className="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <Database className="size-3.5" />
            {dataset.latest_revision
              ? `Latest revision ${dataset.latest_revision.revision_id}`
              : "No published revisions"}
            <span aria-hidden="true">·</span>
            Updated {new Date(dataset.updated_at).toLocaleDateString()}
          </p>
        </div>
        <Link
          aria-label={`Open ${dataset.slug}`}
          className="icon-button mt-1"
          to={`/datasets/${dataset.namespace}/${dataset.slug}`}
        >
          <ArrowRight className="size-4" />
        </Link>
      </div>
    </article>
  );
}

export function UserRepositoriesPage() {
  const { username = "" } = useParams();
  const profileUsername = username.toLowerCase();
  const location = useLocation();
  const { user } = useAuth();
  const [profile, setProfile] = useState<PublicUser | null>(null);
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const repositoriesActive = location.pathname.endsWith("/repositories");

  const load = () => {
    setProfile(null);
    setDatasets(null);
    setError("");
    void Promise.all([api.user(profileUsername), api.listDatasets(profileUsername)])
      .then(([nextProfile, nextDatasets]) => {
        setProfile(nextProfile);
        setDatasets(nextDatasets.filter((dataset) => dataset.owner === profileUsername));
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Could not load this profile.");
      });
  };

  useEffect(load, [profileUsername]);

  const filtered = datasets?.filter((dataset) =>
    [
      `${dataset.namespace}/${dataset.slug}`,
      dataset.description,
      dataset.data_stage ?? "",
      ...dataset.tags,
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const isCurrentUser = profileUsername === user?.username;
  const ownerLabel = profile?.display_name || profile?.username || username;
  const overviewDatasets = datasets?.slice(0, 6) ?? [];

  return (
    <div className="min-h-screen">
      <header className="app-header">
        <div className="app-header-bar page-shell">
          <Brand />
          <UserSearch className="mx-4 hidden min-w-0 max-w-md flex-1 md:block" />
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

      {error ? (
        <main className="page-shell py-16">
          <ErrorState message={error} retry={load} />
        </main>
      ) : !profile || datasets === null ? (
        <main className="page-shell py-16">
          <LoadingState label="Loading profile…" />
        </main>
      ) : (
        <>
          <div className="border-b border-slate-200 bg-white">
            <div className="page-shell pt-4 md:pt-6">
              <UserSearch className="mb-4 md:hidden" />
              <nav
                aria-label="Profile navigation"
                className="flex gap-1 overflow-x-auto md:pl-[calc(296px+2rem)]"
              >
                <Link
                  className={`tab-link ${repositoriesActive ? "" : "tab-link-active"}`}
                  to={`/users/${encodeURIComponent(username)}`}
                >
                  <BookOpen className="size-4" /> Overview
                </Link>
                <Link
                  className={`tab-link ${repositoriesActive ? "tab-link-active" : ""}`}
                  to={`/users/${encodeURIComponent(username)}/repositories`}
                >
                  <Database className="size-4" /> Repositories
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                    {datasets.length}
                  </span>
                </Link>
              </nav>
            </div>
          </div>

          <main className="page-shell py-6">
            <div className="grid items-start gap-8 md:grid-cols-[296px_minmax(0,1fr)]">
              <aside>
                <UserAvatar
                  className="size-32 text-4xl md:size-72 md:text-7xl"
                  user={profile}
                />
                <div className="mt-4">
                  <h1 className="text-2xl font-semibold leading-tight text-slate-950">
                    {ownerLabel}
                  </h1>
                  <p className="mt-0.5 text-xl font-light text-slate-500">{profile.username}</p>
                </div>
                {isCurrentUser ? (
                  <Link className="button-secondary mt-4 w-full" to="/settings">
                    <Settings className="size-4" /> Edit profile
                  </Link>
                ) : null}
                <p className="mt-5 flex items-center gap-2 text-sm text-slate-600">
                  <CalendarDays className="size-4 text-slate-400" /> Joined {formatJoined(profile.created_at)}
                </p>
              </aside>

              <section className="min-w-0">
                {repositoriesActive ? (
                  <>
                    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-4">
                      <div>
                        <h2 className="text-xl font-semibold text-slate-950">
                          {ownerLabel}&apos;s repositories
                        </h2>
                        <p className="mt-1 text-sm text-slate-500">
                          {datasets.length} visible {datasets.length === 1 ? "repository" : "repositories"}
                        </p>
                      </div>
                      <label className="relative block w-full max-w-sm">
                        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
                        <input
                          aria-label="Find a repository"
                          className="field-input mt-0 pl-9"
                          type="search"
                          placeholder="Find a repository"
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                        />
                      </label>
                    </div>
                    <div className="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                      {!filtered?.length ? (
                        <EmptyState
                          title={query ? "No matching repositories" : "No repositories yet"}
                          description={
                            query
                              ? "Try a different name, description, or tag."
                              : `@${username} has no repositories visible to you.`
                          }
                        />
                      ) : (
                        filtered.map((dataset) => (
                          <RepositoryRow dataset={dataset} key={dataset.id} />
                        ))
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-center justify-between gap-4">
                      <h2 className="text-base font-semibold text-slate-950">Popular repositories</h2>
                      {datasets.length > overviewDatasets.length ? (
                        <Link
                          className="text-sm font-semibold text-indigo-600 hover:text-indigo-500"
                          to={`/users/${encodeURIComponent(username)}/repositories`}
                        >
                          View all
                        </Link>
                      ) : null}
                    </div>
                    {overviewDatasets.length ? (
                      <div className="mt-3 grid gap-4 lg:grid-cols-2">
                        {overviewDatasets.map((dataset) => (
                          <RepositoryOverviewCard dataset={dataset} key={dataset.id} />
                        ))}
                      </div>
                    ) : (
                      <div className="surface-panel mt-3">
                        <EmptyState
                          title="No repositories yet"
                          description={`@${username} has no repositories visible to you.`}
                        />
                      </div>
                    )}
                  </>
                )}
              </section>
            </div>
          </main>
        </>
      )}
    </div>
  );
}
