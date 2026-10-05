# PMWizard V1 Architecture

## Purpose

PMWizard is a secure, tool-independent Project Intelligence layer designed to connect project information, build persistent project memory, detect meaningful changes, and help Project Managers and PMOs work faster without transferring project accountability to AI.

PMWizard V1 focuses on a concrete operational problem:

> **Can PMWizard continuously connect meeting notes, email, documents, and existing project records to maintain Action Items, Decisions, RAID, and evidence with less manual effort?**

The first product loop is:

```text
Connect → Observe → Normalize → Understand → Suggest → Human confirms → Learn
```

The architecture should optimize for this loop before adding advanced forecasting, autonomous agents, or portfolio-scale analytics.

---

## 1. Architecture Principles

### 1.1 PMWizard is an intelligence layer, not a replacement for existing tools

Organizations should not need to abandon Jira, Monday, Airtable, SharePoint, internal project systems, spreadsheets, or other execution tools.

```text
Keep the systems of work.
Add a common intelligence layer above them.
```

PMWizard should connect to existing systems through adapters and normalize their information into its own canonical model.

### 1.2 Project is the V1 intelligence boundary

The canonical model supports:

```text
Portfolio
   ↓
Program
   ↓
Project
   ↓
Workstream
   ↓
Milestone
   ↓
WorkItem
```

However, V1 intelligence is primarily scoped around a Project.

Program and Portfolio capabilities should grow from the same model later rather than requiring a redesign.

### 1.3 Human governance is mandatory

PMWizard may read, interpret, connect, and suggest.

It should not autonomously make project-management decisions.

Material AI interpretations flow through the Project Inbox and require authorized human review unless a deterministic structured automation has been explicitly configured.

See `HUMAN_IN_THE_LOOP.md`.

### 1.4 The LLM is a capability, not the system of record

PMWizard must not depend on one model provider.

LLMs may help with:

- information extraction;
- classification;
- summarization;
- entity-resolution assistance;
- contradiction detection;
- semantic matching;
- suggested updates;
- explanations.

Governed project state lives in PMWizard's persistent data model, not inside LLM conversation context.

### 1.5 Security is enforced before AI reasoning

PMWizard must never retrieve unauthorized information and then attempt to filter it from the final answer.

The security path is:

```text
Identity
   ↓
Authentication
   ↓
Authorization
   ↓
Source permissions
   ↓
Filtered retrieval
   ↓
AI reasoning
   ↓
Response
```

No authorized evidence means no retrieval, no model context, and no derived answer.

### 1.6 Read-only integration first

V1 connectors should be read-only by default.

The initial sequence is:

```text
Observe → Understand → Suggest
```

Write-back to Jira, Monday, Outlook, Airtable, or another enterprise source is a later capability requiring explicit authorization and policy.

### 1.7 Start as a modular monolith

PMWizard V1 should be implemented as a modular monolith rather than a distributed microservice architecture.

This keeps the system easier to develop, test, secure, run locally, and understand as an open-source project.

Module boundaries should still be explicit so components can be extracted later if scale requires it.

---

## 2. High-Level Architecture

```text
                        SOURCE SYSTEMS

 Outlook     SharePoint      Airtable       Jira
 Monday      Meetings        Documents      Internal APIs
    │             │              │              │
    └─────────────┴──────────────┴──────────────┘
                          │
                          ▼
                CONNECTOR / ADAPTER LAYER
                          │
                          ▼
                    INGESTION LAYER
                          │
               ┌──────────┴──────────┐
               │                     │
        Structured Data      Unstructured Data
               │                     │
               └──────────┬──────────┘
                          ▼
               SECURITY & SCOPE FILTER
                          │
                          ▼
                 NORMALIZATION LAYER
                          │
                          ▼
             PMWIZARD CANONICAL MODEL
                          │
                          ▼
                    PROJECT MEMORY
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
 Action Items           RAID              Decisions
 Milestones           Evidence              Events
 Dependencies         People             Relationships
      │                   │                   │
      └───────────────────┼───────────────────┘
                          ▼
                ENTITY RESOLUTION ENGINE
                          │
                          ▼
                  INTELLIGENCE ENGINE
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
 Progress             Change             Contradiction
 Detection            Detection            Detection
      │                   │                   │
      └───────────────────┼───────────────────┘
                          │
                          ▼
                    PROJECT INBOX
                          │
                 Accept / Edit / Reject
                          │
                          ▼
                GOVERNED PROJECT STATE
                          │
                          ▼
                 AUDIT + FEEDBACK LOOP
```

---

## 3. Source Systems

PMWizard must assume that project context is fragmented.

