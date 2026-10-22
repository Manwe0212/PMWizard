# Connector Framework V0

## Purpose

The Connector Framework gives PMWizard one stable read-only contract for external source systems.

Future connectors for Microsoft Graph, SharePoint, Jira, Monday, Airtable, CSV, and internal APIs should emit the same canonical ingestion object:

```text
External source
      ↓
SourceConnector
      ↓
SourceRecord
      ↓
Ingestion V0
      ↓
Evidence
```

Connectors retrieve and map source data. They do not decide project meaning.

---

## SourceConnector Contract

A connector exposes:

```python
connector_key

test_connection()

fetch_page(
    project_id,
    cursor,
    limit,
)
```

`fetch_page()` returns a `ConnectorPage`:

```text
records
next_cursor
has_more
```

Each record must already be mapped to a PMWizard `SourceRecord`.

---

## connector_key

`connector_key` is a stable identifier for one connector configuration.

Examples:

```text
microsoft-graph-mail:project-123:inbox
sharepoint:project-123:site-abc:library-documents
jira:project-123:cloud-site:ABC
```

It is used together with:

```text
tenant_id
project_id
```

to scope checkpoints.

A connector key must not contain secrets.

---

## Incremental Sync

Connectors should prefer incremental fetching when the source supports it.

```text
checkpoint N
     ↓
fetch page
     ↓
SourceRecords
     ↓
Ingestion
     ↓
page succeeds
     ↓
checkpoint N+1
```

The framework does not prescribe the cursor format.

A cursor may represent:

- an offset;
- a timestamp;
- a Microsoft Graph delta token;
- a Jira pagination token;
- a provider-specific continuation token.

PMWizard treats it as an opaque string.

---

## Safe Checkpoint Rule

A checkpoint advances only after the entire fetched page has been processed without an unexpected error.

If processing fails halfway through a page:

```text
Record 1 → ingested
Record 2 → error
Record 3 → not trusted as complete page

Checkpoint stays at previous position
```

The next run may fetch the page again.

This is safe because Ingestion V0 is idempotent:

```text
Record 1 → duplicate
Record 2 → retry
Record 3 → process
```

This favors correctness over silently skipping source data.

---

## Connector Run Result

Every run reports:

```text
connector_key
status
started_at
finished_at
start_cursor
end_cursor

pages_processed
fetched
ingested
duplicates
source_changed
empty_content
errors
```

Run status is one of:

```text
success
partial
failed
```

A `partial` result means some pages completed and a later boundary stopped the run, or the configured maximum page count was reached while more data remained.

---

## Error Stages

V0 reports errors by boundary:

```text
fetch
mapping
ingestion
contract
runner
```

Examples:

- source API unavailable → `fetch`;
- connector emits another Project's record → `mapping`;
- unexpected ingestion exception → `ingestion`;
- `has_more=true` without a continuation cursor → `contract`;
- maximum-page guard reached → `runner`.

Errors are surfaced rather than silently discarded.

---

## CheckpointStore

The framework defines a `CheckpointStore` abstraction.

V0 includes:

```text
InMemoryCheckpointStore
```

This is intended for:

- unit tests;
- local demonstrations;
- validating connector behavior.

A durable PostgreSQL checkpoint store should be introduced before production connector scheduling.

The interface is intentionally stable so connector code will not depend on how checkpoints are persisted.

---

## SyntheticConnector

`SyntheticConnector` provides deterministic paginated records without credentials or external systems.

It validates the full composition:

```text
SyntheticConnector
      ↓
ConnectorRunner
      ↓
Ingestion V0
      ↓
Canonical Evidence
```

It is also useful for future integration tests involving Entity Resolution and Progress Intelligence.

---

## Security Boundary

Connectors are read-only in V0.

A production connector must:

- obtain authorization outside the domain model;
- retrieve only approved source scopes;
- preserve source permissions;
- map those permissions into `SourceRecord.permission_scope`;
- avoid logging tokens or secrets;
- never put credentials into `connector_key`, `SourceRecord`, or repository code.

The Connector Framework itself does not authenticate users or store provider tokens.

---

## Responsibility Boundaries

A connector may:

```text
authenticate through an external integration layer
test source connectivity
fetch authorized records
handle provider pagination
map provider payloads to SourceRecord
preserve IDs, timestamps, source references, and permissions
```

A connector must not decide:

```text
whether two project entities are identical
whether an Action Item is complete
whether something is a Risk
whether project health is red/amber/green
whether an AI suggestion becomes governed state
```

Those responsibilities belong to later PMWizard layers.

---

## V0 Flow

```text
SourceConnector
      ↓
ConnectorPage
      ↓
ConnectorRunner
      ↓
SourceRecord
      ↓
Ingestion V0
      ↓
Evidence
      ↓
Entity Resolution
      ↓
Progress Intelligence
      ↓
Human Review
```

---

## Deferred

Connector Framework V0 deliberately defers:

- OAuth implementation;
- token persistence/refresh;
- durable database checkpoints;
- scheduled workers;
- retries with exponential backoff;
- rate-limit handling;
- webhook subscriptions;
- dead-letter queues;
- connector configuration persistence;
- production observability.

Those should be added when implementing real source adapters.

---

## Next Connector

The preferred first production adapter is Microsoft Graph Mail V0.

It should map authorized Outlook messages into `SourceRecord` while preserving:

- Graph message ID;
- sender;
- received/sent timestamp;
- source reference;
- project mapping;
- permission scope;
- provider continuation/delta cursor.

No provider-specific behavior should bypass Ingestion V0.
