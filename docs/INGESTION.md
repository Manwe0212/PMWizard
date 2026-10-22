# Ingestion V0

## Purpose

Ingestion V0 turns an already-authorized raw source record into canonical PMWizard `Evidence`.

It creates the boundary between future connectors and Project Intelligence.

```text
Outlook / SharePoint / Jira / Manual source
              ↓
        Connector adapter
              ↓
         SourceRecord
              ↓
         Ingestion V0
              ↓
      Canonical Evidence
              ↓
      Entity Resolution
              ↓
    Progress Intelligence
```

V0 does not connect directly to Outlook, SharePoint, Jira, Monday, or Airtable yet.

---

## Responsibilities

Ingestion V0 is responsible for:

- validating the target Project within the supplied tenant;
- normalizing plain-text source content deterministically;
- generating a SHA-256 content hash;
- preserving source identity and provenance;
- enforcing a non-empty permission scope;
- preventing duplicate Evidence;
- detecting changed content for an existing source identity;
- persisting canonical `Evidence`.

It does not interpret project meaning.

---

## SourceRecord

A connector or trusted caller provides:

```text
project_id
source_type
source_system
external_id (optional)
source_reference (optional)
author (optional)
captured_at
effective_at (optional)
content
permission_scope
```

The caller must authorize the user, source, and Project before invoking ingestion.

---

## Normalization

V0 normalizes only representation-level noise:

- CRLF / CR line endings → LF;
- repeated horizontal whitespace → one space;
- leading/trailing whitespace per line;
- multiple blank lines → one blank line.

It does not summarize, translate, classify, or rewrite source meaning.

The SHA-256 hash is calculated from the full normalized text.

`content_excerpt` is capped by the configured excerpt size (12,000 characters by default), while the content hash still represents the full normalized source text.

---

## Idempotency

### Same source identity + same content

```text
source_system: outlook
external_id: ABC123
hash: H1

received again:
source_system: outlook
external_id: ABC123
hash: H1
```

Result:

```text
duplicate
```

No second Evidence record is written.

### Same source identity + changed content

```text
source_system: sharepoint
external_id: DOC-42
existing hash: H1
new hash: H2
```

Result:

```text
source_changed
```

V0 does not overwrite historical Evidence.

A later version can introduce explicit source-version history.

### Same normalized content from another source ID

Within the same tenant, Project, source system, and source type, equivalent normalized content is treated as duplicate Evidence even if the external ID differs.

---

## Outcomes

```text
ingested
duplicate
source_changed
empty_content
```

---

## Provenance

Persisted Evidence records are marked with integration provenance:

```text
origin: integration
source_system: <source>
source_type: <type>
source_id: <external_id>
```

This keeps source facts separate from later AI interpretations.

---

## Security Boundary

Ingestion V0 does not authenticate users.

The supplied `tenant_id` must come from trusted application context.

`permission_scope` must be non-empty and should reflect permissions resolved by the connector/application layer.

Future retrieval and reasoning must continue enforcing those permissions before Evidence enters model context.

---

## Relationship to Intelligence

Ingestion creates facts/evidence, not project-state conclusions.

Example:

```text
Email:
"Verify API access was completed today."

        ↓ Ingestion

Evidence

        ↓ Entity Resolution

Verify API access

        ↓ Progress Intelligence

Suggestion: Completed

        ↓ Human Review

Governed state
```

The ingestion step itself never marks the Action Item complete.

---

## Deferred

V0 deliberately defers:

- Microsoft Graph connectors;
- SharePoint file fetching;
- Jira / Monday / Airtable adapters;
- HTML-to-text and rich document parsing;
- attachments;
- OCR;
- source version history;
- batch checkpoints / cursors;
- webhook processing;
- retry queues;
- LLM extraction or summarization.

Those capabilities should build on the stable `SourceRecord → Evidence` contract rather than bypass it.

---

## Guiding Principle

> **Ingestion preserves source truth. Intelligence interprets it. Humans govern what becomes project truth.**