Initial source categories include Outlook email, SharePoint documents, meeting minutes and transcripts, Airtable, Jira, Monday, spreadsheets, internal enterprise project systems, and generic REST APIs.

Future adapters may include Asana, Smartsheet, GitHub, Azure DevOps, ClickUp, Notion, ServiceNow, Teams, and Slack where enterprise permissions allow.

Source systems remain authoritative for the facts they own.

PMWizard stores normalized representations, source references, relationships, evidence metadata, and governed intelligence derived from those sources.

---

## 4. Connector / Adapter Layer

Every source integrates through a common connector contract.

A conceptual interface:

```python
class Connector:
    def authenticate(self): ...
    def test_connection(self): ...
    def get_projects(self): ...
    def get_items(self): ...
    def get_documents(self): ...
    def get_changes(self): ...
    def get_permissions(self): ...
```

Initial adapters should include:

```text
MicrosoftGraphConnector
AirtableConnector
JiraConnector
MondayConnector
GenericAPIConnector
```

An adapter should authenticate to the source, retrieve only authorized content, preserve source identifiers, capture permission context, retrieve incremental changes where possible, and convert source-specific payloads into ingestion objects.

Adapters should not decide whether something is a Risk, whether an Action Item is complete, project health, whether two records refer to the same entity, or whether an AI suggestion becomes governed state.

---

## 5. Microsoft Integration

Microsoft Graph is the preferred initial integration boundary for Microsoft 365 capabilities.

Potential V1 sources:

```text
Outlook
SharePoint
Microsoft 365 files
```

The connector should be explicitly scoped to project-relevant content rather than scanning an entire organization indiscriminately.

A project connection may define:

```text
project_id
mailbox_scope
folder_scope
sharepoint_site
document_library
approved_participants
date_range
allowed_content_types
permission_context
```

OAuth tokens and refresh credentials must never be stored in plaintext. Production deployments should use a dedicated secret-management capability.

---

## 6. Ingestion Layer

The ingestion layer receives authorized source content and creates a traceable ingestion record.

Structured examples include Jira tasks, Monday items, Airtable Action Items, milestones, statuses, due dates, owners, and RAID rows.

Unstructured examples include email bodies, meeting transcripts, meeting minutes, project documents, and notes.

Each ingestion unit should capture:

```text
tenant_id
project_id
source_system
source_type
source_id
source_timestamp
ingested_at
permission_scope
content_hash
processing_status
```

The content hash helps prevent duplicate processing.

Where a source supports change tracking or webhooks, PMWizard should prefer incremental ingestion over repeatedly re-reading everything.

---

## 7. Security and Scope Layer

Security is part of the retrieval architecture.

Every sensitive record should be associated with enough context to enforce access.

Core dimensions include:

```text
tenant_id
project_id
source_connection_id
source_id
permission_scope
authorized_principal
```

### Tenant isolation

Records belonging to one organization must not become retrievable by another organization.

### Project isolation

Even within a tenant, users may have access to different projects.

### Source permission inheritance

A user should not gain access to an email, file, issue, or derived AI insight merely because PMWizard ingested it.

Derived information must remain constrained by the evidence permissions that produced it.

### Retrieval rule

```text
Unauthorized evidence
        ↓
Excluded before retrieval
        ↓
Never included in model context
        ↓
Cannot influence response
```

---

## 8. Normalization Layer

Source-specific objects are translated into the PMWizard Canonical Project Model.

Examples:

```text
Jira Issue
Monday Item
Airtable Record
Internal Work Item
        ↓
     WorkItem
```

or:

```text
Outlook Email
Meeting Transcript
SharePoint Document
        ↓
      Evidence
```

Normalization should preserve source system, external ID, original timestamps, authoritative source values, permission context, and links to original evidence.

Normalization must not silently reinterpret facts.

AI-derived interpretation occurs separately.

See `DATA_MODEL.md`.

---

## 9. Project Memory

Project Memory is the persistent representation of what PMWizard knows about a Project.

It includes project structure, Action Items, RAID, Decisions, Milestones, WorkItems, People, External Parties, Evidence, Events, Relationships, Human Confirmations, and AI Suggestions.

Project Memory is not conversation history. It is a governed, queryable, temporal project model.

### Governed state

The governed state contains facts and human-confirmed project records.

### Suggestion state

AI-proposed interpretations live separately until accepted.

```text
Governed:
ACTION-024
Status = In Progress

AI Suggestion:
ACTION-024 may now be Completed
Confidence = 0.94
Evidence = EMAIL-893
Review status = Pending
```

The AI suggestion does not overwrite the governed record.

---

## 10. Primary Database

PMWizard V1 should use PostgreSQL as the primary operational database.

