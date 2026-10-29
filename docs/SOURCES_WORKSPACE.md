# Sources Workspace V0

## Purpose

Sources Workspace is PMWizard's operational view for the external systems that supply Evidence.

It answers:

```text
Are my authorized sources connected?
Did the latest sync succeed?
Did PMWizard ingest new Evidence?
Were records skipped or rejected?
Does incremental sync have a durable checkpoint?
```

Sources Workspace does not expose provider credentials or raw checkpoint values.

## Durable source state

PR #12 adds three persistent records:

```text
source_connections
connector_checkpoints
connector_runs
```

### source_connections

Stores safe, non-secret metadata for one project-scoped connector configuration:

- connector key;
- source type;
- source system;
- display name;
- permission scopes;
- safe configuration metadata;
- opaque runtime credential reference;
- enabled flag.

The credential reference is not secret material and is not returned by the Sources read API. OAuth access tokens, refresh tokens, client secrets, and passwords must never be stored here.

### connector_checkpoints

Stores the opaque cursor required to resume incremental synchronization.

The raw cursor is operationally sensitive and is never returned by Sources Workspace API or Web.

A short SHA-256 fingerprint is stored separately so operators can tell that a checkpoint changed without seeing its value.

### connector_runs

Stores sanitized run telemetry:

- success / partial / failed;
- timestamps and duration;
- pages processed;
- fetched;
- ingested;
- duplicates;
- source changed;
- empty content;
- skipped;
- sanitized skip reasons;
- sanitized errors;
- checkpoint presence/fingerprint.

Run history never persists the raw cursor from ConnectorError.

## Durable runner composition

Use:

```python
from pmwizard.sources import create_durable_connector_runner

runner = create_durable_connector_runner(session)
```

This composes:

```text
ConnectorRunner
  + SQLAlchemyCheckpointStore
  + SourceTelemetryService
```

The existing InMemoryCheckpointStore remains supported for unit tests and simple local demos.

## Connector descriptors

Real connectors expose a safe ConnectorDescriptor.

Microsoft Graph Mail records:

- connection name;
- mailbox;
- folder ID;
- optional received-after boundary;
- permission scope.

SharePoint Documents records:

- connection name;
- drive ID;
- initial sync mode;
- supported extensions;
- max file size;
- permission scope.

Provider bearer tokens are supplied externally and never enter the descriptor.

## API

```text
GET /v1/projects/{project_id}/sources
```

The endpoint requires authenticated project membership and `project:read`.

Response includes project-scoped source connections, health, checkpoint metadata, latest run, up to five recent runs, and only a boolean `credential_configured` readiness signal.

Credential bindings are managed through:

```text
PUT    /v1/projects/{project_id}/sources/{source_connection_id}/credential
DELETE /v1/projects/{project_id}/sources/{source_connection_id}/credential
```

These mutations require `project:review`.

## Health semantics

```text
healthy       latest run succeeded with no skips/errors
attention     latest run is partial or includes skips/errors
failed        latest run failed
never_synced  connection exists but has no recorded run
disabled      connection is disabled
```

A successful SharePoint run with unsupported PDF/XLSX skips is therefore visible as `attention`, not silently reported as fully healthy.

## Web workspace

The authenticated sidebar now contains:

```text
Project Inbox
Project Memory
Sources
```

Sources Web V0 includes:

- source summary metrics;
- connection list;
- source health;
- last sync;
- latest run metrics;
- sanitized errors and skips;
- safe connector configuration;
- checkpoint fingerprint;
- recent run history;
- secure runtime credential readiness/binding.

The browser calls the Next.js BFF:

```text
GET /api/sources
```

The BFF supplies the HttpOnly Bearer session and selected project server-side.

## Security boundaries

Sources Workspace intentionally does not expose:

- credential reference names after binding;
- OAuth tokens;
- refresh tokens;
- passwords;
- Graph delta URLs;
- raw continuation tokens;
- raw checkpoint cursor values.

Database backups and the connector checkpoint table still require normal production data protection because raw provider cursors are stored there for resumption.

## Deferred

V0 still defers:

- full Source connection creation wizard;
- enable/disable mutation API;
- source-specific retries with exponential backoff;
- rate-limit handling;
- webhook subscriptions;
- delegated OAuth refresh-token lifecycle;
- cloud secret-manager adapters;
- alert notifications;
- source SLAs;
- long-term telemetry aggregation.

## Guiding principle

> Evidence should be traceable to a source, and source health should be observable without exposing source secrets.
