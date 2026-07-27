export type Visibility = "private" | "internal" | "public";
export type RevisionStatus = "uploading" | "validating" | "indexing" | "ready" | "failed";

export interface RevisionSummary {
  revision_id: string;
  git_commit?: string | null;
  dvc_revision?: string | null;
  source_object_set_checksum?: string | null;
  branch: string;
  commit_message: string;
  status: RevisionStatus;
  manifest_sha256: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface Dataset {
  id: string;
  namespace: string;
  slug: string;
  visibility: Visibility;
  description: string;
  default_branch: string;
  created_at: string;
  updated_at: string;
  owner: string | null;
  can_edit: boolean;
  latest_revision: RevisionSummary | null;
}

export interface User {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface RepositoryFile {
  path: string;
  size_bytes: number;
  sha256: string;
  media_type: string;
  is_previewable: boolean;
}

export interface FilePage {
  items: RepositoryFile[];
  total: number;
  offset: number;
  limit: number;
}

export interface FieldSchema {
  name: string;
  type: string;
  nullable: boolean;
}

export interface DatasetSplit {
  name: string;
  data_files: string[];
  num_rows: number | null;
  num_bytes: number;
  schema: FieldSchema[];
}

export interface DatasetConfig {
  name: string;
  builder_name: string;
  builder_parameters: Record<string, unknown>;
  splits: DatasetSplit[];
}

export interface Revision extends RevisionSummary {
  card_markdown: string;
  card_html: string;
  card_metadata: Record<string, unknown>;
  files: RepositoryFile[];
  configs: DatasetConfig[];
}

export interface ViewerResponse {
  repository: string;
  revision: string;
  config: string;
  split: string;
  offset: number;
  limit: number;
  total_rows: number | null;
  available_rows: number;
  rows: Record<string, unknown>[];
  schema: FieldSchema[];
  capabilities: Record<string, boolean>;
}

export interface Problem {
  title: string;
  detail: string;
  status: number;
  code: string;
}
