import { AlertTriangle, DatabaseZap, LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading dataset…" }: { label?: string }) {
  return (
    <div className="grid min-h-64 place-items-center rounded-3xl border border-dashed border-slate-200 bg-white/60">
      <div className="flex flex-col items-center gap-3 text-sm font-medium text-slate-500">
        <LoaderCircle className="size-6 animate-spin text-teal-700" aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="rounded-3xl border border-rose-200 bg-rose-50 p-7 text-rose-950">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <div>
          <h2 className="font-semibold">Something needs attention</h2>
          <p className="mt-1 text-sm text-rose-800">{message}</p>
          {retry ? (
            <button className="button-secondary mt-4" type="button" onClick={retry}>
              Try again
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-72 place-items-center rounded-3xl border border-dashed border-slate-300 bg-white/70 px-6 text-center">
      <div className="max-w-md">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800">
          <DatabaseZap className="size-6" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-950">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </div>
  );
}

