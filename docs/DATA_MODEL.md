# PMWizard Canonical Project Data Model

## Purpose

PMWizard needs a tool-independent way to understand projects.

The canonical data model is the internal language used by PMWizard to normalize information coming from Jira, Monday, Asana, Smartsheet, GitHub, spreadsheets, internal enterprise systems, APIs, databases, meetings, documents, email, and future connectors.

PMWizard should never depend on the structure of a single source platform. Source systems provide data; PMWizard provides project meaning.

The model is designed around one central principle:

> Humans communicate naturally. PMWizard creates structure without losing the original evidence or context.

The first implementation focuses on **Project Intelligence**. The model nevertheless supports a future hierarchy from Portfolio to Program to Project so PMWizard can expand toward Program and Portfolio Intelligence without redesigning its core.

---

## 1. Design Principles

### 1.1 Project is the primary intelligence unit

PMWizard V1 is centered on the Project entity. Portfolio and Program are supported as optional parent structures.

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

A project does not require a portfolio or program parent. This allows PMWizard to work for both small teams and enterprise PMOs.

### 1.2 Tool-independent model

Jira issues, Monday items, spreadsheet rows, internal work items, and similar objects are normalized into PMWizard entities.

```text
Jira ──────────┐
Monday ────────┤
Asana ─────────┤
Smartsheet ────┤
Excel ─────────┼──► PMWizard Canonical Project Model
Internal API ──┤
Database ──────┤
Documents ─────┤
Meetings ──────┘
```

Adapters translate source-specific structures into the canonical model.

### 1.3 Facts and AI inferences must remain separate

PMWizard must distinguish information retrieved from authoritative sources from information inferred by AI or analytical models.

A source fact may be:

```text
Milestone M-12
Due date: 2026-09-15
Status: In Progress
Source: Jira
```

An inference may be:

```text
Schedule risk: High
Estimated probability of delay: 72%
Confidence: 84%
Evidence: M-12, R-04, D-08
```

An inference must never silently overwrite a fact.

### 1.4 Every important insight should be explainable

PMWizard should be able to answer:

> Why are you telling me this?

Insights should therefore link to Evidence and, when applicable, to the entities and relationships that produced them.

### 1.5 Temporal history matters

Projects evolve. PMWizard should preserve what changed, when it changed, and where the change came from.

Historical states should enable questions such as:

- Why did the project move from Green to Yellow?
- When did the delivery risk begin increasing?
- Which event caused the forecast to change?
- What decisions were made before a milestone slipped?

### 1.6 Human-in-the-loop by default

AI may identify, classify, suggest, connect, or enrich project information, but uncertain or material changes should be reviewable by a human.

```text
AI proposes → Human reviews → Human accepts/edits/rejects
```

### 1.7 Security context is part of the data model

Entities and evidence may contain sensitive information. Every object must be capable of carrying access-control and source-permission metadata so retrieval respects the user's authorization.

---

## 2. Core Entity Model

PMWizard V1 defines sixteen primary entities.

| Domain | Entity | Purpose |
|---|---|---|
| Structure | Portfolio | Optional top-level grouping for strategic investments or initiatives |
| Structure | Program | Optional grouping of related projects |
| Structure | Project | Primary PMWizard intelligence unit |
| Structure | Workstream | Functional, technical, operational, or delivery subdivision of a project |
| Delivery | Milestone | Significant delivery checkpoint or target |
| Delivery | WorkItem | Generic execution object such as task, story, epic, activity, feature, or deliverable action |
| Governance | Risk | Uncertain event or condition that may affect objectives |
| Governance | Issue | Current condition already affecting or requiring attention |
| Governance | Dependency | Relationship in which one object requires another condition, object, team, approval, or outcome |
| Governance | Decision | Recorded choice, pending choice, rationale, and impact |
| Governance | ActionItem | Explicit follow-up action with ownership and expected completion |
| People | Person | Individual acting as PM, stakeholder, contributor, approver, executive, or other role |
| People | ExternalParty | Vendor, partner, client organization, regulator, or other external entity |
| Business | FinancialRecord | Budget, forecast, actual, benefit, cost, or other financial observation |
| Knowledge | Evidence | Traceable source supporting facts, relationships, or AI inferences |
| Temporal | Event | Time-based change in project state |

Additional entities may be introduced later, but V1 should resist unnecessary complexity.

---

## 3. Entity Definitions

### 3.1 Portfolio

Represents an optional strategic collection of programs and projects.

Suggested fields:

```text
id
name
description
owner
status
start_date
end_date
strategic_objectives
source_system
external_id
```

### 3.2 Program

Represents a coordinated group of related projects.

Suggested fields:

```text
id
portfolio_id (optional)
name
description
program_manager
status
start_date
end_date
objectives
source_system
external_id
```

### 3.3 Project

