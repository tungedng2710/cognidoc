import { Search, UserRound, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import type { PublicUser } from "../types";
import { UserAvatar } from "./UserAvatar";

export function UserSearch({ className = "" }: { className?: string }) {
  const navigate = useNavigate();
  const resultsId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) {
      setResults([]);
      setLoading(false);
      return;
    }
    let current = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void api.searchUsers(normalized)
        .then((users) => {
          if (current) setResults(users);
        })
        .catch(() => {
          if (current) setResults([]);
        })
        .finally(() => {
          if (current) setLoading(false);
        });
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!focused) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setFocused(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [focused]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const exact = results.find(
      (candidate) => candidate.username.toLowerCase() === query.trim().toLowerCase(),
    );
    const destination = exact ?? results[0];
    if (destination) {
      setFocused(false);
      void navigate(`/users/${encodeURIComponent(destination.username)}`);
    }
  };

  const open = focused && query.trim().length > 0;

  return (
    <div className={`relative ${className}`} ref={rootRef}>
      <form onSubmit={submit} role="search">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
        <input
          aria-label="Search users"
          aria-expanded={open}
          aria-controls={resultsId}
          autoComplete="off"
          className="block h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pr-9 pl-9 text-sm text-slate-900 shadow-xs outline-none transition placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-3 focus:ring-indigo-500/10"
          placeholder="Search users"
          role="combobox"
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setFocused(true);
          }}
          onFocus={() => setFocused(true)}
          onKeyDown={(event) => {
            if (event.key === "Escape") setFocused(false);
          }}
        />
        {query ? (
          <button
            aria-label="Clear user search"
            className="absolute top-1/2 right-2 grid size-6 -translate-y-1/2 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            type="button"
            onClick={() => {
              setQuery("");
              setResults([]);
            }}
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </form>

      {open ? (
        <div
          className="absolute top-full right-0 left-0 z-50 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-950/10"
          id={resultsId}
        >
          {loading ? (
            <p className="px-3 py-3 text-sm text-slate-500">Searching people…</p>
          ) : results.length ? (
            <ul aria-label="User search results" role="listbox">
              {results.map((candidate) => (
                <li key={candidate.username} role="option" aria-selected="false">
                  <Link
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 transition hover:bg-indigo-50"
                    to={`/users/${encodeURIComponent(candidate.username)}`}
                    onClick={() => {
                      setFocused(false);
                      setQuery("");
                    }}
                  >
                    <UserAvatar className="size-9" user={candidate} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-slate-900">
                        {candidate.display_name || candidate.username}
                      </span>
                      <span className="block truncate text-xs text-slate-500">
                        @{candidate.username}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="flex items-center gap-2 px-3 py-3 text-sm text-slate-500">
              <UserRound className="size-4" /> No users found
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
