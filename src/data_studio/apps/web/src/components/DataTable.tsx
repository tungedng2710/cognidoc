import { useVirtualizer } from "@tanstack/react-virtual";
import { Check, Copy, ImageIcon } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "../api";
import type { FieldSchema } from "../types";

function isImageReference(value: unknown): value is { _type: "image"; path: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "_type" in value &&
    value._type === "image" &&
    "path" in value &&
    typeof value.path === "string"
  );
}

function Cell({
  value,
  namespace,
  dataset,
  revision,
}: {
  value: unknown;
  namespace: string;
  dataset: string;
  revision: string;
}) {
  if (value === null || value === undefined) return <span className="text-slate-300">null</span>;
  if (typeof value === "string") {
    return <span className="block max-w-72 truncate" title={value}>{value}</span>;
  }
  if (isImageReference(value)) {
    return (
      <a
        className="flex items-center gap-2 text-teal-800 hover:underline"
        href={api.blobUrl(namespace, dataset, revision, value.path, true)}
        target="_blank"
        rel="noreferrer"
      >
        <span className="grid size-8 place-items-center overflow-hidden rounded-lg bg-teal-50">
          <img
            className="size-full object-cover"
            src={api.blobUrl(namespace, dataset, revision, value.path, true)}
            alt="Dataset preview"
            loading="lazy"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
          <ImageIcon className="absolute size-4" />
        </span>
        <span className="max-w-40 truncate">{value.path}</span>
      </a>
    );
  }
  if (typeof value === "object") {
    const formatted = JSON.stringify(value, null, 2);
    return (
      <details>
        <summary className="max-w-52 cursor-pointer truncate font-mono text-xs text-violet-700">
          {JSON.stringify(value)}
        </summary>
        <pre className="absolute z-20 mt-2 max-h-72 max-w-lg overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100 shadow-xl">
          {formatted}
        </pre>
      </details>
    );
  }
  if (typeof value === "boolean") {
    return <span className="font-mono text-violet-700">{value ? "true" : "false"}</span>;
  }
  if (typeof value === "number") return <span className="font-mono text-blue-700">{value}</span>;
  if (typeof value === "bigint") {
    return <span className="font-mono text-blue-700">{value.toString()}</span>;
  }
  if (typeof value === "symbol") return <span>{value.description ?? "symbol"}</span>;
  if (typeof value === "function") return <span className="text-slate-400">[function]</span>;
  return <span className="text-slate-400">[unsupported value]</span>;
}

interface DataTableProps {
  rows: Record<string, unknown>[];
  schema: FieldSchema[];
  namespace: string;
  dataset: string;
  revision: string;
}

export function DataTable({ rows, schema, namespace, dataset, revision }: DataTableProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const columns = schema.length ? schema.map((field) => field.name) : Object.keys(rows[0] ?? {});
  const gridTemplateColumns = `64px repeat(${columns.length}, minmax(190px, 1fr))`;
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => viewportRef.current,
    estimateSize: () => 52,
    overscan: 8,
  });

  const copyRow = async (index: number) => {
    await navigator.clipboard.writeText(JSON.stringify(rows[index], null, 2));
    setCopied(index);
    window.setTimeout(() => setCopied(null), 1_200);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="overflow-x-auto border-b border-slate-200 bg-slate-50">
        <div className="grid min-w-max text-xs font-semibold text-slate-500" style={{ gridTemplateColumns }}>
          <div className="px-4 py-3">#</div>
          {columns.map((column) => {
            const field = schema.find((item) => item.name === column);
            return (
              <div className="border-l border-slate-200 px-4 py-3" key={column}>
                <span className="text-slate-900">{column}</span>
                <span className="ml-2 font-mono text-[10px] font-normal text-teal-700">
                  {field?.type ?? "unknown"}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <div ref={viewportRef} className="h-[520px] overflow-auto">
        <div className="relative min-w-max" style={{ height: rowVirtualizer.getTotalSize() }}>
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const row = rows[virtualRow.index];
            if (!row) return null;
            return (
              <div
                className="absolute top-0 left-0 grid w-full items-center border-b border-slate-100 bg-white text-sm hover:bg-amber-50/40"
                key={virtualRow.key}
                style={{
                  gridTemplateColumns,
                  height: virtualRow.size,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <div className="flex items-center justify-between px-3 font-mono text-xs text-slate-400">
                  {virtualRow.index + 1}
                  <button
                    className="rounded p-1 hover:bg-slate-100 hover:text-slate-800"
                    type="button"
                    onClick={() => void copyRow(virtualRow.index)}
                    aria-label={`Copy row ${virtualRow.index + 1} as JSON`}
                  >
                    {copied === virtualRow.index ? <Check className="size-3" /> : <Copy className="size-3" />}
                  </button>
                </div>
                {columns.map((column) => (
                  <div className="border-l border-slate-100 px-4 py-3" key={column}>
                    <Cell
                      value={row[column]}
                      namespace={namespace}
                      dataset={dataset}
                      revision={revision}
                    />
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