The central PMWizard entity.

Suggested fields:

```text
id
program_id (optional)
portfolio_id (optional)
name
description
objective
project_manager
sponsor
methodology
industry
lifecycle_phase
status
start_date
planned_end_date
forecast_end_date
actual_end_date
priority
business_value
source_system
external_id
created_at
updated_at
```

Project-level AI intelligence should reference this entity.

### 3.4 Workstream

Represents a major project subdivision.

Examples:

- Data Engineering
- Infrastructure
- Reporting
- Change Management
- Legal
- Marketing

Suggested fields:

```text
id
project_id
name
description
owner
status
start_date
end_date
```

### 3.5 Milestone

Represents an important delivery checkpoint.

Suggested fields:

```text
id
project_id
workstream_id (optional)
name
description
owner
planned_date
forecast_date
actual_date
status
criticality
schedule_float_days
completion_percentage
```

### 3.6 WorkItem

Generic execution entity capable of representing source-specific work structures without forcing PMWizard to reproduce each platform's taxonomy.

Possible source types include:

```text
Task
Story
Epic
Feature
Activity
Deliverable
Subtask
Sprint Item
Custom Work Item
```

Suggested fields:

```text
id
project_id
workstream_id (optional)
parent_work_item_id (optional)
source_type
name
description
owner
status
priority
planned_start
planned_end
forecast_end
actual_end
completion_percentage
estimate
actual_effort
source_system
external_id
```

### 3.7 Risk

Represents an uncertain future condition.

Suggested fields:

```text
id
project_id
title
description
category
probability
impact
exposure
impact_type
trigger
mitigation
contingency
owner
status
due_date
identified_at
closed_at
```

Typical impact types:

```text
Schedule
Cost
Scope
Quality
Resource
Technical
Vendor
Compliance
Stakeholder
Business
```

### 3.8 Issue

Represents an existing problem or condition requiring action.

Suggested fields:

```text
id
project_id
title
description
category
severity
impact_type
owner
status
due_date
identified_at
resolved_at
resolution
```

A Risk may become an Issue, but the two should remain distinct objects with traceable relationships.

### 3.9 Dependency

Represents a requirement or reliance between project objects or external conditions.

Dependency types may include:

```text
Technical
Resource
Vendor
Project
Milestone
WorkItem
Decision
Financial
Approval
Data
Infrastructure
External
```

Suggested fields:

```text
id
project_id
title
description
dependency_type
owner
provider
required_by
status
criticality
```

Dependencies should primarily gain meaning through relationships such as `depends_on`, `blocks`, and `required_for`.

### 3.10 Decision

Decisions are first-class project knowledge.

Suggested fields:

```text
id
project_id
title
description
status
decision_date
decision_maker
context
alternatives_considered
rationale
expected_impact
review_date
```

Possible states:

```text
Proposed
Pending
Approved
Rejected
Superseded
Reversed
```

### 3.11 ActionItem

Represents a concrete follow-up action.

Suggested fields:

```text
id
project_id
title
description
owner
created_at
due_date
completed_at
status
priority
```

### 3.12 Person

Represents a human actor.

Suggested fields:

```text
id
display_name
role
organization
team
capacity
allocation
source_system
external_id
```

Sensitive employee information should not be required for core project intelligence.

### 3.13 ExternalParty

Represents vendors, partners, customers, regulators, or other organizations outside the core project team.

Suggested fields:

```text
id
name
party_type
relationship_owner
status
source_system
external_id
```

### 3.14 FinancialRecord

Flexible financial observation linked to a project, workstream, vendor, milestone, or another supported object.

Record types may include:

```text
Budget
Forecast
Actual
Committed Cost
Benefit
Savings
Revenue
Contingency
```

Suggested fields:

```text
id
project_id
record_type
amount
currency
period
as_of_date
source_system
external_id
```

### 3.15 Evidence

Evidence is the traceable basis for project facts and AI inferences.

Examples:

```text
Jira issue
Monday item
Spreadsheet cell or row
Meeting transcript
Meeting minutes
Email
Slack/Teams message
Project document
Database record
API response
Human PM update
```

Suggested fields:

```text
id
project_id
source_type
source_system
source_reference
external_id
author
captured_at
effective_at
content_excerpt
content_hash
permission_scope
```

The canonical data model should store references and normalized context while respecting source retention and security requirements.

### 3.16 Event

Represents a change in project state over time.

Examples:

```text
RiskCreated
RiskEscalated
IssueOpened
MilestoneMoved
MilestoneCompleted
DecisionApproved
BudgetChanged
ResourceAllocationChanged
DependencyBlocked
ProjectHealthChanged
ScopeChanged
```

Suggested fields:

```text
id
project_id
event_type
occurred_at
actor
entity_type
entity_id
previous_value
new_value
source_evidence_id
```

