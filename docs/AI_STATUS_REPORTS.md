# AI Status Report Generator V0

## Purpose

AI Status Report Generator converts governed PMWizard state into a concise human-reviewable status-report draft.

The model is allowed to write language.

The model is not allowed to create project truth.

The pipeline is:

```text
Authorized Project
      ↓
Governed Project Memory
Deterministic Health
Captured Health Trend
Source telemetry
      ↓
Grounding Packet
      ↓
Structured AI generation
      ↓
Grounding validation
      ↓
Human-reviewable draft
```

## Truth boundary

V0 deliberately excludes pending Project Inbox suggestions from the Grounding Packet.

Until a suggestion is accepted or edited by an authorized human, it is not reportable project truth.

The report can use:

- governed Project fields;
- governed Action Items;
- governed RAID;
- governed Decisions;
- deterministic Project Health;
- persisted Health Trend;
- Source operational health.

## API

```text
POST /v1/projects/{project_id}/status-report/draft
```

The request supports:

```json
{
  "lookback_days": 7,
  "audience": "executive"
}
```

Supported audiences:

```text
executive
project_team
```

Reporting window:

```text
1–31 days
```

Generation requires:

```text
project:read
project:review
```

The additional review permission is intentional because model generation is an explicit, potentially cost-bearing action.

## Grounding Packet

Before calling the model, PMWizard creates deterministic `GroundFact` records.

Each fact contains:

- fact ID;
- category;
- exact reportable text;
- canonical entity type/id when applicable;
- visible supporting Evidence IDs only;
- observation timestamp.

Example:

```text
RISK-001

Active Risk: Vendor capacity.
Status: mitigating.
Impact: high.
Mitigation: Confirm secondary implementation window.
```

## Evidence permission filtering

Canonical governed state may reference Evidence in provenance.

Those Evidence IDs are included only when:

```text
evidence.permission_scope ⊆ caller permissions
```

The canonical fact can remain reportable while unauthorized Evidence identifiers remain hidden.

Raw Evidence content is not sent to the Status Report model in V0.

## Structured output

The AI provider must return the following sections:

- Executive Summary;
- Accomplishments;
- Risks & Issues;
- Decisions Needed;
- Next Steps;
- Data Quality Notes.

Each statement must contain:

```text
text
fact_ids[]
```

A section may be empty when the Grounding Packet does not support a valid statement.

## Grounding validation

Model output is rejected when:

1. a statement cites no facts;
2. a statement cites an unknown fact ID;
3. a numerical value appears in generated wording but does not appear in the cited facts.

Example:

```text
Generated:
"Delivery improved by 47%."

Cited fact:
"API integration completed."

→ REJECT
```

This does not mathematically prove that every sentence is perfect, but it creates a strong V0 barrier against unsupported metrics and uncited claims.

## Provider abstraction

PMWizard depends on:

```text
StructuredGenerationProvider
```

rather than provider-specific APIs throughout the application.

V0 includes:

```text
OpenAIResponsesProvider
```

which uses Responses API Structured Outputs and Pydantic parsing.

Tests use a fake provider and never call an external model.

## Runtime configuration

AI generation is optional.

Without an AI provider, the rest of PMWizard starts normally.

To enable the V0 OpenAI adapter:

```text
PMWIZARD_AI_PROVIDER=openai
PMWIZARD_AI_MODEL=<model name>
OPENAI_API_KEY=<secret>
```

Never commit API keys.

If generation is requested while no provider is configured:

```text
503 AI status-report provider is not configured.
```

## Draft response

The API returns:

- Project/report identity;
- period;
- audience;
- provider/model;
- deterministic Health/Trend metadata;
- structured report sections;
- complete Grounding Fact ledger;
- grounding validation counts;
- explicit AI-draft disclaimer.

The draft is not persisted into Project Memory.

## Web workspace

Navigation includes:

```text
Executive Dashboard
Program & Portfolio
Project Health
Status Reports
Project Inbox
Project Memory
Sources
```

The Status Reports workspace allows the user to:

- select Executive or Project Team audience;
- select a 7/14/21/30-day window;
- generate a draft;
- inspect fact IDs under each statement;
- inspect the full Grounding Fact ledger;
- copy the report as plain text.

## Human governance

The generated output includes:

```text
AI-generated draft.
Facts are grounded in authorized PMWizard state;
wording still requires human review before distribution.
```

V0 does not automatically email, publish, or write the report back to a client system.

## No migration

Status Report V0 is generated on demand and is not persisted.

No new database table or Alembic migration is required.

## Deferred

- persisted report history;
- report approval workflow;
- custom organization templates;
- branded PDF / DOCX export;
- email/Teams/Slack delivery;
- scheduled weekly generation;
- Program/Portfolio status reports;
- citation links to Evidence UI;
- semantic claim verification;
- multilingual report generation;
- provider cost/token telemetry.

## Guiding principle

> AI may write the update; governed facts decide what the update is allowed to say.
