import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.endsWith("/auth/me")) {
          return Promise.resolve({
            ok: false,
            status: 401,
            statusText: "Unauthorized",
            json: () => Promise.resolve({ detail: "Sign in", status: 401 }),
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }),
    );
  });

  it("prompts an anonymous user to create an account", async () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Create your account" })).toBeInTheDocument();
  });

  it("renders the empty dataset hub state", async () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "TonAI Data Studio home" })).toBeInTheDocument();
    expect(await screen.findByText("Your datasets, legible and versioned.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Repositories" })).toBeInTheDocument();
    expect(await screen.findByText("Create your first dataset")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "API guide" })).toHaveAttribute("href", "/docs/api");
  });

  it("renders the API usage guide", async () => {
    render(<MemoryRouter initialEntries={["/docs/api"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Data Studio API guide" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3. Upload and publish" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "5. Pull a complete repository" })).toBeInTheDocument();
  });

  it("highlights the active workspace tab", async () => {
    const createdAt = "2026-07-22T08:00:00Z";
    const summary = {
      revision_id: "abc123",
      branch: "main",
      commit_message: "Initial import",
      status: "ready",
      manifest_sha256: "0".repeat(64),
      error_code: null,
      error_message: null,
      created_at: createdAt,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        let body: unknown;
        if (url.endsWith("/auth/me")) {
          return Promise.resolve({
            ok: false,
            status: 401,
            statusText: "Unauthorized",
            json: () => Promise.resolve({ detail: "Sign in", status: 401 }),
          });
        } else if (url.includes("/revisions/abc123")) {
          body = {
            ...summary,
            card_markdown: "",
            card_html: "",
            card_metadata: {},
            files: [],
            configs: [],
          };
        } else if (url.endsWith("/revisions")) {
          body = [summary];
        } else if (url.includes("/tree/abc123/page")) {
          body = { items: [], total: 0, offset: 0, limit: 100 };
        } else {
          body = {
            id: "dataset-id",
            namespace: "research",
            slug: "demo",
            visibility: "private",
            description: "Demo dataset",
            default_branch: "main",
            created_at: createdAt,
            updated_at: createdAt,
            owner: "research",
            can_edit: false,
            latest_revision: summary,
          };
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      }),
    );

    render(
      <MemoryRouter initialEntries={["/datasets/research/demo/files?revision=abc123"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Repository files")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Files" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dataset card" })).not.toHaveAttribute("aria-current");
  });

  it("lets an owner rename and delete a dataset before its first revision", async () => {
    let currentSlug = "test-dataset";
    const datasetPayload = () => ({
      id: "dataset-id",
      namespace: "owner",
      slug: currentSlug,
      visibility: "private",
      description: "",
      default_branch: "main",
      created_at: "2026-07-22T08:00:00Z",
      updated_at: "2026-07-22T08:00:00Z",
      owner: "owner",
      can_edit: true,
      latest_revision: null,
    });
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/me")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            id: "owner-id",
            username: "owner",
            display_name: "Owner",
            email: null,
            is_admin: false,
            created_at: "2026-07-22T08:00:00Z",
          }),
        });
      }
      if (init?.method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
      }
      if (init?.method === "PATCH") {
        const body = typeof init.body === "string" ? init.body : "{}";
        currentSlug = (JSON.parse(body) as { slug: string }).slug;
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(datasetPayload()) });
      }
      if (url.endsWith("/revisions")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (url.endsWith("/datasets")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(datasetPayload()),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/datasets/owner/test-dataset/settings"]}>
        <App />
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByRole("textbox", { name: /Dataset name/ }), {
      target: { value: "renamed-dataset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/datasets/owner/test-dataset",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            slug: "renamed-dataset",
            description: "",
            visibility: "private",
          }),
        }),
      );
    });

    expect(await screen.findByRole("heading", { name: "renamed-dataset" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Delete dataset" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Confirm dataset name" }), {
      target: { value: "renamed-dataset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Permanently delete" }));

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/datasets/owner/renamed-dataset",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });
});
