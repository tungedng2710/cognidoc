import type {
  Dataset,
  DatasetConfig,
  Problem,
  Revision,
  RevisionSummary,
  ViewerResponse,
  Visibility,
} from "./types";

const API_ROOT = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const fallback: Problem = {
      title: "Request failed",
      detail: `${response.status} ${response.statusText}`,
      status: response.status,
      code: "request_failed",
    };
    const problem = (await response.json().catch(() => fallback)) as Problem;
    throw new ApiError(problem);
  }
  return (await response.json()) as T;
}

export const api = {
  async listDatasets(): Promise<Dataset[]> {
    const response = await request<{ items: Dataset[] }>("/datasets");
    return response.items;
  },

  createDataset(body: {
    namespace: string;
    slug: string;
    visibility: Visibility;
    description: string;
  }): Promise<Dataset> {
    return request("/datasets", { method: "POST", body: JSON.stringify(body) });
  },

  dataset(namespace: string, dataset: string): Promise<Dataset> {
    return request(`/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}`);
  },

  revision(namespace: string, dataset: string, revision = "main"): Promise<Revision> {
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/revisions/${encodeURIComponent(revision)}`,
    );
  },

  revisions(namespace: string, dataset: string): Promise<RevisionSummary[]> {
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/revisions`,
    );
  },

  configs(namespace: string, dataset: string, revision: string): Promise<DatasetConfig[]> {
    const params = new URLSearchParams({ revision });
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/configs?${params}`,
    );
  },

  viewer(
    namespace: string,
    dataset: string,
    config: string,
    split: string,
    options: { revision: string; offset?: number; limit?: number; filter?: string },
  ): Promise<ViewerResponse> {
    const params = new URLSearchParams({
      revision: options.revision,
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 100),
    });
    if (options.filter) params.set("filter", options.filter);
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/viewer/${encodeURIComponent(config)}/${encodeURIComponent(split)}?${params}`,
    );
  },

  statistics(
    namespace: string,
    dataset: string,
    config: string,
    split: string,
    revision: string,
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams({ revision });
    return request(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/statistics/${encodeURIComponent(config)}/${encodeURIComponent(split)}?${params}`,
    );
  },

  async uploadFolder(
    namespace: string,
    dataset: string,
    files: File[],
    onProgress: (message: string) => void,
  ): Promise<Revision> {
    onProgress("Creating upload session…");
    const upload = await request<{ id: string }>(
      `/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/uploads`,
      { method: "POST", body: JSON.stringify({ commit_message: "Upload dataset folder" }) },
    );
    const form = new FormData();
    for (const file of files) {
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
      const pathParts = relative?.split("/") ?? [];
      const path = pathParts.length > 1 ? pathParts.slice(1).join("/") : file.name;
      form.append("files", file, file.name);
      form.append("paths", path);
    }
    onProgress(`Uploading ${files.length.toLocaleString()} files…`);
    await request(`/uploads/${upload.id}/files`, { method: "POST", body: form });
    onProgress("Validating card, layout, and previews…");
    return request(`/uploads/${upload.id}/complete`, {
      method: "POST",
      body: JSON.stringify({ expected_file_count: files.length }),
    });
  },

  blobUrl(
    namespace: string,
    dataset: string,
    revision: string,
    path: string,
    inline = false,
  ): string {
    const encodedPath = path.split("/").map(encodeURIComponent).join("/");
    const suffix = inline ? "?inline=true" : "";
    return `${API_ROOT}/datasets/${encodeURIComponent(namespace)}/${encodeURIComponent(dataset)}/blob/${encodeURIComponent(revision)}/${encodedPath}${suffix}`;
  },
};
