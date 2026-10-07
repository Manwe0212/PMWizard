# Entity Resolution V0

## Purpose

Entity Resolution answers a foundational PMWizard question:

> When new project evidence arrives, does it refer to an existing project entity or something new?

V0 focuses only on resolving new Evidence against existing open Action Items.

Examples:

```text
Existing Action Item:
Verify API access

New email:
"API access has been verified and is working."
```

PMWizard should recognize the existing Action Item as a plausible match instead of automatically creating a duplicate.

---

## V0 Principles

### Explainable before sophisticated

V0 uses deterministic scoring rather than embeddings or an LLM.

Every candidate exposes the factors contributing to its score.

### Project and tenant scoped

Resolution runs only against Action Items that are:

- inside the same Project;
- accessible to the current tenant;
- still open.

### Resolution is not project-state mutation

Matching Evidence to an Action Item does not mark the Action Item complete, blocked, or otherwise change governed state.

Progress interpretation remains a separate intelligence step governed by Human Review.

### Ambiguity is surfaced

When multiple candidates are plausible, PMWizard returns `needs_review` rather than forcing a match.

---

## Outcomes

### matched

A candidate has a sufficiently high and distinct deterministic score.

This means PMWizard may link the Evidence to the entity without interpreting the operational status of that entity.

### needs_review

At least one plausible candidate exists, but the score is not strong enough or multiple candidates are too close.

A later Project Inbox flow can ask the PM to select the correct entity.

### no_match

No existing Action Item reaches the minimum candidate threshold.

The Evidence may describe:

- a new Action Item;
- another entity type;
- general project context;
- irrelevant information.

---

## V0 Scoring Factors

The Action Item resolver currently considers:

```text
Exact title phrase      25%
Title keyword coverage  35%
Text similarity         10%
Token overlap           15%
Owner match             10%
Temporal proximity       5%
```

The score is intentionally transparent and configurable.

Current default thresholds:

```text
Matched:       >= 0.78 and sufficiently distinct
Needs review:  >= 0.30
No match:      < 0.30

Ambiguity margin: 0.08
```

These values are V0 defaults and should be evaluated with a representative benchmark dataset before production use.

---

## Example

```text
Action Item:
Confirm vendor access

Evidence:
"Confirm vendor access was completed today."

Resolution:
matched

Reasons:
- action title appears in evidence
- most Action Item keywords appear in evidence
- strong keyword overlap
- evidence is temporally close to the Action Item
```

This match does **not** mean the Action Item becomes Completed.

A later progress-intelligence step may propose:

```text
Suggested status: Completed
```

and Human Review governs whether that suggestion updates Project Memory.

---

## V0 Flow

```text
New Evidence
     ↓
Authorized Project Memory
     ↓
Open Action Items
     ↓
Deterministic candidate scoring
     ↓
┌──────────────┬──────────────┬──────────────┐
│   matched    │ needs_review │   no_match   │
└──────────────┴──────────────┴──────────────┘
```

---

## Deferred to Later Versions

V0 deliberately does not include:

- embeddings / pgvector candidate search;
- LLM-assisted classification;
- cross-project entity resolution;
- automatic creation of new Action Items;
- RAID or Decision resolution;
- semantic synonym models;
- organization-specific learned weights.

Potential V1 resolution sequence:

```text
Deterministic matching
        +
Semantic candidate retrieval
        +
LLM classification for ambiguous cases
        ↓
Explainable resolution result
        ↓
Human review where required
```

---

## Success Criteria

Entity Resolution should eventually be measured using a labeled benchmark containing:

- true existing-entity matches;
- ambiguous cases;
- duplicate-like Action Items;
- unrelated evidence;
- new-entity cases.

Important metrics include:

```text
Precision of deterministic matches
Recall of known matches
False-link rate
Duplicate-prevention rate
Human correction rate
Ambiguous-case accuracy
```

False linking is more dangerous than asking for human review, so V0 intentionally favors precision over aggressive automation.
