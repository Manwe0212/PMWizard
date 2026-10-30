# Activity Export & Audit Evidence Reference Pack V0 — PR #24

PR #24 builds on the read-only Activity Timeline (PR #23). It makes
**permission-filtered, redacted metadata** exportable as CSV or JSON.

## User workflow

Open **Activity Timeline** for the selected project, apply category, actor or
date filters, and choose **Export CSV** or **Export JSON**. Only members with
both `project:read` and `project:review` may download an export.

The download is a snapshot of the matching timeline rows at export time,
ordered by the PR #23 keyset ordering. Existing source documents and underlying
audit states are *not* included.

## API

`GET /v1/projects/{project_id}/activity/export`

Accepted query parameters:

- `format=csv|json` (defaults to CSV)
- `category` (repeatable; same six categories as the timeline)
- `actor_id` (UUID; filters human actors only)
- `since` and `until` (inclusive ISO-8601 timestamps with timezone)

The Next.js BFF route is `GET /api/activity/export`. It derives `project_id`
and the Bearer token from the authenticated server session. It forwards only the
listed filters and never allows the browser to choose another project.

Responses set:

- `Content-Disposition: attachment; filename="pmwizard-activity-..."`
- `Cache-Control: private, no-store`
- `X-Content-Type-Options: nosniff`
- `X-PMWizard-Export-SHA256` (lowercase SHA-256 hex of the **response bytes**)
- `X-PMWizard-Export-Count` (number of exported rows)
- `X-PMWizard-Export-Truncated` (`true` when more rows exist beyond the cap)

A CSV has a fixed header:

```text
id,occurred_at,category,action,status,actor_kind,actor_id,entity_type,entity_id,summary,changed_fields,evidence_ids
```

`changed_fields` and `evidence_ids` are semicolon-separated values *inside
properly quoted CSV cells*. Potential formula-leading cells are prefixed with a
single quote to reduce spreadsheet formula injection risk, including leading
whitespace and common control prefixes. CSV export does **not** include raw
state values.

A JSON export includes:

```text
schema_version, generated_at, project_id, filters, row_count,
truncated, category_counts, items, limitations
```

Each JSON `item` is an unchanged, redacted `ActivityItem` serialization.

## Security boundaries

- **Export requires additional privilege:** `project:read` and
  `project:review`. Browsing individual timeline pages still requires only
  `project:read`.
- Every page of the export is fetched via `ProjectActivityService.timeline`
  so tenant/project constraints and the evidence `permission_scope` checks
  cannot be bypassed by the exporter.
- No email body, evidence content, source credential, provider errors, audit
  previous/next state, private reviewer notes or worker ID is exported.
- Each request has a **hard cap of 500 records**. Exports fetch pages of up to
  100 records; `X-PMWizard-Export-Truncated` must be checked. If true, narrow
  the date range and download multiple files.
- No server-side export storage, background task, export schema migration or
  automatic distribution is introduced.
- A checksum verifies byte integrity **only**. It is not a digital signature,
  proof of source authenticity, notarization, or an immutable audit chain.
  For regulatory compliance, use an independently managed signing/archive
  process.

## Example verification

```bash
sha256sum pmwizard-activity-*.json
```

Compare the hash with `X-PMWizard-Export-SHA256` captured from the download
response. A different hash means the file bytes have changed.

## Tests

Run `pytest -q tests/test_activity_export.py tests/test_project_activity.py`.

Covered: CSV formula escaping, JSON metadata, SHA-256, date/category/actor
filtering, evidence redaction, multi-page exports, row cap, authorization,
tenant isolation, cache-safe download headers and validation errors.

The standard CI additionally runs Python 3.11/3.12, lint and Next.js build.
