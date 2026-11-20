# PR #37 — Project Delivery Intelligence

## Purpose

Add a dedicated **Delivery Intelligence** project workspace to help project
managers understand delivery pressure from governed records. No AI key,
external integration, new database tables or write endpoints are required.

## Source of truth

The UI reads the existing authenticated `GET /api/memory` route. That
BFF endpoint uses the selected project and checks permissions in the
FastAPI backend, just like Project Memory.

The UI derives only the following from the returned snapshot:

- Open, blocked and overdue Action Items;
- Blocked Dependencies;
- Proposed/pending Decisions;
- Active Issues and active high-impact Risks;
- The project's recorded planned vs forecast finish dates;
- Completed action count as a proportion of all governed Action Items.

It **does not** claim to compute Earned Value, sprint velocity,
a statistical forecast, a critical path, milestones or resource capacity.

## UX

A new sidebar item, **Delivery Intelligence**, opens:

1. Four headline metrics with understandable descriptions.
2. Recorded planned and forecast dates and the calendar-day variance.
3. A completed-action count (explicitly *not* scope delivery).
4. A read-only follow-up queue. It orders critical flagged entries first,
   then nearest recorded dates, then title. Filters: All / Critical /
   Attention. Up to eight initially with optional Show All.
5. A governance disclaimer making the MVP boundaries clear.

The follow-up queue does not conflate a "Pending External" Action Item
with the associated still-blocked Dependency. A blocked Action Item
continues to be flagged, even when its due date is also past due.
A terminal Action Item is excluded from overdue counts.

## Acceptance (manual)

1. Sign in to the local synthetic Atlas Delivery demo.
2. Select **Delivery Intelligence** from the sidebar.
3. Compare open/blocked/overdue Action Items and Dependencies against
   **Project Memory**, including the previously human-reviewed
   `Pending External` activity.
4. Verify a blocked Dependency remains flagged independently.
5. Confirm an overdue date is a recorded date, not a prediction.
6. Compare the two finish dates against Project Memory. If either is
   missing, variance must read `Not available`.
7. Exercise All/Critical/Attention filters and Show All (when present).
8. Check narrow-screen layout and permission-limited project access.
9. Verify the new screen does not modify project state or call paid AI.

## Technical CI gate

- Next.js/TypeScript web build and lint
- Python 3.11 and 3.12 tests
- Docker synthetic demo smoke
- Staging configuration/web image check

## Limits and future additions

No Milestone records are part of this MVP Project Memory response.
A later increment can model Milestones/Workstreams, link blocker
dependencies to specific activities, incorporate actual delivery
baseline dates, and add authorized Jira/Tempo data only after explicit
connector development and staging tests.

`new Date().toISOString().slice(0, 10)` defines UTC "today" consistently
for comparing stored ISO date-only values; the UI labels overdue
measurements as UTC-based. For an international roll-out, consider
per-tenant timezone preferences.

This is an interview-facing synthetic MVP enhancement, not a
production-readiness declaration.
