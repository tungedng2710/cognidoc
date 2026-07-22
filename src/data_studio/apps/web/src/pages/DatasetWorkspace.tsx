import {
  BarChart3,
  BookOpenText,
  Braces,
  CheckCircle2,
  ChevronDown,
  Database,
  File,
  FileArchive,
  Files,
  Filter,
  GitCommitHorizontal,
  Globe2,
  LockKeyhole,
  Search,
  Settings,
  Shield,
  Table2,
  UploadCloud,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { api } from "../api";
import { Brand } from "../components/Brand";
import { DataTable } from "../components/DataTable";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { UploadDialog } from "../components/UploadDialog";
import type {
  Dataset,
  DatasetConfig,
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
      <label className="select-label">
        <span>Subset</span>
        <select
          value={configName}
          onChange={(event) => {
            const next = configs.find((item) => item.name === event.target.value);
            onChange(event.target.value, next?.splits[0]?.name ?? "train");
          }}
        >
          {configs.map((item) => <option key={item.name}>{item.name}</option>)}
        </select>
        <ChevronDown className="size-3" />
      </label>
      <label className="select-label">
        <span>Split</span>
        <select value={splitName} onChange={(event) => onChange(configName, event.target.value)}>
          {config?.splits.map((split) => <option key={split.name}>{split.name}</option>)}
        </select>
        <ChevronDown className="size-3" />
      </label>
    </div>
  );
}