Reasons include transactional consistency, strong relational modeling, JSON support, row-level security capabilities, compatibility with pgvector, and lower infrastructure complexity.

Initial logical tables may include:

```text
tenants
users
projects
workstreams
milestones
work_items

action_items
risks
assumptions
issues
dependencies
decisions

people
external_parties
financial_records

evidence
events
relationships

source_connections
ingestion_records

ai_suggestions
human_reviews
audit_log
```

The exact physical schema should evolve from the canonical model rather than being optimized prematurely.

---

## 11. Vector Search

PMWizard V1 should use pgvector with PostgreSQL for semantic retrieval.

Embeddings may support finding related Action Items, matching new evidence to existing RAID entries, candidate entity resolution, retrieving relevant meeting/email evidence, identifying similar Decisions, and semantic project search.

Vector similarity must not be treated as proof that two entities are identical. It is a candidate-generation mechanism.

---

## 12. Entity Resolution Engine

Entity resolution determines whether incoming information refers to an existing project object or represents something new.

Example:

```text
Meeting:
"John will review the API configuration."

Email:
"The API setup was reviewed."

Jira:
"API Configuration Review" = Done
```

PMWizard should evaluate whether these are evidence about the same underlying Action Item.

Initial resolution should combine:

```text
Exact / normalized text matching
Owner matching
Project / workstream context
Temporal proximity
Source identifiers
Semantic similarity
Relationship context
LLM classification when ambiguity remains
```

Conceptual flow:

```text
New evidence
     ↓
Candidate search
     ↓
Potential matches
     ↓
Resolution scoring
     ↓
High-confidence deterministic match → link
Ambiguous match → AI suggestion / human review
No match → candidate new entity
```

Duplicate prevention is a core product capability.

---

## 13. AI Provider Gateway

PMWizard should isolate model-provider logic behind an AI Provider Gateway.

```text
                  PMWizard Core
                       │
               AI Provider Gateway
                       │
          ┌────────────┼────────────┐
          │            │            │
       OpenAI       Anthropic     Azure /
                                 Enterprise
```

The gateway should standardize capabilities such as:

```text
extract_structured_data()
classify()
summarize()
compare_evidence()
resolve_candidate()
generate_explanation()
```

Provider-specific prompts, APIs, rate limits, and model identifiers should remain outside the domain model.

This allows organizations to select providers according to security, compliance, performance, and cost requirements.

---

## 14. Intelligence Engine

The Intelligence Engine operates on authorized Project Memory plus new evidence.

V1 capabilities should prioritize:

- Action Item extraction;
- Action Item progress detection;
- Decision detection;
- RAID detection;
- RAID progress or resolution;
- contradiction detection;
- evidence-backed explanation generation.

For every important suggestion, PMWizard should expose:

```text
What PMWizard observed
What PMWizard suggests
Why
Evidence
Confidence
Affected project objects
```

---

## 15. Project Inbox

The Project Inbox is the primary human-review surface for AI-generated project intelligence.

A PM might see:

```text
4 Action Item updates
2 possible new Risks
1 possible Decision
1 resolved Issue
1 contradiction
```

Each suggestion should support:

```text
Accept
Edit
Reject
Defer
View evidence
```

A review creates a durable human_review record.

Accepted or edited suggestions may update governed state. Rejected suggestions remain valuable evaluation data.

---

## 16. Audit and Feedback

Every meaningful project-state transition should be traceable.

```text
2026-10-05 10:31

Suggestion:
ACTION-024 → Completed

Evidence:
EMAIL-893

AI confidence:
0.92

Reviewed by:
Authorized PM

Decision:
Edited

Final state:
In Progress
```

The audit layer should capture actor, action, timestamp, entity, previous state, proposed state, final state, source evidence, model/provider when AI was involved, and human review.

This supports accountability, debugging, enterprise trust, model evaluation, product analytics, and future learning datasets.

---

## 17. Background Processing

Ingestion and analysis should not block interactive API requests.

Background work may include connector synchronization, document parsing, embedding generation, entity-resolution candidate generation, intelligence analysis, and scheduled project refresh.

V1 should avoid prematurely introducing a large distributed queue platform. A lightweight worker architecture is sufficient initially.

---

## 18. API Layer

PMWizard should be API-first.

Initial API domains may include:

```text
/projects
/connections
/ingestion
/action-items
/raid
/decisions
/evidence
/suggestions
/reviews
/audit
/search
```

The API must enforce tenant and project authorization independently of the UI. The UI is a client of the security model, not the security boundary.

---

## 19. Initial Technology Stack