Events allow PMWizard to reconstruct project history.

---

## 4. Relationship Model

Entities alone are insufficient. PMWizard intelligence depends on explicit relationships.

A generic relationship should support:

```text
id
project_id
source_entity_type
source_entity_id
relationship_type
target_entity_type
target_entity_id
valid_from
valid_to
confidence
origin
source_evidence_id
```

Example relationships:

```text
Project → belongs_to → Program
Program → belongs_to → Portfolio
Project → contains → Workstream
Workstream → contains → Milestone
Milestone → contains → WorkItem

Risk → impacts → Milestone
Risk → impacts → Project
Risk → may_become → Issue

Issue → blocks → WorkItem
Issue → impacts → Milestone
Decision → resolves → Issue
Decision → mitigates → Risk

WorkItem → depends_on → WorkItem
Milestone → depends_on → Milestone
Project → depends_on → Project
Dependency → blocks → Milestone
Dependency → required_for → WorkItem

Person → owns → Risk
Person → owns → ActionItem
Person → assigned_to → Workstream
ExternalParty → provides → Dependency

FinancialRecord → applies_to → Project
FinancialRecord → applies_to → Workstream
FinancialRecord → applies_to → ExternalParty

Evidence → supports → Risk
Evidence → supports → Issue
Evidence → supports → Decision
Evidence → supports → Inference
```

Relationships can be direct facts or AI-proposed connections. Their origin must be preserved.

---

## 5. Facts, Evidence, and Inferences

PMWizard should model three different concepts.

### Fact

A value or relationship retrieved from an authoritative or human-provided source.

Example:

```text
Milestone planned date = 2026-09-20
```

### Evidence

The traceable source from which a fact or inference was derived.

Example:

```text
Source: Jira issue PROJ-240
Retrieved: 2026-09-09T16:10:00-05:00
```

### Inference

A conclusion produced by AI, rules, statistical models, or analytical logic.

Example:

```text
Inference Type: ScheduleRisk
Value: High
Confidence: 0.86
```

Suggested inference fields:

```text
id
project_id
inference_type
value
confidence
model_or_rule
created_at
valid_until
status
human_review_status
```

Every material inference should link to one or more Evidence records and relevant entities.

---

## 6. Project Health Model

PMWizard should not represent project health as a single unexplained Red/Yellow/Green value.

A **ProjectHealthSnapshot** should evaluate multiple dimensions.

Initial V1 dimensions:

```text
Schedule Health
Financial Health
Scope Health
Resource Health
Risk Health
Dependency Health
Quality Health
Stakeholder Health
```

Suggested snapshot structure:

```text
project_id
as_of_date
overall_health
schedule_health
financial_health
scope_health
resource_health
risk_health
dependency_health
quality_health
stakeholder_health
confidence
```

Each health dimension should connect to drivers and Evidence.

Example:

```text
Resource Health: RED

Drivers:
- Backend engineer allocation = 96%
- Two critical milestones depend on the same resource
- No backup resource identified
```

### Current Health vs Forecast

PMWizard should distinguish present condition from expected future outcome.

```text
Current Health: Green
Forecast Health: Yellow
On-Time Delivery Probability: 58%
```

This enables PMWizard to identify emerging problems before traditional status reporting turns Red.

---

## 7. Natural Language Structuring

PMWizard should allow project professionals to communicate naturally.

Input:

> We are still waiting for the PO. Finance expects it next week, and the vendor cannot start until it is approved.

PMWizard may propose:

```text
Issue
Title: PO approval pending

Dependency
Vendor start depends on PO approval

Potential Impact
Vendor kickoff milestone

Suggested Action
Follow up with Finance
```

These objects should initially be marked as AI-proposed until accepted or confirmed by authorized users or corroborated by authoritative sources.

The goal is not to force PMs to behave like database administrators. PMWizard should translate natural project language into structured project intelligence.

---

## 8. Integration and Source Identity

Every imported entity should preserve source identity.

At minimum:

```text
source_system
external_id
source_url or reference (when permitted)
last_synced_at
source_version or updated_at
```

This enables deduplication, traceability, incremental synchronization, and safe write-back in future releases.

Example mappings:

```text
Jira Epic      → WorkItem(source_type = Epic)
Jira Story     → WorkItem(source_type = Story)
Monday Item    → WorkItem(source_type = MondayItem)
Internal Task  → WorkItem(source_type = Custom)
Excel RAID row → Risk / Issue / Dependency
Meeting note   → Evidence
```

Adapters should map source systems into PMWizard; PMWizard should not redesign itself around adapters.

---

## 9. Security and Access Metadata

PMWizard will potentially process confidential business information. Authorization must therefore propagate into retrieval and AI reasoning.

Entities should support metadata such as:

```text
tenant_id
project_scope
permission_scope
source_connection_id
classification
created_by
```

