import {
  BarChart3,
  BookOpenText,
  Braces,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  File,
  FileArchive,
  Files,
  Filter,
  GitCommitHorizontal,
  Globe2,
  Search,
  Save,
  Settings,
  Shield,
  Table2,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useMatch,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { api } from "../api";
import { AccountControls } from "../components/Auth";
import { ApiGuideLink } from "../components/ApiGuideLink";
import { useAuth } from "../components/auth-context";
import { Brand } from "../components/Brand";
import { DataTable } from "../components/DataTable";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { StudioSelect } from "../components/StudioSelect";
import { UploadDialog } from "../components/UploadDialog";
import type {
  Dataset,
  DatasetConfig,
  FilePage,
  Revision,
  RevisionSummary,
  ViewerResponse,
} from "../types";

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

function SelectionControls({
  configs,
  configName,
  splitName,
  onChange,
}: {
  configs: DatasetConfig[];
  configName: string;
  splitName: string;
  onChange: (config: string, split: string) => void;
}) {
  const config = configs.find((item) => item.name === configName) ?? configs[0];
  return (
    <div className="flex flex-wrap gap-3">
      <StudioSelect
        ariaLabel="Dataset subset"
        className="min-w-44"
        label="Subset"
        value={configName}
        options={configs.map((item) => ({ value: item.name, label: item.name }))}
        onChange={(nextConfig) => {
          const next = configs.find((item) => item.name === nextConfig);
          onChange(nextConfig, next?.splits[0]?.name ?? "train");
        }}
      />
      <StudioSelect
        ariaLabel="Dataset split"
        className="min-w-40"
        label="Split"
        value={splitName}
        options={(config?.splits ?? []).map((split) => ({ value: split.name, label: split.name }))}
        onChange={(nextSplit) => onChange(configName, nextSplit)}
      />
    </div>
  );
}

function CardTab({
  revision,
  openUpload,
  canEdit,
}: {
  revision: Revision;
  openUpload: () => void;
  canEdit: boolean;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
      <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:p-7">
        {revision.card_html ? (
          <div className="card-markdown" dangerouslySetInnerHTML={{ __html: revision.card_html }} />
        ) : (
          <EmptyState
            title="This dataset has no card yet"
            description="Add a README.md to the repository root and publish another revision. YAML front matter is supported."
            action={canEdit ? <button className="button-primary" type="button" onClick={openUpload}><UploadCloud className="size-4" /> Upload revision</button> : undefined}
          />
        )}
      </article>
      <aside className="space-y-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="eyebrow">Dataset metadata</p>
          <dl className="mt-4 space-y-3 text-sm">
            {Object.entries(revision.card_metadata).slice(0, 12).map(([key, value]) => (
              <div className="flex items-start justify-between gap-4" key={key}>
                <dt className="text-slate-500">{key}</dt>
                <dd className="max-w-36 text-right font-medium break-words text-slate-900">
                  {typeof value === "string" ? value : JSON.stringify(value)}
                </dd>
              </div>
            ))}
            {!Object.keys(revision.card_metadata).length ? (
              <p className="text-slate-500">No YAML front matter.</p>
            ) : null}
          </dl>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="eyebrow">Revision</p>
          <p className="mt-3 font-mono text-sm font-semibold text-indigo-700">{revision.revision_id}</p>
          <p className="mt-2 text-xs leading-5 text-slate-500">{revision.commit_message}</p>
          <div className="mt-4 flex items-center gap-2 text-xs font-medium text-emerald-700">
            <CheckCircle2 className="size-4" /> Ready to browse
          </div>
        </div>
      </aside>
    </div>
  );
}

function ViewerTab({
  namespace,
  dataset,
  revision,
  basePath,
}: {
  namespace: string;
  dataset: string;
  revision: Revision;
  basePath: string;
}) {
  const { configName, splitName } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewer, setViewer] = useState<ViewerResponse | null>(null);
  const [error, setError] = useState("");
  const [filterColumn, setFilterColumn] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const selectedConfig = revision.configs.find((item) => item.name === configName) ?? revision.configs[0];
  const selectedSplit = selectedConfig?.splits.find((item) => item.name === splitName) ?? selectedConfig?.splits[0];
  const routeSelectionValid = revision.configs.some(
    (config) => config.name === configName && config.splits.some((split) => split.name === splitName),
  );
  const rawOffset = Number(searchParams.get("offset") ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset >= 0 ? Math.floor(rawOffset) : 0;
  const filter = searchParams.get("filter") ?? undefined;
  const limit = 50;
  const activeFilter = useMemo(() => {
    if (!filter) return null;
    try {
      const parsed = JSON.parse(filter) as { column?: unknown; value?: unknown };
      if (typeof parsed.column === "string" && typeof parsed.value === "string") {
        return { column: parsed.column, value: parsed.value };
      }
    } catch {
      return null;
    }
    return null;
  }, [filter]);
  const normalizedFilter = activeFilter && selectedSplit?.schema.some((field) => field.name === activeFilter.column)
    ? JSON.stringify({ column: activeFilter.column, op: "contains", value: activeFilter.value })
    : undefined;

  useEffect(() => {
    setFilterColumn(activeFilter?.column ?? "");
    setFilterValue(activeFilter?.value ?? "");
  }, [activeFilter]);

  useEffect(() => {
    if (!routeSelectionValid) {
      const firstConfig = revision.configs[0];
      const firstSplit = firstConfig?.splits[0];
      if (firstConfig && firstSplit) {
        void navigate(
          `${basePath}/viewer/${encodeURIComponent(firstConfig.name)}/${encodeURIComponent(firstSplit.name)}?revision=${revision.revision_id}`,
          { replace: true },
        );
      }
    }
  }, [basePath, navigate, revision, routeSelectionValid]);

  useEffect(() => {
    if (!selectedConfig || !selectedSplit) return;
    setViewer(null);
    setError("");
    void api.viewer(namespace, dataset, selectedConfig.name, selectedSplit.name, {
      revision: revision.revision_id,
      offset,
      limit,
      filter: normalizedFilter,
    }).then(setViewer).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load preview rows.");
    });
  }, [dataset, namespace, normalizedFilter, offset, revision.revision_id, selectedConfig, selectedSplit]);

  if (!revision.configs.length) {
    return <EmptyState title="No previewable data found" description="The repository is preserved, but no supported tabular files or ImageFolder layout were detected." />;
  }
  if (!selectedConfig || !selectedSplit) return <LoadingState />;

  const changeSelection = (config: string, split: string) => {
    void navigate(
      `${basePath}/viewer/${encodeURIComponent(config)}/${encodeURIComponent(split)}?revision=${revision.revision_id}`,
    );
  };
  const applyFilter = (event?: FormEvent) => {
    event?.preventDefault();
    const next = new URLSearchParams(searchParams);
    next.set("revision", revision.revision_id);
    next.set("offset", "0");
    if (filterColumn && filterValue) {
      next.set("filter", JSON.stringify({ column: filterColumn, op: "contains", value: filterValue }));
    } else {
      next.delete("filter");
    }
    setSearchParams(next);
  };
  const clearFilter = () => {
    setFilterColumn("");
    setFilterValue("");
    const next = new URLSearchParams(searchParams);
    next.set("revision", revision.revision_id);
    next.set("offset", "0");
    next.delete("filter");
    setSearchParams(next);
  };
  const changePage = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("revision", revision.revision_id);
    next.set("offset", String(Math.max(0, nextOffset)));
    setSearchParams(next);
  };
  const canGoNext = Boolean(viewer && offset + viewer.rows.length < viewer.available_rows);

  return (
    <div>
      <div className="surface-panel flex flex-wrap items-end justify-between gap-4 p-4">
        <SelectionControls configs={revision.configs} configName={selectedConfig.name} splitName={selectedSplit.name} onChange={changeSelection} />
        <form className="flex flex-wrap items-center gap-2" onSubmit={(event) => applyFilter(event)}>
          <StudioSelect
            ariaLabel="Filter column"
            className="w-48"
            value={filterColumn}
            options={[
              { value: "", label: "Choose column" },
              ...selectedSplit.schema.map((field) => ({ value: field.name, label: field.name })),
            ]}
            onChange={setFilterColumn}
          />
          <label className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <input className="field-input mt-0 w-56 pl-9" placeholder="Contains value…" value={filterValue} onChange={(event) => setFilterValue(event.target.value)} />
          </label>
          <button className="button-secondary" type="submit"><Filter className="size-4" /> Filter</button>
          {filter ? <button className="icon-button" type="button" onClick={clearFilter} aria-label="Clear filter"><X className="size-4" /></button> : null}
        </form>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
        <p>
          <span className="font-semibold text-slate-800">{selectedSplit.num_rows?.toLocaleString() ?? "Unknown"}</span> rows
          <span className="mx-2">·</span>{formatBytes(selectedSplit.num_bytes)}
          <span className="mx-2">·</span>{selectedSplit.schema.length} columns
        </p>
        <p>
          {viewer ? `${viewer.available_rows.toLocaleString()} indexed rows available` : "Reading indexed preview…"}
          {filter ? " for this filter" : ""}
        </p>
      </div>
      <div className="mt-4">
        {error ? <ErrorState message={error} /> : null}
        {!error && !viewer ? <LoadingState label="Reading immutable preview…" /> : null}
        {viewer && !viewer.rows.length ? <EmptyState title="No rows in this view" description="The split is empty, the indexed preview ended, or the current filter has no matches." /> : null}
        {viewer?.rows.length ? <DataTable rows={viewer.rows} schema={viewer.schema} namespace={namespace} dataset={dataset} revision={revision.revision_id} rowOffset={offset} /> : null}
        {viewer ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500 shadow-sm">
            <p>
              Showing <span className="font-semibold text-slate-800">{viewer.rows.length ? offset + 1 : 0}–{offset + viewer.rows.length}</span> of {viewer.available_rows.toLocaleString()} indexed rows
            </p>
            <div className="flex gap-2">
              <button className="button-secondary min-h-9 px-3" type="button" disabled={offset === 0} onClick={() => changePage(offset - limit)}><ChevronLeft className="size-4" /> Previous</button>
              <button className="button-secondary min-h-9 px-3" type="button" disabled={!canGoNext} onClick={() => changePage(offset + limit)}>Next <ChevronRight className="size-4" /></button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FilesTab({ namespace, dataset, revision }: { namespace: string; dataset: string; revision: Revision }) {
  const pageSize = 100;
  const [page, setPage] = useState<FilePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setOffset(0);
    setQuery("");
    setSearch("");
  }, [revision.revision_id]);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setError("");
    void api.filePage(namespace, dataset, revision.revision_id, {
      offset,
      limit: pageSize,
      search,
    }).then((nextPage) => {
      if (!cancelled) setPage(nextPage);
    }).catch((caught: unknown) => {
      if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load repository files.");
    });
    return () => { cancelled = true; };
  }, [dataset, namespace, offset, revision.revision_id, search]);

  const findFiles = (event: FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setSearch(query.trim());
  };
  const clearSearch = () => {
    setQuery("");
    setSearch("");
    setOffset(0);
  };

  return (
    <div className="surface-panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-6 py-5">
        <div>
          <h2 className="font-semibold text-slate-950">Repository files</h2>
          <p className="mt-1 text-xs text-slate-500">Original paths and bytes preserved at revision {revision.revision_id}.</p>
        </div>
        <form className="flex w-full max-w-sm gap-2" onSubmit={findFiles}>
          <label className="relative min-w-0 flex-1">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <input className="field-input pl-9" type="search" placeholder="Search file paths" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          {search ? <button className="icon-button mt-1" type="button" onClick={clearSearch} aria-label="Clear file search"><X className="size-4" /></button> : null}
          <button className="button-secondary mt-1" type="submit">Search</button>
        </form>
      </div>
      {error ? <div className="p-5"><ErrorState message={error} /></div> : null}
      {!error && !page ? <div className="p-5"><LoadingState label="Loading repository files…" /></div> : null}
      {page && !page.items.length ? <div className="p-5"><EmptyState title="No matching files" description={search ? `No paths contain “${search}”.` : "This revision does not contain files."} /></div> : null}
      {page?.items.length ? <div className="overflow-x-auto"><div className="min-w-[680px] divide-y divide-slate-100">
        {page.items.map((file) => (
          <a
            className="group grid grid-cols-[minmax(0,1fr)_100px_100px_32px] items-center gap-4 px-6 py-3 text-sm transition-colors hover:bg-indigo-50/45"
            href={api.blobUrl(namespace, dataset, revision.revision_id, file.path)}
            key={file.path}
          >
            <span className="flex min-w-0 items-center gap-3 font-medium text-slate-800">
              {file.path.endsWith(".parquet") ? <FileArchive className="size-4 shrink-0 text-violet-600" /> : <File className="size-4 shrink-0 text-indigo-500" />}
              <span className="truncate group-hover:text-indigo-700">{file.path}</span>
            </span>
            <span className="text-right text-xs text-slate-500">{file.media_type.split("/").at(-1)}</span>
            <span className="text-right font-mono text-xs text-slate-500">{formatBytes(file.size_bytes)}</span>
            <Download className="size-4 text-slate-300 transition group-hover:text-indigo-600" />
          </a>
        ))}
      </div></div> : null}
      {page ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50/70 px-6 py-4 text-xs text-slate-500">
          <p>
            Showing <span className="font-semibold text-slate-800">{page.items.length ? page.offset + 1 : 0}–{page.offset + page.items.length}</span> of {page.total.toLocaleString()} files
          </p>
          <div className="flex gap-2">
            <button className="button-secondary min-h-9 px-3" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}><ChevronLeft className="size-4" /> Previous</button>
            <button className="button-secondary min-h-9 px-3" type="button" disabled={offset + page.items.length >= page.total} onClick={() => setOffset(offset + pageSize)}>Next <ChevronRight className="size-4" /></button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SchemaTab({ revision }: { revision: Revision }) {
  const [params, setParams] = useSearchParams();
  const config = revision.configs.find((item) => item.name === params.get("config")) ?? revision.configs[0];
  const split = config?.splits.find((item) => item.name === params.get("split")) ?? config?.splits[0];
  if (!config || !split) return <EmptyState title="No inferred schema" description="Upload a supported data file to infer an Arrow-compatible schema." />;
  const select = (configName: string, splitName: string) => {
    const next = new URLSearchParams(params);
    next.set("config", configName); next.set("split", splitName);
    setParams(next);
  };
  return (
    <div>
      <SelectionControls configs={revision.configs} configName={config.name} splitName={split.name} onChange={select} />
      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="grid grid-cols-[1fr_1fr_120px] border-b border-slate-200 bg-slate-50 px-6 py-3 text-xs font-semibold text-slate-500">
          <span>Column</span><span>Arrow-compatible type</span><span>Nullable</span>
        </div>
        {split.schema.map((field) => (
          <div className="grid grid-cols-[1fr_1fr_120px] border-b border-slate-100 px-6 py-4 text-sm last:border-0" key={field.name}>
            <span className="font-semibold text-slate-900">{field.name}</span>
            <code className="text-violet-700">{field.type}</code>
            <span className="text-slate-500">{field.nullable ? "Yes" : "No"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatisticsTab({ namespace, dataset, revision }: { namespace: string; dataset: string; revision: Revision }) {
  const [params, setParams] = useSearchParams();
  const config = revision.configs.find((item) => item.name === params.get("config")) ?? revision.configs[0];
  const split = config?.splits.find((item) => item.name === params.get("split")) ?? config?.splits[0];
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!config || !split) return;
    setStats(null); setError("");
    void api.statistics(namespace, dataset, config.name, split.name, revision.revision_id).then(setStats).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load statistics.");
    });
  }, [config, dataset, namespace, revision.revision_id, split]);
  if (!config || !split) return <EmptyState title="No statistics available" description="Statistics are generated for detected dataset splits." />;
  const select = (configName: string, splitName: string) => {
    const next = new URLSearchParams(params); next.set("config", configName); next.set("split", splitName); setParams(next);
  };
  const columns = stats && typeof stats.columns === "object" && stats.columns ? Object.entries(stats.columns as Record<string, Record<string, unknown>>) : [];
  return (
    <div>
      <SelectionControls configs={revision.configs} configName={config.name} splitName={split.name} onChange={select} />
      <div className="mt-5">
        {error ? <ErrorState message={error} /> : null}
        {!error && !stats ? <LoadingState label="Loading bounded statistics…" /> : null}
        {stats ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {columns.map(([name, values]) => (
              <div className="rounded-2xl border border-slate-200 bg-white p-5" key={name}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-slate-950">{name}</h3>
                  <Braces className="size-4 text-violet-600" />
                </div>
                <dl className="mt-4 space-y-2 text-xs">
                  {Object.entries(values).map(([key, value]) => (
                    <div className="flex justify-between gap-4" key={key}>
                      <dt className="text-slate-500">{key.replaceAll("_", " ")}</dt>
                      <dd className="font-mono font-medium text-slate-800">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function VersionsTab({ revisions, selected }: { revisions: RevisionSummary[]; selected: string }) {
  const [params, setParams] = useSearchParams();
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="font-semibold text-slate-950">Immutable revisions</h2>
      <div className="relative mt-6 ml-3 border-l border-slate-200 pl-7">
        {revisions.map((revision) => (
          <button
            className="relative mb-7 block w-full text-left last:mb-0"
            type="button"
            key={revision.revision_id}
            onClick={() => { const next = new URLSearchParams(params); next.set("revision", revision.revision_id); setParams(next); }}
          >
            <span className={`absolute top-1 -left-[2.15rem] size-3 rounded-full border-2 border-white ${revision.revision_id === selected ? "bg-indigo-600 ring-4 ring-indigo-100" : "bg-slate-300"}`} />
            <span className="flex flex-wrap items-center gap-3">
              <code className="font-semibold text-indigo-700">{revision.revision_id}</code>
              <span className="status-pill">{revision.status}</span>
              <span className="text-xs text-slate-400">{new Date(revision.created_at).toLocaleString()}</span>
            </span>
            <span className="mt-1 block text-sm text-slate-600">{revision.commit_message}</span>
            {revision.git_commit || revision.dvc_revision ? (
              <span className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-slate-400">
                {revision.git_commit ? <span>git {revision.git_commit.slice(0, 12)}</span> : null}
                {revision.dvc_revision ? <span>dvc {revision.dvc_revision}</span> : null}
              </span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function SettingsTab({
  dataset,
  onUpdated,
  onDeleted,
}: {
  dataset: Dataset;
  onUpdated: (dataset: Dataset) => void;
  onDeleted: () => void;
}) {
  const { user, openAuth } = useAuth();
  const navigate = useNavigate();
  const [slug, setSlug] = useState(dataset.slug);
  const [description, setDescription] = useState(dataset.description);
  const [visibility, setVisibility] = useState(dataset.visibility);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [confirmation, setConfirmation] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateDataset(dataset.namespace, dataset.slug, {
        slug,
        description,
        visibility,
      });
      onUpdated(updated);
      if (updated.slug !== dataset.slug) {
        await navigate(`/datasets/${updated.namespace}/${updated.slug}/settings`, { replace: true });
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update the dataset.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (confirmation !== dataset.slug) return;
    setSaving(true);
    setError("");
    try {
      await api.deleteDataset(dataset.namespace, dataset.slug);
      onDeleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete the dataset.");
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="surface-panel p-5">
        <div className="flex items-center gap-3"><Shield className="size-5 text-indigo-600" /><h2 className="font-semibold">Repository access</h2></div>
        {dataset.can_edit ? (
          <form className="mt-5 space-y-4" onSubmit={(event) => void save(event)}>
            <label className="field-label">
              Dataset name
              <div className="mt-1 flex min-h-10 items-center overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm focus-within:border-indigo-400 focus-within:ring-3 focus-within:ring-indigo-500/10">
                <span className="border-r border-slate-200 bg-slate-50 px-3 text-sm text-slate-500">{dataset.namespace} /</span>
                <input
                  className="min-w-0 flex-1 px-3 text-sm text-slate-900 outline-none"
                  required
                  pattern="[a-z0-9][a-z0-9._-]{0,95}"
                  value={slug}
                  onChange={(event) => setSlug(event.target.value.toLowerCase())}
                />
              </div>
              <span className="mt-1 block font-normal text-slate-400">Renaming changes the repository URL but keeps every revision intact.</span>
            </label>
            <label className="field-label">
              Description
              <textarea className="field-input min-h-24 resize-none" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <div className="field-label">
              <span>Visibility</span>
              <StudioSelect
                ariaLabel="Dataset visibility"
                className="mt-1"
                value={visibility}
                options={[
                  { value: "private", label: "Private", description: "Only the owner and workspace administrators." },
                  { value: "internal", label: "Internal", description: "Every signed-in Studio user." },
                  { value: "public", label: "Public", description: "Anyone with the repository link." },
                ]}
                onChange={(next) => setVisibility(next as Dataset["visibility"])}
              />
            </div>
            {error ? <p className="text-sm font-medium text-rose-700">{error}</p> : null}
            <button className="button-primary" type="submit" disabled={saving}><Save className="size-4" /> {saving ? "Saving…" : "Save changes"}</button>
          </form>
        ) : (
          <div className="mt-5">
            <dl className="space-y-4 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">Owner</dt><dd className="font-semibold">{dataset.owner ?? "Legacy repository"}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Visibility</dt><dd className="font-semibold capitalize">{dataset.visibility}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Default branch</dt><dd className="font-mono">{dataset.default_branch}</dd></div>
            </dl>
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
              {user ? (
                <p>
                  You are signed in as <strong>{user.username}</strong>. Only {dataset.owner ? <>the owner, <strong>{dataset.owner}</strong>,</> : "a workspace administrator"} can edit or delete this dataset.
                </p>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p>Sign in with the owner account to edit or delete this dataset.</p>
                  <button className="button-secondary bg-white" type="button" onClick={() => openAuth("login")}>Sign in</button>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
      <section className="surface-panel p-5">
        <div className="flex items-center gap-3"><Globe2 className="size-5 text-indigo-600" /><h2 className="font-semibold">Compatibility contract</h2></div>
        <p className="mt-4 text-sm leading-6 text-slate-600">Folder uploads preserve relative paths and understand Dataset Card YAML, declarative configs, conventional splits, sharded filenames, and ImageFolder layouts.</p>
        <p className="mt-3 text-xs leading-5 text-slate-500">Full huggingface_hub protocol compatibility is intentionally not claimed by this release.</p>
      </section>
      {dataset.can_edit ? (
        <section className="rounded-2xl border border-rose-200 bg-rose-50/60 p-5 lg:col-span-2">
          <div className="flex items-center gap-3 text-rose-800"><Trash2 className="size-5" /><h2 className="font-semibold">Delete dataset</h2></div>
          <p className="mt-3 text-sm leading-6 text-rose-800/80">This permanently removes repository metadata, revisions, previews, and file records. Type <strong>{dataset.slug}</strong> to confirm.</p>
          {!deleting ? (
            <button className="button-secondary mt-4 border-rose-200 text-rose-700 hover:bg-rose-100" type="button" onClick={() => setDeleting(true)}><Trash2 className="size-4" /> Delete dataset</button>
          ) : (
            <div className="mt-4 flex flex-wrap gap-3">
              <input className="field-input mt-0 max-w-xs" aria-label="Confirm dataset name" placeholder={dataset.slug} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
              <button className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:opacity-50" type="button" disabled={saving || confirmation !== dataset.slug} onClick={() => void remove()}><Trash2 className="size-4" /> Permanently delete</button>
              <button className="button-secondary" type="button" onClick={() => { setDeleting(false); setConfirmation(""); }}>Cancel</button>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}

const tabs = [
  { to: "", label: "Dataset card", icon: BookOpenText, end: true },
  { to: "viewer", label: "Data Studio", icon: Table2, end: false },
  { to: "files", label: "Files", icon: Files, end: false },
  { to: "schema", label: "Schema", icon: Database, end: false },
  { to: "statistics", label: "Statistics", icon: BarChart3, end: false },
  { to: "versions", label: "Versions", icon: GitCommitHorizontal, end: false },
  { to: "settings", label: "Settings", icon: Settings, end: false },
] as const;

export function DatasetWorkspace() {
  const { namespace = "", dataset = "" } = useParams();
  const navigate = useNavigate();
  const isSettingsRoute = Boolean(useMatch("/datasets/:namespace/:dataset/settings"));
  const { user, loading: authLoading } = useAuth();
  const [params, setParams] = useSearchParams();
  const [repository, setRepository] = useState<Dataset | null>(null);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revisionError, setRevisionError] = useState("");
  const [revisionReload, setRevisionReload] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const selectedRevision = params.get("revision") ?? repository?.latest_revision?.revision_id;
  const basePath = `/datasets/${namespace}/${dataset}`;

  const reloadRepository = useCallback(() => {
    setLoading(true); setError("");
    void Promise.all([api.dataset(namespace, dataset), api.revisions(namespace, dataset)])
      .then(([nextRepository, nextRevisions]) => { setRepository(nextRepository); setRevisions(nextRevisions); })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Could not load dataset."))
      .finally(() => setLoading(false));
  }, [dataset, namespace]);
  useEffect(() => {
    if (!authLoading) reloadRepository();
  }, [authLoading, reloadRepository, user?.id]);

  useEffect(() => {
    if (!selectedRevision) { setRevision(null); setRevisionError(""); return; }
    let cancelled = false;
    setRevision(null);
    setRevisionError("");
    void api.revision(namespace, dataset, selectedRevision).then((nextRevision) => {
      if (!cancelled) setRevision(nextRevision);
    }).catch((caught: unknown) => {
      if (!cancelled) setRevisionError(caught instanceof Error ? caught.message : "Could not load revision.");
    });
    return () => { cancelled = true; };
  }, [dataset, namespace, revisionReload, selectedRevision]);

  const selectedParams = useMemo(() => {
    const next = new URLSearchParams(params);
    if (selectedRevision) next.set("revision", selectedRevision);
    return next;
  }, [params, selectedRevision]);

  if (loading || authLoading) return <div className="page-shell py-6"><LoadingState /></div>;
  if (error || !repository) return <div className="page-shell py-6"><ErrorState message={error || "Dataset not found."} retry={reloadRepository} /></div>;

  const changeRevision = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("revision", value);
    next.delete("offset");
    next.delete("filter");
    setParams(next);
  };

  const splitCount = revision?.configs.reduce((total, config) => total + config.splits.length, 0) ?? 0;
  const totalRows = revision?.configs.reduce(
    (total, config) => total + config.splits.reduce((splitTotal, split) => splitTotal + (split.num_rows ?? 0), 0),
    0,
  ) ?? 0;
  const totalBytes = revision?.configs.reduce(
    (total, config) => total + config.splits.reduce((splitTotal, split) => splitTotal + split.num_bytes, 0),
    0,
  ) ?? 0;

  return (
    <div className="min-h-screen">
      <header className="app-header sticky top-0 z-40">
        <div className="page-shell flex items-center justify-between py-2">
          <Brand />
          <div className="flex items-center gap-2">
            <Link className="header-action border-transparent shadow-none" to="/"><ChevronLeft className="size-4" /> All datasets</Link>
            <ApiGuideLink />
            <AccountControls />
          </div>
        </div>
      </header>
      <main>
        <section className="border-b border-slate-200 bg-white/90 shadow-sm shadow-slate-900/3">
          <div className="page-shell pt-3">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-indigo-600 to-cyan-500 text-white shadow-md shadow-indigo-950/15"><Database className="size-4.5" /></span>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-slate-500">{namespace} /</p>
                    <h1 className="truncate text-2xl font-semibold tracking-[-0.035em] text-slate-950">{dataset}</h1>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 pl-12 text-xs text-slate-500">
                  <p className="max-w-xl truncate">{repository.description || "No description yet."}</p>
                  {revision ? (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                      <span><strong className="font-semibold text-slate-800">{revision.configs.length.toLocaleString()}</strong> subsets</span>
                      <span><strong className="font-semibold text-slate-800">{splitCount.toLocaleString()}</strong> splits</span>
                      <span><strong className="font-semibold text-slate-800">{totalRows.toLocaleString()}</strong> rows</span>
                      <span><strong className="font-semibold text-slate-800">{formatBytes(totalBytes)}</strong> indexed</span>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {revision ? (
                  <a
                    className="button-secondary"
                    href={api.archiveUrl(namespace, dataset, revision.revision_id)}
                  >
                    <Download className="size-4" /> Download dataset
                  </a>
                ) : null}
                {revisions.length ? (
                  <StudioSelect
                    ariaLabel="Dataset revision"
                    className="min-w-56"
                    label="Revision"
                    leadingIcon={<GitCommitHorizontal className="size-4" />}
                    value={selectedRevision ?? revisions[0]?.revision_id ?? ""}
                    options={revisions.map((item) => ({
                      value: item.revision_id,
                      label: item.revision_id,
                      description: item.commit_message,
                    }))}
                    onChange={changeRevision}
                  />
                ) : null}
                {repository.can_edit ? <button className="button-primary" type="button" onClick={() => setUploadOpen(true)}><UploadCloud className="size-4" /> Upload revision</button> : null}
              </div>
            </div>
            <nav className="mt-2 flex gap-1 overflow-x-auto" aria-label="Dataset sections">
              {tabs.map((tab) => (
                <NavLink
                  className={({ isActive }) => `tab-link ${isActive ? "tab-link-active" : ""}`}
                  end={tab.end}
                  key={tab.to}
                  to={{
                    pathname: tab.to ? `${basePath}/${tab.to}` : basePath,
                    search: selectedParams.toString(),
                  }}
                >
                  <tab.icon className="size-4" /> {tab.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </section>
        <section className="page-shell py-5 lg:py-6">
          {isSettingsRoute ? (
            <SettingsTab dataset={repository} onUpdated={setRepository} onDeleted={() => void navigate("/")} />
          ) : revisionError ? (
            <ErrorState message={revisionError} retry={() => setRevisionReload((value) => value + 1)} />
          ) : selectedRevision && !revision ? (
            <LoadingState label="Loading immutable revision…" />
          ) : !revision ? (
            <EmptyState title="No published revision" description={repository.can_edit ? "Upload a Hugging Face-compatible folder to create the first immutable revision." : "The owner has not published a revision yet."} action={repository.can_edit ? <button className="button-primary" type="button" onClick={() => setUploadOpen(true)}><UploadCloud className="size-4" /> Upload folder</button> : undefined} />
          ) : (
            <Routes>
              <Route index element={<CardTab revision={revision} openUpload={() => setUploadOpen(true)} canEdit={repository.can_edit} />} />
              <Route path="viewer" element={<ViewerTab namespace={namespace} dataset={dataset} revision={revision} basePath={basePath} />} />
              <Route path="viewer/:configName/:splitName" element={<ViewerTab namespace={namespace} dataset={dataset} revision={revision} basePath={basePath} />} />
              <Route path="files" element={<FilesTab namespace={namespace} dataset={dataset} revision={revision} />} />
              <Route path="schema" element={<SchemaTab revision={revision} />} />
              <Route path="statistics" element={<StatisticsTab namespace={namespace} dataset={dataset} revision={revision} />} />
              <Route path="versions" element={<VersionsTab revisions={revisions} selected={revision.revision_id} />} />
              <Route path="*" element={<Navigate to={{ pathname: basePath, search: selectedParams.toString() }} replace />} />
            </Routes>
          )}
        </section>
      </main>
      {repository.can_edit ? <UploadDialog namespace={namespace} dataset={dataset} open={uploadOpen} onClose={() => setUploadOpen(false)} onComplete={(nextRevision) => { setUploadOpen(false); setRevision(nextRevision); reloadRepository(); changeRevision(nextRevision.revision_id); }} /> : null}
    </div>
  );
}
