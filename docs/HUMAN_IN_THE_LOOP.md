# PMWizard Human-in-the-Loop Governance

## Purpose

PMWizard is designed to make Project Managers and PMOs faster, more informed, and more consistent without transferring project accountability to AI.

The core principle is:

> **PMWizard augments the Project Manager; it does not replace the Project Manager.**

PMWizard may observe project information, structure it, connect it, explain it, and suggest updates. Material changes to the official project record remain governed by humans unless an organization has explicitly configured a trusted automation for a specific structured source.

The operating cycle is:

```text
Connect → Observe → Understand → Suggest → Human confirms → Learn
```

---

## 1. Human Accountability

The Project Manager, Program Manager, PMO, or another authorized human remains responsible for:

- approving material project-status changes;
- accepting, editing, or rejecting AI-proposed RAID entries;
- confirming AI interpretations of unstructured information;
- validating decisions and their business meaning;
- determining escalation and mitigation actions;
- publishing official project status;
- authorizing any automated write-back to source systems.

PMWizard should reduce administrative effort, not remove professional judgment.

---

## 2. The Three Core AI Behaviors

### 2.1 Observe

PMWizard may read authorized project information from connected sources.

Examples:

- meeting minutes and transcripts;
- email;
- Jira, Monday, Airtable, Asana, Smartsheet, or internal tools;
- SharePoint or other document repositories;
- RAID logs;
- project schedules;
- project documents;
- approved APIs and databases.

Observation should be read-only by default.

### 2.2 Suggest

PMWizard may interpret observed information and propose structured changes.

Examples:

- possible new Action Item;
- possible Risk or Issue;
- possible Decision;
- Action Item progress;
- possible blocker;
- possible dependency;
- suggested health change;
- suspected contradiction between sources;
- suggested relationship between project entities.

Every material suggestion should include:

```text
suggested_change
reason
source_evidence
confidence
affected_entity
timestamp
```

### 2.3 Confirm

An authorized human accepts, edits, rejects, or defers the suggestion.

The accepted result becomes part of the governed project record.

```text
AI suggestion
      ↓
Human review
      ↓
Accept / Edit / Reject / Defer
      ↓
Governed project state
```

---

## 3. Facts, Evidence, and Inferences

PMWizard must never silently convert an AI inference into an authoritative fact.

### Fact

Information obtained directly from an authoritative structured source or explicitly confirmed by a human.

Example:

```text
Jira Issue ABC-123
Status: Done
Source: Jira
```

### Evidence

The source material that supports a fact or inference.

Example:

```text
Email - Oct 5
"The configuration has now been tested and is working."
```

### AI Inference

PMWizard's interpretation of available evidence.

Example:

```text
Suggested Action Item status: Completed
Confidence: 94%
Evidence: Email - Oct 5
```

An inference must preserve its evidence and confidence and remain distinguishable from a human-confirmed fact.

---

## 4. Action Item Intelligence

Action Items are a primary V1 use case.

Suggested lifecycle:

```text
Not Started
In Progress
Blocked
Pending External
Ready for Review
Completed
Cancelled
```

Recommended fields include:

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
progress_summary
last_progress_date
latest_evidence_id
source_origin
human_verified
```

### Progress detection

PMWizard may compare new meetings, emails, documents, and connected work-item changes against open Action Items.

Example:

```text
Action:
Verify PRISM cash score configuration

Current status:
In Progress

New evidence:
Email - Oct 5

AI interpretation:
Configuration was verified and is now working.

Suggested status:
Completed

Confidence:
94%
```

The PM may then accept, edit, reject, or keep the Action Item open.

Partial progress should not be treated as completion.

---

## 5. Decision Intelligence

Decisions are first-class project records and must preserve history.

PMWizard may identify a possible decision from a meeting or email, but the official record should be human-confirmed.

A Decision should preserve:

```text
decision
date
decision_maker
context
rationale
expected_impact
source_evidence
status
```

Decisions should not be overwritten when they change.

Instead:

```text
DECISION-041
supersedes
DECISION-023
```

This preserves organizational memory and allows PMWizard to explain why the project evolved.

---

## 6. RAID Governance

PMWizard may propose new or updated:

- Risks;
- Assumptions;
- Issues;
- Dependencies.

Examples:

```text
Meeting statement:
"The vendor may need another week."

PMWizard suggestion:
Possible Risk - Vendor delivery delay
Impact type: Schedule
Probability: Medium
Impact: High
Confidence: 87%
```

or:

```text
Existing Issue:
Production approval pending