function CardTab({ revision, openUpload }: { revision: Revision; openUpload: () => void }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm lg:p-10">
        {revision.card_html ? (
          <div className="card-markdown" dangerouslySetInnerHTML={{ __html: revision.card_html }} />
        ) : (
          <EmptyState
            title="This dataset has no card yet"
            description="Add a README.md to the repository root and publish another revision. YAML front matter is supported."
            action={<button className="button-primary" type="button" onClick={openUpload}><UploadCloud className="size-4" /> Upload revision</button>}
          />
        )}
      </article>
      <aside className="space-y-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
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
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="eyebrow">Revision</p>
          <p className="mt-3 font-mono text-sm font-semibold text-teal-800">{revision.revision_id}</p>
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
  const offset = Number(searchParams.get("offset") ?? 0);
  const filter = searchParams.get("filter") ?? undefined;

  useEffect(() => {
    if (!configName || !splitName) {
      const firstConfig = revision.configs[0];
      const firstSplit = firstConfig?.splits[0];
      if (firstConfig && firstSplit) {
        void navigate(
          `${basePath}/viewer/${encodeURIComponent(firstConfig.name)}/${encodeURIComponent(firstSplit.name)}?revision=${revision.revision_id}`,
          { replace: true },
        );
      }
    }
  }, [basePath, configName, navigate, revision, splitName]);

  useEffect(() => {
    if (!selectedConfig || !selectedSplit) return;
    setViewer(null);
    setError("");
    void api.viewer(namespace, dataset, selectedConfig.name, selectedSplit.name, {
      revision: revision.revision_id,
      offset,
      limit: 100,
      filter,
    }).then(setViewer).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load preview rows.");
    });
  }, [dataset, filter, namespace, offset, revision.revision_id, selectedConfig, selectedSplit]);

  if (!revision.configs.length) {
    return <EmptyState title="No previewable data found" description="The repository is preserved, but no supported tabular files or ImageFolder layout were detected." />;
  }
  if (!selectedConfig || !selectedSplit) return <LoadingState />;

  const changeSelection = (config: string, split: string) => {
    void navigate(
      `${basePath}/viewer/${encodeURIComponent(config)}/${encodeURIComponent(split)}?revision=${revision.revision_id}`,
    );
  };
  const applyFilter = () => {
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

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SelectionControls configs={revision.configs} configName={selectedConfig.name} splitName={selectedSplit.name} onChange={changeSelection} />
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
            <input className="field-input w-56 pl-9" placeholder="Filter value" value={filterValue} onChange={(event) => setFilterValue(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") applyFilter(); }} />
          </label>
          <select className="field-input w-44" value={filterColumn} onChange={(event) => setFilterColumn(event.target.value)} aria-label="Filter column">
            <option value="">Choose column</option>
            {selectedSplit.schema.map((field) => <option key={field.name}>{field.name}</option>)}
          </select>
          <button className="button-secondary" type="button" onClick={applyFilter}><Filter className="size-4" /> Filter</button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
        <p>
          <span className="font-semibold text-slate-800">{selectedSplit.num_rows?.toLocaleString() ?? "Unknown"}</span> rows
          <span className="mx-2">·</span>{formatBytes(selectedSplit.num_bytes)}
          <span className="mx-2">·</span>{selectedSplit.schema.length} columns
        </p>
        <p>Preview is bounded to the indexed sample for this revision.</p>
      </div>
      <div className="mt-4">
        {error ? <ErrorState message={error} /> : null}
        {!error && !viewer ? <LoadingState label="Reading immutable preview…" /> : null}
        {viewer && !viewer.rows.length ? <EmptyState title="No rows in this view" description="The split is empty, the bounded preview ended, or the current filter has no matches." /> : null}
        {viewer?.rows.length ? <DataTable rows={viewer.rows} schema={viewer.schema} namespace={namespace} dataset={dataset} revision={revision.revision_id} /> : null}
      </div>
    </div>
  );
}

function FilesTab({ namespace, dataset, revision }: { namespace: string; dataset: string; revision: Revision }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <div>
          <h2 className="font-semibold text-slate-950">Repository files</h2>
          <p className="mt-1 text-xs text-slate-500">Original paths and bytes preserved at revision {revision.revision_id}.</p>
        </div>
        <span className="status-pill">{revision.files.length} files</span>
      </div>
      <div className="divide-y divide-slate-100">
        {revision.files.map((file) => (
          <a
            className="group grid grid-cols-[minmax(0,1fr)_100px_100px] items-center gap-4 px-6 py-3 text-sm hover:bg-amber-50/50"
            href={api.blobUrl(namespace, dataset, revision.revision_id, file.path)}
            key={file.path}
          >
            <span className="flex min-w-0 items-center gap-3 font-medium text-slate-800">
              {file.path.endsWith(".parquet") ? <FileArchive className="size-4 shrink-0 text-violet-600" /> : <File className="size-4 shrink-0 text-teal-700" />}
              <span className="truncate group-hover:text-teal-800">{file.path}</span>
            </span>
            <span className="text-right text-xs text-slate-500">{file.media_type.split("/").at(-1)}</span>
            <span className="text-right font-mono text-xs text-slate-500">{formatBytes(file.size_bytes)}</span>
          </a>
        ))}
      </div>
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
      <div className="mt-5 overflow-hidden rounded-3xl border border-slate-200 bg-white">
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
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
    <div className="rounded-3xl border border-slate-200 bg-white p-6">
      <h2 className="font-semibold text-slate-950">Immutable revisions</h2>
      <div className="relative mt-6 ml-3 border-l border-slate-200 pl-7">
        {revisions.map((revision) => (
          <button
            className="relative mb-7 block w-full text-left last:mb-0"
            type="button"
            key={revision.revision_id}
            onClick={() => { const next = new URLSearchParams(params); next.set("revision", revision.revision_id); setParams(next); }}
          >
            <span className={`absolute top-1 -left-[2.15rem] size-3 rounded-full border-2 border-white ${revision.revision_id === selected ? "bg-teal-700 ring-4 ring-teal-100" : "bg-slate-300"}`} />
            <span className="flex flex-wrap items-center gap-3">
              <code className="font-semibold text-teal-800">{revision.revision_id}</code>
              <span className="status-pill">{revision.status}</span>
              <span className="text-xs text-slate-400">{new Date(revision.created_at).toLocaleString()}</span>
            </span>
            <span className="mt-1 block text-sm text-slate-600">{revision.commit_message}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function SettingsTab({ dataset }: { dataset: Dataset }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <div className="flex items-center gap-3"><Shield className="size-5 text-teal-800" /><h2 className="font-semibold">Repository access</h2></div>
        <dl className="mt-5 space-y-4 text-sm">
          <div className="flex justify-between"><dt className="text-slate-500">Visibility</dt><dd className="font-semibold capitalize">{dataset.visibility}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Default branch</dt><dd className="font-mono">{dataset.default_branch}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Authorization</dt><dd>Role-based</dd></div>
        </dl>
      </section>
      <section className="rounded-3xl border border-slate-200 bg-white p-6">
        <div className="flex items-center gap-3"><Globe2 className="size-5 text-teal-800" /><h2 className="font-semibold">Compatibility contract</h2></div>
        <p className="mt-4 text-sm leading-6 text-slate-600">Folder uploads preserve relative paths and understand Dataset Card YAML, declarative configs, conventional splits, sharded filenames, and ImageFolder layouts.</p>
        <p className="mt-3 text-xs leading-5 text-slate-500">Full huggingface_hub protocol compatibility is intentionally not claimed by this release.</p>
      </section>
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
  const [params, setParams] = useSearchParams();
  const [repository, setRepository] = useState<Dataset | null>(null);
  const [revision, setRevision] = useState<Revision | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const selectedRevision = params.get("revision") ?? repository?.latest_revision?.revision_id;
  const basePath = `/datasets/${namespace}/${dataset}`;

  const reloadRepository = () => {
    setLoading(true); setError("");
    void Promise.all([api.dataset(namespace, dataset), api.revisions(namespace, dataset)])
      .then(([nextRepository, nextRevisions]) => { setRepository(nextRepository); setRevisions(nextRevisions); })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Could not load dataset."))
      .finally(() => setLoading(false));
  };
  useEffect(reloadRepository, [dataset, namespace]);

  useEffect(() => {
    if (!selectedRevision) { setRevision(null); return; }
    setRevision(null);
    void api.revision(namespace, dataset, selectedRevision).then(setRevision).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load revision.");
    });
  }, [dataset, namespace, selectedRevision]);

  const selectedParams = useMemo(() => {
    const next = new URLSearchParams(params);
    if (selectedRevision) next.set("revision", selectedRevision);
    return next;
  }, [params, selectedRevision]);

  if (loading) return <div className="mx-auto max-w-7xl p-6"><LoadingState /></div>;
  if (error || !repository) return <div className="mx-auto max-w-5xl p-6"><ErrorState message={error || "Dataset not found."} retry={reloadRepository} /></div>;

  const changeRevision = (value: string) => {
    const next = new URLSearchParams(params); next.set("revision", value); setParams(next);
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-[#fffefa]">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-6 py-3">
          <Brand />
          <Link className="text-xs font-semibold text-slate-500 hover:text-teal-800" to="/">All datasets</Link>
        </div>
      </header>
      <main>
        <section className="border-b border-slate-200 bg-white">
          <div className="mx-auto max-w-[1500px] px-6 pt-8">
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="flex items-start gap-4">
                <span className="grid size-12 place-items-center rounded-2xl bg-teal-900 text-amber-200"><Database className="size-6" /></span>
                <div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
                    <span>{namespace}</span><span>/</span><span className="status-pill"><LockKeyhole className="size-3" /> {repository.visibility}</span>
                  </div>
                  <h1 className="mt-1 text-3xl font-semibold tracking-[-0.035em] text-slate-950">{dataset}</h1>
                  <p className="mt-2 max-w-2xl text-sm text-slate-500">{repository.description || "No description yet."}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {revisions.length ? (
                  <label className="select-label">
                    <GitCommitHorizontal className="size-3" /><span>Revision</span>
                    <select value={selectedRevision} onChange={(event) => changeRevision(event.target.value)}>
                      {revisions.map((item) => <option key={item.revision_id} value={item.revision_id}>{item.revision_id}</option>)}
                    </select><ChevronDown className="size-3" />
                  </label>
                ) : null}
                <button className="button-primary" type="button" onClick={() => setUploadOpen(true)}><UploadCloud className="size-4" /> Upload revision</button>
              </div>
            </div>
            <nav className="mt-8 flex gap-1 overflow-x-auto" aria-label="Dataset sections">
              {tabs.map((tab) => (
                <NavLink
                  className={({ isActive }) => `tab-link ${isActive ? "tab-link-active" : ""}`}
                  end={tab.end}
                  key={tab.to}
                  to={{ pathname: tab.to, search: selectedParams.toString() }}
                >
                  <tab.icon className="size-4" /> {tab.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </section>
        <section className="mx-auto max-w-[1500px] px-6 py-7">
          {!revision ? (
            <EmptyState title="No published revision" description="Upload a Hugging Face-compatible folder to create the first immutable revision." action={<button className="button-primary" type="button" onClick={() => setUploadOpen(true)}><UploadCloud className="size-4" /> Upload folder</button>} />
          ) : (
            <Routes>
              <Route index element={<CardTab revision={revision} openUpload={() => setUploadOpen(true)} />} />
              <Route path="viewer" element={<ViewerTab namespace={namespace} dataset={dataset} revision={revision} basePath={basePath} />} />
              <Route path="viewer/:configName/:splitName" element={<ViewerTab namespace={namespace} dataset={dataset} revision={revision} basePath={basePath} />} />
              <Route path="files" element={<FilesTab namespace={namespace} dataset={dataset} revision={revision} />} />
              <Route path="schema" element={<SchemaTab revision={revision} />} />
              <Route path="statistics" element={<StatisticsTab namespace={namespace} dataset={dataset} revision={revision} />} />
              <Route path="versions" element={<VersionsTab revisions={revisions} selected={revision.revision_id} />} />
              <Route path="settings" element={<SettingsTab dataset={repository} />} />
              <Route path="*" element={<Navigate to={{ pathname: basePath, search: selectedParams.toString() }} replace />} />
            </Routes>
          )}
        </section>
      </main>
      <UploadDialog namespace={namespace} dataset={dataset} open={uploadOpen} onClose={() => setUploadOpen(false)} onComplete={(nextRevision) => { setUploadOpen(false); setRevision(nextRevision); reloadRepository(); changeRevision(nextRevision.revision_id); }} />
    </div>
  );
}
