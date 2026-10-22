# Project Memory Workspace V0

## Purpose

Project Memory Workspace is the read-only browser and API surface for PMWizard's governed project state.

It answers a different question from Project Inbox:

```text
Project Inbox  → What intelligence requires a human decision?
Project Memory → What has already become governed project truth?
```

No direct edits are allowed from Project Memory V0.

## API

```text
GET /v1/projects/{project_id}/memory
```

The endpoint requires authenticated project access and the `project:read` permission.

## Snapshot contents

The response contains:

- Project metadata and objective;
- Action Items;
- Risks;
- Assumptions;
- Issues;
- Dependencies;
- Decisions;
- summary counts for open/blocked/approved records.

All rows are tenant/project scoped.

## Summary semantics

Action Items are open unless status is `completed` or `cancelled`.

Assumptions are open until validated, invalidated, converted, or closed.

Issues are open until resolved or closed.

Dependencies are open until satisfied, waived, or closed.

Risks remain open until closed.

Decisions remain visible regardless of status because superseded/reversed decisions are part of project history.

## Governance boundary

Project Memory does not create a second mutation path.

The core loop stays:

```text
Evidence
  ↓
Intelligence
  ↓
Project Inbox
  ↓
Human Review
  ↓
Governed write
  ↓
Project Memory
```

An accepted or edited Action Item suggestion therefore becomes visible in the Memory snapshot only after `ProjectMemoryService.review_suggestion()` applies the governed update.

## Web workspace

The existing PMWizard sidebar now exposes:

```text
Project Inbox
Project Memory
Sources (future)
```

Project Memory Web V0 includes:

- governed-truth project header;
- executive summary metrics;
- project metadata;
- Action Items table;
- RAID grouped as Risks / Assumptions / Issues / Dependencies;
- Decisions timeline;
- refresh control;
- read-only governance notice.

The same authenticated project selector introduced in PR #10 applies to both Inbox and Memory.

## Security

The Web calls its Next.js BFF:

```text
GET /api/memory
```

The BFF obtains the HttpOnly PMWizard access token and selected project cookie server-side, then calls the authenticated FastAPI Project Memory endpoint.

The browser never supplies tenant IDs, user IDs, project permissions, or Bearer tokens directly.

## V0 boundaries

Deferred:

- direct Project Memory editing;
- owner/person name resolution;
- rich filtering and search;
- audit-history drilldown;
- Evidence drilldown from every governed entity;
- relationship graph;
- Project Health scoring;
- timeline/Gantt views;
- export/report generation.

## Guiding principle

> Inbox is where project truth is governed. Memory is where governed truth is observed.
