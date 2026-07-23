import { ArrowLeft, BookOpenText, Braces, KeyRound, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

import { AccountControls } from "../components/Auth";
import { Brand } from "../components/Brand";

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="mt-4 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950 p-4 text-[13px] leading-6 text-cyan-100 shadow-inner">
      <code>{children}</code>
    </pre>
  );
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
              <BookOpenText className="size-3.5" /> Developer documentation
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">Data Studio API guide</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
              Authenticate, create a repository, upload a Hugging Face-compatible folder, publish an immutable revision, and query its preview through the REST API.
            </p>
            <div className="mt-5 inline-flex rounded-xl border border-white/10 bg-white/8 px-3 py-2 font-mono text-xs text-cyan-100">
              {apiRoot}
            </div>
          </div>
        </section>

        <div className="mt-7 grid items-start gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
          <nav className="surface-panel hidden p-4 xl:sticky xl:top-20 xl:block" aria-label="API guide sections">
            <p className="px-3 pb-2 text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase">On this page</p>
            {[
              ["authentication", "Authentication"],
              ["create", "Create dataset"],
              ["upload", "Upload folder"],
              ["browse", "Browse data"],
            ].map(([id, label]) => (
              <a className="block rounded-xl px-3 py-2 text-sm font-medium text-slate-600 hover:bg-indigo-50 hover:text-indigo-700" href={`#${id}`} key={id}>{label}</a>
            ))}
          </nav>

          <article className="space-y-6">
            <section className="surface-panel p-6 lg:p-8" id="authentication">
              <div className="flex items-center gap-3"><KeyRound className="size-5 text-indigo-600" /><h2 className="text-xl font-semibold">1. Authenticate</h2></div>
              <p className="mt-3 text-sm leading-6 text-slate-600">Sign in with a cookie session, then create a personal token. The raw token is shown once.</p>
              <CodeBlock>{`export API=${apiRoot}\n\ncurl -c studio.cookies -H 'Content-Type: application/json' \\\n+  -d '{"username":"owner","password":"your-password"}' \\\n+  "$API/auth/login"\n\nexport TOKEN=$(curl -sS -b studio.cookies \\\n+  -H 'Content-Type: application/json' \\\n+  -d '{"name":"cli","scopes":["read","write"]}' \\\n+  "$API/auth/tokens" | jq -r .token)`}</CodeBlock>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="create">
              <div className="flex items-center gap-3"><Braces className="size-5 text-indigo-600" /><h2 className="text-xl font-semibold">2. Create a dataset</h2></div>
              <p className="mt-3 text-sm leading-6 text-slate-600">Use <code className="rounded bg-slate-100 px-1.5 py-0.5">private</code>, <code className="rounded bg-slate-100 px-1.5 py-0.5">internal</code>, or <code className="rounded bg-slate-100 px-1.5 py-0.5">public</code> visibility.</p>
              <CodeBlock>{`curl -H "Authorization: Bearer $TOKEN" \\\n+  -H 'Content-Type: application/json' \\\n+  -d '{"namespace":"owner","slug":"sentiment-demo","visibility":"private"}' \\\n+  "$API/datasets"`}</CodeBlock>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="upload">
              <div className="flex items-center gap-3"><UploadCloud className="size-5 text-indigo-600" /><h2 className="text-xl font-semibold">3. Upload and publish</h2></div>
              <p className="mt-3 text-sm leading-6 text-slate-600">Create an upload, send files with matching relative POSIX paths, then complete it.</p>
              <CodeBlock>{`UPLOAD_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \\\n+  -H 'Content-Type: application/json' -d '{"commit_message":"Initial import"}' \\\n+  "$API/datasets/owner/sentiment-demo/uploads" | jq -r .id)\n\ncurl -H "Authorization: Bearer $TOKEN" \\\n+  -F 'files=@README.md' -F 'files=@data/train.parquet' \\\n+  -F 'paths=README.md' -F 'paths=data/train.parquet' \\\n+  "$API/uploads/$UPLOAD_ID/files"\n\ncurl -H "Authorization: Bearer $TOKEN" \\\n+  -H 'Content-Type: application/json' -d '{"expected_file_count":2}' \\\n+  "$API/uploads/$UPLOAD_ID/complete"`}</CodeBlock>
            </section>

            <section className="surface-panel p-6 lg:p-8" id="browse">
              <div className="flex items-center gap-3"><BookOpenText className="size-5 text-indigo-600" /><h2 className="text-xl font-semibold">4. Browse preview rows</h2></div>
              <p className="mt-3 text-sm leading-6 text-slate-600">Public datasets need no token. Private and internal reads include the bearer header.</p>
              <CodeBlock>{`curl -H "Authorization: Bearer $TOKEN" \\\n+  "$API/datasets/owner/sentiment-demo"\n\ncurl -G -H "Authorization: Bearer $TOKEN" \\\n+  --data-urlencode 'revision=main' \\\n+  --data-urlencode 'limit=50' \\\n+  "$API/datasets/owner/sentiment-demo/viewer/default/train"`}</CodeBlock>
              <p className="mt-5 text-sm leading-6 text-slate-500">
                The repository also includes a detailed <code className="rounded bg-slate-100 px-1.5 py-0.5">docs/API_USAGE.md</code> reference covering filtering, downloads, updates, deletion, and problem responses.
              </p>
            </section>
          </article>
        </div>
      </main>
    </div>
  );
}
