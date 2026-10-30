"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { ActivityCategory, ActivityItem, ActivityTimeline } from "@/lib/types";

const CATEGORIES: { value: ActivityCategory | ""; label: string }[] = [
  { value: "", label: "All activity" },
  { value: "event", label: "Project events" },
  { value: "human_review", label: "Human reviews" },
  { value: "audit", label: "Audit log" },
  { value: "source_run", label: "Source syncs" },
  { value: "automation_run", label: "Automations" },
  { value: "health_snapshot", label: "Health snapshots" },
];

type Filters = {
  category: ActivityCategory | "";
  actorId: string;
  since: string;
  until: string;
};

const EMPTY_FILTERS: Filters = {
  category: "",
  actorId: "",
  since: "",
  until: "",
};

function pretty(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function queryFor(filters: Filters, cursor: string | null): string {
  const params = new URLSearchParams({ limit: "40" });
  if (filters.category) params.set("category", filters.category);
  if (filters.actorId.trim()) params.set("actor_id", filters.actorId.trim());
  if (filters.since) params.set("since", new Date(filters.since).toISOString());
  if (filters.until) params.set("until", new Date(filters.until).toISOString());
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

export function ActivityWorkspace() {
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const requestVersion = useRef(0);

  const loadPage = useCallback(
    async (cursor: string | null = null) => {
      const version = ++requestVersion.current;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/activity?${queryFor(filters, cursor)}`, {
          cache: "no-store",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === "string"
              ? payload.detail
              : `Activity request failed (${response.status})`,
          );
        }
        if (version !== requestVersion.current) return;
        const data = payload as ActivityTimeline;
        setItems((current) => (cursor ? [...current, ...data.items] : data.items));
        setNextCursor(data.next_cursor);
      } catch (reason) {
        if (version !== requestVersion.current) return;
        setError(
          reason instanceof Error ? reason.message : "Unable to load project activity.",
        );
      } finally {
        if (version === requestVersion.current) setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    void loadPage();
    return () => {
      requestVersion.current += 1;
    };
  }, [loadPage, refresh]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({ ...draft });
    setItems([]);
    setNextCursor(null);
  }

  function clearFilters() {
    setDraft(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setItems([]);
    setNextCursor(null);
    setRefresh((value) => value + 1);
  }

  return (
    <section className="activityWorkspace" aria-label="Project activity timeline">
      <div className="activityIntro">
        <div>
          <span className="eyebrow">Project Activity Timeline & Audit Explorer</span>
          <h2>What happened in this project?</h2>
          <p>
            Read-only chronology of governed changes, reviews, source syncs,
            automations and health captures. Sensitive payloads are never exposed.
          </p>
        </div>
        <button className="secondaryButton" type="button" onClick={() => setRefresh((v) => v + 1)}>
          Refresh
        </button>
      </div>

      <form className="activityFilters" onSubmit={applyFilters}>
        <label>
          Activity type
          <select
            value={draft.category}
            onChange={(event) =>
              setDraft((previous) => ({
                ...previous,
                category: event.target.value as ActivityCategory | "",
              }))
            }
          >
            {CATEGORIES.map((option) => (
              <option value={option.value} key={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Actor UUID
          <input
            type="text"
            value={draft.actorId}
            placeholder="Optional human actor"
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, actorId: event.target.value }))
            }
          />
        </label>
        <label>
          From
          <input
            type="datetime-local"
            value={draft.since}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, since: event.target.value }))
            }
          />
        </label>
        <label>
          Until
          <input
            type="datetime-local"
            value={draft.until}
            onChange={(event) =>
              setDraft((previous) => ({ ...previous, until: event.target.value }))
            }
          />
        </label>
        <div className="activityFilterActions">
          <button className="primaryButton" type="submit">Apply filters</button>
          <button className="secondaryButton" type="button" onClick={clearFilters}>
            Clear
          </button>
        </div>
      </form>

      {error && (
        <div className="activityError" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void loadPage()}>Retry</button>
        </div>
      )}

      {loading && items.length === 0 && <p className="activityEmpty">Loading activity…</p>}
      {!loading && !error && items.length === 0 && (
        <p className="activityEmpty">No activity matches these filters.</p>
      )}

      <ol className="activityTimeline">
        {items.map((item) => (
          <li key={`${item.category}:${item.id}`} className="activityEntry">
            <div className="activityEntryHeader">
              <span className="activityCategory">{pretty(item.category)}</span>
              <time dateTime={item.occurred_at}>{formatDate(item.occurred_at)}</time>
            </div>
            <div className="activityEntryTitle">
              <strong>{pretty(item.action)}</strong>
              {item.status && <span className="activityStatus">{pretty(item.status)}</span>}
            </div>
            {item.summary && <p>{item.summary}</p>}
            <div className="activityMeta">
              <span>By: {item.actor_kind}{item.actor_id ? ` (${item.actor_id})` : ""}</span>
              {item.entity_type && (
                <span>
                  Entity: {item.entity_type}
                  {item.entity_id ? ` / ${item.entity_id}` : ""}
                </span>
              )}
            </div>
            {item.changed_fields.length > 0 && (
              <p className="activityChanges">
                Changed fields: {item.changed_fields.map(pretty).join(", ")}
              </p>
            )}
            {item.evidence_ids.length > 0 && (
              <details className="activityEvidence">
                <summary>
                  {item.evidence_ids.length} authorized evidence reference(s)
                </summary>
                <ul>
                  {item.evidence_ids.map((id) => <li key={id}><code>{id}</code></li>)}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ol>

      {nextCursor && (
        <div className="activityLoadMore">
          <button
            className="secondaryButton"
            type="button"
            disabled={loading}
            onClick={() => void loadPage(nextCursor)}
          >
            {loading ? "Loading…" : "Load older activity"}
          </button>
        </div>
      )}
    </section>
  );
}
