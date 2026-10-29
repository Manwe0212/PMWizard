# Secure Source Runtime + Scheduled Source Sync V0

## Purpose

PR #19 lets the Automation worker reconstruct authorized Outlook and SharePoint connectors at runtime without storing provider secrets in PostgreSQL.

The security boundary is:

```text
source_connections
  ├─ safe_config
  └─ credential_ref = env:GRAPH_MAIN
                    ↓
              Automation Worker
                    ↓
       EnvironmentSecretProvider
                    ↓
      PMWIZARD_SECRET_GRAPH_MAIN
                    ↓
          runtime credential JSON
                    ↓
       Microsoft Graph token provider
                    ↓
         read-only Source connector
```

The secret value never becomes a Source field, API response, checkpoint, Automation config, or telemetry payload.

## Migration

```text
0007_source_runtime_v0
```

adds one nullable field:

```text
source_connections.credential_ref
```

The field stores only an opaque reference.

Example:

```text
env:GRAPH_PROJECT_A
```

It does not store:

- access tokens;
- refresh tokens;
- client secrets;
- passwords;
- OAuth responses.

## Environment secret namespace

V0 intentionally does not allow arbitrary environment variable names.

A stored reference must match:

```text
env:ALIAS
```

where ALIAS contains only:

```text
A-Z
0-9
_
```

Maximum alias length: 64 characters.

The resolver maps:

```text
env:GRAPH_PROJECT_A
```

only to:

```text
PMWIZARD_SECRET_GRAPH_PROJECT_A
```

Therefore a database value cannot ask the worker to read arbitrary process variables such as:

```text
OPENAI_API_KEY
PMWIZARD_DATABASE_URL
PMWIZARD_AUTH_SECRET
```

## Credential schemas

The environment value is JSON.

### Bearer token

Useful for local development, tests, or externally managed short-lived tokens:

```json
{
  "kind": "bearer_token",
  "access_token": "<runtime token>"
}
```

Bearer tokens are not persisted by PMWizard.

### Microsoft Entra client credentials

Production-oriented app-only runtime:

```json
{
  "kind": "entra_client_credentials",
  "tenant_id": "<tenant>",
  "client_id": "<application id>",
  "client_secret": "<secret>",
  "scope": "https://graph.microsoft.com/.default"
}
```

PMWizard exchanges these credentials at runtime against Microsoft Entra.

The resulting access token is cached only in worker memory until shortly before expiry.

It is never written to PostgreSQL.

## Mail application-access note

Microsoft Graph application permissions do not use the delegated `/me` identity in the same way as a signed-in user.

For app-only Outlook schedules, configure the Source mailbox as the target user mailbox rather than relying on `me`.

## Source binding API

Bind:

```text
PUT /v1/projects/{project_id}/sources/{source_connection_id}/credential
```

Body:

```json
{
  "credential_ref": "env:GRAPH_PROJECT_A"
}
```

Clear:

```text
DELETE /v1/projects/{project_id}/sources/{source_connection_id}/credential
```

Both require:

```text
project:read
project:review
```

Responses reveal only:

```json
{
  "source_connection_id": "...",
  "credential_configured": true
}
```

The API does not return the stored reference.

## Sources Workspace

Each Source now reports:

```text
credential_configured: true | false
```

Authorized reviewers can bind or clear an environment alias.

The workspace never displays the saved alias after submission.

This reduces the chance that internal secret naming conventions leak through normal Project read access.

## Runtime connector reconstruction

`SourceRuntimeResolver` loads:

- Source system;
- display name;
- exact persisted connector key;
- permission scopes;
- safe configuration;
- credential reference.

It then resolves credentials and reconstructs:

```text
MicrosoftGraphMailConnector
MicrosoftGraphSharePointConnector
```

The persisted connector key is preserved exactly.

This is critical because durable checkpoints and telemetry are keyed by:

```text
tenant
project
connector_key
```

A reconstructed Source therefore resumes the same delta stream instead of accidentally creating a second logical connection.

## Scheduled Source Sync

Automation gains a second task type:

```text
source_sync
```

Its only persisted task config is:

```json
{
  "source_connection_id": "..."
}
```

No credential reference or secret is copied into Automation config.

Creating a Source Sync schedule requires the Source to:

- belong to the same tenant/project;
- be enabled;
- have a runtime credential binding;
- use a supported scheduled runtime.

## Execution

```text
AutomationWorker
      ↓
SourceSyncAutomationHandler
      ↓
SourceRuntimeResolver
      ↓
SecretProvider
      ↓
Graph Connector
      ↓
ConnectorRunner
      ├─ durable checkpoint
      ├─ Evidence ingestion
      └─ sanitized Source telemetry
```

The existing ConnectorRunner remains responsible for idempotent ingestion and safe checkpoint advancement.

## Delta resume

Because the reconstructed connector uses the original connector key:

```text
First run
Graph initial delta
      ↓
checkpoint = deltaLink #1

Second run
      ↓
load deltaLink #1
      ↓
Graph delta
      ↓
checkpoint = deltaLink #2
```

Restarting the worker does not reset Source progress.

## Failure behavior

Credential resolution failures become normal Automation failures.

Examples:

- binding removed;
- environment variable unavailable;
- invalid JSON schema;
- unsupported Source system;
- Microsoft Entra unavailable;
- Microsoft Graph fetch failure.

The Automation run stores only sanitized error text.

Connector failures remain visible in Sources telemetry.

Secret values are never intentionally included in exception strings.

## Supported V0 Source runtimes

```text
microsoft_graph_mail
microsoft_graph_sharepoint
```

Other Source systems remain observable but cannot yet be scheduled through Secure Source Runtime.

## Web flow

### Sources

```text
Source
  ↓
Bind credential alias
  ↓
credential_configured = true
```

### Automations

Credential-ready Microsoft Sources appear under:

```text
Scheduled Source sync
```

Selecting:

```text
Schedule hourly sync
```

creates:

```text
task_type = source_sync
interval = 60 minutes
config = source_connection_id only
```

After creation, the normal Automation controls can change cadence, pause/resume, or queue Run now.

## Security properties

V0 explicitly tests that:

- arbitrary environment variables cannot be resolved;
- Source API responses do not expose credential refs;
- Source API responses do not expose secret values;
- safe_config does not contain secret material;
- scheduled Graph sync receives the runtime token;
- durable delta checkpoints resume;
- clearing a binding causes future sync to fail safely;
- the failure does not contain the token.

## Secret-provider extensibility

The worker depends on:

```text
SecretProvider
```

not directly on environment variables.

`EnvironmentSecretProvider` is the first implementation.

Future production deployments can add adapters for:

- Azure Key Vault;
- AWS Secrets Manager;
- Google Secret Manager;
- HashiCorp Vault;
- organization-specific secret brokers.

Those providers can replace environment resolution without changing Source rows or Automation schedules.

## Deferred

- delegated OAuth refresh-token lifecycle;
- interactive Microsoft consent flow;
- Key Vault / cloud secret-manager adapters;
- credential rotation UI;
- Graph permission diagnostics;
- source-specific retry/backoff;
- lease heartbeat for very long syncs;
- Source connection creation wizard;
- Source enable/disable administration;
- Jira / Monday / Airtable runtime resolvers.

## Guiding principle

> Store references to secrets, never secrets; resolve them only where work executes.