New evidence:
Production has been enabled.

PMWizard suggestion:
Issue may be resolved
Confidence: 96%
```

The official RAID state changes only after an authorized human confirms the interpretation, unless a specific trusted automation has been configured.

---

## 7. Project Inbox

AI-generated suggestions should enter a review queue rather than immediately modifying governed project records.

Conceptually:

```text
PMWizard Project Inbox

4 Action Item updates
2 Possible Risks
1 Possible Decision
3 Possible completed Actions
1 Contradiction detected
```

For each suggestion:

```text
Accept
Edit
Reject
Defer
View evidence
```

This creates a fast review workflow while preserving accountability.

---

## 8. Structured Automation Exceptions

Not every change requires manual confirmation forever.

PMWizard may support explicitly configured automation for deterministic, trusted events.

Example:

```text
Jira task status = Done
        ↓
Pre-authorized mapping rule
        ↓
Linked PMWizard WorkItem = Completed
```

This differs from interpreting ambiguous natural language.

Example requiring human review:

```text
"We should be finished with this."
        ↓
AI interpretation
        ↓
Human review required
```

Automation should therefore depend on:

- source authority;
- structured vs. unstructured data;
- confidence and ambiguity;
- materiality of the change;
- organization-specific authorization.

---

## 9. Source Authority

PMWizard should support configurable source authority rather than assuming every source has equal weight.

A possible model:

```text
Level 1 - Human-confirmed governed record
Level 2 - Authoritative structured system
Level 3 - Approved project document
Level 4 - Meeting or email evidence
Level 5 - AI inference
```

This hierarchy is contextual, not universal. Organizations may define different source-authority rules.

When sources conflict, PMWizard should surface the contradiction rather than silently choosing one.

---

## 10. AI Confidence

Confidence is useful for prioritization, but confidence alone must not determine whether a material change becomes authoritative.

A suggestion should ideally expose:

```text
confidence_score
evidence_count
evidence_sources
reasoning_summary
source_authority
human_review_status
```

High confidence does not remove accountability.

---

## 11. Security and Authorization

Human-in-the-loop governance depends on strong authorization.

PMWizard must ensure:

> A user must never receive an AI-generated insight based on data they are not authorized to access.

Permissions must therefore propagate through:

```text
Identity
   ↓
Authentication
   ↓
Authorization
   ↓
Source access
   ↓
Retrieval
   ↓
AI reasoning
   ↓
Response
```

A human may only review or confirm project changes they are authorized to govern.

---

## 12. Learning from Human Feedback

Human review may generate valuable feedback for future PMWizard models.

Examples:

```text
AI suggested: Completed
Human corrected: In Progress

AI suggested: New Risk
Human rejected: Duplicate of R-014

AI suggested: Dependency
Human accepted and changed criticality to High
```

This feedback can later support evaluation, prompt improvement, classification models, entity-resolution improvements, and organization-specific intelligence.

PMWizard should never interpret feedback as permission to reduce human governance without explicit configuration.

---

## 13. Product Success

PMWizard should not be measured only by model accuracy.

The product should also measure whether it makes project management more effective.

Potential success metrics:

```text
Time spent preparing status updates
Time spent maintaining RAID
Time spent reviewing meeting notes
Action Items missed
Action Items overdue
Decisions without traceability
Risks identified late
Suggestions accepted
Suggestions edited
Suggestions rejected
False completion detections
Time saved per PM
```

The target outcome is:

> **Less time collecting project information. More time managing the project.**

---

## 14. V1 Governance Boundary

PMWizard V1 should prioritize:

```text
READ
authorized project information

STRUCTURE
meetings, emails, documents, and source-system data

CONNECT
Action Items, Decisions, RAID, milestones, and evidence

SUGGEST
progress, changes, risks, issues, blockers, and relationships

CONFIRM
through an authorized human

LEARN
from accepted, edited, and rejected suggestions
```

V1 should not autonomously:

- make project-management decisions;
- publish official status without human approval;
- create commitments on behalf of people;
- escalate stakeholders;
- approve budget or scope changes;
- modify RAID based only on unstructured AI interpretation;
- write back to enterprise systems without explicit authorization.

---

## 15. Guiding Principle

PMWizard should make the Project Manager faster without making the Project Manager less responsible.

> **AI interprets. Evidence proves. Human governs.**
