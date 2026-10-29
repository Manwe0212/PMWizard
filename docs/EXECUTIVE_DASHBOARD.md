# Executive Dashboard V0

## Purpose

Executive Dashboard is the authenticated landing workspace for PMWizard.

It answers one operational question:

> What requires attention across the projects I am authorized to see?

The dashboard is deterministic, read-only, and authorization-preserving.

## Inputs

Executive Dashboard composes existing governed PMWizard read models:

```text
ProjectMembership
      ↓
Program / Portfolio Intelligence
Project Health + Trends
Project Inbox
Project Memory
Sources Workspace
      ↓
ExecutiveDashboardService
      ↓
Executive Dashboard
```

It does not create a second source of project truth.

## API

```text
GET /v1/executive/dashboard
```

Bearer authentication is required.

Trusted-header compatibility mode is rejected because an executive rollup requires the authenticated user's complete ProjectMembership set.

Only memberships containing:

```text
project:read
```

participate.

## Evidence visibility

Inbox workload is not calculated by counting AI suggestion rows directly.

For each authorized Project, Executive Dashboard calls the existing permission-aware `ProjectInboxService`.

Therefore a suggestion requiring Evidence scopes unavailable to the user:

- is not counted;
- is not listed;
- does not affect executive review workload.

## Executive summary

The summary reports:

```text
Portfolio / authorized-project Health rollup
Projects needing attention
Pending Inbox reviews
Deferred Inbox reviews
Critical RAID
Pending Decisions
Source failures
Additional Source attention
Cross-project signals
```

## Projects needing attention

The dashboard reuses Program & Portfolio Intelligence.

A Project enters executive attention when it is:

- Red;
- Amber;
- or Deteriorating.

The underlying current Health and persisted trend remain visible and explainable in Project Health.

Selecting the Project opens its Project Health workspace.

## Critical RAID

V0 deliberately uses deterministic criteria.

### Risk

Critical when:

- status = `materialized`; or
- active impact label is `critical`, `high`, or `severe`.

### Assumption

Critical when:

- status = `invalidated`.

### Issue

Critical when:

- status = `blocked`; or
- active severity label is `critical`, `high`, or `severe`.

### Dependency

Critical when:

- status = `blocked`; or
- active criticality label is `critical`, `high`, or `severe`.

These rules are intentionally explicit rather than AI-generated.

Selecting an item opens Project Memory for its Project.

## Pending Decisions

A governed Decision appears when status is:

```text
proposed
pending
```

Items with a review date are ordered by the nearest review date first.

Selecting a Decision opens Project Memory.

## Source operations

Source alerts include enabled connections in:

```text
failed
attention
never_synced
```

Failed sources rank first.

The summary separates hard failures from additional attention states.

Selecting an alert opens the Project Sources workspace.

## Review workload

Visible Project Inbox items are aggregated across authorized Projects.

Pending items rank before Deferred items, then newest first.

Selecting an item opens the corresponding Project Inbox.

## Cross-project signals

Executive Dashboard reuses the conservative Program & Portfolio shared Risk/Dependency signals.

No semantic or fuzzy cross-project relationship is asserted by Executive Dashboard itself.

## Web behavior

The authenticated navigation now starts with:

```text
Executive Dashboard
Program & Portfolio
Project Health
Project Inbox
Project Memory
Sources
```

Executive Dashboard is the default landing workspace after login.

It is cross-project, so the top bar displays authorized scope instead of a single Project selector.

Every actionable row can switch the active Project and route to the relevant workspace.

## Why no LLM narrative yet?

V0 intentionally keeps executive status deterministic.

Before PMWizard generates executive narratives, the system must establish that:

- every metric is grounded;
- authorization is preserved;
- Health is explainable;
- review workload respects Evidence permissions;
- RAID and Decisions are governed state.

A future AI Status Report can summarize this read model, but the generated language must not become the source of truth.

## V0 performance boundary

The dashboard composes per-Project read models synchronously.

This is appropriate for the initial V1 / PMO-scale implementation.

Future optimization may introduce:

- cached project summaries;
- asynchronous dashboard materialization;
- precomputed organization rollups;
- event-driven invalidation.

Those optimizations must preserve the same output and authorization semantics.

## Guiding principle

> Executive intelligence should reduce navigation, not reduce governance.
