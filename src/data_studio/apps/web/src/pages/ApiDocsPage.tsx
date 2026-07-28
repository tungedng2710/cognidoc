import {
  ArrowLeft,
  BookOpenText,
  Braces,
  Check,
  Copy,
  Download,
  KeyRound,
  ListTree,
  UploadCloud,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AccountControls } from "../components/Auth";
import { Brand } from "../components/Brand";

function CodeBlock({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2_000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="relative mt-4">
      <pre className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950 p-4 pr-24 text-[13px] leading-6 text-cyan-100 shadow-inner">
        <code>{children}</code>
      </pre>
      <button
        className="absolute top-3 right-3 inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-white/10 bg-white/8 px-2.5 text-xs font-semibold text-slate-300 transition hover:bg-white/15 hover:text-white"
        type="button"
        onClick={() => void copy()}
        aria-label="Copy code"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function InlineCode({ children }: { children: string }) {
  return <code className="rounded bg-slate-100 px-1.5 py-0.5">{children}</code>;
}

const apiRoot = `${window.location.origin}/api/v1`;

export function ApiDocsPage() {
  return (
    <div className="min-h-screen">
      <header className="app-header sticky top-0 z-30">
        <div className="page-shell flex items-center justify-between py-2.5">
          <Brand />
          <div className="flex items-center gap-2">
            <Link
              className="inline-flex min-h-9 items-center gap-2 rounded-xl border border-white/15 px-3 text-xs font-semibold text-slate-200 transition hover:bg-white/10 hover:text-white"
              to="/"
            >
              <ArrowLeft className="size-4" /> <span className="hidden sm:inline">All datasets</span>
            </Link>
            <AccountControls />
          </div>
        </div>
      </header>

      <main className="page-shell py-7 lg:py-9">
        <section className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-7 py-8 text-white shadow-2xl shadow-slate-950/15 sm:px-10">
          <div className="pointer-events-none absolute -top-32 right-0 size-80 rounded-full bg-indigo-500/25 blur-3xl" />
          <div className="relative max-w-4xl">
            <p className="flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] text-cyan-300 uppercase">
              <BookOpenText className="size-3.5" /> Friendly API recipes
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
              Start using the API in minutes
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
              Set up a token once, then use short, copy-pasteable commands to create, upload,
              inspect, and download a dataset.
            </p>
            <div className="mt-5 inline-flex rounded-xl border border-white/10 bg-white/8 px-3 py-2 font-mono text-xs text-cyan-100">
              {apiRoot}
            </div>
          </div>
        </section>

        <div className="mt-7 grid items-start gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="surface-panel hidden p-4 xl:sticky xl:top-20 xl:block" aria-label="API guide sections">
            <p className="px-3 pb-2 text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase">Quick recipes</p>
            {[
              ["setup", "One-time setup"],
              ["create", "Create a dataset"],
              ["upload", "Upload files"],
              ["browse", "Browse data"],
              ["download", "Download"],
              ["tips", "Useful tips"],
            ].map(([id, label]) => (
              <a className="block rounded-xl px-3 py-2 text-sm font-medium text-slate-600 hover:bg-indigo-50 hover:text-indigo-700" href={`#${id}`} key={id}>{label}</a>
            ))}
          </nav>

          <article className="space-y-6">
            <section className="surface-panel p-6 lg:p-8" id="setup">
              <div className="flex items-center gap-3">
                <KeyRound className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">1. One-time setup</h2>
              </div>
              <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-600">
                <li>Sign in, open <Link className="font-semibold text-indigo-600 hover:text-indigo-500" to="/settings">Account settings</Link>, and generate a personal API token.</li>
                <li>Copy the token when it appears—it is shown only once.</li>
                <li>Paste it below and choose the dataset path you want to use.</li>
              </ol>
              <CodeBlock>{`export API=${apiRoot}
export TOKEN='ds_pat_paste_your_token_here'
export DATASET=owner/sentiment-demo

ds() {
  curl \
    --fail-with-body \
    --silent \
    --show-error \
    --header "Authorization: Bearer $TOKEN" \
    "$@"
}

ds_json() {
  ds \
    --header 'Content-Type: application/json' \
    "$@"
}
`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                The <InlineCode>ds</InlineCode> helper adds your token automatically.
                <InlineCode>ds_json</InlineCode> also marks a request as JSON. The examples use
                <InlineCode>jq</InlineCode> only to make responses easier to read.
              </p>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="create">
              <div className="flex items-center gap-3">
                <Braces className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">2. Create a dataset</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                The namespace is usually your username. Visibility can be
                <InlineCode>private</InlineCode>, <InlineCode>internal</InlineCode>, or
                <InlineCode>public</InlineCode>.
              </p>
              <CodeBlock>{`ds_json \
  --data '{
    "namespace": "owner",
    "slug": "sentiment-demo",
    "visibility": "private",
    "description": "Sentiment examples"
  }' \
  "$API/datasets" \
  | jq`}</CodeBlock>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="upload">
              <div className="flex items-center gap-3">
                <UploadCloud className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">3. Upload and publish</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                An upload has three small steps. This example sends a Dataset Card and one Parquet
                file while preserving their repository paths.
              </p>
              <CodeBlock>{`UPLOAD=$(
  ds_json \
    --data '{"commit_message":"Initial import"}' \
    "$API/datasets/$DATASET/uploads" \
  | jq --raw-output '.id'
)

ds \
  --form 'files=@README.md' \
  --form 'paths=README.md' \
  --form 'files=@data/train.parquet' \
  --form 'paths=data/train.parquet' \
  "$API/uploads/$UPLOAD/files" \
  | jq

REVISION=$(
  ds_json \
    --data '{"expected_file_count":2}' \
    "$API/uploads/$UPLOAD/complete?include_files=false" \
  | jq --raw-output '.revision_id'
)

echo "Published revision: $REVISION"`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                Every <InlineCode>files</InlineCode> value needs a matching
                <InlineCode>paths</InlineCode> value. Send large folders in several requests, then
                publish once.
              </p>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="browse">
              <div className="flex items-center gap-3">
                <ListTree className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">4. Browse datasets and rows</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                List what you can access, inspect the detected configs and splits, then fetch ten
                preview rows.
              </p>
              <CodeBlock>{`# Visible datasets
ds \
  "$API/datasets" \
  | jq '.items[] | {
      name: (.namespace + "/" + .slug),
      visibility
    }'

# Available configs and splits
ds \
  --get \
  --data-urlencode 'revision=main' \
  "$API/datasets/$DATASET/configs" \
  | jq

# First 10 preview rows
ds \
  --get \
  --data-urlencode 'revision=main' \
  --data-urlencode 'limit=10' \
  "$API/datasets/$DATASET/viewer/default/train" \
  | jq '.rows'`}</CodeBlock>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="download">
              <div className="flex items-center gap-3">
                <Download className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">5. Download a repository</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Use <InlineCode>main</InlineCode> for the latest version, or replace it with an
                immutable revision ID for a reproducible download.
              </p>
              <CodeBlock>{`ds \
  --location \
  --output sentiment-demo.zip \
  "$API/datasets/$DATASET/archive/main"

unzip -l sentiment-demo.zip`}</CodeBlock>
              <p className="mt-4 text-sm leading-6 text-slate-500">
                The ZIP keeps the original Hugging Face-compatible folder layout. This REST
                workflow replaces <InlineCode>hf download</InlineCode>, which is not supported by
                this Studio.
              </p>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="tips">
              <div className="flex items-center gap-3">
                <BookOpenText className="size-5 text-indigo-600" />
                <h2 className="text-xl font-semibold">Useful tips</h2>
              </div>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
                <li>Public datasets can be read with ordinary <InlineCode>curl</InlineCode>; no token is needed.</li>
                <li>Use a read-only token for scripts that never upload or change data.</li>
                <li>Keep tokens out of shell history, source code, screenshots, and Git.</li>
                <li>API errors include a readable <InlineCode>detail</InlineCode> and stable <InlineCode>code</InlineCode>.</li>
              </ul>
              <p className="mt-5 text-sm leading-6 text-slate-500">
                For filtering, individual file downloads, updates, deletion, and cookie-based
                login, see <InlineCode>docs/API_USAGE.md</InlineCode> in the repository.
              </p>
            </section>
          </article>
        </div>
      </main>
    </div>
  );
}
