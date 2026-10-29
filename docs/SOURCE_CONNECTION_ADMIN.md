# Source Connection Administration V0

## Purpose

Source Connection Administration turns the Sources workspace from an observability-only view into a governed configuration surface for Microsoft Graph Sources.

V0 supports:

```text
Outlook Mail
SharePoint Documents
```

Authorized Project reviewers can:

- create a Source;
- edit safe connector configuration;
- manage Evidence permission scopes;
- enable or disable a Source;
- bind or clear the existing secure runtime credential alias;
- queue a connection test.

Secrets remain outside PostgreSQL.

## Administration boundary

The API manages only:

```text
display_name
source_system
safe_config
permission_scope
enabled state
credential_ref alias
```

The runtime secret value remains in the configured SecretProvider.

## Immutable connector identity

Sources created through the administration API receive a UUID-based connector key.

Mail example:

```text
microsoft-graph-mail:admin:<source-uuid>:v0
```

SharePoint example:

```text
microsoft-graph-sharepoint:admin:<source-uuid>:v0
```

Renaming the Source does not change the connector key.

This preserves:

- durable checkpoints;
- telemetry continuity;
- scheduled Source Sync identity.

## Safe configuration validation

Administration does not accept an arbitrary JSON blob.

The supplied `safe_config` is validated through the same Pydantic connector configuration model used by runtime execution.

### Outlook Mail

Supported safe fields:

```text
mailbox
folder_id
received_after
```

### SharePoint

Supported safe fields:

```text
drive_id
initial_sync_mode
supported_extensions
max_file_bytes
```

Fields such as `access_token`, `client_secret`, or other extra values are rejected.

## Evidence permission scope

Each Source has a non-empty `permission_scope`.

Default:

```text
project:read
```

Additional scopes can be configured for more restrictive Evidence visibility.

Changing Source administration permissions does not automatically grant those permissions to users.

## Checkpoint invalidation

A stream configuration change can make an existing provider delta cursor invalid.

Therefore:

```text
safe_config changed
      ↓
delete current connector checkpoint
      ↓
preserve historical connector_runs
      ↓
next sync starts from new configuration
```

A display-name change does not reset the checkpoint.

Credential rebinding does not reset the checkpoint.

## Enable / disable

A disabled Source cannot:

- run a scheduled sync;
- be connection-tested.

When a Source is disabled, PMWizard also pauses active `source_sync` schedules that reference it.

Re-enabling the Source does not automatically resume those schedules.

This keeps the decision explicit.

## Migration

```text
0008_source_connection_admin_v0
```

adds worker-owned connection-test state to `source_connections`:

```text
test_requested_at
test_requested_by
test_lease_owner
test_lease_expires_at
last_test_at
last_test_status
last_test_message
```

No secret value is stored in these fields.

## Connection-test architecture

The web/API process never performs the provider call.

```text
Sources UI
   ↓
POST /sources/{id}/test
   ↓
test_requested_at
   ↓
Automation Worker
   ↓
SourceConnectionTestWorker
   ↓ lease claim
SourceRuntimeResolver
   ↓
SecretProvider
   ↓
connector.test_connection()
   ↓
sanitized result
```

This preserves the runtime-secret boundary introduced in PR #19.

## Test lease

Multiple workers may poll for connection tests.

A worker claims one Source by writing a unique lease token and expiration.

A second worker cannot claim it until the lease expires.

If the first worker disappears, another worker can retry the pending request after expiration.

## Test statuses

Workspace statuses:

```text
never_tested
queued
running
success
failed
```

The stored message is capped and normalized before persistence.

The UI never displays the runtime credential alias or secret value.

## API

Create:

```text
POST /v1/projects/{project_id}/sources
```

Update:

```text
PATCH /v1/projects/{project_id}/sources/{source_connection_id}
```

Queue test:

```text
POST /v1/projects/{project_id}/sources/{source_connection_id}/test
```

Credential binding remains:

```text
PUT    /v1/projects/{project_id}/sources/{source_connection_id}/credential
DELETE /v1/projects/{project_id}/sources/{source_connection_id}/credential
```

All mutations require:

```text
project:read
project:review
```

The existing read endpoint remains:

```text
GET /v1/projects/{project_id}/sources
```

and requires only:

```text
project:read
```

## Web workflow

### Add Source

```text
Sources
  ↓
Add source
  ↓
Outlook | SharePoint
  ↓
safe configuration
  ↓
Evidence permission scope
  ↓
Create
```

### Prepare runtime

```text
Created Source
  ↓
Bind credential alias
  ↓
Test connection
  ↓
Worker executes test
  ↓
success / failed
```

### Automate

A credential-ready enabled Source can then be scheduled from Automations.

## Governance

Administration does not:

- write to Outlook or SharePoint;
- alter Project Memory directly;
- accept Inbox suggestions;
- expose secrets;
- publish reports.

Source connectors remain read-only.

## Deferred

- delete/archive Source;
- interactive OAuth consent;
- Azure Key Vault UI;
- provider permission diagnostics;
- SharePoint site/drive discovery;
- Outlook folder discovery;
- Jira/Monday/Airtable connection wizards;
- organization-level Source templates;
- automatic schedule resume when re-enabled.

## Guiding principle

> Configuration may be governed in the application; credentials remain runtime-only.
