# Project Activity Timeline & Audit Explorer V0 — PR #23

## Why this exists

A PM needs one trustworthy answer to: **What happened, when, who initiated it,
what changed, and what evidence can I review?** The timeline is an indexed,
read-only view across existing PMWizard data. It does not create an alternate
source of project truth, make decisions, or mutate state.

## Sources

| Category | Source table | Time used | Attribution |
| --- | --- | --- | --- |
| `event` | `events` | `occurred_at` | event actor or system |
| `human_review` | `human_reviews` | `reviewed_at` | human reviewer |
| `audit` | `audit_log` | `created_at` | actor or system |
| `source_run` | `connector_runs` | `finished_at` | worker |
| `automation_run` | `automation_runs` | `started_at` | worker |
| `health_snapshot` | `project_health_snapshots` | `captured_at` | human or worker |

The six sources have deterministic ordering by (UTC event time, category,
record UUID), descending. All rows come from the requested tenant and project.
Results are queried in bounded batches (at most `limit + 1` per source).

## API

`GET /v1/projects/{project_id}/activity`

Requires project membership and `project:read` with Bearer authentication,
or explicit trusted-header permissions in test/development mode.

Optional query parameters:

- `category` — repeatable: `event`, `human_review`, `audit`, `source_run`,
  `automation_run`, `health_snapshot`.
- `actor_id` — UUID for a human actor. Worker-only records do not match this filter.
- `since`, `until` — inclusive ISO 8601 datetimes with timezone offsets.
- `limit` — 1–100 (default 40).
- `cursor` — opaque, URL-safe pagination position emitted as `next_cursor`.

Example:

```http
GET /v1/projects/{project_id}/activity?category=audit&category=human_review&limit=40
Authorization: Bearer <access-token>
```

Response:

```json
{
  "project_id": "<uuid>",
  "count": 1,
  "items": [
    {
      "id": "<uuid>",
      "category": "human_review",
      "occurred_at": "2026-10-30T19:00:00Z",
      "actor_kind": "human",
      "actor_id": "<uuid>",
      "action": "suggestion_reviewed",
      "entity_type": "AISuggestion",
      "entity_id": "<uuid>",
      "status": "accepted",
      "summary": "Human review of an AI-proposed change.",
      "changed_fields": [],
      "evidence_ids": []
    }
  ],
  "next_cursor": null
}
```

Web: select **Activity Timeline** in the project sidebar. The BFF endpoint
`/api/activity` always obtains the project ID and bearer token from the
authenticated HTTP-only session. The browser cannot switch project scope by
injecting a project ID.

## Security and redaction

- No raw `previous_state`, `final_state`, `proposed_state`,
  `previous_value`, `new_value`, suggestion reason, reviewer note,
  source errors, connectors' credential references, worker IDs or raw health
  snapshot JSON are serialized.
- Changed fields are **names only**, restricted to a fixed allowlist. Values
  are never returned.
- Evidence references are resolved within the same tenant/project and
  returned only if the evidence `permission_scope` is a subset of the
  current project permissions. Hidden evidence IDs are omitted.
- This is a *metadata explorer*, not an evidence-content viewer; existing
  evidence authorization remains authoritative.
- Failed connector/automation messages can carry secrets and are intentionally
  omitted. The returned status is safe operational metadata.
- No new database table or migration is needed. Existing audit records are
  not rewritten, and neither AI nor workers may bypass review.

## Implementation boundaries / next iteration

V0 focuses on a **single selected project**, safe chronology and operational
history. Cross-project export, signed evidence-detail links, cryptographically
verified audit chains, actor display-name enrichment, materialized timeline
indexes, and full-text search are deferred. For very large audit histories,
consider a database-side `UNION ALL` keyset index or a derived event projection.

## Tests

`pytest -q tests/test_project_activity.py`

Covers all six source types, deterministic ordering, cursor pagination,
category/actor/time filters, tenant and permission isolation, evidence scope
redaction and HTTP failure codes. All existing tests remain part of CI.
