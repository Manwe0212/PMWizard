# Project Inbox V0 + API

## Purpose

Project Inbox is the human-governance surface for PMWizard intelligence.

It exposes AI suggestions without allowing AI to silently overwrite governed project state.

Flow:

```text
Evidence
  ↓
Entity Resolution / Intelligence
  ↓
AISuggestion
  ↓
Project Inbox API
  ↓
Accept / Edit / Reject / Defer
  ↓
HumanReview + Audit
  ↓
Governed Project Memory
```

## API endpoints

```text
GET  /healthz

GET  /v1/projects/{project_id}/inbox
GET  /v1/projects/{project_id}/inbox/{suggestion_id}
POST /v1/projects/{project_id}/inbox/{suggestion_id}/review
```

The default Inbox lists suggestions whose review status is:

```text
pending
deferred
```

Terminal suggestions can be queried explicitly with the `review_status` query parameter.

## Trusted identity context

Authentication + Project Selection V0 uses Authorization: Bearer <token> for normal API access. Project permissions are loaded from ProjectMembership for the authenticated user. The earlier trusted headers remain available only in explicitly enabled compatibility/test mode.

## Project permissions

Reading the Inbox requires:

```text
project:read
```

Submitting a human review additionally requires:

```text
project:review
```

## Evidence permission inheritance

A suggestion is visible only when the caller can view every Evidence record supporting it.

If Evidence requires:

```text
project:read
source:mail
```

the caller must hold both scopes.

For a suggestion supported by multiple Evidence records, PMWizard effectively enforces the union of their required scopes.

This avoids exposing derived intelligence whose supporting sources are not authorized for the reviewer.

## Inbox list

The list response exposes:

- suggestion ID and type;
- target entity;
- proposed changes;
- reason;
- confidence;
- review status;
- evidence count;
- evidence source systems;
- creation timestamp.

The list does not need to expose full Evidence excerpts.

## Inbox detail

The detail endpoint adds:

- current target Action Item state, when applicable;
- authorized Evidence excerpts;
- source type/system;
- source reference;
- author;
- capture timestamp;
- permission scope.

This lets a PM evaluate both the recommendation and its supporting context before acting.

## Human review transitions

Allowed review decisions are:

```text
accepted
edited
rejected
deferred
```

A review cannot set a suggestion back to `pending`.

Reviewable source states are:

```text
pending
deferred
```

Terminal states are:

```text
accepted
edited
rejected
```

A terminal suggestion cannot be reviewed again.

A deferred suggestion can later be accepted, edited, rejected, or deferred again.

## Accept

`accepted` applies the original AI-proposed safe changes when the target is an Action Item.

Example:

```json
{
  "status": "accepted"
}
```

The reviewer identity comes from trusted API context, not from the request body.

## Edit

`edited` requires `final_changes`.

Example:

```json
{
  "status": "edited",
  "reviewer_note": "Legal approval is still pending.",
  "final_changes": {
    "status": "blocked",
    "progress_summary": "Technical work is complete; legal approval remains."
  }
}
```

For Action Items, V0 allows only governed fields already approved by Project Memory:

```text
status
progress_summary
last_progress_date
latest_evidence_id
completed_at
due_date
priority
```

Unsupported fields are rejected instead of silently ignored.

## Reject

`rejected` records the human decision and audit event but does not mutate the Action Item.

## Defer

`deferred` records that the PM wants to decide later.

It does not mutate governed state and remains in the default Inbox.

## Audit

Every review continues through `ProjectMemoryService.review_suggestion()`.

Therefore the API does not create a second governance path.

The same service persists:

- HumanReview;
- suggestion review status;
- approved Action Item changes;
- AuditLog entry.

## Tenant and project isolation

Every Inbox query is scoped by:

```text
tenant_id
project_id
```

Cross-tenant project access returns not found.

Evidence and target entities must belong to the same authorized project.

## Running locally

After configuring PostgreSQL:

```bash
uvicorn pmwizard.api.app:create_default_app --factory --reload
```

The default app requires:

```text
PMWIZARD_DATABASE_URL
```

OpenAPI documentation is then available through FastAPI's standard documentation routes.

## V0 boundaries

Project Inbox V0 is an API surface, not yet a browser UI.

Deferred capabilities include:

- Next.js / web Inbox;
- real OIDC/OAuth user authentication;
- organization roles;
- durable permission/principal model;
- pagination cursors;
- batch review;
- assignment/delegation;
- notifications;
- comments/discussion threads;
- SLA / aging views;
- websocket/live updates;
- mobile experience.

## Guiding principle

> Intelligence proposes. Evidence supports. The authorized Project Manager decides.