Initial security principles:

1. **Least privilege** — connectors receive only the access needed for their function.
2. **Read-only first** — early PMWizard releases should observe and recommend before gaining write access.
3. **Source permissions respected** — PMWizard must not reveal information a user could not access in the originating environment.
4. **AI retrieval authorization** — access filtering happens before context is sent to an AI model, not only in the UI.
5. **Traceability** — important insights identify their supporting sources.
6. **Tenant isolation** — enterprise information must remain isolated across organizations.
7. **No silent AI mutation** — inferred values do not overwrite authoritative source data.

Detailed security architecture will be defined separately.

---

## 10. Temporal Intelligence

PMWizard should preserve project evolution rather than only current values.

For example:

```text
Aug 08  Vendor access delayed
Aug 14  Integration milestone moved +4 days
Aug 20  Backend capacity decreased 20%
Aug 27  UAT schedule buffer reached zero
Sep 02  Critical issue opened
Sep 05  Project health changed to Red
```

With this history PMWizard can answer:

> Why did the project become Red?

using traceable state changes rather than a generic LLM summary.

Events and snapshots also provide future training data for forecasting and machine-learning models.

---

## 11. PM and PMO Views

The same canonical model should support different levels of abstraction.

### Project Manager

Typical questions:

- What requires my attention today?
- Which risks are increasing?
- Which actions are overdue?
- What is threatening the next milestone?
- What changed since the last status meeting?

### Program Manager

Typical questions:

- Which dependencies cross projects?
- Where are shared resources overallocated?
- Which projects are likely to affect other projects?

### PMO

Typical questions:

- Which projects are deteriorating?
- Where is portfolio exposure increasing?
- Which vendors affect multiple projects?
- What systemic patterns are appearing across delivery?
- Which projects need escalation?

### Executive

Typical questions:

- Why is the initiative Yellow?
- What changed this month?
- What decisions are required?
- What is most likely to affect business outcomes?

The data model stays consistent while the intelligence and presentation layer adapts to the user's role.

---

## 12. V1 Scope Boundary

PMWizard V1 should prioritize:

```text
Connect
→ Normalize
→ Structure
→ Relate
→ Explain
```

V1 does **not** need to become a full Jira/Monday replacement.

Out of scope for the initial canonical model implementation:

- Full Kanban or Scrum execution UI
- Time tracking platform replacement
- Full resource management suite
- Automated project changes without review
- Complex portfolio optimization
- Autonomous project management
- Large-scale predictive ML before sufficient data exists

These capabilities may evolve later from the intelligence foundation.

---

## 13. Initial Canonical Flow

```text
Source Systems
     │
     ▼
Adapters
     │
     ▼
Canonical Project Model
     │
     ├── Entities
     ├── Relationships
     ├── Facts
     ├── Evidence
     └── Events
     │
     ▼
Project Intelligence
     │
     ├── Health
     ├── Drivers
     ├── Emerging Risks
     ├── Dependencies
     ├── Changes
     └── Explanations
     │
     ▼
PM / Program Manager / PMO / Executive
```

---

## 14. Example Project Context

A simplified PMWizard representation might contain:

```text
Project: Customer Platform Transformation

Milestone M-07: API Integration
Planned date: Sep 25
Schedule float: 3 days

Dependency D-04: Vendor API credentials
Status: Open
Required by: Sep 18

Risk R-08: Vendor access delay
Probability: Medium
Impact: High

Person P-12: Backend Engineer
Allocation: 92%

Milestone M-09: UAT Start
Planned date: Sep 28
```

Relationships:

```text
D-04 blocks M-07
R-08 impacts M-07
M-09 depends_on M-07
P-12 assigned_to M-07
```

PMWizard could then produce an explainable inference:

```text
Schedule Risk: HIGH
Confidence: 87%

Reasoning drivers:
1. Critical vendor dependency remains open.
2. Integration milestone has only three days of schedule float.
3. UAT directly depends on integration completion.
4. Primary backend resource is already allocated at 92%.
```

This illustrates the goal of the canonical model: transform fragmented project information into connected, explainable project intelligence.

---

## 15. Future Extensions

The model should be extensible toward:

- Project Digital Twins
- Program and Portfolio dependency graphs
- Historical project learning
- Predictive delivery models
- Resource conflict forecasting
- Scenario simulation
- AI agents specialized in schedule, risk, finance, resources, governance, and executive reporting
- Open project interchange schemas
- Secure enterprise knowledge graphs
- Human-approved write-back into source systems

These extensions should build on the canonical model rather than bypass it.

---

## 16. Foundational Product Principle

PMWizard is not designed to replace the way project professionals communicate.

It is designed to understand that communication, connect it to reliable project data, structure what matters, preserve evidence, and explain what the project is actually telling us.

> Keep your tools. Connect the intelligence between them.
