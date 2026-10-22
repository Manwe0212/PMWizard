# Microsoft Graph Mail V0

## Purpose

Microsoft Graph Mail V0 is PMWizard's first real external-source adapter.

It reads newly created Outlook messages from one authorized mail folder and maps them into the provider-independent connector pipeline.

```text
Microsoft Graph
      ↓
Mail folder delta query
      ↓
MicrosoftGraphMailConnector
      ↓
SourceRecord
      ↓
ConnectorRunner
      ↓
Ingestion V0
      ↓
Evidence
      ↓
Entity Resolution
      ↓
Progress Intelligence
```

The connector is read-only.

---

## Authentication Boundary

PMWizard does not store OAuth secrets or refresh tokens in the connector.

The HTTP transport receives an external token provider:

```python
transport = MicrosoftGraphHttpTransport(
    token_provider=get_access_token,
)
```

The token provider is responsible for acquiring and refreshing a valid Microsoft Graph bearer token.

Tokens must not be committed to the repository, placed in connector keys, or persisted as Evidence.

---

## Required Mail Permission

The connector requests message body content so that project intelligence can reason over more than message metadata.

For Microsoft Graph, `Mail.ReadBasic` does not include the message body or body preview.

A deployment that uses this connector therefore needs a permission capable of reading message content, normally:

```text
Delegated:   Mail.Read
Application: Mail.Read
```

The exact authentication/consent model belongs to the deployment and integration layer.

For application permissions, administrators should restrict mailbox access according to their Microsoft 365 security model rather than granting indiscriminate organizational access.

---

## Folder Scope

One connector configuration reads one mailbox folder.

Example:

```python
MicrosoftGraphMailConfig(
    connection_name="project-inbox",
    mailbox="me",
    folder_id="inbox",
    permission_scope=["microsoft-graph:mail:read"],
)
```

For another mailbox:

```python
mailbox="project.manager@company.example"
```

The connector never scans every mailbox by itself.

---

## Incremental Delta Sync

V0 uses Microsoft Graph message delta queries for a specific mail folder.

Initial request:

```text
/me/mailFolders/{folder}/messages/delta
```

or:

```text
/users/{mailbox}/mailFolders/{folder}/messages/delta
```

V0 requests only `created` changes:

```text
changeType=created
```

This aligns with PMWizard's immutable Evidence model: newly observed source records are ingested as Evidence rather than treating source updates as silent replacements.

Graph returns one of:

```text
@odata.nextLink
@odata.deltaLink
```

PMWizard stores the full URL as an opaque connector checkpoint.

### nextLink

More pages remain in the current synchronization round.

```text
has_more = true
next_cursor = @odata.nextLink
```

### deltaLink

The synchronization round is complete.

```text
has_more = false
next_cursor = @odata.deltaLink
```

The next connector run begins from that saved delta URL and retrieves only later changes.

---

## Initial Time Boundary

A connector configuration may define:

```python
received_after=<timezone-aware datetime>
```

The first delta request then applies:

```text
$filter=receivedDateTime ge <timestamp>
```

This avoids an uncontrolled first synchronization of an old mailbox.

After Graph returns a delta cursor, subsequent requests use Graph's continuation URL exactly as returned.

---

## Body Handling

The connector asks Graph for text bodies with:

```http
Prefer: outlook.body-content-type="text"
```

It also requests:

```text
body
bodyPreview
```

Mapping behavior:

```text
body.contentType == text
        ↓
use full body

body.contentType != text
        ↓
use bodyPreview
```

V0 intentionally does not parse arbitrary HTML.

Canonical content is:

```text
Subject: <message subject>

<plain-text body or preview>
```

This gives Entity Resolution useful title/context text while keeping source normalization deterministic.

---

## SourceRecord Mapping

Each non-removed Graph message maps to:

```text
project_id       → configured Project
source_type      → email
source_system    → microsoft_graph_mail
external_id      → Graph message id
source_reference → Outlook webLink when available
author           → From address, then sender fallback
captured_at      → receivedDateTime / sentDateTime fallback
effective_at     → same source timestamp
content          → subject + text body
permission_scope → configured authorized scope
```

The Graph message ID remains the authoritative external identity.

---

## Removed Messages

Delta responses can include:

```json
{
  "@removed": {
    "reason": "deleted"
  }
}
```

V0 ignores these entries.

Deleting or moving an Outlook message does not delete previously persisted PMWizard Evidence.

That preserves auditability and historical project context.

A future source-lifecycle feature may record source removal as a separate Event.

---

## Checkpoint Safety

The connector relies on Connector Framework V0 rules:

```text
fetch Graph page
      ↓
map messages
      ↓
ingest every SourceRecord
      ↓
whole page succeeds?
  yes ──→ save nextLink/deltaLink
  no  ──→ keep old checkpoint
```

If a page is retried, Ingestion V0 prevents duplicate Evidence.

---

## Connection Test

`test_connection()` performs a lightweight read of the configured mail folder and returns:

```text
ok
message
```

It does not persist content.

---

## Example Composition

```python
config = MicrosoftGraphMailConfig(
    connection_name="project-inbox",
    mailbox="me",
    folder_id="inbox",
    permission_scope=["microsoft-graph:mail:read"],
)

transport = MicrosoftGraphHttpTransport(
    token_provider=get_access_token,
)

connector = MicrosoftGraphMailConnector(
    config,
    transport,
)

runner.run(
    tenant_id=tenant_id,
    project_id=project_id,
    connector=connector,
)
```

The token-acquisition implementation is deliberately not part of this example.

---

## Security Requirements

Production deployment must ensure:

- least-privilege Microsoft Graph consent;
- explicit project/mailbox/folder mapping;
- protected token storage outside Project Memory;
- HTTPS only;
- tenant-aware connector configuration;
- source permission mapping into `SourceRecord.permission_scope`;
- no token logging;
- no organization-wide mailbox scan by default.

Security authorization must happen before source content reaches Intelligence.

---

## Deferred

Microsoft Graph Mail V0 does not yet include:

- OAuth authorization-code flow;
- client-credential setup;
- refresh-token persistence;
- Exchange application RBAC configuration;
- attachment ingestion;
- MIME parsing;
- HTML parsing;
- shared-mailbox UX;
- webhook subscriptions;
- Graph retry/backoff;
- rate-limit-aware scheduling;
- source-removal Events;
- durable database connector configuration.

Those capabilities should extend this connector without bypassing the common Connector Framework or Ingestion V0.

---

## Guiding Principle

> **Graph retrieves authorized mail. Ingestion preserves evidence. Intelligence interprets it. Humans govern project truth.**