| Area | Initial choice |
|---|---|
| Language | Python |
| API | FastAPI |
| Validation / schemas | Pydantic |
| ORM / persistence | SQLAlchemy |
| Primary DB | PostgreSQL |
| Semantic search | pgvector |
| Migrations | Alembic |
| Microsoft integration | Microsoft Graph |
| Jira integration | Jira REST API |
| Monday integration | Monday GraphQL API |
| Airtable integration | Airtable API |
| AI | Provider abstraction layer |
| Testing | pytest |
| Local environment | Docker Compose |
| UI | Deferred initially; Next.js is a candidate |

These are implementation defaults, not permanent product constraints.

---

## 20. Repository Structure

```text
PMWizard/
│
├── docs/
│   ├── VISION.md
│   ├── DATA_MODEL.md
│   ├── HUMAN_IN_THE_LOOP.md
│   └── ARCHITECTURE.md
│
├── src/
│   └── pmwizard/
│       ├── api/
│       ├── core/
│       ├── models/
│       ├── connectors/
│       ├── ingestion/
│       ├── intelligence/
│       ├── resolution/
│       ├── security/
│       ├── audit/
│       └── ai/
│
├── tests/
├── examples/
└── README.md
```

---

## 21. First Functional Vertical

The first end-to-end vertical should prove the product concept before broad integration work.

### Inputs

```text
Existing Action Items
Existing RAID
Existing Decisions
Meeting minutes
New meeting notes
New email evidence
```

### Processing

```text
Ingest
  ↓
Normalize
  ↓
Resolve entities
  ↓
Compare evidence with current project state
  ↓
Generate suggestions
```

### Outputs

```text
New possible Action Items
Action Item progress
Possible completed Action Items
New Decisions
New RAID entries
RAID progress / resolution
Contradictions
Evidence links
```

### Human review

```text
Project Inbox
   ↓
Accept / Edit / Reject / Defer
   ↓
Governed Project Memory
```

This vertical should work with synthetic or explicitly authorized demonstration data before expanding to enterprise deployment.

---

## 22. Migration from an Existing Airtable-Based Prototype

An existing Airtable workflow can be treated as an early operational prototype rather than discarded.

```text
Airtable
   ↓
Airtable Connector
   ↓
PMWizard Canonical Model
   ↓
Project Memory
```

This allows PMWizard to reuse working Action Item and RAID concepts, discover which fields are genuinely useful, compare suggestions with an existing human-managed system, and migrate incrementally rather than requiring a big-bang replacement.

Airtable may remain an operational interface during early development. PMWizard should not make Airtable its permanent domain model.

---

## 23. Evolution Roadmap

### V0 — Project Memory

Meetings, existing Action Items, Decisions, RAID, Evidence, and Human Review.

Goal: establish persistent, traceable project memory.

### V0.5 — Progress Intelligence

Use new meeting and email evidence to detect Action Item, Decision, and RAID progress through the Project Inbox.

Goal: reduce manual project maintenance.

### V1 — Integration Intelligence

Add production-quality adapters for Microsoft 365, Airtable, Jira, Monday, and generic APIs.

Goal: connect PMWizard to existing project ecosystems.

### V1.5 — Project Health

Use governed Project Memory to explain Schedule, Risk, Dependency, Resource, Scope, Financial, Stakeholder, and Overall Health.

Goal: explain project state from evidence rather than manual RAG color alone.

### V2 — Predictive Intelligence

Potential capabilities include delay probability, resource conflicts, risk trends, anomaly detection, forecast changes, and cross-project dependencies.

Goal: anticipate, not only explain.

### Future — Program and Portfolio Intelligence

Use the existing canonical model to reason across multiple projects.

---

## 24. Deferred Decisions

The following should not be introduced until evidence shows they are required:

- Neo4j or another dedicated graph database;
- Kubernetes;
- Kafka or large streaming platforms;
- multiple vector databases;
- autonomous agents;
- automatic enterprise write-back.

PostgreSQL relationships, pgvector, a modular monolith, lightweight workers, read-only connectors, and human-governed changes are sufficient for the first implementation.

---

## 25. Architecture Success Criteria

The architecture is successful if PMWizard can answer questions such as:

> What changed in this project since the previous meeting?

> Which open Action Items show evidence of progress?

> Which Action Items may be complete but have not been confirmed?

> What Decisions were made this week?

> Which RAID items changed?

> What evidence supports this suggested update?

> Are two sources contradicting each other?

> Why is PMWizard suggesting this change?

and always preserve:

```text
Source
Evidence
Permission
Confidence
Human governance
Audit history
```

---

## 26. Guiding Architecture Statement

PMWizard should be easy to connect, difficult to misuse, and explicit about what it knows versus what it infers.

> **Keep your tools. Connect the intelligence between them.**
